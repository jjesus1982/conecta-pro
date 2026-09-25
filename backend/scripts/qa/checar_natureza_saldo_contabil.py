#!/usr/bin/env python3
"""Conta com saldo de natureza INVERTIDA — ativo negativo, passivo devedor, receita a débito.

## A regra que isto afirma

Em partida dobrada, cada tipo de conta tem uma natureza esperada:

| Tipo | Natureza | Saldo normal |
|---|---|---|
| ASSET, EXPENSE, COST | devedora | **débito > crédito** |
| LIABILITY, EQUITY, REVENUE | credora | **crédito > débito** |

Saldo invertido não é ilegal — um banco pode ficar negativo (cheque especial), um adiantamento
a fornecedor pode virar credor. **Mas é sempre uma pergunta**, e numa contabilidade que ninguém
confere ele é o primeiro lugar onde erro de classificação aparece.

Esta casa já teve o Balanço exibindo **PL de +R$ 2,02 milhões** por meses porque não havia
oráculo contábil. Saldo invertido é o sintoma mais barato de procurar.

## O que ele NÃO faz

Não corrige, não reclassifica, não julga se o saldo está errado. Lista, com o valor e o peso
relativo, para quem entende do negócio olhar. **Reclassificar conta é ato do contador.**

Linha canônica: `TOTAL: <n> conta(s) com saldo de natureza invertida`.
"""

from __future__ import annotations

import asyncio
import sys

DEVEDORAS = {"ASSET", "EXPENSE", "COST"}
CREDORAS = {"LIABILITY", "EQUITY", "REVENUE"}

#: Abaixo disto é poeira de arredondamento, não achado.
PISO = 0.01


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    async with async_session_factory() as db:
        linhas = (
            await db.execute(
                text(
                    "SELECT m.conta, coalesce(a.name,'(fora do plano)') nome,"
                    "       coalesce(a.account_type,'(sem tipo)') tipo,"
                    "       sum(m.d) d, sum(m.c) c"
                    "  FROM ("
                    "     SELECT conta_debito AS conta, sum(valor) d, 0::numeric c"
                    "       FROM accounting_entries GROUP BY 1"
                    "     UNION ALL"
                    "     SELECT conta_credito, 0::numeric, sum(valor)"
                    "       FROM accounting_entries GROUP BY 1) m"
                    "  LEFT JOIN fin_accounting_accounts a ON a.code = m.conta"
                    " GROUP BY 1,2,3 ORDER BY 1"
                )
            )
        ).all()

        # a equação: a soma de TODOS os saldos tem de ser zero numa partida dobrada íntegra
        soma = sum(float(d) - float(c) for _, _, _, d, c in linhas)
        invertidas: list[tuple] = []
        sem_tipo = 0
        for conta, nome, tipo, d, c in linhas:
            saldo = float(d) - float(c)
            if tipo in ("(sem tipo)",):
                sem_tipo += 1
                continue
            if abs(saldo) < PISO:
                continue
            if (tipo in DEVEDORAS and saldo < 0) or (tipo in CREDORAS and saldo > 0):
                invertidas.append((conta, nome, tipo, saldo, float(d), float(c)))

    print(f"contas movimentadas: {len(linhas)} · sem tipo no plano: {sem_tipo}")
    print(f"soma de todos os saldos: {soma:,.2f}  (partida dobrada íntegra = 0,00)")
    if abs(soma) >= PISO:
        print("  ⚠️ A SOMA NÃO FECHA — antes de olhar natureza, há lançamento perdido ou valor truncado.")
    print()
    if invertidas:
        print("SALDO DE NATUREZA INVERTIDA (não é erro por si — é pergunta):")
        for conta, nome, tipo, saldo, d, c in sorted(invertidas, key=lambda x: -abs(x[3])):
            esperado = "devedora" if tipo in DEVEDORAS else "credora"
            print(f"  {conta:<14} {tipo:<10} {nome[:38]:<38}")
            print(f"  {'':<14} esperada {esperado:<9} saldo {saldo:>15,.2f}  (D {d:,.2f} · C {c:,.2f})")
    print(f"\nTOTAL: {len(invertidas)} conta(s) com saldo de natureza invertida")
    return 1 if (invertidas or abs(soma) >= PISO) else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
