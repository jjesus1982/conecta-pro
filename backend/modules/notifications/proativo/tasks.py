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

from sqlalchemy import text

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


async def _digest(db) -> dict:
    """07:00 Manaus: 1 notificação-resumo por destinatário com o que PERSISTE
    (o que `_avaliar` já viu antes e não é novo — não redispara individual).

    Consolida por REGRA, não por família: RBAC vem SEMPRE de
    `REGISTRY[linha["regra"]].roles_destino` (mesmo contrato server-side de
    `_avaliar` — nunca do achado/LLM). Uma linha cuja regra foi removida do
    REGISTRY é pulada com log (órfã: silêncio honesto, não inventa destinatário).

    Dedup diário DETERMINÍSTICO: cada digest carrega em extra_data um
    correlation_id `digest:{user_id}:{yyyy-mm-dd Manaus}`. Rodar a task 2x no
    mesmo dia não cria um 2º registro para o mesmo user (checa a existência
    ANTES de inserir). Destinatário sem nenhuma condição persistente sua não
    entra em `por_user` → nunca recebe digest vazio (silêncio honesto).
    """
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from modules.notifications.proativo import estado
    from modules.notifications.proativo.entrega import resolver_usuarios_por_roles
    from modules.notifications.proativo.regras import REGISTRY

    ativos = await estado.persistentes_ativos(db)
    if not ativos:
        return {"destinatarios": 0, "notificacoes": 0}

    # user_id -> títulos das condições que ELE pode ver, via roles_destino da
    # REGRA de cada linha (não da família — uma família pode ter regras com
    # roles_destino diferentes; escopar por regra é o contrato pós-review T3).
    por_user: dict[str, list[str]] = {}
    for linha in ativos:
        regra_obj = REGISTRY.get(linha["regra"])
        if regra_obj is None:
            logger.warning(
                "[proativo] digest: regra %r ativa no estado mas fora do "
                "REGISTRY — pulando (não inventa destinatário)", linha["regra"])
            continue
        destinatarios = await resolver_usuarios_por_roles(db, regra_obj.roles_destino)
        for uid in destinatarios:
            por_user.setdefault(uid, []).append(linha["title"])

    hoje = datetime.now(ZoneInfo("America/Manaus")).strftime("%Y-%m-%d")
    _NOW_ = "(now() AT TIME ZONE 'America/Manaus')"
    notificacoes = 0
    for uid, titulos in por_user.items():
        cid_digest = f"digest:{uid}:{hoje}"
        existe = (await db.execute(text(
            "SELECT 1 FROM communication_notifications "
            "WHERE user_id=:u AND extra_data->>'correlation_id'=:cid LIMIT 1"),
            {"u": uid, "cid": cid_digest})).first()
        if existe:
            continue  # dedup diário: já mandamos o digest de hoje p/ este user
        corpo = "Itens que precisam da sua atenção:\n- " + "\n- ".join(titulos[:20])
        extra = json.dumps({"origem": "proativo_digest", "correlation_id": cid_digest,
                            "itens": len(titulos)})
        await db.execute(text(
            f"INSERT INTO communication_notifications "
            f"(id, tenant_id, user_id, title, body, type, reference_type, reference_id, "
            f" action_url, extra_data, is_active, sent_at, created_at) "
            f"VALUES (gen_random_uuid(), :u, :u, :title, :body, 'sistema', 'proativo_digest', "
            f" NULL, '/notificacoes', CAST(:extra AS jsonb), true, {_NOW_}, {_NOW_})"),
            {"u": uid, "title": "Bom dia — o que precisa da sua atenção",
             "body": corpo, "extra": extra})
        notificacoes += 1
    await db.commit()
    return {"destinatarios": len(por_user), "notificacoes": notificacoes}


