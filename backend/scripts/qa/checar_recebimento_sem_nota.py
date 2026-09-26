#!/usr/bin/env python3
"""Dinheiro de cliente que entrou na conta e não tem nota nenhuma atrás dele.

## A regra que isto afirma

Todo real que um CLIENTE deposita numa conta nossa é preço de um serviço prestado, e
serviço prestado gera NFS-e. Dinheiro recebido sem nota é receita omitida: o ISS não foi
recolhido, o DRE não conhece a receita, e o cliente tem um pagamento que não consegue
lançar na contabilidade dele.

Este é o **terceiro lado do triângulo**, e o que faltava:

    contrato ←→ nota      [checar_contrato_vs_faturado.py]
    contrato ←→ dinheiro  [checar_dinheiro_fora_do_sistema.py]
    nota     ←→ dinheiro  ← ESTE

Os dois primeiros partem do contrato. Quem não tem contrato cadastrado — ou tem um
contrato que não descreve o que foi cobrado — passa por baixo dos dois. Foi assim que o
HAWK EYE ficou treze meses recebendo sem nota: o dono é que contou, nenhuma trava contou.

## Como compara, e por que ACUMULADO

Nota de setembro é paga em setembro ou em outubro. Comparar mês a mês acusaria todo
cliente todo mês por um atraso de dias. A comparação é do **acumulado da janela**: quanto
esse documento depositou e quanto foi faturado para ele no mesmo período. Assim o
descasamento de calendário se cancela e sobra o buraco de verdade.

Medido em 26/09/2026, janela de 4 competências fechadas:

    HAWK EYE                 recebeu R$ 1.000,00   faturado R$     0,00   NENHUMA NOTA
    PARQUE DOS FRANCESES     recebeu R$ 4.272,00   faturado R$ 1.800,00   dif R$ 2.472,00

O Hawk Eye foi faturado nesta mesma noite (NFS-e 124).

O do Parque dos Franceses é a razão de esta trava existir, e não por achar o que os outros
não achavam: `checar_contrato_vs_faturado.py` JÁ acusava agosto como «SEM NOTA». Quem
descartou o alarme fui eu, lendo-o como defasagem de calendário do faturamento — o
contrato começa em 01/08 e a primeira nota é de setembro, o que parecia explicar tudo.

Não explicava. O título de 08/2026 foi cancelado em 10/08 sob a premissa de que o contrato
só começava em setembro; em 14/08 o dono REVERTEU essa premissa (está escrito em
`backend/scripts/corrigir_inicio_franceses.py`) e ninguém recriou o título. Agosto era
faturável, ficou sem nota, e **o cliente pagou R$ 2.508,00 em 27/08**.

Foi o lado do DINHEIRO que furou a explicação: contra um alarme que se consegue justificar,
um depósito sem nota atrás não se justifica. É para isso que o terceiro lado do triângulo
serve — não para achar mais, mas para não deixar arquivar.

## O que ele NÃO faz

Não emite nota. Emitir sobre o valor recebido é chute quando o recebido não bate com o
contratado: pode ser duas competências juntas, pode ser serviço extra, pode ser
adiantamento. E há entrada que legitimamente não é receita — estorno, empréstimo,
transferência entre os CNPJs do grupo (essas saem daqui pelo filtro). A trava mostra o par.

## O que ele NÃO ENXERGA — e por isso conta a população antes

A comparação só alcança a entrada cujo documento de contraparte está preenchido E casa com
um cliente cadastrado. Na janela de 26/09/2026 isso era 74% do dinheiro que entrou; os
outros 26% ficam fora do alcance e o cabeçalho os imprime, porque «TOTAL: 1» sobre uma
população silenciosamente cortada é pior que nenhuma medida.

Linha canônica: `TOTAL: <n> cliente(s) com dinheiro recebido sem nota`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

#: Quantas competências fechadas somar. Mais curto que isto e o atraso de pagamento vira achado.
MESES = 4
#: Diferença abaixo disto é retenção/tarifa, não buraco. (ISS retido de 2% em R$ 1.800 = R$ 36.)
PISO = 300.0
#: Os nossos. Transferência entre os dois CNPJs não é receita de cliente.
CNPJS_DO_GRUPO = ("35710481000103", "66014833000110")


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    hoje = date.today()
    fim = date(hoje.year, hoje.month, 1)
    ini = fim
    for _ in range(MESES):
        ini = date(ini.year - 1, 12, 1) if ini.month == 1 else date(ini.year, ini.month - 1, 1)

    async with async_session_factory() as db:
        # Entradas por documento de contraparte, só de quem é CLIENTE cadastrado. Sem o
        # vínculo com `clients` entraria empréstimo, estorno e resgate de aplicação.
        recebido = (
            await db.execute(
                text("""
            SELECT regexp_replace(t.counterparty_document, '[^0-9]', '', 'g') doc,
                   max(coalesce(cl.name, t.counterparty_name)) nome,
                   round(sum(t.amount), 2) v, count(*) n,
                   max(t.transaction_date)::date ultimo
              FROM bank_transactions t
              JOIN clients cl
                ON regexp_replace(coalesce(cl.document_number,''), '[^0-9]', '', 'g')
                 = regexp_replace(t.counterparty_document, '[^0-9]', '', 'g')
             WHERE t.amount > 0
               AND t.transaction_date >= :ini AND t.transaction_date < :fim
               AND regexp_replace(t.counterparty_document, '[^0-9]', '', 'g') <> ALL(:grupo)
             GROUP BY 1"""),
                {"ini": ini, "fim": fim, "grupo": list(CNPJS_DO_GRUPO)},
            )
        ).all()

        # A população: quanto do dinheiro que entrou esta régua alcança. Sem isto o TOTAL
        # lá embaixo se lê como «o resto está certo», e o resto nem foi olhado.
        populacao = (
            await db.execute(
                text("""
            WITH e AS (
                SELECT amount, regexp_replace(coalesce(counterparty_document,''), '[^0-9]', '', 'g') doc
                  FROM bank_transactions
                 WHERE amount > 0 AND transaction_date >= :ini AND transaction_date < :fim)
            SELECT CASE
                     WHEN doc = '' THEN 'entrada sem documento de contraparte'
                     WHEN doc = ANY(:grupo) THEN 'transferência entre os nossos CNPJs'
                     WHEN EXISTS (SELECT 1 FROM clients c
                                   WHERE regexp_replace(coalesce(c.document_number,''),
                                         '[^0-9]', '', 'g') = e.doc)
                       THEN 'cliente cadastrado (é o que esta régua compara)'
                     ELSE 'documento preenchido, mas nenhum cliente com ele'
                   END faixa, count(*) n, round(sum(amount), 2) v
              FROM e GROUP BY 1 ORDER BY 3 DESC"""),
                {"ini": ini, "fim": fim, "grupo": list(CNPJS_DO_GRUPO)},
            )
        ).all()

        # Faturado no mesmo período, pela COMPETÊNCIA da nota — que é o mês do serviço, o
        # mesmo eixo do dinheiro. Nota cancelada e nota de homologação não faturam nada.
        comps = []
        c = ini
        while c < fim:
            comps.append(f"{c.year:04d}-{c.month:02d}")
            c = date(c.year + 1, 1, 1) if c.month == 12 else date(c.year, c.month + 1, 1)
        faturado = {
            r[0]: float(r[1])
            for r in (
                await db.execute(
                    text("""
                SELECT regexp_replace(coalesce(tomador_cnpj,''), '[^0-9]', '', 'g') doc,
                       round(sum(valor_servicos), 2)
                  FROM nfse_emitidas_nacional
                 WHERE competencia = ANY(:c) AND coalesce(cancelada, FALSE) = FALSE
                   AND coalesce(ambiente, '') <> 'homologacao'
                 GROUP BY 1"""),
                    {"c": comps},
                )
            ).all()
        }

    print(f"janela: {ini} a {fim} — competências {', '.join(comps)}")
    total_pop = sum(float(r[2]) for r in populacao) or 1.0
    alcanca = sum(float(r[2]) for r in populacao if r[0].startswith("cliente cadastrado"))
    print(f"entrou no período: R$ {total_pop:,.2f} em {sum(r[1] for r in populacao)} crédito(s)")
    for faixa, n, v in populacao:
        print(f"   {faixa:<48} {n:>4}x  R$ {float(v):>12,.2f}  {100 * float(v) / total_pop:>5.1f}%")
    print(f"→ esta régua alcança {100 * alcanca / total_pop:.0f}% do dinheiro. O resto não foi olhado por ela.")
    print(f"clientes que depositaram no período: {len(recebido)}\n")

    achados = []
    for doc, nome, v, n, ultimo in recebido:
        f = faturado.get(doc, 0.0)
        dif = float(v) - f
        if dif < PISO:
            continue
        achados.append((nome, doc, float(v), f, dif, n, ultimo))

    if achados:
        print(f"RECEBEU MAIS DO QUE FOI FATURADO — {len(achados)}:")
        for nome, doc, v, f, dif, n, ultimo in sorted(achados, key=lambda x: -x[4]):
            marca = "  ← NENHUMA NOTA NO PERÍODO" if f == 0 else ""
            t = "CNPJ" if len(doc) == 14 else "CPF " if len(doc) == 11 else "----"
            print(f"   {t} {doc:<15} {(nome or '?')[:30]:<30} recebeu R$ {v:>11,.2f} ({n}x, último {ultimo})")
            print(f"      faturado R$ {f:>11,.2f}   dif R$ {dif:>11,.2f}{marca}")
        print()
        print("   → Dinheiro de cliente sem nota atrás é receita omitida: ISS não recolhido,")
        print("     DRE que não conhece a receita, e um pagamento que o cliente não consegue")
        print("     lançar. Emitir sobre o valor recebido é chute quando ele não bate com o")
        print("     contrato — pode ser duas competências juntas, extra ou adiantamento.")

    print(f"\nTOTAL: {len(achados)} cliente(s) com dinheiro recebido sem nota")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
