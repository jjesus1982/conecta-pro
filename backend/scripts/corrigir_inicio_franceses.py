#!/usr/bin/env python3
"""PARQUE DOS FRANCESES entra em AGOSTO, não em setembro.

Decisão do Jordan em 14/08/2026, registrada no PROMPT_T2_GEDEON: o contrato do CONDOMINIO
RESIDENCIAL PARQUE DOS FRANCESES está cadastrado com `start_date = 2026-09-01` e **isso está
errado** — ele entra em agosto, e é dele a PRIMEIRA NOTA e o PRIMEIRO BOLETO da vida do
cliente com a gente.

POR QUE A DATA IMPORTA MAIS DO QUE PARECE. A lista de kits e de faturamento de uma
competência é derivada dos CONTRATOS ATIVOS naquela competência — é a única das três fontes
que sabe QUANDO o contrato vale (`condominios.tipo_servico` não tem vigência,
`gedeon_kit_config` só tem `ativo`). Com `start_date` em 01/09, agosto simplesmente não
enxerga este cliente: nem nota, nem boleto, nem cobrança. O cliente entra e ninguém fatura.

⚠️ ISTO VIRA DINHEIRO, e por isso o ensaio é o padrão. Sem `--aplicar` o script só mostra o
que faria. UMA linha, e ela decide a primeira impressão de um cliente novo com a empresa.

⚠️ NÃO EMITE NADA. Corrige a data e para. A emissão de NF-e é ato de governo, irreversível,
e o próprio prompt manda combinar com o T1 antes — uma por vez, conferindo cada uma.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
      python3 /app/scripts/corrigir_inicio_franceses.py            # ensaio
    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
      python3 /app/scripts/corrigir_inicio_franceses.py --aplicar
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts/qa")

from _mutacao import Mutacao  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

# ⚠️ OBJETO `date`, NÃO STRING. O asyncpg recusa str em coluna `date` mesmo com
# `CAST(:x AS date)` no SQL — o CAST é do lado do Postgres e a codificação do parâmetro
# acontece antes: "'str' object has no attribute 'toordinal'". Já mordeu duas vezes hoje.
DE, PARA = date(2026, 9, 1), date(2026, 8, 1)

SQL_ALVO = text(
    "SELECT c.id::text AS id, cl.name AS cliente, c.start_date, c.end_date, "
    "       coalesce(e.nome_fantasia,'—') AS emitente, c.monthly_value "
    "FROM contracts c "
    "LEFT JOIN clients cl ON cl.id = c.client_id "
    "LEFT JOIN empresas e ON e.id = c.empresa_id "
    "WHERE upper(coalesce(cl.name,'')) LIKE '%FRANCESES%' "
    "  AND c.start_date = CAST(:de AS date)"
)


async def main() -> int:
    m = Mutacao("corrigir início do contrato do Parque dos Franceses", teto=1)

    async with async_session_factory() as db:
        linhas = (await db.execute(SQL_ALVO, {"de": DE})).mappings().all()
        if not linhas:
            print(f"\nNenhum contrato do Parque dos Franceses com início em {DE}.")
            print("Ou já foi corrigido, ou a data mudou — confira antes de insistir.")
            return 0

        alvos = [
            (r["id"][:8],
             f'{r["cliente"]} — {r["emitente"]} · início {r["start_date"]} → {PARA} '
             f'· fim {r["end_date"]} · mensal R$ {r["monthly_value"] or 0}')
            for r in linhas
        ]
        print(f"\n══ início do contrato: {DE} → {PARA} ══")
        print("   (é a 1ª nota e o 1º boleto deste cliente — decisão do Jordan em 14/08)")

        if not m.confirmar(alvos):
            return 0

        n = (await db.execute(text(
            "UPDATE contracts c SET start_date = CAST(:para AS date), updated_at = now() "
            "FROM clients cl "
            "WHERE cl.id = c.client_id "
            "  AND upper(coalesce(cl.name,'')) LIKE '%FRANCESES%' "
            "  AND c.start_date = CAST(:de AS date)"
        ), {"de": DE, "para": PARA})).rowcount
        await db.commit()
        m.feito(n)

        conf = (await db.execute(text(
            "SELECT count(*) FROM contracts c LEFT JOIN clients cl ON cl.id=c.client_id "
            "WHERE c.start_date <= CAST(:fim AS date) "
            "  AND coalesce(c.end_date, CAST('9999-12-31' AS date)) >= CAST(:ini AS date) "
            "  AND lower(coalesce(c.status::text,'')) = 'active'"
        ), {"ini": date(2026, 8, 1), "fim": date(2026, 8, 31)})).scalar()
        print(f"  DEPOIS: {conf} contrato(s) ativo(s) em agosto/2026")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