@app.task(name="proativo.digest_diario", bind=True, max_retries=1)
def digest_diario_task(self):
    try:
        res = _run_async(_digest)
        logger.info("[proativo] digest_diario: %s", res)
        return res
    except Exception as exc:
        logger.error("[proativo] digest_diario erro: %s", exc)
        raise self.retry(exc=exc, countdown=300)


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
                "WHERE extra_data->>'origem' IN ('proativo','proativo_digest')"))).scalars().all())
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

                # ── DIGEST: 2 (financeiro) + 1 (operacional) persistentes → prova
                #    (a) consolidação 1 notif/destinatário, (b) RBAC gestor≠admin,
                #    (c) dedup diário (correlation_id determinístico), (d) sem
                #    persistente = 0 digest. Usa REGRAS REAIS do REGISTRY (já
                #    restaurado acima) para o roteamento RBAC ser o de produção. ──
                from modules.notifications.proativo import estado as _st
                from modules.notifications.proativo.entrega import (
                    resolver_usuarios_por_roles as _ru,
                )
                dgt_c1 = "caixa_baixo:__DGT1__:2026-07"   # financeiro (admin)
                dgt_c2 = "certidao:__DGT2__:2026-12-31"   # documentos (admin)
                dgt_c3 = "posto_descoberto:__DGT3__"      # operacional (admin+gerente+supervisor)

                admins_dgt = await _ru(db, ("admin",))
                gerentes_dgt = await _ru(db, ("gerente_operacional",))
                funcionarios_dgt = await _ru(db, ("funcionario",))
                assert set(gerentes_dgt).isdisjoint(admins_dgt), \
                    "gerente_operacional e admin devem ser papéis disjuntos p/ o teste RBAC valer"

                await _st.transicionar(db, correlation_id=dgt_c1, regra="caixa_baixo_cnpj",
                                       severidade="critico", title="[TESTE] Caixa baixo DGT1",
                                       body="b", destinatarios=admins_dgt)
                await _st.transicionar(db, correlation_id=dgt_c2, regra="certidao_vencendo",
                                       severidade="atencao", title="[TESTE] Certidão DGT2",
                                       body="b", destinatarios=admins_dgt)
                await _st.transicionar(db, correlation_id=dgt_c3, regra="posto_descoberto",
                                       severidade="critico", title="[TESTE] Posto DGT3",
                                       body="b", destinatarios=admins_dgt + gerentes_dgt)
                await db.commit()

                async def _corpo_novo_digest(uid: str) -> list[str]:
                    """Corpos de digest criados DEPOIS de pre_notif p/ este uid
                    (imune a digest real pré-existente de outro dia/execução)."""
                    rows = (await db.execute(text(
                        "SELECT body FROM communication_notifications "
                        "WHERE user_id=:u AND extra_data->>'origem'='proativo_digest' "
                        "AND id::text <> ALL(:pre)"),
                        {"u": uid, "pre": list(pre_notif) or ['']})).scalars().all()
                    return list(rows)

                dg = await _digest(db)
                assert dg["notificacoes"] >= 1, dg

                # (a) 1 notificação ÚNICA consolidada por admin (financeiro x2 + operacional)
                if admins_dgt:
                    corpos_admin = await _corpo_novo_digest(admins_dgt[0])
                    assert len(corpos_admin) == 1, \
                        f"digest do admin deveria ser 1 notif única, veio {len(corpos_admin)}"
                    assert all(m in corpos_admin[0] for m in
                               ("Caixa baixo DGT1", "Certidão DGT2", "Posto DGT3")), \
                        f"digest do admin deveria consolidar as 3 condições: {corpos_admin[0]!r}"

                # (b) RBAC: digest do gestor tem SÓ o item operacional — financeiro
                #     (roles_destino=admin) NUNCA aparece pra ele.
                if gerentes_dgt:
                    corpos_ger = await _corpo_novo_digest(gerentes_dgt[0])
                    assert len(corpos_ger) == 1, \
                        f"digest do gestor deveria ser 1 notif única, veio {len(corpos_ger)}"
                    assert "Posto DGT3" in corpos_ger[0]
                    assert "Caixa baixo DGT1" not in corpos_ger[0] \
                        and "Certidão DGT2" not in corpos_ger[0], \
                        f"RBAC vazou item financeiro pro gestor: {corpos_ger[0]!r}"

                # (d) destinatário sem condição persistente SUA (funcionario não está
                #     em roles_destino de NENHUMA regra registrada) → 0 digest novo.
                if funcionarios_dgt:
                    corpos_func = await _corpo_novo_digest(funcionarios_dgt[0])
                    assert len(corpos_func) == 0, \
                        f"funcionario sem persistente seu recebeu digest: {corpos_func}"

                # (c) rodar 2x no mesmo dia NÃO duplica — correlation_id determinístico
                #     digest:{user}:{data Manaus} já existe → 2ª chamada não insere de novo.
                dg2 = await _digest(db)
                assert dg2["notificacoes"] == 0, \
                    f"2ª chamada no mesmo dia não deveria criar novos digests: {dg2}"
                if admins_dgt:
                    corpos_admin2 = await _corpo_novo_digest(admins_dgt[0])
                    assert len(corpos_admin2) == 1, \
                        f"digest do admin duplicou na 2ª rodada: {len(corpos_admin2)}"
                if gerentes_dgt:
                    corpos_ger2 = await _corpo_novo_digest(gerentes_dgt[0])
                    assert len(corpos_ger2) == 1, \
                        f"digest do gestor duplicou na 2ª rodada: {len(corpos_ger2)}"

                print(f"OK digest — (a) consolidado 1/admin {dg}; "
                      f"(b) RBAC gestor sem financeiro; (c) 2ª chamada {dg2} sem duplicar; "
                      f"(d) funcionario sem persistente = 0 digest")
            finally:
                # ── (e) limpa SÓ o que este teste criou (não apaga produção) — por
                #        diff pre/pós (id/correlation_id), nunca por janela de tempo
                #        ou UPDATE em massa: cobre tanto os alertas 'proativo' (T3)
                #        quanto os digests 'proativo_digest' (T7) num único crivo. ──
                await db.execute(text(
                    "DELETE FROM communication_notifications "
                    "WHERE extra_data->>'origem' IN ('proativo','proativo_digest') "
                    "AND id::text <> ALL(:pre)"),
                    {"pre": list(pre_notif) or ['']})
                await db.execute(text(
                    "DELETE FROM proativo_alert_state WHERE correlation_id <> ALL(:pre)"),
                    {"pre": list(pre_state) or ['']})
                await db.commit()
                rem_n = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'origem' IN ('proativo','proativo_digest') "
                    "AND id::text <> ALL(:pre)"),
                    {"pre": list(pre_notif) or ['']})).scalar()
                rem_s = (await db.execute(text(
                    "SELECT count(*) FROM proativo_alert_state WHERE correlation_id <> ALL(:pre)"),
                    {"pre": list(pre_state) or ['']})).scalar()
                assert rem_n == 0 and rem_s == 0, f"remanescentes notif={rem_n} state={rem_s}"
                print(f"OK limpeza — remanescentes notif={rem_n} state={rem_s} (0/0)")
        await eng.dispose()

    asyncio.run(main())
