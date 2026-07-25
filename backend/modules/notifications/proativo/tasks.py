"""Fase 5.3 — Tasks celery-beat do proativo: avaliar_regras (*/15min).

_avaliar re-deriva TODAS as regras da fonte, diffa contra proativo_alert_state e
dispara alerta individual SÓ na transição (novo). Persistente atualiza estado (vai
pro digest). Resolvido (sumiu dos ativos DAQUELA regra) → resolved_at. Isolamento
POR REGRA: falha de uma NÃO derruba as outras nem resolve os alertas dela
(try/except + rollback + continue + log).

Contrato pós-review T3 (loop POR REGRA, não por família): para cada regra —
detectar; SUCESSO → para cada achado transicionar (True = transição nova → redigir
+ enviar individual) + marcar_resolvidos(regra, ativos_daquela_regra); FALHA →
rollback + continue, NADA da regra é tocado (nunca resolve-e-reabre).

RBAC fim-a-fim está AQUI: o destinatário vem SEMPRE de `regra.roles_destino`
(server-side), NUNCA do achado/LLM.
"""
import logging

from celery_app import app

logger = logging.getLogger(__name__)


def _run_async(coro):
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    url = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        eng = create_async_engine(url, echo=False)
        session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with session() as s:
            return await coro(s)

    return asyncio.run(_inner())


async def _avaliar(db) -> dict:
    """Coração testável (sem celery). Loop POR REGRA (contrato pós-review T3):

    Para cada regra do REGISTRY:
      1) `detectar(db)` — FALHA (except) → rollback + log + continue: NENHUMA linha
         da regra é tocada (nem resolvida por regra vizinha da MESMA família, pois
         `marcar_resolvidos` é escopado por REGRA, não por família — ex. "financeiro"
         = `caixa_baixo_cnpj` + `aging_reforcado`). Regra que falha não reabre como
         'novo' na rodada seguinte = sem spam duplo.
      2) SUCESSO → para cada achado: redigir + resolver destinatários por
         `regra.roles_destino` (matriz RBAC) + `transicionar` ATÔMICO. Retorno True
         (condição NOVA) → dispara o alerta individual no sino (1x). False
         (persistente) → só atualiza estado, vai pro digest, NÃO redispara.
      3) `marcar_resolvidos(db, nome, ativos_daquela_regra)` com o conjunto COMPLETO
         de ativos DAQUELA regra na rodada (vazio = resolve todas as ativas dela).

    Idempotente: rodar 2x seguidas NÃO gera alerta duplicado (graças ao
    transicionar atômico). Severidade dinâmica: `achado.dados["severidade"]`
    (per-instância, ex. certidão vencida=critico) sobrescreve `regra.severidade`.
    """
    from modules.notifications.proativo import estado, redator
    from modules.notifications.proativo.entrega import (
        enviar_individual,
        resolver_usuarios_por_roles,
    )
    from modules.notifications.proativo.regras import REGISTRY

    novos = persistentes = resolvidos = 0
    por_familia: dict[str, int] = {}

    for nome, regra in REGISTRY.items():
        try:
            achados = await regra.detectar(db)
        except Exception as exc:  # noqa: BLE001 — isolamento por regra
            logger.error("[proativo] regra %s falhou na detecção: %s", nome, exc)
            await db.rollback()  # asyncpg: transação envenenada precisa rollback
            # NÃO chama marcar_resolvidos desta regra → nada dela é tocado,
            # nem por uma regra vizinha da MESMA família que tenha sucesso.
            continue

        # detecção OK: ativos desta REGRA (mesmo sem achados → resolve todos dela)
        ativos_regra: set[str] = set()
        for achado in achados:
            ativos_regra.add(achado.correlation_id)
            try:
                title, body = await redator.redigir(regra, achado)
                # severidade dinâmica (per-achado) sobrescreve a estática da regra
                sev = achado.dados.get("severidade", regra.severidade)
                dest = await resolver_usuarios_por_roles(db, regra.roles_destino)
                if not dest:
                    logger.warning("[proativo] %s sem destinatário resolvido", nome)
                    continue
                # transição atômica: True SÓ se ESTA chamada levou a condição a NOVA.
                novo = await estado.transicionar(
                    db, correlation_id=achado.correlation_id, regra=nome,
                    severidade=sev, title=title, body=body,
                    destinatarios=dest)
                if novo:
                    await enviar_individual(
                        db, user_ids=dest, title=title, body=body,
                        familia=regra.familia, severidade=sev,
                        correlation_id=achado.correlation_id, action_url=regra.action_url)
                    novos += 1
                else:
                    persistentes += 1
                por_familia[regra.familia] = por_familia.get(regra.familia, 0) + 1
                await db.commit()
            except Exception as exc:  # noqa: BLE001 — isolamento por achado
                logger.error("[proativo] achado %s falhou: %s", achado.correlation_id, exc)
                await db.rollback()

        # resolução ESCOPADA POR REGRA: detecção desta regra teve sucesso nesta
        # rodada → resolve só o que é DELA (nunca de uma regra vizinha da mesma família).
        try:
            resolvidos += await estado.marcar_resolvidos(db, nome, ativos_regra)
            await db.commit()
        except Exception as exc:  # noqa: BLE001 — isolamento por regra
            logger.error("[proativo] resolver regra %s falhou: %s", nome, exc)
            await db.rollback()

    return {"novos": novos, "persistentes": persistentes,
            "resolvidos": resolvidos, "por_familia": por_familia}


