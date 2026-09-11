#!/usr/bin/env python3
"""Apaga a batida de ponto de quem está AFASTADO — só a que nenhuma pessoa fez (11/09/2026).

Autorização do Jordan em 11/09: "apaga essas batidas da Cintia e do Aryelton".

O QUE SE DESCOBRIU. A CINTIA está afastada por acidente de trajeto desde 21/05 (CAT S-2210 no
INSS, `sst_afastamentos` ativo, sem retorno) e mesmo assim tem 132 batidas até 10/09. O
ARYELTON, com suspensão contratual desde 02/02, tem 124. O padrão das duas denuncia a origem:
`06:00–18:00` cravado, todo dia, e no caso dele também `09:00 / 15:00 / 16:00 / 21:00` — horas
exatas, **sem facial, sem geofence, sem confiança de reconhecimento**. Ninguém bate na hora
cheia todos os dias: é jornada PREVISTA preenchida por sistema que nunca soube do afastamento.
Entrava no nosso ponto como trabalho feito e alimentava espelho, horas e folha.

🔴 A TRAVA QUE IMPORTA: este script **recusa apagar batida com marca de gente** — `facial_match`
verdadeiro ou `dentro_geofence` preenchido significam que alguém esteve lá, com rosto e
localização. Essas saem NOMEADAS e ficam. Apagar registro de trabalho que aconteceu é o erro
mais caro possível em ponto: vira palavra contra palavra numa reclamatória, e a palavra que
falta é a do trabalhador.

Reversível: a linha inteira vai para `/app/uploads/batidas_afastado_backup_*.json`.

    python3 backend/scripts/apagar_batidas_de_afastado.py
    python3 backend/scripts/apagar_batidas_de_afastado.py --aplicar
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, "/app")

_SQL = """
SELECT p.punch_id, a.employee_nome AS nome, a.tipo, a.data_inicio::text AS afastado_desde,
       to_char(p.punch_timestamp,'DD/MM/YYYY HH24:MI:SS') AS quando,
       p.device_type, p.facial_match, p.dentro_geofence, p.facial_confidence,
       to_jsonb(p.*) AS linha
  FROM sst_afastamentos a
  JOIN gp_clock_punches p ON p.employee_id::text = a.employee_id::text
   AND p.punch_timestamp > a.data_inicio + interval '1 day'
 WHERE lower(coalesce(a.status,'')) = 'ativo' AND a.data_retorno IS NULL
 ORDER BY a.employee_nome, p.punch_timestamp
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    aplicar = "--aplicar" in sys.argv
    async with async_session_factory() as db:
        linhas = (await db.execute(text(_SQL))).mappings().all()
        if not linhas:
            print("nenhuma batida de afastado — nada a apagar")
            return 0

        de_gente = [r for r in linhas
                    if r["facial_match"] is True or r["dentro_geofence"] is not None
                    or (r["facial_confidence"] or 0) > 0]
        de_maquina = [r for r in linhas if r not in de_gente]

        por_pessoa: dict[str, int] = {}
        for r in de_maquina:
            por_pessoa[r["nome"]] = por_pessoa.get(r["nome"], 0) + 1
        for nome, n in sorted(por_pessoa.items(), key=lambda x: -x[1]):
            amostra = next(r for r in de_maquina if r["nome"] == nome)
            print(f"  {n:>3} batida(s) sem marca de gente: {nome} "
                  f"(afastado por {amostra['tipo']} desde {amostra['afastado_desde']})")
        for r in de_gente:
            print(f"  ⚠️ FICA (tem marca de gente): {r['nome']} {r['quando']} {r['device_type']} "
                  f"facial={r['facial_match']} geofence={r['dentro_geofence']} — alguém esteve lá")

        if not aplicar:
            print(f"\nENSAIO: {len(de_maquina)} seriam apagadas · {len(de_gente)} ficariam. "
                  "Rode com --aplicar.")
            return 0

        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("/app/uploads", exist_ok=True)
        caminho = f"/app/uploads/batidas_afastado_backup_{carimbo}.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump([dict(r["linha"]) for r in de_maquina], f, ensure_ascii=False,
                      indent=1, default=str)
        await db.execute(text("DELETE FROM gp_clock_punches WHERE punch_id = ANY(:ids)"),
                         {"ids": [r["punch_id"] for r in de_maquina]})
        await db.execute(text(
            "INSERT INTO gp_audit_logs (id, timestamp, action, entity, entity_id, description, "
            " source_module, actor_user_id, actor_user_name, actor_user_role, actor_user_module, "
            " extra_data) VALUES (CAST(:i AS uuid), (now() AT TIME ZONE 'America/Manaus'), "
            " 'ponto.batidas_de_afastado_apagadas', 'gp_clock_punches', 'lote', :d, "
            " 'people_management.ponto', 'jordan', 'Jordan Jesus (autorização em 11/09/2026)', "
            " 'dono', 'ponto', CAST(:x AS jsonb))"),
            {"i": str(uuid.uuid4()),
             "d": f"{len(de_maquina)} batidas apagadas de pessoas com afastamento ativo "
                  f"(nenhuma com marca de gente); backup em {caminho}",
             "x": json.dumps({"apagadas": len(de_maquina), "mantidas": len(de_gente),
                              "por_pessoa": por_pessoa, "backup": caminho}, ensure_ascii=False)})
        await db.commit()
        print(f"\nAPLICADO: {len(de_maquina)} apagadas · {len(de_gente)} mantidas por terem marca de gente")
        print(f"reversão guardada em {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
