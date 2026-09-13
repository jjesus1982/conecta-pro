#!/usr/bin/env python3
"""Contrato com preço mexido por ROTINA e sem aditivo assinado (frente 03, 12/09/2026).

Pré-mortem, frente 3, item 3: propagar o aumento do VR/VT ao preço do cliente por rotina é
alterar contrato assinado — faturamento indevido. A regra da casa é: o reajuste de benefício
abre PEDIDO (agent_drafts, tipo `reajuste_beneficio_repasse`) e só vira preço por ADITIVO
(`contract_addendums`, tipo 'adjustment', `signed = true`). Este caçador conta o que escapou:

  A. contrato ativo com `last_adjustment_date` preenchido e NENHUM aditivo de reajuste assinado
     vigente a partir dessa data — o preço foi reajustado por alguma rotina e ninguém assinou;
  B. pedido de repasse APROVADO cujo contrato hoje tem `monthly_value` diferente do "R$ Contrato"
     que o pedido registrou, sem aditivo de reajuste assinado depois da decisão.

⚠️ `contracts` não tem trilha de preço (audit_logs: 0 linhas de contrato com monthly_value,
medido 12/09/2026 no staging). Por isso A depende de `last_adjustment_date` e B do próprio
pedido — pista, não prova. Se um dia houver histórico de preço, troque a pista pelo fato.

Linha canônica: `TOTAL repasses sem aditivo: N` — alvo permanente 0. Sai 1 se N > 0.

    python3 backend/scripts/qa/checar_repasse_sem_aditivo.py      # no container, PYTHONPATH=/app
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

sys.path.insert(0, "/app")

SQL_A = """
SELECT c.contract_number, coalesce(c.name,''), c.monthly_value, c.last_adjustment_date
  FROM contracts c
 WHERE lower(c.status::text) IN ('active','ativo','vigente')
   AND c.last_adjustment_date IS NOT NULL
   AND NOT EXISTS (
     SELECT 1 FROM contract_addendums a
      WHERE a.contract_id = c.id AND a.addendum_type::text = 'adjustment'
        AND coalesce(a.signed,false)
        AND coalesce(a.effective_date, a.created_at::date) >= c.last_adjustment_date)
 ORDER BY 1
"""

SQL_B = """
SELECT d.id::text, d.titulo, d.status, d.decidido_em, d.payload
  FROM agent_drafts d
 WHERE d.tipo = 'reajuste_beneficio_repasse'
   AND lower(coalesce(d.status,'')) IN ('aprovado','approved','executado','executed')
"""

SQL_CTR = """
SELECT c.id::text, c.monthly_value,
       EXISTS (SELECT 1 FROM contract_addendums a WHERE a.contract_id = c.id AND a.addendum_type::text = 'adjustment'
                  AND coalesce(a.signed,false) AND coalesce(a.effective_date, a.created_at::date) >= CAST(:desde AS date))
  FROM contracts c WHERE c.contract_number = :n
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    achados: list[str] = []
    async with async_session_factory() as db:
        for num, nome, valor, quando in (await db.execute(text(SQL_A))).fetchall():
            achados.append(f"A {num} · {nome[:34]} · R$ {Decimal(valor or 0):,.2f} · reajustado em {quando} sem aditivo assinado")
        for did, titulo, status, decidido, payload in (await db.execute(text(SQL_B))).fetchall():
            for ctr in (payload or {}).get("contratos", []):
                num = str(ctr.get("contrato", "")).split(" · ")[0].strip()
                antes = ctr.get("valor_contrato")
                if not num.startswith("CTR") or antes in (None, "", "None"):
                    continue
                row = (await db.execute(text(SQL_CTR), {"n": num, "desde": (decidido.date() if decidido else None)})).first()
                if row and row[1] is not None and Decimal(str(row[1])) != Decimal(str(antes)) and not row[2]:
                    achados.append(f"B {num}: pedido {did[:8]} ({status}) registrou R$ {Decimal(str(antes)):,.2f}, "
                                   f"contrato hoje R$ {Decimal(str(row[1])):,.2f}, sem aditivo assinado desde {decidido:%d/%m/%Y}")
    for a in achados:
        print("💸", a)
    print(f"\nTOTAL repasses sem aditivo: {len(achados)}")
    if achados:
        print("FAIL checar_repasse_sem_aditivo — preço de contrato mudou sem aditivo assinado")
        return 1
    print("OK checar_repasse_sem_aditivo")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
