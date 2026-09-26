#!/usr/bin/env python3
"""Adjudica os grupos multi-fonte CONTRA O EXTRATO DO BANCO. Só lê, nunca apaga.

Nasceu em 26/09/2026, quando o oráculo do extrato saltou de 12 para 73 grupos. O salto
não foi defeito novo: a conciliação passou a nomear 545 transações que estavam sem
contraparte, e a checagem **exige favorecido preenchido** — os 61 grupos sempre existiram
e eram invisíveis por falta de nome. (O próprio comentário do oráculo já avisava:
«ela exige favorecido preenchido, e essas cópias vêm sem nome».)

O que se sabe deles, medido:

  · 73 grupos, 77 linhas excedentes, **R$ 9.864,13**;
  · 71 são `inter_api_backfill_20260811 + inter_api_sync` — a assinatura de importação
    dupla, agravada porque a linha da API vem com `external_id` NULO e o índice único do
    banco é parcial (`WHERE external_id IS NOT NULL`): nulo nunca colide com nulo;
  · **todos entre 2026-03 e 2026-07**, ou seja ANTES do corte contábil de 01/08 — por
    isso a conferência de saldo contra o banco, que começa no corte, continua verde;
  · **as 77 têm lançamento no razão.** Se forem cópias, são R$ 9.864,13 de despesa
    contada duas vezes no resultado arqueológico de 2026.

Em 26/09/2026 o `/banking/v2/extrato/completo` do Inter devolveu **503** em todos os
intervalos, inclusive nos recentes. Sem a contagem do banco não há adjudicação, e este
script RECUSA concluir em vez de chutar.

O método é o do oráculo do extrato, e ele existe porque casar por NOME deu respostas
contraditórias para o mesmo caso: **para cada dia, quantos lançamentos de cada valor o
banco tem, contra quantos nós temos.** Se o nosso excede o do banco, é cópia.

Nunca apagar sem isto: já se apagou um pagamento achando que era duplicata, e o saldo
denunciou com a diferença exata de R$ 32,00.
"""

import asyncio
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, "/app")


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.integrations.inter.inter_sync_service import _build_adapter

    async with async_session_factory() as db:
        grupos = (await db.execute(text("""
            SELECT transaction_date d, amount a, unaccent(upper(counterparty_name)) n,
                   count(*) nossas,
                   string_agg(DISTINCT coalesce(imported_from, origin, '?'), ' + ') fontes
              FROM bank_transactions t
             WHERE coalesce(counterparty_name, '') <> ''
               AND bank_account_id = (SELECT id FROM bank_accounts
                                       WHERE bank_name ILIKE '%inter%' LIMIT 1)
             GROUP BY 1, 2, 3
            HAVING count(DISTINCT coalesce(imported_from, origin, '?')) > 1
             ORDER BY 1"""))).all()

    if not grupos:
        print("nenhum grupo multi-fonte no Inter")
        return 0

    dias = sorted({g[0] for g in grupos})
    print(f"grupos multi-fonte no Inter: {len(grupos)} em {len(dias)} dia(s) "
          f"({dias[0]} a {dias[-1]})")

    ad = _build_adapter()
    do_banco: dict[date, Counter] = {}
    try:
        ini, fim = dias[0], dias[-1]
        # o extrato completo é paginado e aceita intervalo; puxa mês a mês para não
        # estourar as 40 páginas
        cur = date(ini.year, ini.month, 1)
        while cur <= fim:
            prox = date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
            try:
                txs = await ad.get_statement_completo(cur, date.fromordinal(prox.toordinal() - 1))
            except Exception as exc:  # noqa: BLE001
                print(f"   ({cur:%Y-%m}: extrato indisponível — {str(exc)[:70]})")
                txs = []
            for t in txs:
                d = getattr(t, "date", None) or getattr(t, "transaction_date", None)
                v = float(getattr(t, "amount", 0) or 0)
                if d:
                    do_banco.setdefault(d, Counter())[round(abs(v), 2)] += 1
            print(f"   {cur:%Y-%m}: {len(txs)} lançamento(s) no banco")
            cur = prox
    finally:
        await ad.close()

    if not do_banco:
        print("\nRECUSO CONCLUIR: o banco não devolveu extrato. Sem a contagem do banco não")
        print("há adjudicação — e apagar sem ela já custou caro nesta casa.")
        return 2

    copias = legitimos = sem_cobertura = 0
    v_copias = 0.0
    print()
    for d, a, n, nossas, fontes in grupos:
        if d not in do_banco:
            sem_cobertura += 1
            continue
        no_banco = do_banco[d][round(abs(float(a)), 2)]
        if nossas > no_banco:
            copias += 1
            v_copias += (nossas - no_banco) * abs(float(a))
            print(f"   CÓPIA    {d}  R$ {abs(float(a)):>9,.2f}  {n[:26]:<26} "
                  f"nós {nossas} × banco {no_banco}   [{fontes}]")
        else:
            legitimos += 1
    print()
    print(f"legítimos (banco tem tantos quanto nós): {legitimos}")
    print(f"CÓPIAS (nós temos a mais): {copias} · R$ {v_copias:,.2f}")
    print(f"sem cobertura do extrato do banco: {sem_cobertura}")
    print("\nNADA foi apagado. Apagar é decisão do dono, e o valor está aí.")
    return 0


raise SystemExit(asyncio.run(main()))
