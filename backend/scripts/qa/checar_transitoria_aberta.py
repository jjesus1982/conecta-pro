#!/usr/bin/env python3
"""O que sobrou nas contas transitórias — como fila de decisão, não como mistério.

## A regra que isto afirma

`5.9.9.01 Saídas a Classificar` e `4.9.9.01 Entradas a Classificar` são conta de passagem.
O que fica nelas é dinheiro que a empresa movimentou e ninguém disse o que era. Enquanto
estiver ali, o DRE mostra uma linha sem significado no lugar de despesa ou receita.

Em 25/09/2026 a transitória de saída tinha **R$ 524.588,32 em 855 lançamentos — 19% de toda
a despesa do ano**. A varredura daquele dia tirou R$ 252.192,83 aplicando as regras que
existiam (transferência entre as empresas do grupo, CNPJ de fornecedor conhecido, pagamento
de salário já provisionado). O que ficou, **R$ 272.395,49**, não sai por regra: são
pagamentos a empresas reais e PIX a pessoas de fora do cadastro, cada um precisando de
alguém que conheça o negócio para dizer o que foi.

## O que ele faz

Não classifica e não chuta. Agrupa o que restou **por contraparte**, ordenado por valor, de
modo que a decisão seja uma lista finita e não uma linha de R$ 272 mil no demonstrativo.
Uma contraparte decidida costuma resolver vários lançamentos de uma vez — a Solides eram 16
linhas com o mesmo destino.

## O que ele NÃO faz

Não escreve no razão. Reclassificar conta é ato de contador, e um pagamento a CNPJ pode ser
despesa de serviço, parcela de financiamento (parte passivo, parte juros), empréstimo ou
gasto pessoal do sócio — a descrição diz, a regra não.

Linha canônica: `TOTAL: <n> lançamento(s) em conta transitória`.
"""

from __future__ import annotations

import asyncio
import re
import sys

#: As duas contas de passagem do plano.
TRANSITORIAS = {"5.9.9.01": "Saídas a Classificar", "4.9.9.01": "Entradas a Classificar"}

#: Abaixo disto é poeira: não vale a atenção de ninguém.
PISO_CONTRAPARTE = 300.0


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    total = 0
    async with async_session_factory() as db:
        for conta, nome in TRANSITORIAS.items():
            lado = "conta_debito" if conta.startswith("5") else "conta_credito"
            linhas = (await db.execute(text(f"""
                SELECT a.valor v, coalesce(b.counterparty_name,'') nome,
                       coalesce(b.counterparty_document,'') doc,
                       coalesce(b.description,'') descr,
                       coalesce(b.justificativa_categoria,'(sem categoria)') cat
                  FROM accounting_entries a
                  LEFT JOIN bank_transactions b ON b.id = a.bank_transaction_id
                 WHERE a.{lado} = :c AND coalesce(a.tipo_lancamento,'') <> 'apuracao'
            """), {"c": conta})).mappings().all()
            if not linhas:
                print(f"{conta} «{nome}»: vazia ✓")
                continue

            soma = sum(float(r["v"]) for r in linhas)
            total += len(linhas)
            print(f"\n{conta} «{nome}»: {len(linhas)} lançamento(s), R$ {soma:,.2f}")

            por: dict[str, list] = {}
            for r in linhas:
                doc = re.sub(r"\D", "", r["doc"])
                chave = doc or (r["nome"].strip().upper() or "(sem contraparte)")
                por.setdefault(chave, []).append(r)

            grandes = sorted(
                ((k, v) for k, v in por.items() if sum(float(x["v"]) for x in v) >= PISO_CONTRAPARTE),
                key=lambda x: -sum(float(r["v"]) for r in x[1]),
            )
            miudos = [(k, v) for k, v in por.items() if k not in dict(grandes)]

            print(f"  {len(por)} contraparte(s) distinta(s) — decidir por contraparte resolve em lote:")
            for chave, rs in grandes[:25]:
                v = sum(float(x["v"]) for x in rs)
                nm = next((x["nome"] for x in rs if x["nome"].strip()), "") or "(sem nome)"
                tipo = "CNPJ" if len(chave) == 14 else "CPF " if len(chave) == 11 else "----"
                amostra = next((x["descr"] for x in rs if x["descr"].strip()), "")[:46]
                print(f"     {tipo} {nm[:30]:<30} {len(rs):>3}x  R$ {v:>11,.2f}  {amostra}")
            if len(grandes) > 25:
                resto = sum(sum(float(x["v"]) for x in rs) for _k, rs in grandes[25:])
                print(f"     … mais {len(grandes) - 25} contraparte(s) acima de "
                      f"R$ {PISO_CONTRAPARTE:,.0f}: R$ {resto:,.2f}")
            if miudos:
                vm = sum(sum(float(x["v"]) for x in rs) for _k, rs in miudos)
                print(f"     (+ {len(miudos)} contraparte(s) abaixo de R$ {PISO_CONTRAPARTE:,.0f}, "
                      f"somando R$ {vm:,.2f})")

    print(f"\nTOTAL: {total} lançamento(s) em conta transitória")
    return 1 if total else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
