#!/usr/bin/env python3
"""Os quatro casos "tortos" da escala, resolvidos com o que o Jordan informou (11/09/2026).

O `test_oraculo_hora_da_escala` separa o desvio de UMA HORA LIMPA (corrigível por régua) do
desvio torto, que ele relata e não corrige — porque ali não é hora errada na escala, é
combinação de trabalho, e isso ninguém deriva de batida. O Jordan informou as quatro:

  MAURICIO ALVES CHAGAS   mudou de posto e de escala: agora Green Hills, NOTURNO.
  DANIEL VIDAL LARROQUE   mesmo condomínio, função nova: agente de portaria RONDISTA NOTURNO.
  PAULO DA SILVA LAMEGO   bate 09:00 e está certo — é o sistema que está errado.
  EDIWILSON CORREA MARQUES agora entra 07:00 e sai 19:00.

Cada hora abaixo foi conferida contra as batidas dos últimos 16 dias antes de ser escrita.

⚠️ GREEN HILLS NÃO TINHA POSTO. Existe como CLIENTE (contrato CTR-2026-00019, R$ 22.100/mês,
`draft`, início 01/09) e como cliente do GED, mas sem `posts` — então não havia para onde
alocar o Mauricio, nem escala, nem presença, nem kit com gente dentro. O posto é criado aqui,
SEM coordenada: a geofence fica desligada até alguém medir o ponto no local. Chutar latitude
reprovaria batida de quem está no lugar certo.

    python3 backend/scripts/corrigir_quatro_escalas_20260911.py            # ensaio
    python3 backend/scripts/corrigir_quatro_escalas_20260911.py --aplicar
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, "/app")

CLIENTE_GREEN = "c0750f70-7e60-4898-9ed2-d303e361c41e"
GED_GREEN = "b4a13504-cffc-4505-8e91-e1bebed493ed"
ENDERECO_GREEN = "Rua Marques de Suassuna, SN - Parque das Laranjeiras"

#: Paridade ÍMPAR para o Daniel: das quatro entradas noturnas dele em setembro, três caem em
#: dia ímpar (03, 05, 09) — e é a paridade que o Adeilson e o Jonhata já cobrem no mesmo posto.
#: É inferência, não fato do dono: se estiver errada, são dois comandos para trocar, e o
#: oráculo da hora acusa em uma semana.
DIAS_DANIEL = "impar"


async def _rodar(aplicar: bool) -> dict:
    from sqlalchemy import text

    from core.database import async_session_factory

    rel: dict = {"passos": [], "aplicar": aplicar}
    backup: dict = {}

    async with async_session_factory() as db:
        async def ver(nome: str) -> list[dict]:
            r = (await db.execute(text(
                "SELECT sh.id::text id, sh.shift_date::text data, "
                "       to_char(sh.planned_start_time,'HH24:MI') ini, "
                "       to_char(sh.planned_end_time,'HH24:MI') fim, sh.planned_hours h, "
                "       sh.is_night_shift noite, sh.post_id::text posto, sh.scale_id::text escala "
                "  FROM shifts sh JOIN employees e ON e.id=sh.employee_id "
                " WHERE e.nome=:n AND sh.shift_date >= current_date AND sh.is_active"),
                {"n": nome})).mappings().all()
            return [dict(x) for x in r]

        for nome in ("MAURICIO ALVES CHAGAS", "DANIEL VIDAL LARROQUE",
                     "PAULO DA SILVA LAMEGO", "EDIWILSON CORREA MARQUES"):
            backup[nome] = await ver(nome)

        # ── 1. POSTO do Green Hills ─────────────────────────────────────────────────────
        posto_green = (await db.execute(text(
            "SELECT id::text FROM posts WHERE name = 'Condomínio Green Hills'"))).scalar()
        if not posto_green:
            posto_green = str(uuid.uuid4())
            rel["passos"].append(f"CRIA posto 'Condomínio Green Hills' ({posto_green[:8]}) "
                                 f"ligado ao cliente e ao GED, sem geofence")
            if aplicar:
                await db.execute(text(
                    "INSERT INTO posts (id, code, name, post_type, status, shift_type, "
                    "  required_headcount, client_id, ged_client_id, address, is_active, "
                    "  created_at, updated_at, notes) "
                    "VALUES (CAST(:id AS uuid), :code, :name, 'portaria', 'active', '12x36', 1, "
                    "  CAST(:cli AS uuid), CAST(:ged AS uuid), :end, true, now(), now(), :obs)"),
                    {"id": posto_green, "code": "GREENHILLS", "name": "Condomínio Green Hills",
                     "cli": CLIENTE_GREEN, "ged": GED_GREEN, "end": ENDERECO_GREEN,
                     "obs": "Criado em 11/09/2026: o cliente existia (contrato CTR-2026-00019) e o "
                            "posto não, então o Mauricio trabalhava aqui sem estar alocado em lugar "
                            "nenhum. SEM coordenada de geofence — medir no local antes de ligar."})
        else:
            rel["passos"].append(f"posto Green Hills já existe ({posto_green[:8]})")

        # ── 2. MAURICIO: Green Hills, noturno 19:00–07:00 ───────────────────────────────
        emp_m = (await db.execute(text(
            "SELECT id::text FROM employees WHERE nome='MAURICIO ALVES CHAGAS'"))).scalar()
        escala_green = (await db.execute(text(
            "SELECT id::text FROM scales WHERE post_id = CAST(:p AS uuid) AND month=:m AND year=:a"),
            {"p": posto_green, "m": 9, "a": 2026})).scalar()
        if not escala_green:
            escala_green = str(uuid.uuid4())
            rel["passos"].append(f"CRIA escala 09/2026 do Green Hills ({escala_green[:8]})")
            if aplicar:
                await db.execute(text(
                    "INSERT INTO scales (id, post_id, scale_type, status, month, year, name, "
                    "  start_date, end_date, total_shifts, filled_shifts, total_hours, "
                    "  overtime_hours, is_active, created_at, updated_at, notes) "
                    "VALUES (CAST(:id AS uuid), CAST(:p AS uuid), '12x36', 'published', 9, 2026, "
                    "  'Escala 09/2026 — Green Hills', DATE '2026-09-01', DATE '2026-09-30', 0,0,0,0, "
                    "  true, now(), now(), 'Criada junto com o posto em 11/09/2026.')"),
                    {"id": escala_green, "p": posto_green})
        rel["passos"].append("MAURICIO: alocação Mirante → Green Hills; turnos futuros "
                             "07:00–19:00 → 19:00–07:00 (noturno, 12h)")
        if aplicar:
            await db.execute(text(
                "UPDATE allocations SET end_date = current_date - 1, status='finished', updated_at=now() "
                " WHERE employee_id = CAST(:e AS uuid) AND status='active' AND is_active"),
                {"e": emp_m})
            await db.execute(text(
                "INSERT INTO allocations (id, employee_id, post_id, start_date, status, is_active, "
                "  created_at, updated_at) VALUES (gen_random_uuid(), CAST(:e AS uuid), "
                "  CAST(:p AS uuid), current_date, 'active', true, now(), now())"),
                {"e": emp_m, "p": posto_green})
            await db.execute(text(
                "UPDATE shifts SET post_id = CAST(:p AS uuid), scale_id = CAST(:s AS uuid), "
                "  planned_start_time = TIME '19:00', planned_end_time = TIME '07:00', "
                "  is_night_shift = true, updated_at = now() "
                " WHERE employee_id = CAST(:e AS uuid) AND shift_date >= current_date AND is_active"),
                {"e": emp_m, "p": posto_green, "s": escala_green})

        # ── 3. DANIEL: rondista noturno 18:00–06:00, 12x36 ímpar ────────────────────────
        emp_d = (await db.execute(text(
            "SELECT id::text FROM employees WHERE nome='DANIEL VIDAL LARROQUE'"))).scalar()
        base = backup["DANIEL VIDAL LARROQUE"]
        rel["passos"].append(
            f"DANIEL: cargo → AGENTE DE PORTARIA RONDISTA NOTURNO; {len(base)} turno(s) de "
            f"44h diurnos viram 12x36 noturno 18:00–06:00 nos dias ÍMPARES")
        if aplicar and base:
            await db.execute(text(
                "UPDATE employees SET cargo = 'AGENTE DE PORTARIA RONDISTA NOTURNO', updated_at=now() "
                " WHERE id = CAST(:e AS uuid)"), {"e": emp_d})
            # desliga os turnos do padrão antigo e recria pela paridade
            await db.execute(text(
                "UPDATE shifts SET is_active = false, status='cancelled', updated_at=now() "
                " WHERE employee_id = CAST(:e AS uuid) AND shift_date >= current_date AND is_active"),
                {"e": emp_d})
            posto_d, escala_d = base[0]["posto"], base[0]["escala"]
            await db.execute(text(
                "INSERT INTO shifts (id, scale_id, post_id, employee_id, status, shift_date, "
                "  planned_start_time, planned_end_time, planned_break_minutes, planned_hours, "
                "  actual_hours, overtime_hours, night_hours, is_holiday, is_night_shift, "
                "  is_overtime, is_off_day, needs_substitution, base_pay, overtime_pay, "
                "  night_bonus, holiday_bonus, total_pay, is_active, created_at, updated_at, notes) "
                "SELECT gen_random_uuid(), CAST(:sc AS uuid), CAST(:po AS uuid), CAST(:e AS uuid), "
                "  'scheduled', d::date, TIME '18:00', TIME '06:00', 0, 12, 0,0,0, false, true, "
                "  false, false, false, 0,0,0,0,0, true, now(), now(), "
                "  'Rondista noturno 12x36 (informado pelo dono em 11/09/2026)' "
                "  FROM generate_series(current_date, DATE '2026-09-30', interval '1 day') AS d "
                " WHERE (extract(day from d)::int % 2) = 1"),
                {"sc": escala_d, "po": posto_d, "e": emp_d})

        # ── 4. PAULO: 09:00 nos dias úteis, 08:00 no meio período de domingo ────────────
        rel["passos"].append("PAULO: dias úteis 07:00–16:00 → 09:00–18:00; domingo 07:00–11:00 → 08:00–12:00")
        if aplicar:
            await db.execute(text(
                "UPDATE shifts SET planned_start_time = planned_start_time + interval '2 hours', "
                "  planned_end_time = planned_end_time + interval '2 hours', updated_at=now() "
                " WHERE employee_id = (SELECT id FROM employees WHERE nome='PAULO DA SILVA LAMEGO') "
                "   AND shift_date >= current_date AND is_active AND planned_hours >= 8"))
            await db.execute(text(
                "UPDATE shifts SET planned_start_time = planned_start_time + interval '1 hour', "
                "  planned_end_time = planned_end_time + interval '1 hour', updated_at=now() "
                " WHERE employee_id = (SELECT id FROM employees WHERE nome='PAULO DA SILVA LAMEGO') "
                "   AND shift_date >= current_date AND is_active AND planned_hours < 8"))

        # ── 5. EDIWILSON: 10:00–22:00 → 07:00–19:00 ─────────────────────────────────────
        rel["passos"].append("EDIWILSON: 10:00–22:00 → 07:00–19:00 (12h, mesma duração)")
        if aplicar:
            await db.execute(text(
                "UPDATE shifts SET planned_start_time = TIME '07:00', planned_end_time = TIME '19:00', "
                "  updated_at=now() "
                " WHERE employee_id = (SELECT id FROM employees WHERE nome='EDIWILSON CORREA MARQUES') "
                "   AND shift_date >= current_date AND is_active"))

        if aplicar:
            carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("/app/uploads", exist_ok=True)
            caminho = f"/app/uploads/escala_quatro_backup_{carimbo}.json"
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(backup, f, ensure_ascii=False, indent=1)
            rel["backup"] = caminho
            await db.commit()
    return rel


def main() -> int:
    import asyncio

    rel = asyncio.run(_rodar("--aplicar" in sys.argv))
    for p in rel["passos"]:
        print("  " + p)
    print(f"\n{'APLICADO' if rel['aplicar'] else 'ENSAIO'}")
    if rel.get("backup"):
        print(f"reversão guardada em {rel['backup']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
