#!/usr/bin/env python3
"""Parcelamento tributário que o balanço não conhece — e que rescinde se parar de pagar.

## Por que esta trava existe

Em 26/09/2026, explorando o portal da contabilidade a pedido do dono, apareceram **seis
parcelamentos vivos** da Eletrônica que o razão não conhecia. E o dono confirmou o que a
ausência de pagamento no extrato já sugeria: *«não to pagando nada da eletronica, não
sobra dinheiro (...) todos os parcelamentos estão atrasados.»*

    Dívida Ativa 1 — Simples        parcela 33 de 145      R$ 1.068,92/mês
    Dívida Ativa 2 — Simples        parcela 12 de 145      R$   266,08/mês
    Dívida Ativa 3 — Simples        parcela  4 de 145      R$ 1.331,16/mês
    Dívida Ativa 4 — demais débitos parcela  4 de  60      R$ 4.349,96/mês
    ISSQN                           parcela  9 de  30      R$   285,01/mês
    ISSQN 2                         parcela  5 de 100      R$   367,92/mês
                                                           ─────────────────
                                                           R$ 7.669,05/mês

O recibo de adesão da negociação 014020428 (PGFN, 20/10/2025) traz o número que falta no
balanço: **VALOR DA DÍVIDA NA DATA DA ADESÃO — R$ 582.262,83**, com desconto máximo
possível de 60,02% e capacidade de pagamento avaliada em R$ 232.773,98 em 60 meses.

## O que está em jogo, nas palavras do próprio recibo

> «EVITE A RESCISÃO: pode ocorrer (...) se o optante descumprir alguma regra da
> negociação. Por exemplo, deixar acumular parcelas atrasadas. Nesse caso, o optante será
> excluído da negociação e perderá todos os benefícios. (...) o optante não poderá
> formalizar uma nova transação pelo prazo de dois anos.»

Rescindir não devolve a dívida ao ponto de partida: devolve **sem o desconto de 60%**, de
uma vez, e tranca a porta de renegociar por dois anos. É por isso que atraso em
parcelamento não é a mesma coisa que atraso em fornecedor, e por isso ele tem trava
própria em vez de somar no contas-a-pagar.

## A decisão do dono, em 26/09/2026

*«sem problemas perder o parcelamento, não tenho dinheiro agora para pagar, quando eu
puder eu renegocio.»*

Isso muda o que esta trava PEDE, e não o que ela mede. Ela deixou de cobrar pagamento —
cobrar o que o dono decidiu não fazer é o alarme que ensina a ignorar o painel. Ela segue
medindo a EXPOSIÇÃO, porque a dívida não some com a decisão: ela cresce, e o dia da
renegociação precisa do número.

O que muda com a rescisão, e é o que vale acompanhar: o desconto de até 60,02% cai, a
dívida volta ao valor cheio e vencida de uma vez, e a empresa fica **dois anos sem poder
aderir a nova transação** — inclusive de outras dívidas. É o prazo que define quando
«quando eu puder eu renegocio» vira possível.

## O que ele mede

Compara o que os órgãos dizem que a empresa deve com o que o **razão** registra como
passivo tributário. A diferença é o tamanho do que o balanço esconde.

## O que ele NÃO faz

Não lança o passivo. O saldo ATUAL de cada negociação está no portal Regularize da PGFN e
muda todo mês por SELIC; lançar o valor da adesão como se fosse o de hoje seria inventar
precisão. Registrar dívida de R$ 582 mil muda o patrimônio líquido da empresa em quatro
vezes — é ato de contador com o extrato na mão, não de varredura noturna.

Linha canônica: `TOTAL: <n> parcelamento(s) tributário(s) fora do balanço`.
"""

from __future__ import annotations

import asyncio
import sys

#: O que foi LIDO nos documentos do portal da contabilidade em 26/09/2026. Cada linha
#: aponta o documento que a prova — número não tem valor aqui sem a fonte.
#: (rótulo, parcela atual, total de parcelas, valor da parcela, fonte)
PARCELAMENTOS: tuple[tuple[str, int, int, float, str], ...] = (
    ("Dívida Ativa 1 — Simples Nacional", 33, 145, 1068.92,
     "PARC 33_145 ... 09 2026.pdf · PGFN-SISPAR 009523101"),
    ("Dívida Ativa 2 — Simples Nacional", 12, 145, 266.08,
     "PARC 12_145 ... 09 2026.pdf · PGFN-SISPAR 014020428"),
    ("Dívida Ativa 3 — Simples Nacional", 4, 145, 1331.16,
     "PARC 4_145 ... 09 2026.pdf · PGFN-SISPAR 016215688"),
    ("Dívida Ativa 4 — demais débitos", 4, 60, 4349.96,
     "PARC 4_60 ... 09 2026.pdf · PGFN-SISPAR 016215689"),
    ("ISSQN — Prefeitura de Manaus", 9, 30, 285.01,
     "PARC 9_30 PARCELAMENTO ISSQN ... 10 2026.pdf"),
    ("ISSQN 2 — Prefeitura de Manaus", 5, 100, 367.92,
     "PARC 5_100 PARCELAMENTO ISSQN 2 ... 10 2026.pdf"),
)

