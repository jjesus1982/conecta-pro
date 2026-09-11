"""Oráculo — quem está AFASTADO não tem batida de ponto (11/09/2026).

Achado na pesquisa de ponto do José Luís. A CINTIA respondeu que não bate porque está
**afastada pelo INSS há 3 meses** — acidente de trajeto em 21/05, fratura de fêmur e tíbia,
CAT S-2210 já registrada. O afastamento está em `sst_afastamentos` com status `ativo` e sem
data de retorno.

E mesmo assim ela tem **132 batidas entre 03/06 e 10/09**, todas vindas do Tangerino. O padrão
entrega o que são: `06:00–18:00` cravado, dois registros por dia, todo dia. Ninguém bate na
hora exata todos os dias — isso é a jornada PREVISTA sendo preenchida por um sistema que nunca
soube do afastamento. O mesmo vale para o ARYELTON, com suspensão contratual desde 02/02 e 80
batidas desde 03/08.

Por que isso é grave e não cosmético: essas batidas entram no nosso ponto como trabalho feito.
Alimentam espelho, horas e o que a folha lê — para uma pessoa que o INSS está pagando e que
legalmente não está trabalhando. É divergência entre dois sistemas da casa que ninguém cruzava.

A regra afirmada: afastamento ATIVO sem data de retorno não pode ter batida depois do início.
Tolerância de 1 dia no começo (o dia do acidente costuma ter batida de entrada legítima).

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys

_SQL = """
SELECT a.employee_nome AS nome, a.tipo, a.data_inicio::text AS inicio,
       count(p.id) AS batidas,
       max(p.punch_timestamp)::date::text AS ultima,
       string_agg(DISTINCT p.device_type, ',') AS origens
  FROM sst_afastamentos a
  JOIN gp_clock_punches p ON p.employee_id::text = a.employee_id::text
   AND p.punch_timestamp > a.data_inicio + interval '1 day'
 WHERE lower(coalesce(a.status,'')) = 'ativo' AND a.data_retorno IS NULL
 GROUP BY a.employee_nome, a.tipo, a.data_inicio
 ORDER BY count(p.id) DESC
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    gen = get_db()
    db = await gen.__anext__()
    linhas = (await db.execute(text(_SQL))).mappings().all()
    total = (await db.execute(text(
        "SELECT count(*) FROM sst_afastamentos WHERE lower(coalesce(status,''))='ativo' "
        "  AND data_retorno IS NULL"))).scalar() or 0

    for r in linhas:
        print(f"FALHOU: {r['nome']} — afastado por {r['tipo']} desde {r['inicio']} e tem "
              f"{r['batidas']} batida(s) depois disso (última {r['ultima']}, origem "
              f"{r['origens']}). Ou o afastamento acabou e ninguém fechou o registro, ou essas "
              f"batidas não são de trabalho que aconteceu.")
    print(f"afastamentos ativos sem retorno: {total} · com batida posterior: {len(linhas)}")
    if linhas:
        raise AssertionError(
            f"{len(linhas)} pessoa(s) afastadas com batida de ponto depois do afastamento. "
            "Essas batidas entram no espelho e na folha como trabalho feito.")
    print("OK: ninguém afastado tem batida de ponto depois do início do afastamento")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
