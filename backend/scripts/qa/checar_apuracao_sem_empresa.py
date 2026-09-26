#!/usr/bin/env python3
"""Encerramento de resultado que não sabe de qual CNPJ é.

## A regra que isto afirma

São duas empresas com CNPJ próprio, regime próprio e ECD própria. Cada lançamento do razão
diz a qual delas pertence — **menos os de apuração**.

`apuracao_resultado.apurar(competencia)` fecha 4.x e 5.x contra o PL **por competência, sem
filtrar empresa**. Grava `empresa_id = NULL`. Medido em 25/09/2026: **171 lançamentos,
R$ 5.132.437,80 — e são os ÚNICOS 171 do razão inteiro sem empresa.**

## Por que isso importa para sair da contabilidade terceirizada

1. **A ECD de cada CNPJ nasce sem o encerramento.** O gerador filtra `empresa_id`, então os
   lançamentos de apuração ficam de fora do bloco I200/I250 — que é o Livro Diário. Um
   diário sem os lançamentos de encerramento não é o diário do exercício.
2. **O resultado dos dois CNPJs é somado num lançamento só.** São duas pessoas jurídicas
   distintas; o lucro de uma não encerra contra o patrimônio da outra.
3. **`dre-consolidado`, que filtra `empresa_id`, nunca enxerga a apuração.**

Resultado de 2026 por empresa, que é o que cada encerramento deveria levar ao PL:

    CONECTAMAIS ELETRONICA    receita 1.584.579,69  despesa 1.842.082,34  →  −257.502,65
    CONECTAMAIS PATRIMONIAL   receita   597.155,75  despesa   776.170,01  →  −179.014,26

## Por que esta trava NÃO conserta

Tornar a apuração por CNPJ tem uma armadilha: as apurações já feitas têm `empresa_id` nulo,
então uma apuração filtrada por empresa **não as enxergaria** e calcularia o resultado cheio
de novo — fechando o mês em DOBRO. Corrigir exige decidir o que fazer com os 171 lançamentos
existentes, e isso é ato de contador. A trava conta e descreve; não escreve.

Linha canônica: `TOTAL: <n> lançamento(s) de encerramento sem empresa`.
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
        n, valor = (await db.execute(text(
            "SELECT count(*), coalesce(round(sum(valor), 2), 0) FROM accounting_entries "
            " WHERE coalesce(tipo_lancamento,'') = 'apuracao' AND empresa_id IS NULL"
        ))).one()
        total_apur = (await db.execute(text(
            "SELECT count(*) FROM accounting_entries WHERE coalesce(tipo_lancamento,'') = 'apuracao'"
        ))).scalar()
        outros_sem = (await db.execute(text(
            "SELECT count(*) FROM accounting_entries "
            " WHERE empresa_id IS NULL AND coalesce(tipo_lancamento,'') <> 'apuracao'"
        ))).scalar()

        print(f"lançamentos de apuração: {total_apur} · sem empresa: {n} · "
              f"R$ {float(valor):,.2f}")
        print(f"outros lançamentos sem empresa (não-apuração): {outros_sem}")

        if n:
            print("\npor competência:")
            for comp, q, v in (await db.execute(text(
                "SELECT periodo_competencia, count(*), round(sum(valor), 2) "
                "  FROM accounting_entries "
                " WHERE coalesce(tipo_lancamento,'') = 'apuracao' AND empresa_id IS NULL "
                " GROUP BY 1 ORDER BY 1"
            ))).all():
                print(f"   {comp or '(sem competência)':<12} {q:>3} lanç.  R$ {float(v):>13,.2f}")

            print("\nresultado de 2026 por empresa — o que cada encerramento deveria levar ao PL:")
            for nome, rec, desp in (await db.execute(text("""
                WITH mov AS (
                    SELECT e.empresa_id, e.conta_credito AS conta, e.valor AS v
                      FROM accounting_entries e
                     WHERE coalesce(e.tipo_lancamento,'') <> 'apuracao'
                       AND substr(coalesce(e.periodo_competencia,''), 1, 4) = '2026'
                    UNION ALL
                    SELECT e.empresa_id, e.conta_debito, -e.valor
                      FROM accounting_entries e
                     WHERE coalesce(e.tipo_lancamento,'') <> 'apuracao'
                       AND substr(coalesce(e.periodo_competencia,''), 1, 4) = '2026'
                )
                SELECT coalesce(em.razao_social, '(sem empresa)'),
                       coalesce(round(sum(mov.v) FILTER (WHERE upper(a.account_type) = 'REVENUE'), 2), 0),
                       coalesce(round(-sum(mov.v) FILTER (WHERE upper(a.account_type) IN ('EXPENSE','COST')), 2), 0)
                  FROM mov
                  JOIN fin_accounting_accounts a ON a.code = mov.conta
                  LEFT JOIN empresas em ON em.id = mov.empresa_id
                 GROUP BY 1 ORDER BY 2 DESC
            """))).all():
                r, d = float(rec), float(desp)
                print(f"   {nome[:30]:<30} receita R$ {r:>13,.2f}  despesa R$ {d:>13,.2f}"
                      f"  →  R$ {r - d:>13,.2f}")

            print("\n  → A ECD de cada CNPJ sai SEM estes lançamentos (o gerador filtra")
            print("    empresa_id), e o encerramento soma as duas pessoas jurídicas num só.")
            print("    Corrigir exige decidir o destino dos lançamentos existentes: uma")
            print("    apuração por CNPJ não os enxergaria e fecharia o mês em DOBRO.")
            print("    Ato de contador — esta trava conta, não escreve.")

    print(f"\nTOTAL: {n} lançamento(s) de encerramento sem empresa")
    return 1 if n else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
