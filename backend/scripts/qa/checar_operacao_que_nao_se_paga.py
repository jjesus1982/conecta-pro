#!/usr/bin/env python3
"""Empresa cuja OPERAÇÃO não se paga — o indicador que o resultado total esconde.

## A regra que isto afirma

Resultado total e resultado OPERACIONAL são coisas diferentes, e só o segundo diz se o
negócio deve continuar existindo. Uma empresa pode fechar o mês no azul por receita que não
vem da operação — aporte do sócio, venda de um bem, empréstimo — enquanto a operação em si
consome mais do que produz.

A lição vem do material que o dono comprou e mandou estudar (Macro Bit, "Gestão Financeira",
aula de indicadores, 26/09/2026):

> «A lucratividade do meu negócio foi de 86,91%… porém ele só foi lucrativo porque teve uma
> receita NÃO operacional. A minha operação me deu prejuízo de 13,79%. Já vi diversas
> empresas onde o sócio ficava aportando dinheiro para manter a empresa viva. Não faz
> sentido aportar dinheiro se a tua operação é ruim.»

## O que ele mede

  resultado operacional = receita de serviços (4.1.1.x)
                        − despesa e custo operacionais (EXPENSE/COST, exceto financeiras)

Despesa financeira (5.2.3.x) fica FORA: juros e financiamento são custo de capital, não da
operação. Uma operação que se paga e afunda em juros é um problema de dívida; uma que não se
paga é um problema de negócio, e os dois se resolvem de formas opostas.

## O que ele mediu quando nasceu (26/09/2026, competência 2026-08)

  PATRIMONIAL  receita 262.161,56 · despesa 256.542,76 → **+5.618,80  (+2,1%)**
  ELETRÔNICA   receita  13.300,00 · despesa  31.454,13 → **−18.154,13 (−136,5%)**

A Eletrônica gasta 2,4× o que fatura só para existir. Ela transferiu os contratos para a
irmã em junho/2026 e ficou com a estrutura: a operação não encolheu junto com a receita.

## O que ele NÃO faz

Não julga se a empresa deve fechar. A separação operacional × não operacional, que ele media
por aproximação quando nasceu, passou a ser do PLANO DE CONTAS em 26/09/2026: o grupo
`4.3 Receitas Não Operacionais` foi criado com quatro analíticas (venda de imobilizado,
receitas financeiras, indenizações, outras). Enquanto ninguém lançar nada em 4.3 o resultado
é o mesmo — a diferença aparece no primeiro dia em que uma venda de bem entrar, e aí ela
não vai somar com faturamento de portaria sem ninguém ver.

Linha canônica: `TOTAL: <n> empresa(s) com operação que não se paga`.
"""

from __future__ import annotations

import asyncio
import sys

#: Receita da operação. O que não estiver aqui não é serviço prestado.
PREFIXO_RECEITA_OPERACIONAL = "4.1"

#: Receita que NÃO vem da operação — venda de bem, indenização, rendimento financeiro.
#: O grupo nasceu em 26/09/2026 justamente para esta medida: antes dele o plano só tinha
#: `4.1 Receitas Operacionais`, e este caçador media a operação por aproximação (pelo que
#: ela fatura em serviço). Agora a distinção é do plano, não da heurística.
PREFIXO_RECEITA_NAO_OPERACIONAL = "4.3"

#: Despesa financeira sai da conta da operação: é custo de capital.
PREFIXO_FINANCEIRA = "5.2.3"

#: Meses a olhar, do mais recente fechado para trás.
MESES = 3


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    total = 0
    async with async_session_factory() as db:
        comps = [
            r[0]
            for r in (
                await db.execute(
                    text("""
                SELECT DISTINCT periodo_competencia FROM accounting_entries
                 WHERE periodo_competencia IS NOT NULL
                   AND periodo_competencia < to_char(now(), 'YYYY-MM')
                 ORDER BY 1 DESC LIMIT :n
            """),
                    {"n": MESES},
                )
            ).all()
        ]
        if not comps:
            print("Nenhuma competência fechada — nada a medir.")
            print("\nTOTAL: 0 empresa(s) com operação que não se paga")
            return 0

        linhas = (
            (
                await db.execute(
                    text("""
                SELECT e.razao_social nome, a.periodo_competencia comp,
                       coalesce(sum(a.valor) FILTER (
                           WHERE a.conta_credito LIKE :rec || '%'
                             AND a.conta_credito NOT LIKE :naoop || '%'), 0) receita,
                       coalesce(sum(a.valor) FILTER (
                           WHERE a.conta_credito LIKE :naoop || '%'), 0) nao_operacional,
                       coalesce(sum(a.valor) FILTER (
                           WHERE c.account_type IN ('EXPENSE','COST')
                             AND a.conta_debito NOT LIKE :fin || '%'), 0) despesa
                  FROM accounting_entries a
                  JOIN empresas e ON e.id = a.empresa_id
             LEFT JOIN fin_accounting_accounts c ON c.code = a.conta_debito
                 WHERE a.periodo_competencia = ANY(:comps)
                   AND coalesce(a.tipo_lancamento,'') <> 'apuracao'
                 GROUP BY 1, 2 ORDER BY 1, 2
            """),
                    {
                        "rec": PREFIXO_RECEITA_OPERACIONAL,
                        "naoop": PREFIXO_RECEITA_NAO_OPERACIONAL,
                        "fin": PREFIXO_FINANCEIRA,
                        "comps": comps,
                    },
                )
            )
            .mappings()
            .all()
        )

        por_empresa: dict[str, list] = {}
        for linha in linhas:
            por_empresa.setdefault(linha["nome"], []).append(linha)

        for nome, ms in por_empresa.items():
            print(f"\n  {nome}")
            negativos = 0
            for m in ms:
                rec, desp = float(m["receita"]), float(m["despesa"])
                res = rec - desp
                pct = (100 * res / rec) if rec > 0 else None
                marca = "OPERAÇÃO NÃO SE PAGA" if res < 0 else "ok"
                if res < 0:
                    negativos += 1
                nao_op = float(m["nao_operacional"])
                print(
                    f"     {m['comp']}  receita R$ {rec:>12,.2f}  despesa R$ {desp:>12,.2f}"
                    f"  → R$ {res:>12,.2f}"
                    + (f"  ({pct:>6.1f}%)" if pct is not None else "  (sem receita)")
                    + f"  {marca}"
                    + (f"   [+ R$ {nao_op:,.2f} NÃO operacional, fora da conta]" if nao_op else "")
                )
            # Só acusa quem não se paga em TODOS os meses olhados: um mês ruim é operação,
            # três seguidos é estrutura.
            if negativos == len(ms) and ms:
                total += 1
                print(f"     → {negativos}/{len(ms)} meses no vermelho OPERACIONAL: é estrutura, não mês ruim")

    print(f"\nTOTAL: {total} empresa(s) com operação que não se paga")
    return 1 if total else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
