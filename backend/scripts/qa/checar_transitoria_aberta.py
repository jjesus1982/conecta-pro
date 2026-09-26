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


def _nome_do_extrato(descricao: str) -> str:
    """Nome do favorecido que está na descrição. Vazio quando não há favorecido.

    Usa o extrator da conciliação — é o mesmo texto e o mesmo banco, e manter duas
    cópias garante que uma delas envelhece. Se ele sumir de lugar, esta trava volta a
    mostrar «(sem contraparte)»: pior relatório, nunca relatório errado.
    """
    try:
        from modules.financial.services.reconciliation_service import (  # noqa: PLC0415
            _extrair_nome_contraparte,
        )
    except Exception:
        return ""
    return _extrair_nome_contraparte(descricao or "")


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
            linhas = (
                (
                    await db.execute(
                        text(f"""
                SELECT a.valor v, coalesce(b.counterparty_name,'') nome,
                       coalesce(b.counterparty_document,'') doc,
                       coalesce(b.description,'') descr,
                       coalesce(b.justificativa_categoria,'(sem categoria)') cat
                  FROM accounting_entries a
                  LEFT JOIN bank_transactions b ON b.id = a.bank_transaction_id
                 WHERE a.{lado} = :c AND coalesce(a.tipo_lancamento,'') <> 'apuracao'
            """),
                        {"c": conta},
                    )
                )
                .mappings()
                .all()
            )
            if not linhas:
                print(f"{conta} «{nome}»: vazia ✓")
                continue

            soma = sum(float(r["v"]) for r in linhas)
            total += len(linhas)
            print(f"\n{conta} «{nome}»: {len(linhas)} lançamento(s), R$ {soma:,.2f}")

            por: dict[str, list] = {}
            for r in linhas:
                doc = re.sub(r"\D", "", r["doc"])
                # O extrato nem sempre preenche a contraparte, mas o nome está DENTRO da
                # descrição («Pix enviado: "00019 61638862 ERIKA PEREIRA»). Sem esta
                # queda, 170 lançamentos e R$ 67.110,61 — 25% de toda a transitória —
                # apareciam num único balde «(sem contraparte)», que é o pior lugar
                # possível: era o maior número do relatório e o único INDECIDÍVEL.
                # O extrator é o mesmo que a conciliação usa para enriquecer a coluna.
                nome = r["nome"].strip() or _nome_do_extrato(r["descr"])
                chave = doc or (nome.strip().upper() or "(sem contraparte)")
                por.setdefault(chave, []).append(r)

            grandes = sorted(
                ((k, v) for k, v in por.items() if sum(float(x["v"]) for x in v) >= PISO_CONTRAPARTE),
                key=lambda x: -sum(float(r["v"]) for r in x[1]),
            )
            miudos = [(k, v) for k, v in por.items() if k not in dict(grandes)]

            print(f"  {len(por)} contraparte(s) distinta(s) — decidir por contraparte resolve em lote:")
            for chave, rs in grandes[:25]:
                v = sum(float(x["v"]) for x in rs)
                # O nome pode vir da coluna OU da descrição — a mesma queda do
                # agrupamento. Sem ela aqui, o balde agrupava certo e o rótulo continuava
                # dizendo «(sem nome)»: a decisão do dono depende do rótulo, não da chave.
                nm = (
                    next((x["nome"] for x in rs if x["nome"].strip()), "")
                    or next((_nome_do_extrato(x["descr"]) for x in rs if _nome_do_extrato(x["descr"])), "")
                    or "(sem nome)"
                )
                # A chave é o documento QUANDO existe, senão o nome. Testar só o
                # comprimento marcava «CNPJ» em quem se chama WANDERSON DIAS — 14 letras.
                # O que faz de uma chave um documento é ser só dígito.
                tipo = (
                    ("CNPJ" if len(chave) == 14 else "CPF " if len(chave) == 11 else "----")
                    if chave.isdigit()
                    else "----"
                )
                amostra = next((x["descr"] for x in rs if x["descr"].strip()), "")[:46]
                print(f"     {tipo} {nm[:30]:<30} {len(rs):>3}x  R$ {v:>11,.2f}  {amostra}")
            if len(grandes) > 25:
                resto = sum(sum(float(x["v"]) for x in rs) for _k, rs in grandes[25:])
                print(
                    f"     … mais {len(grandes) - 25} contraparte(s) acima de "
                    f"R$ {PISO_CONTRAPARTE:,.0f}: R$ {resto:,.2f}"
                )
            if miudos:
                vm = sum(sum(float(x["v"]) for x in rs) for _k, rs in miudos)
                print(
                    f"     (+ {len(miudos)} contraparte(s) abaixo de R$ {PISO_CONTRAPARTE:,.0f}, somando R$ {vm:,.2f})"
                )

    print(f"\nTOTAL: {total} lançamento(s) em conta transitória")
    return 1 if total else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