@app.task(name="proativo.avaliar_regras", bind=True, max_retries=1)
def avaliar_regras_task(self):
    try:
        res = _run_async(_avaliar)
        logger.info("[proativo] avaliar_regras: %s", res)
        return res
    except Exception as exc:
        logger.error("[proativo] avaliar_regras erro: %s", exc)
        raise self.retry(exc=exc, countdown=120)


if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            # Captura o estado PRÉ-teste p/ limpeza cirúrgica (não apagar produção):
            # tudo que NÃO existia antes = criado por este teste.
            pre_state = set((await db.execute(text(
                "SELECT correlation_id FROM proativo_alert_state"))).scalars().all())
            pre_notif = set((await db.execute(text(
                "SELECT id::text FROM communication_notifications "
                "WHERE extra_data->>'origem'='proativo'"))).scalars().all())
            try:
                # ── (a) 1ª rodada: cria alertas das condições reais de hoje ──
                res = await _avaliar(db)
                assert "novos" in res and "por_familia" in res, res
                assert res["novos"] >= 1, f"esperado >=1 novo na 1ª rodada, veio {res}"

                # prova RBAC (a): destinatários vêm de regra.roles_destino, por família.
                # Financeiro (roles=admin) NUNCA chega a não-admin.
                from modules.notifications.proativo.entrega import (
                    resolver_usuarios_por_roles,
                )
                from modules.notifications.proativo.regras import REGISTRY
                admins = set(await resolver_usuarios_por_roles(db, ("admin",)))
                fin_dest = set((await db.execute(text(
                    "SELECT user_id::text FROM communication_notifications "
                    "WHERE extra_data->>'origem'='proativo' "
                    "AND extra_data->>'familia'='financeiro' "
                    "AND id::text <> ALL(:pre)"), {"pre": list(pre_notif) or ['']}
                )).scalars().all())
                assert fin_dest.issubset(admins), \
                    f"financeiro vazou p/ não-admin: {fin_dest - admins}"
                # cada notif proativa criada foi p/ um destinatário resolvido pelos
                # roles da SUA família (nunca do achado).
                fam_roles = {r.familia: r.roles_destino for r in REGISTRY.values()}
                linhas = (await db.execute(text(
                    "SELECT extra_data->>'familia' AS fam, user_id::text AS uid "
                    "FROM communication_notifications "
                    "WHERE extra_data->>'origem'='proativo' AND id::text <> ALL(:pre)"),
                    {"pre": list(pre_notif) or ['']})).mappings().all()
                for ln in linhas:
                    esperados = set(await resolver_usuarios_por_roles(
                        db, fam_roles.get(ln["fam"], ())))
                    assert ln["uid"] in esperados, \
                        f"destinatário {ln['uid']} fora dos roles da família {ln['fam']}"

                # ── (b) 2ª rodada: idempotente — nada novo (persistentes) ──
                res2 = await _avaliar(db)
                assert res2["novos"] == 0, f"2ª rodada NÃO pode gerar novo: {res2}"
                assert res2["persistentes"] >= res["novos"], res2
                # nenhuma notif individual NOVA criada na 2ª rodada
                pos_1e2 = set((await db.execute(text(
                    "SELECT id::text FROM communication_notifications "
                    "WHERE extra_data->>'origem'='proativo' AND id::text <> ALL(:pre)"),
                    {"pre": list(pre_notif) or ['']})).scalars().all())
                novos_notifs = len(pos_1e2)  # todos criados só na 1ª rodada

                # ── (c) isolamento por regra: 1 regra explode → OUTRAS seguem, e os
                #        alertas da que falhou NÃO são resolvidos. Sub-teste com
                #        REGISTRY controlado (só dados sintéticos, não toca produção). ──
                from modules.notifications.proativo.regras import Regra
                orig = dict(REGISTRY)
                boom_cid = "t6_boom:__ISOLAMENTO__"
                ok_cid = "t6_ok:__ISOLAMENTO__"
                try:
                    # semeia 2 estados ATIVOS: um da regra que vai falhar, um da que
                    # vai suceder-sem-achados (será resolvida → prova que o loop
                    # continuou PASSANDO pela regra que estourou).
                    for cid, rg in ((boom_cid, "t6_boom"), (ok_cid, "t6_ok")):
                        await db.execute(text(
                            "INSERT INTO proativo_alert_state "
                            "(correlation_id, regra, severidade, title, body, "
                            " destinatarios, first_seen_at, last_seen_at, resolved_at, "
                            " notified_individually) VALUES (:c, :r, 'info', 't', 'b', "
                            " '[]'::jsonb, now(), now(), NULL, true)"),
                            {"c": cid, "r": rg})
                    await db.commit()

                    async def _boom(_db):
                        raise RuntimeError("t6 falha forçada")

                    async def _empty(_db):
                        return []

                    REGISTRY.clear()
                    REGISTRY["t6_boom"] = Regra(
                        nome="t6_boom", familia="t6", severidade="info",
                        roles_destino=("admin",), action_url="/",
                        detectar=_boom, template=lambda d: ("t", "b"))
                    REGISTRY["t6_ok"] = Regra(
                        nome="t6_ok", familia="t6", severidade="info",
                        roles_destino=("admin",), action_url="/",
                        detectar=_empty, template=lambda d: ("t", "b"))

                    res3 = await _avaliar(db)
                    # a regra que FALHOU não teve o alerta resolvido (segue ativo)
                    boom_ativo = (await db.execute(text(
                        "SELECT resolved_at IS NULL FROM proativo_alert_state "
                        "WHERE correlation_id=:c"), {"c": boom_cid})).scalar()
                    assert boom_ativo is True, \
                        "alerta da regra que FALHOU foi resolvido (isolamento quebrado)"
                    # a regra seguinte (sucesso) RESOLVEU seu ativo → loop continuou
                    ok_resolvido = (await db.execute(text(
                        "SELECT resolved_at IS NOT NULL FROM proativo_alert_state "
                        "WHERE correlation_id=:c"), {"c": ok_cid})).scalar()
                    assert ok_resolvido is True, \
                        "regra seguinte não rodou (loop parou na exceção)"
                    assert res3["resolvidos"] >= 1, res3
                    isolamento = f"boom_ativo={boom_ativo} ok_resolvido={ok_resolvido}"
                finally:
                    REGISTRY.clear()
                    REGISTRY.update(orig)
                    await db.execute(text(
                        "DELETE FROM proativo_alert_state WHERE correlation_id = ANY(:c)"),
                        {"c": [boom_cid, ok_cid]})
                    await db.commit()

                print(f"OK task — (a) 1ª {res} ({novos_notifs} notifs no sino, RBAC ok); "
                      f"(b) 2ª novos={res2['novos']} persistentes={res2['persistentes']}; "
                      f"(c) isolamento {isolamento}; (d) limpeza abaixo")
            finally:
                # ── (d) limpa SÓ o que este teste criou (não apaga produção) ──
                await db.execute(text(
                    "DELETE FROM communication_notifications "
                    "WHERE extra_data->>'origem'='proativo' AND id::text <> ALL(:pre)"),
                    {"pre": list(pre_notif) or ['']})
                await db.execute(text(
                    "DELETE FROM proativo_alert_state WHERE correlation_id <> ALL(:pre)"),
                    {"pre": list(pre_state) or ['']})
                await db.commit()
                rem_n = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'origem'='proativo' AND id::text <> ALL(:pre)"),
                    {"pre": list(pre_notif) or ['']})).scalar()
                rem_s = (await db.execute(text(
                    "SELECT count(*) FROM proativo_alert_state WHERE correlation_id <> ALL(:pre)"),
                    {"pre": list(pre_state) or ['']})).scalar()
                assert rem_n == 0 and rem_s == 0, f"remanescentes notif={rem_n} state={rem_s}"
                print(f"OK limpeza — remanescentes notif={rem_n} state={rem_s} (0/0)")
        await eng.dispose()

    asyncio.run(main())
