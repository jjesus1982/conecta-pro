"""Prova do digest diário do DP: monta do banco, ordena por severidade, NÃO envia.

Invariantes:
  • silêncio honesto — sem item aberto devolve None (não manda e-mail dizendo "0 itens");
  • ordena 🔴 antes de 🟡/🔵 — o irreversível/dinheiro aparece no topo;
  • marca [OTP] no que exige;
  • NÃO envia nada (montar_digest só devolve o corpo).
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

MARCA = "BANCADA_DIGEST"
SQL_INS = text(
    "INSERT INTO agent_drafts (id, tipo, modulo, titulo, resumo, payload, status, gate, "
    " requires_otp, roles_aprovador, criado_por_agente, created_at) "
    "VALUES (gen_random_uuid(), :t, 'dp', :ti, 'bancada', '{}'::jsonb, 'rascunho', :g, "
    "        :o, ARRAY['admin'], true, now())"
)


async def main() -> None:
    from modules.notifications.proativo.digest_dp import montar_digest

    eng = create_async_engine(os.environ["DATABASE_URL"])
    S = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with S() as db:
            for t, g, otp in (("pagar_folha_lote", "🔴", True),
                              ("alocar_em_posto", "🟡", False),
                              ("registrar_ferias", "🔵", False)):
                await db.execute(SQL_INS, {"t": t, "ti": f"{MARCA} {t}", "g": g, "o": otp})
            await db.commit()

            d = await montar_digest(db)
            assert d is not None, "deveria montar com 3 itens abertos"
            print(f"assunto: {d['assunto']}\n")
            print(d["corpo"][:400])

            assert d["total"] >= 3 and d["criticos"] >= 1, d
            assert d["corpo"].index("🔴") < d["corpo"].index("🔵"), "🔴 deve vir antes de 🔵"
            assert "[OTP]" in d["corpo"], "deveria marcar OTP"
            print("\nTESTE ordem/OTP/total PASS")
    finally:
        async with S() as db:
            await db.execute(text("DELETE FROM agent_drafts WHERE titulo LIKE :m"),
                             {"m": f"{MARCA}%"})
            await db.commit()
            rem = (await db.execute(text("SELECT count(*) FROM agent_drafts WHERE titulo LIKE :m"),
                                    {"m": f"{MARCA}%"})).scalar()
            assert rem == 0, f"resíduo: {rem}"
            print("LIMPEZA OK — 0 resíduo")
        await eng.dispose()


asyncio.run(main())