#: Do recibo de adesão e consolidação da negociação 014020428, de 20/10/2025.
DIVIDA_NA_ADESAO = 582262.83
CAPACIDADE_60_MESES = 232773.98
DESCONTO_MAXIMO = 60.02

#: Contas em que um passivo tributário parcelado apareceria no razão.
CONTAS_PASSIVO_TRIBUTARIO = ("2.1.2.04", "2.1.2.09", "2.1.3.01", "2.1.3.02", "2.1.3.03")


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    mensal = sum(p[3] for p in PARCELAMENTOS)
    a_vencer = sum((p[2] - p[1]) * p[3] for p in PARCELAMENTOS)

    async with async_session_factory() as db:
        no_razao = (await db.execute(text("""
            SELECT round(coalesce(sum(CASE WHEN conta_credito = ANY(:c) THEN valor
                                           WHEN conta_debito  = ANY(:c) THEN -valor
                                           ELSE 0 END), 0), 2)
              FROM accounting_entries
             WHERE status = 'confirmado' AND (conta_credito = ANY(:c) OR conta_debito = ANY(:c))
        """), {"c": list(CONTAS_PASSIVO_TRIBUTARIO)})).scalar() or 0

        pagos = (await db.execute(text("""
            SELECT count(*) FROM bank_transactions
             WHERE amount < 0 AND transaction_date >= (CURRENT_DATE - INTERVAL '60 days')
               AND upper(coalesce(description,'') || coalesce(counterparty_name,''))
                   ~ 'PGFN|SISPAR|DIVIDA ATIVA|REGULARIZE'
        """))).scalar() or 0

    print(f"{'parcelamento':<36} {'parcela':>10} {'valor/mês':>12} {'a vencer':>13}")
    for rot, atual, total, valor, _fonte in PARCELAMENTOS:
        print(f"{rot:<36} {atual:>4} de {total:<3} R$ {valor:>9,.2f} "
              f"R$ {(total - atual) * valor:>11,.2f}")
    print(f"{'':<36} {'':>10} R$ {mensal:>9,.2f} R$ {a_vencer:>11,.2f}")

    print(f"\ndívida na data da adesão (PGFN, 20/10/2025): R$ {DIVIDA_NA_ADESAO:,.2f}")
    print(f"   desconto máximo possível {DESCONTO_MAXIMO:.2f}% · capacidade de pagamento "
          f"em 60 meses R$ {CAPACIDADE_60_MESES:,.2f}")
    print(f"passivo tributário no razão ...............: R$ {float(no_razao):,.2f}")
    print(f"o balanço NÃO enxerga .....................: R$ {DIVIDA_NA_ADESAO - float(no_razao):,.2f}")
    print(f"\npagamentos com cara de PGFN nos últimos 60 dias: {pagos}")
    if not pagos:
        print("   → NENHUM. E o dono confirmou em 26/09/2026: «todos os parcelamentos")
        print("     estão atrasados».")

    print("\n   → DECISÃO DO DONO em 26/09/2026: «sem problemas perder o parcelamento,")
    print("     não tenho dinheiro agora para pagar, quando eu puder eu renegocio».")
    print("     Esta trava NÃO pede pagamento — mede a exposição, que continua existindo.")
    print(f"   → Com a rescisão o desconto de {DESCONTO_MAXIMO:.2f}% sobre "
          f"R$ {DIVIDA_NA_ADESAO:,.2f} cai, a dívida volta cheia e vencida de uma vez, e a")
    print("     empresa fica DOIS ANOS sem poder aderir a nova transação — inclusive de")
    print("     outras dívidas. Esse prazo é o que define quando dá para renegociar.")
    print("   → Esta trava não lança o passivo: o saldo de hoje está no portal Regularize")
    print("     e muda por SELIC. Lançar o valor da adesão como se fosse o de agora seria")
    print("     inventar precisão num número que multiplica o PL por quatro.")

    print(f"\nTOTAL: {len(PARCELAMENTOS)} parcelamento(s) tributário(s) fora do balanço")
    return 1


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
