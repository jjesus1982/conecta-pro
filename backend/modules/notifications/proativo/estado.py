"""Fase 5.3 — Estado de transição das regras proativas (proativo_alert_state).

Distingue "condição NOVA" (transição → alerta individual 1x) de "persistente"
(vai só pro digest). Resolvida (não está mais entre os ativos) → resolved_at,
some do digest. Único ponto de ESCRITA do proativo além da notificação no sino.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_NOW = "(now() AT TIME ZONE 'America/Manaus')"


async def classificar(db: AsyncSession, correlation_id: str) -> str:
    row = (await db.execute(text(
        "SELECT 1 FROM proativo_alert_state "
        "WHERE correlation_id = :c AND resolved_at IS NULL"),
        {"c": correlation_id})).first()
    return "persistente" if row else "novo"


async def registrar_novo(db: AsyncSession, *, correlation_id: str, familia: str,
                         severidade: str, title: str, body: str,
                         destinatarios: list[str]) -> None:
    await db.execute(text(
        f"INSERT INTO proativo_alert_state "
        f"(correlation_id, familia, severidade, title, body, destinatarios, "
        f" first_seen_at, last_seen_at, resolved_at, notified_individually) "
        f"VALUES (:c, :f, :s, :t, :b, CAST(:d AS jsonb), {_NOW}, {_NOW}, NULL, true) "
        f"ON CONFLICT (correlation_id) DO UPDATE SET "
        f"  familia=EXCLUDED.familia, severidade=EXCLUDED.severidade, "
        f"  title=EXCLUDED.title, body=EXCLUDED.body, "
        f"  destinatarios=EXCLUDED.destinatarios, last_seen_at={_NOW}, "
        f"  resolved_at=NULL, notified_individually=true"),
        {"c": correlation_id, "f": familia, "s": severidade, "t": title,
         "b": body, "d": json.dumps(destinatarios)})


async def tocar_persistente(db: AsyncSession, correlation_id: str, *,
                            title: str, body: str) -> None:
    await db.execute(text(
        f"UPDATE proativo_alert_state SET last_seen_at={_NOW}, title=:t, body=:b "
        f"WHERE correlation_id=:c AND resolved_at IS NULL"),
        {"c": correlation_id, "t": title, "b": body})


async def marcar_resolvidos(db: AsyncSession, ativos: set[str]) -> int:
    if ativos:
        r = await db.execute(text(
            f"UPDATE proativo_alert_state SET resolved_at={_NOW} "
            f"WHERE resolved_at IS NULL AND NOT (correlation_id = ANY(:ativos))"),
            {"ativos": list(ativos)})
    else:
        r = await db.execute(text(
            f"UPDATE proativo_alert_state SET resolved_at={_NOW} "
            f"WHERE resolved_at IS NULL"))
    return r.rowcount or 0


async def persistentes_ativos(db: AsyncSession) -> list[dict]:
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
        cid = "posto_descoberto:__TESTE_ESTADO__"
        async with Session() as db:
            try:
                # 1ª passada: novo
                assert await classificar(db, cid) == "novo"
                await registrar_novo(db, correlation_id=cid, familia="operacional",
                                     severidade="critico", title="t", body="b",
                                     destinatarios=["u1"])
                await db.commit()
                # 2ª passada (rodar de novo): agora persistente, NÃO novo
                assert await classificar(db, cid) == "persistente"
                await tocar_persistente(db, cid, title="t2", body="b2")
                await db.commit()
                # aparece em persistentes_ativos
                ativos = await persistentes_ativos(db)
                assert any(r["correlation_id"] == cid for r in ativos)
                # condição some do mundo → resolvida sai do digest
                n = await marcar_resolvidos(db, ativos=set())  # nada ativo agora
                await db.commit()
                assert n >= 1
                assert await classificar(db, cid) == "novo"  # resolvida volta a ser "novo"
                print("OK estado — transição/dedup/resolvido")
            finally:
                await db.execute(text("DELETE FROM proativo_alert_state WHERE correlation_id=:c"),
                                 {"c": cid})
                await db.commit()
                rem = (await db.execute(text(
                    "SELECT count(*) FROM proativo_alert_state WHERE correlation_id=:c"),
                    {"c": cid})).scalar()
                assert rem == 0, f"remanescentes={rem}"
        await eng.dispose()

    asyncio.run(main())
