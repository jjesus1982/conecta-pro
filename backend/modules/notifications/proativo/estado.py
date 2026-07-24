"""Fase 5.3 — Estado de transição das regras proativas (proativo_alert_state).

Distingue "condição NOVA" (transição → alerta individual 1x) de "persistente"
(vai só pro digest). Resolvida (não está mais entre os ativos DAQUELA FAMÍLIA)
→ resolved_at, some do digest. Único ponto de ESCRITA do proativo além da
notificação no sino.

Contrato (pós-review T3):
- `transicionar(...) -> bool`  — transição ATÔMICA sem lock explícito. Retorna
  True quando ESTA chamada foi a que levou a condição a NOVA (criou ou reabriu)
  → o chamador dispara o alerta individual. False = já estava ativa (persistente)
  → só atualiza estado, vai pro digest. Substitui o par não-atômico
  classificar()+registrar_novo()+tocar_persistente().
- `marcar_resolvidos(db, familia, ativos_familia)` — resolve SÓ dentro da família,
  e SÓ deve ser chamado para famílias cuja detecção teve SUCESSO na rodada.
  Família que falhou não é passada aqui → seus alertas permanecem ativos (não
  reabrem como "novos" na rodada seguinte = sem spam duplo).
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_NOW = "(now() AT TIME ZONE 'America/Manaus')"


async def transicionar(db: AsyncSession, *, correlation_id: str, familia: str,
                       severidade: str, title: str, body: str,
                       destinatarios: list[str]) -> bool:
    """Transição atômica: True se ESTA chamada transicionou a condição para NOVA.

    Cada statement é atômico no Postgres; numa corrida só existe um vencedor por
    correlation_id — não há janela em que duas execuções concorrentes disparem o
    mesmo alerta individual.

    1) INSERT ... ON CONFLICT DO NOTHING RETURNING  → retornou linha = EU criei
       (transição NOVA) → True.
    2) senão UPDATE ... WHERE resolved_at IS NOT NULL RETURNING → retornou = EU
       reabri uma condição resolvida (transição NOVA) → True.
    3) senão UPDATE last_seen_at/title/body (persistente) → False.
    """
    row = (await db.execute(text(
        f"INSERT INTO proativo_alert_state "
        f"(correlation_id, familia, severidade, title, body, destinatarios, "
        f" first_seen_at, last_seen_at, resolved_at, notified_individually) "
        f"VALUES (:c, :f, :s, :t, :b, CAST(:d AS jsonb), {_NOW}, {_NOW}, NULL, true) "
        f"ON CONFLICT (correlation_id) DO NOTHING "
        f"RETURNING correlation_id"),
        {"c": correlation_id, "f": familia, "s": severidade, "t": title,
         "b": body, "d": json.dumps(destinatarios)})).first()
    if row is not None:
        return True  # EU criei → transição NOVA

    # Reabertura: só vence quem encontrar a linha ainda resolvida. Refresca o
    # conteúdo (severidade/title/body/destinatarios) para o digest não exibir o
    # texto do episódio anterior.
    row = (await db.execute(text(
        f"UPDATE proativo_alert_state SET "
        f"  resolved_at=NULL, last_seen_at={_NOW}, notified_individually=false, "
        f"  severidade=:s, title=:t, body=:b, destinatarios=CAST(:d AS jsonb) "
        f"WHERE correlation_id=:c AND resolved_at IS NOT NULL "
        f"RETURNING correlation_id"),
        {"c": correlation_id, "s": severidade, "t": title, "b": body,
         "d": json.dumps(destinatarios)})).first()
    if row is not None:
        return True  # EU reabri → transição NOVA

    # Persistente: já estava ativa. Só toca last_seen_at + conteúdo do digest.
    await db.execute(text(
        f"UPDATE proativo_alert_state SET last_seen_at={_NOW}, title=:t, body=:b "
        f"WHERE correlation_id=:c AND resolved_at IS NULL"),
        {"c": correlation_id, "t": title, "b": body})
    return False


async def marcar_resolvidos(db: AsyncSession, familia: str,
                            ativos_familia: set[str]) -> int:
    """Resolve as linhas ATIVAS da `familia` que não estão mais entre os ativos.

    ESCOPADO POR FAMÍLIA: chame 1x por família e SÓ para famílias cuja detecção
    teve SUCESSO nesta rodada. Uma família que falhou (except → continue no
    consumidor) NÃO deve ser passada aqui, ou suas condições ativas seriam
    resolvidas em massa e reabririam como "novas" na próxima rodada (spam duplo).
    `ativos_familia` vazio = nenhuma condição ativa desta família = resolve todas
    as ativas DELA (nunca de outras famílias).
    """
    if ativos_familia:
        r = await db.execute(text(
            f"UPDATE proativo_alert_state SET resolved_at={_NOW} "
            f"WHERE resolved_at IS NULL AND familia = :familia "
            f"AND NOT (correlation_id = ANY(:ativos))"),
            {"familia": familia, "ativos": list(ativos_familia)})
    else:
        r = await db.execute(text(
            f"UPDATE proativo_alert_state SET resolved_at={_NOW} "
            f"WHERE resolved_at IS NULL AND familia = :familia"),
            {"familia": familia})
    return r.rowcount or 0


async def persistentes_ativos(db: AsyncSession,
                              familia: str | None = None) -> list[dict]:
    """Insumo do digest: condições ativas (resolved_at IS NULL). Filtra por
    família quando informado."""
    if familia is not None:
        rows = (await db.execute(text(
            "SELECT correlation_id, familia, severidade, title, body, destinatarios "
            "FROM proativo_alert_state WHERE resolved_at IS NULL AND familia = :familia "
            "ORDER BY severidade DESC, last_seen_at DESC"),
            {"familia": familia})).mappings().all()
    else:
        rows = (await db.execute(text(
            "SELECT correlation_id, familia, severidade, title, body, destinatarios "
            "FROM proativo_alert_state WHERE resolved_at IS NULL "
            "ORDER BY severidade DESC, last_seen_at DESC"))).mappings().all()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import asyncio, os
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        FAM_A = "__TESTE_FAM_A__"
        FAM_B = "__TESTE_FAM_B__"
        a1 = "posto_descoberto:__TESTE_A1__"
        b1 = "cnd_vencida:__TESTE_B1__"
        cids = [a1, b1]

        def kw(cid: str, fam: str) -> dict:
            return dict(correlation_id=cid, familia=fam, severidade="critico",
                        title="t", body="b", destinatarios=["u1"])

        async with Session() as db:
            try:
                # higieniza resquício de execução anterior
                await db.execute(text(
                    "DELETE FROM proativo_alert_state WHERE correlation_id = ANY(:c)"),
                    {"c": cids})
                await db.commit()

                # ── 4 PONTAS via transicionar ─────────────────────────────────
                # (1) NOVO → transição True (dispara individual)
                assert await transicionar(db, **kw(a1, FAM_A)) is True, "novo deveria ser True"
                await db.commit()
                # (2) PERSISTENTE → False (não redispara)
                assert await transicionar(db, **kw(a1, FAM_A)) is False, "persistente deveria ser False"
                await db.commit()
                # aparece em persistentes_ativos (escopo família)
                assert any(r["correlation_id"] == a1
                           for r in await persistentes_ativos(db, familia=FAM_A))

                # ── FAMÍLIA A FALHA, B RESOLVE ────────────────────────────────
                # B também está ativa
                assert await transicionar(db, **kw(b1, FAM_B)) is True
                await db.commit()
                # B some do mundo → resolve SÓ a família B; A (que "falhou") NÃO é passada
                nB = await marcar_resolvidos(db, FAM_B, set())
                await db.commit()
                assert nB >= 1, f"B deveria resolver, nB={nB}"
                # A permanece ATIVA — não foi tocada por marcar_resolvidos de outra família
                assert any(r["correlation_id"] == a1
                           for r in await persistentes_ativos(db, familia=FAM_A)), \
                    "A deve permanecer ATIVA quando sua família falha (não resolver)"
                # e continua persistente (não virou 'novo' → não haveria re-alerta)
                assert await transicionar(db, **kw(a1, FAM_A)) is False, \
                    "A ativa deve seguir persistente (False), não reabrir"
                await db.commit()

                # (3+4) RESOLVER e REABRIR: resolve A, e nova transição vira True
                nA = await marcar_resolvidos(db, FAM_A, set())
                await db.commit()
                assert nA >= 1, f"A deveria resolver, nA={nA}"
                assert not await persistentes_ativos(db, familia=FAM_A), "A deve sumir do digest"
                assert await transicionar(db, **kw(a1, FAM_A)) is True, "reabertura deveria ser True"
                await db.commit()

                # ── CORRIDA: 2 transicionar sequenciais do MESMO cid NOVO → 1 True ─
                await db.execute(text(
                    "DELETE FROM proativo_alert_state WHERE correlation_id = :c"),
                    {"c": b1})
                await db.commit()
                r1 = await transicionar(db, **kw(b1, FAM_B))
                r2 = await transicionar(db, **kw(b1, FAM_B))
                await db.commit()
                assert (r1, r2) == (True, False), \
                    f"corrida deu ({r1},{r2}), esperado exatamente 1 True → (True,False)"

                print("OK estado — 4 pontas via transicionar + família-A-falha isolada "
                      "+ corrida (1 vencedor)")
            finally:
                await db.execute(text(
                    "DELETE FROM proativo_alert_state WHERE correlation_id = ANY(:c)"),
                    {"c": cids})
                await db.commit()
                rem = (await db.execute(text(
                    "SELECT count(*) FROM proativo_alert_state WHERE correlation_id = ANY(:c)"),
                    {"c": cids})).scalar()
                assert rem == 0, f"remanescentes={rem}"
        await eng.dispose()

    asyncio.run(main())
