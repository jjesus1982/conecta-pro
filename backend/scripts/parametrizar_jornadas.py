#!/usr/bin/env python3
"""Grava a jornada de cada posto em `work_schedules` — horário sai da planilha, entra no sistema.

ATÉ 14/08/2026 O HORÁRIO DE ENTRADA NÃO EXISTIA NO SISTEMA. Vivia numa planilha do Jordan e
na cabeça de quem opera. Por isso o painel só sabia dizer "bateu / não bateu" — nunca
"está atrasado". Quando 42 pessoas apareceram sem bater às 07:24, eu não tinha como separar
quem estava atrasado de quem ainda nem tinha hora de entrar, e chutei "diurno = 06:00" para
todo mundo. Errei em quatro dos sete que apontei.

`work_schedules` já existia, com TODOS os campos certos (`default_entry_time`,
`default_exit_time`, `entry_tolerance_minutes`, `work_days`, `daily_schedule`) e ZERO linhas
— estava no meu próprio inventário de "tabela morta". Não era morta: era a estrutura certa
esperando ser usada. Preencher o que existe é melhor que criar tabela nova.

FONTE. Os horários vêm do Jordan, posto a posto, em 14/08, e batem com o que o histórico do
SÓLIDES (01–10/08, 962 batidas, antes da virada para o Conecta PRO) mostra na prática:

  Ideal Flores · Villa dos Pássaros · Prime Arena · Villa Dei Fiori — mesmo padrão
      AGP/Líder diurno   06:00–18:00      (medido: 05:50 a 06:03)
      AGP/Líder noturno  18:00–06:00      (medido: 17:50 a 18:00)
      ASG/artífice/jard  08:00–17:00      (medido: 08:00 a 08:05)
  Laranjeiras Village
      AGP/Líder diurno   07:00–19:00      (medido: 06:59)
      AGP/Líder noturno  19:00–07:00      (medido: 19:00)
      sem ASG
  Mirante das Flores
      AGP/Líder diurno   07:00–19:00      (medido: 07:00)
      AGP/Líder noturno  19:00–07:00      (medido: 18:59)
      ASG                07:00–16:00      (medido: 07:02)
  Michelangelo
      artífice           08:00–17:00      (medido: 07:30 — chegam cedo)

SÁBADO. Quem é 44h (ASG, artífice, jardineiro) trabalha 08:00–12:00 e bate 2 vezes, sem
pausa. AGP em 12x36 não tem sábado especial — a escala dele é dia sim, dia não.

TOLERÂNCIA: 15 minutos (decisão do Jordan). "Ninguém vai bater o ponto às 06:00, vai bater
sempre atrasado" — então cobrar o minuto exato transformaria o alerta em ruído diário.
Villa dos Pássaros chega ~10 min ANTES, e 15 min cobre os dois lados.

EXCEÇÕES INDIVIDUAIS que o Sólides mostrou e o Jordan confirmou como reais — ficam com
registro próprio, não puxam a média do posto:
  ANTONIO CARLOS CASTRO GAMA (Mirante, AGP)     10:00
  PAULO DA SILVA LAMEGO      (Mirante, ASG)     09:00

Ensaio é o padrão. Aplicar: --aplicar --forcar.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
      python3 /app/scripts/parametrizar_jornadas.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import time as _time

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts/qa")

from _mutacao import Mutacao  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

TOLERANCIA_MIN = 15

#: `posto → grupo → (entrada, saída)`. Grupo casa pelo cargo; `None` = o posto não tem.
#: AGP/Líder de portaria seguem o mesmo horário — a diferença é o turno, não o cargo.
PADRAO_06 = {"agp_diurno": ("06:00", "18:00"), "agp_noturno": ("18:00", "06:00"),
             "asg": ("08:00", "17:00")}
PADRAO_07 = {"agp_diurno": ("07:00", "19:00"), "agp_noturno": ("19:00", "07:00"),
             "asg": None}

JORNADAS = {
    "Condomínio Ideal Flores da Cidade": PADRAO_06,
    "Condomínio Villa dos Pássaros": PADRAO_06,
    "Condomínio Prime Arena": PADRAO_06,
    "Condomínio Villa Dei Fiori": PADRAO_06,
    "Residencial Laranjeiras Village": PADRAO_07,
    "Condomínio Mirante das Flores": {**PADRAO_07, "asg": ("07:00", "16:00")},
    "Condomínio Michelangelo": {"agp_diurno": None, "agp_noturno": None,
                                "asg": ("08:00", "17:00")},
}

#: Quem foge do horário do próprio posto, confirmado pelo Jordan em 14/08.
EXCECOES = {
    "ANTONIO CARLOS CASTRO GAMA": ("10:00", "22:00"),
    "PAULO DA SILVA LAMEGO": ("09:00", "18:00"),
}

#: Sábado do 44h: meio período, 2 batidas.
SABADO_44H = ("08:00", "12:00")


def _hhmm(s: str) -> _time:
    """'18:00' → time(18, 0). asyncpg recusa string em coluna `time`, mesmo com CAST."""
    h, mi = s.split(":")
    return _time(int(h), int(mi))


def _grupo(cargo: str, entrada_medida: str | None) -> str:
    c = (cargo or "").upper()
    if any(k in c for k in ("SERVIÇOS GERAIS", "SERVICOS GERAIS", "ARTÍFICE", "ARTIFICE",
                            "JARDINEIRO")):
        return "asg"
    # AGP/Líder: o turno vem da hora que a pessoa realmente entra
    if entrada_medida and 4 <= int(entrada_medida[:2]) <= 13:
        return "agp_diurno"
    return "agp_noturno"


SQL_ENTRADA_MEDIDA = text(
    # mediana da entrada por pessoa no histórico do Sólides, agrupando por TURNO (não por
    # dia): o noturno vira a meia-noite e por dia-calendário ele aparece com 1 batida
    "WITH b AS ("
    "  SELECT pc.employee_id, pc.punch_timestamp, "
    "         CASE WHEN lag(pc.punch_timestamp) OVER ("
    "                     PARTITION BY pc.employee_id ORDER BY pc.punch_timestamp) "
    "                   > pc.punch_timestamp - interval '14 hours' THEN 0 ELSE 1 END AS novo "
    "  FROM gp_clock_punches pc "
    "  WHERE pc.punch_timestamp::date BETWEEN '2026-08-01' AND '2026-08-10' "
    "    AND pc.device_type = 'tangerino'), "
    "g AS (SELECT employee_id, punch_timestamp, "
    "             sum(novo) OVER (PARTITION BY employee_id ORDER BY punch_timestamp) AS t "
    "      FROM b), "
    "ini AS (SELECT employee_id, t, min(punch_timestamp) AS ent FROM g GROUP BY 1,2) "
    "SELECT employee_id::text AS id, "
    "       to_char(percentile_disc(0.5) WITHIN GROUP (ORDER BY ent::time),'HH24:MI') AS med "
    "FROM ini GROUP BY 1"
)


async def main() -> int:
    m = Mutacao("parametrizar jornadas em work_schedules", teto=20)

    async with async_session_factory() as db:
        medidas = {r["id"]: r["med"]
                   for r in (await db.execute(SQL_ENTRADA_MEDIDA)).mappings()}

        pessoas = (await db.execute(text(
            "SELECT e.id::text AS id, e.nome AS nome, coalesce(e.cargo,'') AS cargo, "
            "       coalesce(p.name,'') AS posto, coalesce(e.escala_padrao,'') AS escala, "
            "       coalesce(e.recebe_intrajornada,false) AS recebe "
            "FROM employees e LEFT JOIN posts p ON p.id = e.posto_atual_id "
            "WHERE lower(coalesce(e.status,'')) = 'ativo' "
            "  AND upper(coalesce(e.nome,'')) NOT LIKE '%TESTE%' "
            "  AND upper(coalesce(e.nome,'')) NOT LIKE '%HOMOLOGA%' "
            "ORDER BY p.name, e.nome"
        ))).mappings().all()

        plano, sem_regra = [], []
        for r in pessoas:
            med = medidas.get(r["id"])
            grp = _grupo(r["cargo"], med)
            if r["nome"].upper().strip() in EXCECOES:
                ent, sai = EXCECOES[r["nome"].upper().strip()]
                origem = "exceção individual"
            else:
                cfg = (JORNADAS.get(r["posto"]) or {}).get(grp)
                if not cfg:
                    sem_regra.append((r["nome"], r["posto"], grp, med))
                    continue
                ent, sai = cfg
                origem = f"{r['posto'] or '—'} / {grp}"
            quarenta_e_quatro = "44" in r["escala"]
            plano.append({
                "id": r["id"], "nome": r["nome"], "ent": ent, "sai": sai,
                "grupo": grp, "origem": origem, "med": med or "—",
                "sab": SABADO_44H if quarenta_e_quatro else None,
                "batidas": 2 if r["recebe"] else 4,
            })

        alvos = [
            (p["id"][:8],
             f"{p['nome'][:30]:32} {p['ent']}–{p['sai']}"
             f"{'  sáb ' + p['sab'][0] + '–' + p['sab'][1] if p['sab'] else ''}"
             f"  · {p['batidas']} batidas · medido {p['med']} · {p['origem']}")
            for p in plano
        ]
        print(f"\n══ jornadas: {len(plano)} pessoa(s) · tolerância {TOLERANCIA_MIN} min ══")
        if sem_regra:
            print(f"  ⚠️ {len(sem_regra)} SEM REGRA (posto/grupo não parametrizado):")
            for n, po, g, md in sem_regra:
                print(f"       {n[:30]:32} {po[:28]:30} {g} (medido {md or '—'})")

        if not m.confirmar(alvos):
            return 0

        gravadas = 0
        for p in plano:
            dias = {"seg": [p["ent"], p["sai"]], "ter": [p["ent"], p["sai"]],
                    "qua": [p["ent"], p["sai"]], "qui": [p["ent"], p["sai"]],
                    "sex": [p["ent"], p["sai"]]}
            if p["sab"]:
                dias["sab"] = [p["sab"][0], p["sab"][1]]
            await db.execute(text(
                "INSERT INTO work_schedules "
                "(id, code, name, schedule_type, status, employee_id, "
                " default_entry_time, default_exit_time, entry_tolerance_minutes, "
                " exit_tolerance_minutes, daily_schedule, is_template, is_deleted, "
                " weekly_hours_minutes, daily_hours_minutes, notes, created_at, updated_at) "
                "VALUES "
                "(CAST(:id AS uuid), :code, :name, 'individual', 'ativo', CAST(:emp AS uuid), "
                " :ent, :sai, :tol, :tol, "
                " CAST(:dias AS jsonb), false, false, :semana, :dia, :notes, now(), now())"
            ), {
                "id": str(uuid.uuid4()),
                "code": f"JOR-{p['id'][:8].upper()}",
                "name": f"{p['nome']} — {p['ent']}–{p['sai']}",
                # asyncpg exige objeto `time` — o CAST no SQL não converte string
                "emp": p["id"], "ent": _hhmm(p["ent"]), "sai": _hhmm(p["sai"]),
                "tol": TOLERANCIA_MIN,
                # carga em MINUTOS, NOT NULL na tabela. 44h/semana = 2640; o 12x36 faz
                # 12h por turno em dias alternados ≈ 44h/semana na média do mês (CCT).
                "semana": 2640,
                "dia": 480 if p["sab"] else 720,
                "dias": json.dumps(dias, ensure_ascii=False),
                "notes": (f"origem: {p['origem']} · entrada medida no Sólides 01–10/08: "
                          f"{p['med']} · {p['batidas']} batidas/turno"),
            })
            gravadas += 1
        await db.commit()
        m.feito(gravadas)

        conf = (await db.execute(text(
            "SELECT count(*) AS n, count(DISTINCT employee_id) AS pessoas "
            "FROM work_schedules WHERE coalesce(is_deleted,false) = false"
        ))).first()
        print(f"  DEPOIS: {conf[0]} jornada(s) para {conf[1]} pessoa(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
