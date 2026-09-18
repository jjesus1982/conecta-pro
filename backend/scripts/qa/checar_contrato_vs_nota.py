#!/usr/bin/env python3
"""O que está no CONTRATO é o que foi para a NOTA? — a conferência que ninguém fazia.

Origem: 18/09/2026. O dono explicou por que os números do MIRANTE DAS FLORES não fechavam:
«tiramos a jardinagem, o valor da jardinagem não entra mais». A nota sabia disso desde
agosto (R$ 13.561,50 → R$ 12.061,50). O contrato, o MRR e o contas a receber continuaram com
os R$ 1.500 por mais de um mês, e NADA acusava — o MRR da casa estava inflado e ninguém via.

O contrato é a promessa; a nota é o que se cobrou de verdade. Quando divergem, um dos dois
está errado, e os dois sentidos custam dinheiro:

    faturado A MENOS   nota que não saiu. Serviço prestado e não cobrado.
    faturado A MAIS    nota a mais (erro de emissão) ou contrato desatualizado para baixo.

Na estreia, medido em 08/2026: 7 clientes batendo ao centavo e 4 divergindo, sendo
R$ 39.338,33 de serviço prestado e não faturado.

## A régua

Compara, por CLIENTE, a soma dos contratos recorrentes VIGENTES na competência contra a
soma das notas não canceladas daquela competência.

Vigência é obrigatória, e foi um falso positivo meu que ensinou: o GREEN HILLS tem contrato
de R$ 22.100 que começa em 01/09 e eu o comparei com a nota de agosto — «faltavam»
R$ 21.600 que não faltavam. Contrato que ainda não começou, ou que já terminou, não devia
nota nenhuma naquele mês.

    python3 backend/scripts/qa/checar_contrato_vs_nota.py

Linha canônica: `TOTAL: <n> cliente(s) com contrato e nota divergentes`. Exit 1 quando há achado.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date

#: Caminho absoluto: ruff S607 recusa executável parcial.
DOCKER = "/usr/bin/docker"  # nosec B607

#: Dia do mês a partir do qual a competência ANTERIOR é cobrada. Medido: as notas saem dentro
#: do próprio mês de competência (12 das 13 de agosto), mas uma saiu em setembro. Cobrar no
#: dia 1º acusaria todo mundo que ainda não emitiu — trava que grita no início de todo mês é
#: trava que se ignora. Do dia 11 em diante, quem não emitiu tem o que explicar.
_DIA_DE_COBRAR = 11

#: Diferença que não é achado: centavo de arredondamento na divisão de parcelas.
_TOLERANCIA = 0.01

SQL = """
WITH lim AS (
  SELECT %s::date AS ini, (%s::date + interval '1 month - 1 day')::date AS fim, %s::text AS c
)
SELECT cl.name,
       sum(ct.monthly_value)::numeric AS contratado,
       coalesce((SELECT sum(n.valor_servicos) FROM nfse_emitidas_nacional n
                  WHERE coalesce(n.cancelada, FALSE) = FALSE AND n.competencia = l.c
                    AND regexp_replace(coalesce(n.tomador_cnpj,''), '[^0-9]', '', 'g')
                        = regexp_replace(coalesce(cl.document_number,''), '[^0-9]', '', 'g')), 0)::numeric AS faturado,
       count(*) AS contratos
  FROM clients cl
  JOIN contracts ct ON ct.client_id = cl.id
   AND ct.status = 'active' AND ct.contract_type = 'recurring' AND coalesce(ct.monthly_value, 0) > 0
  CROSS JOIN lim l
 WHERE ct.start_date <= l.fim AND (ct.end_date IS NULL OR ct.end_date >= l.ini)
   -- Cliente sem CNPJ no cadastro não dá para casar com nota nenhuma. Sai da conta e é
   -- relatado à parte: acusar quem não dá para medir é a mesma mentira do verde cego.
   AND regexp_replace(coalesce(cl.document_number,''), '[^0-9]', '', 'g') <> ''
 GROUP BY cl.name, cl.document_number, l.c
 ORDER BY 2 DESC
