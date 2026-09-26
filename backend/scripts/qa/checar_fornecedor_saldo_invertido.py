#!/usr/bin/env python3
"""Fornecedor pago sem nota escriturada — o passivo que vira negativo.

## A regra que isto afirma

`2.1.4.01 Fornecedores a Pagar` é passivo: nasce no CRÉDITO (a nota tomada, por
competência) e morre no DÉBITO (o pagamento). Se o débito acumulado passa o crédito, o
saldo fica **negativo**, e isso nunca é um fato do negócio — é um destes três:

  • pagou-se uma nota que nunca foi escriturada (a despesa some do DRE);
  • a nota está sob o CNPJ errado (a irmã escriturou, esta pagou);
  • o pagamento foi casado com a nota errada.

## Por que ele existe

Em 26/09/2026 o extrato passou a reconhecer que pagar uma NFS-e tomada já escriturada é
LIQUIDAÇÃO, não despesa nova — 58 lançamentos, R$ 119.280,90, que entravam duas vezes no
DRE. O casamento é por CNPJ do prestador + valor, e é forte, mas não infalível: no mesmo
dia a Patrimonial ficou com `2.1.4.01` em **−R$ 9.858,54**, porque uma nota da Portte de
maio/2026 foi recusada pelo corte contábil e o pagamento dela não. O saldo invertido é o
preço honesto dessa escolha — e este caçador é quem o cobra.

## O que ele NÃO faz

Não reclassifica nada de volta. Saldo negativo pode significar despesa faltando OU
pagamento casado errado, e só quem olha o par nota×pagamento decide.

Linha canônica: `TOTAL: <n> empresa(s) com fornecedor em saldo invertido`.
"""

from __future__ import annotations

import asyncio
import sys

#: Conta de fornecedores. Centavo de arredondamento não é alarme.
CONTA = "2.1.4.01"
PISO = 1.0


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
                SELECT e.razao_social nome,
                       coalesce(sum(a.valor) FILTER (WHERE a.conta_credito = :c), 0) provisionado,
                       coalesce(sum(a.valor) FILTER (WHERE a.conta_debito  = :c), 0) pago
                  FROM accounting_entries a
                  JOIN empresas e ON e.id = a.empresa_id
                 WHERE :c IN (a.conta_debito, a.conta_credito)
                 GROUP BY 1 ORDER BY 1
            """),
                    {"c": CONTA},
                )
            )
            .mappings()
            .all()
        )
        for linha in linhas:
            saldo = float(linha["provisionado"]) - float(linha["pago"])
            marca = "ok" if saldo >= -PISO else "INVERTIDO"
            print(
                f"  {linha['nome'][:34]:<34} nota R$ {float(linha['provisionado']):>12,.2f}"
                f"  pago R$ {float(linha['pago']):>12,.2f}  saldo R$ {saldo:>12,.2f}  {marca}"
            )
            if saldo < -PISO:
                total += 1
                for d in (
                    (
                        await db.execute(
                            text("""
                        SELECT a.data_lancamento dia, a.valor v, left(a.historico, 70) h
                          FROM accounting_entries a
                          JOIN empresas e ON e.id = a.empresa_id
                         WHERE a.conta_debito = :c AND e.razao_social = :n
                         ORDER BY a.valor DESC LIMIT 5
                    """),
                            {"c": CONTA, "n": linha["nome"]},
                        )
                    )
                    .mappings()
                    .all()
                ):
                    print(f"       pago {d['dia']}  R$ {float(d['v']):>10,.2f}  {d['h']}")

    print(f"\nTOTAL: {total} empresa(s) com fornecedor em saldo invertido")
    return 1 if total else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
