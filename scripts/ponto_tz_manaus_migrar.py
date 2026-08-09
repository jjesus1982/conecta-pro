"""Migra as batidas do Tangerino para o horário de Manaus (+1h). RODA UMA VEZ SÓ.

Contexto em `ponto_tz_manaus_diag.py`: o Tangerino codifica o epoch em horário de Brasília
(UTC-3); a conversão no container (Manaus, UTC-4) deixava a batida 1h atrasada. A entrada já
foi corrigida em `solides/tasks.py`; isto acerta o que já estava gravado.

TRAVA CONTRA DUPLA EXECUÇÃO: antes de tocar em qualquer linha, confere um caso conhecido —
CELIANE, que o Jordan confirmou entrar às 08:00. Se o banco já disser 08:00, a migração já
rodou e o script recusa. Rodar duas vezes deslocaria 2h e ninguém perceberia olhando a tela.

Só mexe em `device_type='tangerino'`. As batidas 'web'/'facial'/'manual' nascem da nossa
aplicação com `datetime.now()` num container em America/Manaus — já estão certas.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

#: caso-testemunha: Jordan confirmou em 09/08 que ela entra 08:00 (Manaus)
TESTEMUNHA = ("CELIANE%", 8)

SQL_ENTRADA_MODAL = """
SELECT mode() WITHIN GROUP (ORDER BY extract(hour FROM p)) FROM (
  SELECT min(punch_timestamp) p FROM gp_clock_punches k
  JOIN employees e ON e.id = k.employee_id
  WHERE e.nome LIKE :n AND k.device_type = 'tangerino'
    AND k.punch_timestamp >= '2026-07-01'
  GROUP BY k.punch_timestamp::date) x
"""


def main() -> None:
    db = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "")).connect()
    nome, hora_certa = TESTEMUNHA

    antes = db.execute(text(SQL_ENTRADA_MODAL), {"n": nome}).scalar()
    if antes is None:
        sys.exit(f"ABORTADO: não achei batidas da testemunha {nome} para conferir.")
    antes = int(antes)
    print(f"  testemunha {nome.rstrip('%')}: entrada modal {antes:02d}:00 "
          f"(esperado ANTES da migração: {hora_certa - 1:02d}:00)")

    if antes == hora_certa:
        sys.exit("ABORTADO: a testemunha já está no horário certo — a migração JÁ RODOU. "
                 "Rodar de novo deslocaria mais 1h.")
    if antes != hora_certa - 1:
        sys.exit(f"ABORTADO: testemunha em {antes:02d}:00, esperado {hora_certa - 1:02d}:00. "
                 f"O desvio não é o que este script corrige — investigar antes de mexer.")

    n = db.execute(text(
        "SELECT count(*) FROM gp_clock_punches WHERE device_type = 'tangerino'")).scalar()
    print(f"  migrando {n} batidas 'tangerino' (+1h)...")

    r = db.execute(text(
        "UPDATE gp_clock_punches SET punch_timestamp = punch_timestamp + interval '1 hour', "
        "updated_at = now() WHERE device_type = 'tangerino'"))
    db.commit()
    print(f"  linhas alteradas: {r.rowcount}")

    depois = int(db.execute(text(SQL_ENTRADA_MODAL), {"n": nome}).scalar())
    print(f"  testemunha depois: {depois:02d}:00 (esperado {hora_certa:02d}:00)")
    if depois != hora_certa:
        sys.exit(f"ATENÇÃO: testemunha ficou em {depois:02d}:00. Reverter com "
                 f"interval '-1 hour' e investigar.")
    print("  OK — histórico em horário de Manaus.")


if __name__ == "__main__":
    main()