"""

SQL_SEM_CNPJ = """
SELECT DISTINCT cl.name FROM clients cl
  JOIN contracts ct ON ct.client_id = cl.id AND ct.status = 'active'
   AND ct.contract_type = 'recurring' AND coalesce(ct.monthly_value, 0) > 0
 WHERE regexp_replace(coalesce(cl.document_number,''), '[^0-9]', '', 'g') = ''
 ORDER BY 1
"""


def _competencia_alvo(hoje: date) -> date:
    """O primeiro dia da competência a conferir: a última FECHADA que já deu tempo de faturar."""
    primeiro = hoje.replace(day=1)
    passos = 1 if hoje.day >= _DIA_DE_COBRAR else 2
    for _ in range(passos):
        primeiro = (primeiro - __import__("datetime").timedelta(days=1)).replace(day=1)
    return primeiro


def _psql(sql: str, *args: str) -> list[list[str]]:
    # Os argumentos são datas ISO e a competência que ESTE script gera — nunca entrada de
    # fora. Ainda assim, só dígitos, hífen e o formato de data passam: parâmetro de fora
    # nunca deve chegar aqui sem bind de verdade.
    for a in args:
        if not all(ch.isdigit() or ch == "-" for ch in a):
            raise RuntimeError(f"argumento inesperado para a consulta: {a!r}")
        sql = sql.replace("%s", f"'{a}'", 1)
    r = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
        [
            DOCKER,
            "exec",
            "conecta-pro-postgres",
            "psql",
            "-U",
            "postgres",
            "-d",
            "conecta_pro",
            "-tA",
            "-F",
            "|",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return [ln.split("|") for ln in r.stdout.splitlines() if ln.strip()]


def main() -> int:
    ini = _competencia_alvo(date.today())
    comp = ini.strftime("%Y-%m")
    try:
        linhas = _psql(SQL, ini.isoformat(), ini.isoformat(), comp)
        sem_cnpj = [x[0] for x in _psql(SQL_SEM_CNPJ)]
    except RuntimeError as exc:
        print(f"NÃO VERIFICADO: não deu para consultar o banco — {exc}")
        print("TOTAL: 0 cliente(s) com contrato e nota divergentes")
        return 0

    a_menos: list[tuple] = []
    a_mais: list[tuple] = []
    for nome, contratado, faturado, _n in linhas:
        c, f = float(contratado), float(faturado)
        if abs(f - c) <= _TOLERANCIA:
            continue
        (a_menos if f < c else a_mais).append((nome, c, f))

    for nome, c, f in sorted(a_menos, key=lambda x: x[1] - x[2], reverse=True):
        print(f"  💸 {nome[:38]:<38} contrato R$ {c:>12,.2f} · nota R$ {f:>12,.2f} — NÃO FATURADO R$ {c - f:,.2f}")
    for nome, c, f in sorted(a_mais, key=lambda x: x[2] - x[1], reverse=True):
        print(f"  ⚠️  {nome[:38]:<38} contrato R$ {c:>12,.2f} · nota R$ {f:>12,.2f} — nota A MAIS R$ {f - c:,.2f}")
    if sem_cnpj:
        print(f"  (sem CNPJ no cadastro, não dá para casar: {', '.join(sem_cnpj)})")

    achados = len(a_menos) + len(a_mais)
    perdido = sum(c - f for _, c, f in a_menos)
    print(
        f"competência {comp} · {len(linhas)} cliente(s) com contrato vigente · "
        f"{len(linhas) - achados} batendo ao centavo"
    )
    if perdido:
        print(f"serviço prestado e NÃO faturado: R$ {perdido:,.2f}")
    print(f"TOTAL: {achados} cliente(s) com contrato e nota divergentes")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
