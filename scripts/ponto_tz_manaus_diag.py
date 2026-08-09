"""Diagnóstico do deslocamento de fuso das batidas do Tangerino — SÓ LÊ, não altera nada.

O Tangerino codifica o epoch da batida em horário de BRASÍLIA (UTC-3), não em UTC. Quem bate
08:00 em Manaus vira epoch de 11:00 UTC; convertendo no container (America/Manaus, UTC-4)
saía 07:00 — uma hora atrasada em relação ao relógio que vale para nós.

A entrada já foi corrigida (`solides/tasks.py`). Este script mede o que a correção do
HISTÓRICO atingiria, para o Jordan decidir com número na mão antes de qualquer UPDATE.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, text

SQL_ESCOPO = """
SELECT count(*) AS tot,
       min(punch_timestamp)::date AS ini,
       max(punch_timestamp)::date AS fim
FROM gp_clock_punches WHERE device_type = 'tangerino'
"""

SQL_OUTRAS = """
SELECT coalesce(device_type,'(sem origem)') AS origem, count(*) AS n
FROM gp_clock_punches WHERE coalesce(device_type,'') <> 'tangerino'
GROUP BY 1 ORDER BY 2 DESC
"""

#: janela do adicional noturno (CCT): 22:00–05:00
SQL_NOTURNO = """
SELECT count(*) FROM gp_clock_punches
WHERE device_type = 'tangerino'
  AND (extract(hour FROM {expr}) >= 22 OR extract(hour FROM {expr}) < 5)
"""


def main() -> None:
    db = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "")).connect()

    e = db.execute(text(SQL_ESCOPO)).mappings().first()
    print(f"  escopo: {e['tot']} batidas 'tangerino', de {e['ini']} a {e['fim']}")
    print("  fora do escopo (não seriam tocadas):")
    for r in db.execute(text(SQL_OUTRAS)).all():
        print(f"    {r[0]:<18} {r[1]}")

    print()
    print("  impacto na janela do adicional noturno (22:00–05:00):")
    for lbl, expr in (("hoje       ", "punch_timestamp"),
                      ("após +1h   ", "punch_timestamp + interval '1 hour'")):
        n = db.execute(text(SQL_NOTURNO.format(expr=expr))).scalar()
        print(f"    {lbl} {n} batidas caem na janela")

    print()
    print("  competências afetadas (a folha de cada uma teria que ser reconferida):")
    for r in db.execute(text(
        "SELECT to_char(punch_timestamp,'MM/YYYY') c, count(*) n FROM gp_clock_punches "
        "WHERE device_type='tangerino' GROUP BY 1 ORDER BY min(punch_timestamp) DESC")).all():
        print(f"    {r[0]}  {r[1]:>5} batidas")

    print()
    print("  UPDATE proposto (NÃO executado por este script):")
    print("    UPDATE gp_clock_punches SET punch_timestamp = punch_timestamp + interval '1 hour'")
    print("    WHERE device_type = 'tangerino';")
    print()
    print("  Reversível com interval '-1 hour' na mesma cláusula, desde que rodado uma única vez —")
    print("  por isso o WHERE é por device_type e não por data: rodar duas vezes desloca 2h.")


if __name__ == "__main__":
    main()
