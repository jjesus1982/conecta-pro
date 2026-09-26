#!/usr/bin/env python3
"""Mesma competência, mesmo tomador, mesmo valor — duas notas.

## A regra que isto afirma

Um serviço mensal gera UMA nota por competência. Duas notas com o mesmo tomador, o mesmo
valor e a mesma competência são, até prova em contrário, a mesma cobrança emitida duas
vezes — e cada uma custa três coisas: o cliente cobrado em dobro, o ISS recolhido sobre
faturamento que não existiu, e a receita do mês inflada no DRE.

Medido em 25/09/2026, sobre as 115 NFS-e de produção: **5 grupos duplicados,
R$ 130.328,02 de excedente, com R$ 4.292,94 de ISS pago em cima.**

    2026-06  IDEAL FLORES      R$ 65.842,42 ×2   notas 4 e 111   Patrimonial + Eletrônica
    2026-06  LARANJEIRAS       R$ 42.544,50 ×2   notas 3 e 109   Patrimonial + Eletrônica
    2026-08  MIRANTE FLORES    R$ 12.061,50 ×2   notas 26 e 27   mesma empresa, mesmo dia
    2026-07  GELAIN            R$  6.000,00 ×2   notas 112 e 115
    2026-06  PRIME ARENA       R$  3.879,60 ×2   notas 98 e 100

Os dois maiores têm causa conhecida: em junho/2026 o faturamento dos condomínios migrou da
Eletrônica para a Patrimonial, e o mesmo mês foi emitido pelos DOIS CNPJs. Os outros três
são a mesma empresa emitindo duas vezes.

## O que ele NÃO faz

Não cancela nota. Cancelamento no fisco tem prazo, exige justificativa e é ato do dono —
e há casos legítimos de duas notas iguais no mês (duas parcelas idênticas, dois postos com o
mesmo preço). A trava mede e mostra o par para alguém olhar.

Linha canônica: `TOTAL: <n> grupo(s) de nota duplicada`.
"""

from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    async with async_session_factory() as db:
        vivas = (await db.execute(text(
            "SELECT count(*) FROM nfse_emitidas_nacional "
            " WHERE coalesce(cancelada, FALSE) = FALSE AND coalesce(ambiente,'') <> 'homologacao'"
        ))).scalar()

        grupos = (await db.execute(text("""
            SELECT n.competencia, coalesce(n.tomador_nome,'(sem nome)') tomador,
                   n.valor_servicos, count(*) q,
                   string_agg(n.numero::text, ', ' ORDER BY n.numero::text) nums,
                   string_agg(DISTINCT coalesce(e.razao_social, '(sem empresa)'), ' | ') emps,
                   string_agg(DISTINCT n.data_emissao::date::text, ' | ') datas,
                   round(avg(coalesce(n.iss_valor, 0)), 2) iss
              FROM nfse_emitidas_nacional n
              LEFT JOIN empresas e ON e.id = n.empresa_id
             WHERE coalesce(n.cancelada, FALSE) = FALSE
               AND coalesce(n.ambiente, '') <> 'homologacao'
               AND coalesce(n.valor_servicos, 0) > 0
             GROUP BY 1, 2, 3
            HAVING count(*) > 1
             ORDER BY (count(*) - 1) * n.valor_servicos DESC
        """))).all()

    print(f"NFS-e de produção vivas: {vivas}")
    if not grupos:
        print("\nNenhuma competência com nota repetida para o mesmo tomador e valor.")
        print("\nTOTAL: 0 grupo(s) de nota duplicada")
        return 0

    excedente = sum(float(g[2]) * (g[3] - 1) for g in grupos)
    iss = sum(float(g[7]) * (g[3] - 1) for g in grupos)
    print(f"\n{len(grupos)} grupo(s) duplicado(s) · excedente R$ {excedente:,.2f} · "
          f"ISS sobre o excedente R$ {iss:,.2f}\n")
    for comp, tomador, valor, q, nums, emps, datas, _iss in grupos:
        exc = float(valor) * (q - 1)
        dois_cnpj = "|" in (emps or "")
        print(f"   {comp}  {tomador[:34]:<34} R$ {float(valor):>10,.2f} ×{q}  "
              f"excedente R$ {exc:>10,.2f}")
        print(f"        notas {nums}  ·  {emps}  ·  {datas}"
              + ("   ← DOIS CNPJs emitiram o mesmo mês" if dois_cnpj else ""))

    print("\n   → Cada duplicata cobra o cliente duas vezes, recolhe ISS sobre faturamento")
    print("     que não existiu e infla a receita do mês no DRE. Cancelar no fisco tem")
    print("     prazo e é ato do dono; a trava mostra o par.")
    print(f"\nTOTAL: {len(grupos)} grupo(s) de nota duplicada")
    return 1


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
