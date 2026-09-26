#!/usr/bin/env python3
"""Crédito de retenção na fonte que ninguém compensou — dinheiro já pago, parado.

## A regra que isto afirma

Em cessão de mão de obra o tomador retém **11% do valor da nota** (Lei 9.711/98) e recolhe
ao INSS em nome do prestador. Esse valor **não é receita perdida nem inadimplência**: é
crédito a compensar com a contribuição previdenciária própria. A DCTFWeb o reconhece
nominalmente como "Retenção Lei 9711/98".

Crédito de retenção que cresce mês após mês sem ser abatido significa uma de duas coisas, e
as duas custam caro:

  • o débito que ele existe para pagar **não está sendo declarado** (é o caso da
    Patrimonial: a CPP patronal não aparece nem no DAS nem na DCTFWeb); ou
  • está sendo declarado e pago **em dinheiro**, com o crédito intacto ao lado.

## O que ele mediu quando nasceu (26/09/2026)

  CONECTAMAIS PATRIMONIAL  R$ 84.709,90 retidos em 29 notas (jun–set/2026)
  CONECTAMAIS ELETRONICA   R$ 91.290,28 retidos em 24 notas
  DCTFWeb 08/2026 da Patrimonial: R$ 19.544,08 informados · R$ 7.011,23 usados
                                  → R$ 12.532,85 de saldo disponível, todo mês

É a "Estratégia 4 — recuperação de créditos acumulados" do material de mercado, só que o
instrumento aqui não é PIS/COFINS (Simples não gera, e no Lucro Real 91,6% da receita desta
casa é cumulativa por lei): é a retenção previdenciária.

## O que ele NÃO faz

Não compensa nada. Compensação é ato declaratório — vai na DCTFWeb/PER-DCOMP e depende do
enquadramento previdenciário estar certo primeiro. Ele mede o saldo e o expõe.

Linha canônica: `TOTAL: <n> empresa(s) com crédito de retenção sem compensar`.
"""

from __future__ import annotations

import asyncio
import sys

#: Conta do crédito no plano. Nasceu em 26/09/2026 junto com o lançamento da retenção.
CONTA_CREDITO = "1.1.3.02"

#: Abaixo disto não vale a atenção de ninguém.
PISO = 1000.0


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    total = 0
    async with async_session_factory() as db:
        linhas = (
            (
                await db.execute(
                    text("""
                SELECT e.razao_social nome, e.id::text id,
                       coalesce(sum(a.valor) FILTER (WHERE a.conta_debito  = :c), 0) acumulado,
                       coalesce(sum(a.valor) FILTER (WHERE a.conta_credito = :c), 0) compensado
                  FROM accounting_entries a
                  JOIN empresas e ON e.id = a.empresa_id
                 WHERE :c IN (a.conta_debito, a.conta_credito)
                 GROUP BY 1, 2 ORDER BY 1
            """),
                    {"c": CONTA_CREDITO},
                )
            )
            .mappings()
            .all()
        )
        if not linhas:
            print("  nenhuma retenção escriturada — nada a medir")
            print("\nTOTAL: 0 empresa(s) com crédito de retenção sem compensar")
            return 0

        for linha in linhas:
            saldo = float(linha["acumulado"]) - float(linha["compensado"])
            print(
                f"  {linha['nome'][:34]:<34} retido R$ {float(linha['acumulado']):>12,.2f}"
                f"  compensado R$ {float(linha['compensado']):>12,.2f}"
                f"  parado R$ {saldo:>12,.2f}"
            )
            if saldo <= PISO:
                continue
            total += 1
            # Por competência, para ficar claro se PARA de crescer depois de decidido.
            for m in (
                (
                    await db.execute(
                        text("""
                    SELECT a.periodo_competencia comp, sum(a.valor) v, count(*) n
                      FROM accounting_entries a
                     WHERE a.conta_debito = :c AND a.empresa_id = CAST(:e AS uuid)
                     GROUP BY 1 ORDER BY 1
                """),
                        {"c": CONTA_CREDITO, "e": linha["id"]},
                    )
                )
                .mappings()
                .all()
            ):
                print(f"       {m['comp']}  R$ {float(m['v']):>11,.2f}  em {m['n']} nota(s)")

    print(f"\nTOTAL: {total} empresa(s) com crédito de retenção sem compensar")
    return 1 if total else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
