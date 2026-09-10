#!/usr/bin/env python3
"""Contrato ATIVO cujo dinheiro ninguém está esperando.

Um contrato assinado é uma promessa de receita. Se o financeiro não sabe dela, o dinheiro
não entra por esquecimento — e o esquecimento não dá erro em lugar nenhum.

Duas naturezas, dois caminhos, e só um deles existe hoje (medido em 09/09/2026):

    recurring  contrato ativo → `client_contracts` (a linha do MRR) → recebíveis
               com `origem='contrato'`. Funciona: 10 linhas de faturamento, 27 recebíveis.

    one_time   contrato ativo → NADA. `_bridge_contract_to_billing` devolve False logo na
               primeira linha para tudo que não é `recurring` — e está certo, porque valor
               único não é MRR. Só que não há o outro caminho: o cronograma de pagamento
               vive em `contract_items` (entrada, parcelas, retida) e ninguém o transforma
               em conta a receber.

Concretamente: o CTR-2026-00022 vale R$ 46.320,00 em quatro parcelas. No dia em que for
ativado, o contas a receber continua sem saber que R$ 23.160,00 vencem na assinatura.

⚠️ `receivable_accounts` **não tem coluna de contrato**. Tem `customer_id`, `description`,
`due_date` e até `total_installments`/`current_installment` — a forma de um cronograma
parcelado já existe —, mas nada aponta para `contracts`. Por isso esta trava casa pelo
NÚMERO DO CONTRATO dentro de `description`: é pista, não prova. Confira a linha antes de
agir, e se um dia alguém criar o vínculo por chave, troque este ILIKE por ele.

Hoje passa em verde porque nenhum contrato de valor único está ativo ainda. É deliberado:
a trava existe para acusar no dia em que o primeiro for — que é o dia em que passa a
custar dinheiro.

    python3 backend/scripts/qa/checar_contrato_sem_cobranca.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app")

SQL = """
SELECT c.contract_number,
       coalesce(cl.name, c.name, '—')                         AS cliente,
       coalesce(c.total_value, 0)                             AS total,
       (SELECT count(*) FROM contract_items i
         WHERE i.contract_id = c.id AND coalesce(i.is_active, true)) AS parcelas,
       (SELECT count(*) FROM receivable_accounts r
         WHERE coalesce(r.origem::text, '') = 'contrato'
           AND coalesce(r.description, '') ILIKE '%' || c.contract_number || '%') AS recebiveis_proximos
  FROM contracts c
  LEFT JOIN clients cl ON cl.id = c.client_id
 WHERE c.contract_type::text = 'one_time'
   AND lower(c.status::text) IN ('active', 'ativo', 'vigente')
"""


async def main() -> int:
    import main_production  # noqa: F401,PLC0415,I001
    from core.database import async_session_factory  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    async with async_session_factory() as db:
        linhas = (await db.execute(text(SQL))).mappings().all()

    orfaos = [r for r in linhas if not r["recebiveis_proximos"]]
    for r in orfaos:
        print(f"💰 {r['contract_number']} · {r['cliente'][:34]} · R$ {r['total']:,.2f} "
              f"em {r['parcelas']} parcela(s) — sem conta a receber")

    print(f"\nTOTAL contratos de valor único ativos sem cobrança: {len(orfaos)} "
          f"(de {len(linhas)} ativo(s))")
    if orfaos:
        print("O cronograma está em contract_items e o contas a receber não sabe dele.")
        print("FAIL checar_contrato_sem_cobranca")
        return 1
    print("OK checar_contrato_sem_cobranca")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
