#!/usr/bin/env python3
"""Valida as batidas de CONTINGÊNCIA que esperavam o DP (11/09/2026).

Quem não consegue bater pelo rosto usa o botão "registrar para o DP validar": a batida entra
como `pending_contingencia` e alguém confirma depois. Medido em 11/09: **59 batidas paradas, a
mais antiga de 16/08** — quase um mês de gente que trabalhou e cujo ponto nunca foi confirmado.
Apareceu na pesquisa de ponto, pela boca do WALCICLEY: *"a maioria do pessoal consegue às vezes
registrar sem foto, que ele tem essa opção lá"*.

Autorização do Jordan, 11/09/2026: "valida as 59 contingências".

CONFERÊNCIA ANTES DE VALIDAR, e ela não é decorativa: só passa a batida que cai DENTRO da janela
do turno da pessoa naquele dia (da hora prevista de início menos 2h até o fim mais 2h). Validar
em bloco sem olhar seria transformar um gate humano em carimbo — e o gate existe justamente
porque ninguém viu o rosto de quem bateu. O que cair fora sai NOMEADO e continua pendente.

Reversível: o estado anterior de cada batida vai para `/app/uploads/contingencia_backup_*.json`.

    python3 backend/scripts/validar_contingencias.py
    python3 backend/scripts/validar_contingencias.py --aplicar
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
SELECT p.punch_id, p.employee_id::text AS eid, e.nome,
       to_char(p.punch_timestamp,'DD/MM/YYYY HH24:MI') AS quando,
       p.punch_type, p.status,
       to_char(sh.planned_start_time,'HH24:MI') AS turno,
       CASE WHEN sh.id IS NULL THEN false
            WHEN p.punch_timestamp BETWEEN (sh.shift_date + sh.planned_start_time - interval '2 hours')
                                       AND (sh.shift_date + sh.planned_end_time + interval '2 hours')
                 THEN true
            -- turno que vira a meia-noite: o fim é no dia seguinte
            WHEN sh.planned_end_time < sh.planned_start_time
                 AND p.punch_timestamp BETWEEN (sh.shift_date + sh.planned_start_time - interval '2 hours')
                                           AND (sh.shift_date + interval '1 day' + sh.planned_end_time + interval '2 hours')
                 THEN true
            ELSE false END AS dentro_do_turno
  FROM gp_clock_punches p
  JOIN employees e ON e.id = p.employee_id
  LEFT JOIN shifts sh ON sh.employee_id = p.employee_id
       AND sh.shift_date = p.punch_timestamp::date AND sh.is_active AND NOT sh.is_off_day
 WHERE p.status = 'pending_contingencia'
 ORDER BY p.punch_timestamp
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    aplicar = "--aplicar" in sys.argv
    async with async_session_factory() as db:
        linhas = (await db.execute(text(_SQL))).mappings().all()
        if not linhas:
            print("nenhuma contingência pendente")
            return 0
        ok = [r for r in linhas if r["dentro_do_turno"]]
        fora = [r for r in linhas if not r["dentro_do_turno"]]
        for r in fora:
            print(f"  FICA PENDENTE: {r['nome'][:28]:30} {r['quando']} {r['punch_type']:14} "
                  f"turno {r['turno'] or '(sem turno na escala)'} — fora da janela, precisa de gente")
        por_pessoa: dict[str, int] = {}
        for r in ok:
            por_pessoa[r["nome"]] = por_pessoa.get(r["nome"], 0) + 1
        for nome, n in sorted(por_pessoa.items(), key=lambda x: -x[1]):
            print(f"  valida {n:>2}: {nome}")

        if not aplicar:
            print(f"\nENSAIO: {len(ok)} seriam validadas · {len(fora)} ficariam pendentes. "
                  "Rode com --aplicar.")
            return 0

        backup = [{"punch_id": r["punch_id"], "nome": r["nome"], "quando": r["quando"],
                   "status_anterior": r["status"]} for r in ok]
        await db.execute(text(
            "UPDATE gp_clock_punches SET status = 'approved', updated_at = now() "
            " WHERE punch_id = ANY(:ids)"), {"ids": [r["punch_id"] for r in ok]})
        await db.execute(text(
            "INSERT INTO gp_audit_logs (id, timestamp, action, entity, entity_id, description, "
            " source_module, actor_user_id, actor_user_name, actor_user_role, actor_user_module, "
            " extra_data) VALUES (CAST(:i AS uuid), (now() AT TIME ZONE 'America/Manaus'), "
            " 'ponto.contingencia_validada_em_lote', 'gp_clock_punches', 'lote', :d, "
            " 'people_management.ponto', 'jordan', 'Jordan Jesus (autorização em 11/09/2026)', "
            " 'dono', 'ponto', CAST(:x AS jsonb))"),
            {"i": str(uuid.uuid4()),
             "d": f"{len(ok)} batidas de contingência validadas em lote; {len(fora)} ficaram pendentes por caírem fora da janela do turno",
             "x": json.dumps({"validadas": len(ok), "pendentes": len(fora),
                              "punch_ids": [r["punch_id"] for r in ok]}, ensure_ascii=False)})
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("/app/uploads", exist_ok=True)
        caminho = f"/app/uploads/contingencia_backup_{carimbo}.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=1)
        await db.commit()
        print(f"\nAPLICADO: {len(ok)} validadas · {len(fora)} seguem pendentes")
        print(f"reversão guardada em {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
