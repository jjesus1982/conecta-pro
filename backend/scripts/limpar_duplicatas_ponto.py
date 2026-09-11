#!/usr/bin/env python3
"""Apaga a batida DUPLICADA que o import do Tangerino criou (11/09/2026).

Autorização do Jordan em 11/09: "limpa as duplicatas antigas". O estancamento já foi feito no
importador (`solides/tasks.py`); isto limpa o que ficou para trás.

O DEFEITO, medido: 802 batidas duplicadas em 30 dias, e das 419 abaixo de 90 segundos **414 vêm
de origens DIFERENTES** — a pessoa bate no nosso app e a MESMA batida chega de novo pelo import.
Duas pessoas relataram no mesmo dia, sem combinar: "estava registrando jornada duplicada"
(Edilene) e "às vezes duplica a entrada, duplica a saída" (Walcicley).

A RÉGUA É A MESMA DO IMPORTADOR, e isso é deliberado: janela de 10 minutos, ignorando o TIPO
(o Tangerino só conhece `entrada` e `saida`; o app distingue saída e retorno de almoço, e o par
mais comum é justamente o do almoço). Duas réguas para o mesmo fato divergem, e a que diverge
cala — a limpeza tem que apagar exatamente o que o importador deixaria de criar hoje.

QUEM MORRE E QUEM FICA: morre a do **Tangerino**, fica a do **app** — ela tem rosto, geofence,
tipo fino e chegou primeiro; a do Tangerino chega de 6 a 15 horas depois e só confirmaria.

⚠️ PAR DA MESMA ORIGEM NÃO É TOCADO. Dois toques no mesmo aparelho podem ser dedo duplo — ou
dois fatos. São 6 em 30 dias: saem NOMEADOS para alguém olhar, e nenhum script decide por eles.

Reversível: a linha inteira de cada batida apagada vai para
`/app/uploads/duplicatas_backup_*.json` antes do DELETE.

    python3 backend/scripts/limpar_duplicatas_ponto.py
    python3 backend/scripts/limpar_duplicatas_ponto.py --aplicar
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, "/app")

# 20 e não 10: o Tangerino grava na hora CHEIA (18:00:00) e o app na hora real (18:14) — medido
# em 11/09, o maior intervalo entre o mesmo evento nos dois sistemas é de 20 minutos exatos.
# Não colapsa evento distinto: a menor jornada desta casa é o meio período de 4h (08:00–12:00),
# e ninguém entra duas vezes em 20 minutos.
JANELA_MIN = 20
DIAS = 120

#: Pares em que existe uma batida do APP e uma do TANGERINO a menos de `:janela` minutos.
#: `to_jsonb(t.*)` leva a linha inteira para o backup — reverter é reinserir.
_SQL = """
SELECT t.punch_id, t.employee_id::text AS eid, e.nome,
       to_char(t.punch_timestamp,'DD/MM/YYYY HH24:MI:SS') AS quando_tangerino,
       t.punch_type AS tipo_tangerino,
       to_char(a.punch_timestamp,'HH24:MI:SS') AS quando_app,
       a.punch_type AS tipo_app, a.device_type AS origem_app,
       to_jsonb(t.*) AS linha
  FROM gp_clock_punches t
  JOIN employees e ON e.id = t.employee_id
  JOIN LATERAL (
        SELECT x.punch_timestamp, x.punch_type, x.device_type
          FROM gp_clock_punches x
         WHERE x.employee_id = t.employee_id
           AND x.device_type <> 'tangerino'
           AND x.punch_timestamp BETWEEN t.punch_timestamp - make_interval(mins => :janela)
                                     AND t.punch_timestamp + make_interval(mins => :janela)
         ORDER BY abs(extract(epoch from (x.punch_timestamp - t.punch_timestamp)))
         LIMIT 1) a ON TRUE
 WHERE t.device_type = 'tangerino'
   AND t.punch_timestamp > current_date - make_interval(days => :dias)
 ORDER BY t.punch_timestamp
"""

#: Pares da MESMA origem — relatados, nunca apagados.
_SQL_MESMA = """
WITH par AS (
  SELECT p.employee_id, p.punch_type, p.punch_timestamp, p.device_type,
         lag(p.punch_timestamp) OVER (PARTITION BY p.employee_id, p.punch_type, p.device_type
                                      ORDER BY p.punch_timestamp) ant
    FROM gp_clock_punches p
   WHERE p.punch_timestamp > current_date - make_interval(days => :dias))
SELECT e.nome, to_char(par.punch_timestamp,'DD/MM HH24:MI:SS') AS quando,
       par.punch_type, par.device_type,
       round(extract(epoch from (par.punch_timestamp - par.ant))::numeric) AS segundos
  FROM par JOIN employees e ON e.id = par.employee_id
 WHERE par.ant IS NOT NULL
   AND par.punch_timestamp - par.ant < make_interval(mins => :janela)
 ORDER BY par.punch_timestamp DESC
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    aplicar = "--aplicar" in sys.argv
    async with async_session_factory() as db:
        pares = (await db.execute(text(_SQL),
                                  {"janela": JANELA_MIN, "dias": DIAS})).mappings().all()
        mesma = (await db.execute(text(_SQL_MESMA),
                                  {"janela": JANELA_MIN, "dias": DIAS})).mappings().all()

        por_pessoa: dict[str, int] = {}
        for r in pares:
            por_pessoa[r["nome"]] = por_pessoa.get(r["nome"], 0) + 1
        for nome, n in sorted(por_pessoa.items(), key=lambda x: -x[1]):
            print(f"  {n:>3} duplicata(s) do Tangerino: {nome}")
        for r in mesma:
            print(f"  ⚠️ MESMA ORIGEM (não toco): {r['nome'][:28]:30} {r['quando']} "
                  f"{r['punch_type']:14} {r['device_type']:12} {int(r['segundos'])}s depois da anterior")

        if not aplicar:
            print(f"\nENSAIO: {len(pares)} batida(s) do Tangerino seriam apagadas · "
                  f"{len(mesma)} par(es) da mesma origem ficam para alguém olhar. Rode com --aplicar.")
            return 0

        backup = [dict(r["linha"]) for r in pares]
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("/app/uploads", exist_ok=True)
        caminho = f"/app/uploads/duplicatas_backup_{carimbo}.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=1, default=str)
        await db.execute(text("DELETE FROM gp_clock_punches WHERE punch_id = ANY(:ids)"),
                         {"ids": [r["punch_id"] for r in pares]})
        await db.execute(text(
            "INSERT INTO gp_audit_logs (id, timestamp, action, entity, entity_id, description, "
            " source_module, actor_user_id, actor_user_name, actor_user_role, actor_user_module, "
            " extra_data) VALUES (CAST(:i AS uuid), (now() AT TIME ZONE 'America/Manaus'), "
            " 'ponto.duplicatas_apagadas', 'gp_clock_punches', 'lote', :d, "
            " 'people_management.ponto', 'jordan', 'Jordan Jesus (autorização em 11/09/2026)', "
            " 'dono', 'ponto', CAST(:x AS jsonb))"),
            {"i": str(uuid.uuid4()),
             "d": f"{len(pares)} batidas do Tangerino apagadas por duplicarem batida do app "
                  f"(janela de {JANELA_MIN} min); backup em {caminho}",
             "x": json.dumps({"apagadas": len(pares), "backup": caminho,
                              "mesma_origem_intocadas": len(mesma)}, ensure_ascii=False)})
        await db.commit()
        print(f"\nAPLICADO: {len(pares)} apagadas · {len(mesma)} da mesma origem intocadas")
        print(f"reversão guardada em {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
