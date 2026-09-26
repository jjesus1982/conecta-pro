#!/usr/bin/env python3
"""O que está contratado foi faturado no mês? — e o que foi faturado tem contrato?

## A regra que isto afirma

Receita recorrente só é previsível se, todo mês, o contrato vira nota. Um contrato vigente
sem NFS-e na competência é dinheiro que a empresa trabalhou e não cobrou. Uma nota sem
contrato vigente é cobrança que ninguém consegue justificar se o cliente perguntar.

A comparação **respeita a vigência**: contrato conta no mês em que `start_date` já começou e
`end_date` ainda não passou. Sem isso a régua acusa o certo — em 25/09/2026, comparar os
últimos três meses contra a lista de contratos ATIVOS HOJE fez o Green Hills aparecer como
«R$ 21.600/mês não faturados», quando na verdade o contrato de R$ 22.100 começou em 01/09 e
o de R$ 500 que rodou até agosto foi cobrado certinho, todos os meses.

## O que ele mede, por competência fechada

 · contrato vigente **sem nota** — trabalho feito e não cobrado;
 · nota **acima** do contratado — pode ser serviço extra legítimo, pode ser duplicata
   (para esta, ver [checar_nota_duplicada.py]);
 · nota **abaixo** do contratado — cobrança parcial;
 · nota **sem contrato vigente** — cobrança sem lastro contratual.

O mês CORRENTE fica de fora: faturamento acontece no fim do mês, e acusar dia 10 que
«não faturou» é alarme que ensina a ignorar o painel.

## O que ele NÃO faz

Não emite nota, não corrige contrato. Serviço extra, reajuste e parcela combinada por fora
existem e são legítimos — a trava mostra a diferença para alguém decidir.

Linha canônica: `TOTAL: <n> divergência(s) entre contrato e faturamento`.
"""

from __future__ import annotations

import asyncio
import re
import sys
import unicodedata
from datetime import date

#: Quantas competências fechadas olhar para trás.
MESES = 3
#: Diferença abaixo disto é arredondamento de contrato, não achado.
PISO = 100.0


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\b(CONDOMINIO|CONDOMINIOS|RESIDENCIAL|EDIFICIO|DO|DA|DE|DOS|DAS|LTDA)\b", " ", s)
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()


def _competencias(n: int) -> list[str]:
    hoje = date.today()
    ano, mes = hoje.year, hoje.month
    saida = []
    for _ in range(n):
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
        saida.append(f"{ano:04d}-{mes:02d}")
    return list(reversed(saida))


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    achados = 0
    async with async_session_factory() as db:
        for comp in _competencias(MESES):
            ini = date.fromisoformat(f"{comp}-01")
            fim = date(ini.year + (ini.month // 12), (ini.month % 12) + 1, 1)
            fim = date.fromordinal(fim.toordinal() - 1)

            vigentes = (await db.execute(text("""
                SELECT coalesce(cl.name, cl.trading_name, '(sem nome)') cliente,
                       regexp_replace(coalesce(cl.document_number,''), '[^0-9]', '', 'g') doc,
                       round(sum(coalesce(c.monthly_value, 0)), 2) mes,
                       string_agg(c.contract_number, ', ') contratos
                  FROM contracts c LEFT JOIN clients cl ON cl.id = c.client_id
                 WHERE c.start_date <= :fim
                   AND (c.end_date IS NULL OR c.end_date >= :ini)
                   AND lower(c.status::text) NOT IN ('draft','rascunho','cancelled','cancelado')
                   AND coalesce(c.monthly_value, 0) > 0
                 GROUP BY 1, 2"""), {"ini": ini, "fim": fim})).all()

            notas = (await db.execute(text("""
                SELECT regexp_replace(coalesce(tomador_cnpj,''), '[^0-9]', '', 'g') doc,
                       coalesce(tomador_nome,'') nome, round(sum(valor_servicos), 2) v
                  FROM nfse_emitidas_nacional
                 WHERE competencia = :c AND coalesce(cancelada, FALSE) = FALSE
                   AND coalesce(ambiente,'') <> 'homologacao'
                 GROUP BY 1, 2"""), {"c": comp})).all()

            por_doc: dict[str, float] = {}
            por_nome: dict[str, float] = {}
            for d, n, v in notas:
                if d:
                    por_doc[d] = por_doc.get(d, 0.0) + float(v)
                por_nome[_norm(n)] = por_nome.get(_norm(n), 0.0) + float(v)

            linhas: list[str] = []
            docs_contrato = {d for _c, d, _m, _n in vigentes if d}
            nomes_contrato = {_norm(c) for c, _d, _m, _n in vigentes}

            for cliente, doc, mes, contratos in sorted(vigentes, key=lambda x: -float(x[2])):
                m = float(mes)
                f = por_doc.get(doc) if doc and doc in por_doc else por_nome.get(_norm(cliente))
                if f is None:
                    linhas.append(f"   {cliente[:34]:<34} contrato R$ {m:>10,.2f}  SEM NOTA "
                                  f"({contratos})")
                    continue
                d = f - m
                if abs(d) < PISO:
                    continue
                lado = "faturou a MAIS" if d > 0 else "faturou a MENOS"
                linhas.append(f"   {cliente[:34]:<34} contrato R$ {m:>10,.2f}  "
                              f"nota R$ {f:>10,.2f}  dif R$ {d:>10,.2f}  ← {lado}")

            for doc, nome, v in sorted(notas, key=lambda x: -float(x[2])):
                if (doc and doc in docs_contrato) or _norm(nome) in nomes_contrato:
                    continue
                if float(v) < PISO:
                    continue
                linhas.append(f"   {nome[:34]:<34} {'':>21}  nota R$ {float(v):>10,.2f}  "
                              "← SEM CONTRATO VIGENTE")

            if linhas:
                print(f"\n═══ {comp} ═══")
                for x in linhas:
                    print(x)
                achados += len(linhas)
            else:
                print(f"\n═══ {comp} ═══  contrato e faturamento batem")

    print(f"\nTOTAL: {achados} divergência(s) entre contrato e faturamento")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
