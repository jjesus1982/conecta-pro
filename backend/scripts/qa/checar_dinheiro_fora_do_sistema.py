#!/usr/bin/env python3
"""Contrato ativo cujo dinheiro não aparece em conta nenhuma que o sistema conheça.

## A regra que isto afirma

Contrato vigente com valor mensal gera duas pegadas: uma NOTA e um RECEBIMENTO. Se nenhuma
das duas aparece, uma de três coisas é verdade, e todas são decisão:

 1. o cliente não está pagando — e ninguém cobrou;
 2. o serviço não está sendo prestado — e o contrato devia estar encerrado;
 3. **o dinheiro está entrando numa conta que o sistema não conhece.**

A terceira é a que ninguém procura, e foi o caso medido em 26/09/2026.

## O caso que fez esta trava nascer

O HAWK EYE é cliente desde agosto de 2025 — contrato ativo de R$ 4.000/mês. Em todo o
extrato de 2026 há **um único recebimento dele: R$ 1.000 em 13/08**. E **nenhuma NFS-e foi
emitida para ele, nunca**.

O dono explicou: o cliente pagava na **conta pessoa física dele, no Itaú**, e há uns quatro
meses passou a pagar na conta PJ da Eletrônica. O Itaú **não é uma das contas cadastradas**
— `bank_accounts` tem Inter (Eletrônica), Cora e Asaas (Patrimonial). Nada que passou por
lá existe no razão.

Treze meses de prestação, receita recebida fora do sistema, e nenhuma nota. Do ponto de
vista dos livros, isso é receita omitida; e dinheiro de cliente em conta pessoal é confusão
patrimonial. Nenhum relatório acusava, porque todo relatório lê as contas que conhece.

## O que ele NÃO faz

Não emite nota, não cobra, não encerra contrato. Faturar 13 meses para trás tem consequência
tributária (ISS complementar do período, com acréscimos) e é decisão de dono com contador.
A trava mede o buraco.

Linha canônica: `TOTAL: <n> contrato(s) com dinheiro fora do sistema`.
"""

from __future__ import annotations

import asyncio
import re
import sys
import unicodedata
from datetime import date

#: Quanto do contratado precisa aparecer, no período, para a pegada ser considerada normal.
#: Abaixo disto, ou o cliente não pagou ou o dinheiro entrou noutro lugar.
FRACAO_ESPERADA = 0.5
#: Quantos meses fechados olhar.
MESES = 3


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(
        r"\b(CONDOMINIO|CONDOMINIOS|RESIDENCIAL|EDIFICIO|DO|DA|DE|DOS|DAS|LTDA|SA|ME|EIRELI)\b",
        " ", s,
    )
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    hoje = date.today()
    ini = date(hoje.year, hoje.month, 1)
    for _ in range(MESES):
        ini = date(ini.year - 1, 12, 1) if ini.month == 1 else date(ini.year, ini.month - 1, 1)
    fim = date(hoje.year, hoje.month, 1)

    async with async_session_factory() as db:
        contas = (await db.execute(text(
            "SELECT coalesce(bank_name, name, '(sem nome)') FROM bank_accounts"
        ))).scalars().all()

        contratos = (await db.execute(text("""
            SELECT coalesce(cl.name, cl.trading_name, '(sem nome)') cliente,
                   regexp_replace(coalesce(cl.document_number,''), '[^0-9]', '', 'g') doc,
                   round(sum(coalesce(c.monthly_value, 0)), 2) mes,
                   string_agg(DISTINCT c.contract_number, ', ') contratos,
                   min(c.start_date) desde
              FROM contracts c JOIN clients cl ON cl.id = c.client_id
             WHERE c.start_date < :fim
               AND (c.end_date IS NULL OR c.end_date >= :ini)
               AND lower(c.status::text) NOT IN ('draft','rascunho','cancelled','cancelado')
               AND coalesce(c.monthly_value, 0) > 0
             GROUP BY 1, 2"""), {"ini": ini, "fim": fim})).all()

        recebimentos = (await db.execute(text("""
            SELECT regexp_replace(coalesce(counterparty_document,''), '[^0-9]', '', 'g') doc,
                   coalesce(counterparty_name,'') nome, round(sum(amount), 2) v
              FROM bank_transactions
             WHERE amount > 0 AND transaction_date >= :ini AND transaction_date < :fim
             GROUP BY 1, 2"""), {"ini": ini, "fim": fim})).all()

        notas = (await db.execute(text("""
            SELECT regexp_replace(coalesce(tomador_cnpj,''), '[^0-9]', '', 'g') doc,
                   coalesce(tomador_nome,'') nome, count(*) q
              FROM nfse_emitidas_nacional
             WHERE coalesce(cancelada, FALSE) = FALSE AND coalesce(ambiente,'') <> 'homologacao'
             GROUP BY 1, 2"""))).all()

    rec_doc: dict[str, float] = {}
    rec_nome: dict[str, float] = {}
    for d, n, v in recebimentos:
        if d:
            rec_doc[d] = rec_doc.get(d, 0.0) + float(v)
        if _norm(n):
            rec_nome[_norm(n)] = rec_nome.get(_norm(n), 0.0) + float(v)
    docs_nota = {d for d, _n, _q in notas if d}
    nomes_nota = {_norm(n) for _d, n, _q in notas if _norm(n)}

    print(f"contas bancárias que o sistema conhece: {len(contas)} — {', '.join(contas)}")
    print(f"janela: {ini} a {fim} ({MESES} competência(s) fechada(s))\n")

    achados = []
    for cliente, doc, mes, nums, desde in contratos:
        esperado = float(mes) * MESES
        # Documento primeiro; nome só quando não há documento — casar por prefixo de nome
        # produz falso positivo em série (vários condomínios com o mesmo começo).
        recebido = rec_doc.get(doc) if doc else rec_nome.get(_norm(cliente))
        recebido = float(recebido or 0)
        tem_nota = (doc and doc in docs_nota) or (_norm(cliente) in nomes_nota)
        if recebido >= esperado * FRACAO_ESPERADA:
            continue
        achados.append((cliente, float(mes), esperado, recebido, tem_nota, nums, desde))

    if achados:
        print(f"CONTRATO ATIVO SEM O DINHEIRO CORRESPONDENTE — {len(achados)}:")
        for cliente, mes, esperado, recebido, tem_nota, nums, desde in sorted(
            achados, key=lambda x: -(x[2] - x[3])
        ):
            print(f"   {cliente[:34]:<34} contrato R$ {mes:>9,.2f}/mês  desde {desde}")
            print(f"      esperado no período R$ {esperado:>11,.2f} · "
                  f"apareceu R$ {recebido:>11,.2f} · "
                  f"nota emitida alguma vez: {'sim' if tem_nota else 'NUNCA'}   ({nums})")
        print()
        print("   → Três leituras possíveis, e as três são decisão: o cliente não paga e")
        print("     ninguém cobrou; o serviço parou e o contrato devia estar encerrado; ou")
        print("     o dinheiro entra numa conta que o sistema não conhece. A terceira é a")
        print("     que ninguém procura — e foi o caso do HAWK EYE, pago na conta pessoal")
        print("     do dono por 13 meses, sem nota nenhuma.")

    print(f"\nTOTAL: {len(achados)} contrato(s) com dinheiro fora do sistema")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
