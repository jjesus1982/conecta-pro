"""Regenera as escalas de JULHO/2026 a partir do padrão REAL de trabalho (batidas Sólides).

Regras (ordem do Jordan, 2026-07-08):
- AGENTE DE PORTARIA (AGP): 12x36. Turno (diurno/noturno) e paridade de dias inferidos das
  batidas reais (últimos 60 dias, convertidas UTC→Manaus). Sem histórico → preenche a lacuna
  de cobertura do posto (nota no shift).
- TODOS os demais cargos (ASG, ARTÍFICE, JARDINEIRO, LÍDER DE PORTARIA): 44h semanais em
  horário comercial — seg-sex 8h (com 1h de almoço) + sábado 4h; início pela mediana real
  de entrada (fallback 07:00, padrão provado do ADEMIR: 07:00-16:00 c/ almoço 11-12).
- Substitui TODOS os shifts de julho das 9 escalas published (eram plano fictício auto-gerado
  hoje, padrão 12x36 arbitrário, zero check-ins reais — backup feito antes).

Roda no container backend. NUNCA fabrica presença — isto é PLANO, derivado do padrão real.
"""
import sys

sys.path.insert(0, "/app")
import uuid
from collections import Counter
from datetime import date, datetime, time, timedelta

from sqlalchemy import text

from core.database.session import SyncSessionLocal

MES, ANO = 7, 2026
DIAS_MES = 31
db = SyncSessionLocal()

# ── 1. Escalas de julho por posto ──────────────────────────────────────────
scales = {
    r[1]: r[0]
    for r in db.execute(
        text("SELECT id::text, post_id::text FROM scales WHERE month=:m AND year=:a AND is_active"),
        {"m": MES, "a": ANO},
    ).fetchall()
}
print(f"escalas de julho: {len(scales)} postos")

# ── 2. Funcionários ativos alocados (1 posto por funcionário; prioriza is_primary) ─
alocados = db.execute(
    text(
        """
        SELECT DISTINCT ON (e.id) e.id::text, e.nome, e.cargo, a.post_id::text, p.name
        FROM allocations a
        JOIN employees e ON e.id = a.employee_id AND e.status = 'ativo'
        JOIN posts p ON p.id = a.post_id AND p.is_active
        WHERE a.status = 'active' AND a.is_active
        ORDER BY e.id, a.is_primary DESC, a.created_at DESC
        """
    )
).fetchall()
print(f"funcionários ativos alocados: {len(alocados)}")

# ── 3. Padrão real de batidas (60d, UTC→Manaus): 1ª entrada por dia ────────
padroes = {}
rows = db.execute(
    text(
        """
        SELECT employee_id::text,
               dia,
               min(primeira) AS primeira
        FROM (
          SELECT employee_id,
                 (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus')::date AS dia,
                 (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus')::time AS primeira
          FROM gp_clock_punches
          WHERE punch_timestamp >= now() - interval '60 days'
            AND COALESCE(status,'') NOT IN ('rejected','cancelado')
            AND punch_type = 'entrada'
        ) x
        GROUP BY employee_id, dia
        """
    )
).fetchall()
por_emp: dict[str, list] = {}
for emp, dia, primeira in rows:
    por_emp.setdefault(emp, []).append((dia, primeira))

for emp, dias in por_emp.items():
    horas = sorted(t for _, t in dias)
    mediana = horas[len(horas) // 2]
    impares = sum(1 for d, _ in dias if d.day % 2 == 1)
    pares = len(dias) - impares
    padroes[emp] = {"mediana": mediana, "impares": impares, "pares": pares, "n": len(dias)}


def _round30(t: time) -> time:
    total = t.hour * 60 + t.minute
    total = int(round(total / 30.0)) * 30 % (24 * 60)
    return time(total // 60, total % 60)


def _clamp(t: time, lo: time, hi: time, default: time) -> time:
    return t if lo <= t <= hi else default


# ── 4. Montar plano por funcionário ────────────────────────────────────────
plano = []          # (emp_id, nome, post_id, tipo, inicio, fim, paridade|None, obs)
cobertura = {}      # post_id -> {('diurno','impar'):nome, ...} p/ preencher lacunas
sem_historico = []

for emp_id, nome, cargo, post_id, post_nome in alocados:
    if post_id not in scales:
        print(f"  AVISO: {nome} alocado em posto sem escala de julho ({post_nome}) — pulado")
        continue
    eh_agp = cargo.strip().upper() == "AGENTE DE PORTARIA"
    pad = padroes.get(emp_id)
    if eh_agp:
        if pad and pad["n"] >= 5:
            med = pad["mediana"]
            diurno = time(4, 0) <= med < time(14, 0)
            inicio = _clamp(_round30(med), time(6, 0), time(10, 0), time(7, 0)) if diurno \
                else _clamp(_round30(med), time(16, 0), time(21, 0), time(18, 0))
            paridade = "impar" if pad["impares"] >= pad["pares"] else "par"
            obs = f"padrao real: {pad['n']} dias batidos, mediana {med.strftime('%H:%M')} Manaus"
        else:
            diurno, inicio, paridade, obs = None, None, None, "sem historico de batidas"
            sem_historico.append((emp_id, nome, post_id, post_nome))
            plano.append((emp_id, nome, post_id, "agp_pendente", None, None, None, obs))
            continue
        fim = (datetime.combine(date.today(), inicio) + timedelta(hours=12)).time()
        turno = "diurno" if diurno else "noturno"
        cobertura.setdefault(post_id, {})[(turno, paridade)] = nome
        plano.append((emp_id, nome, post_id, f"12x36_{turno}", inicio, fim, paridade, obs))
    else:
        if pad and pad["n"] >= 5:
            inicio = _clamp(_round30(pad["mediana"]), time(6, 0), time(10, 0), time(7, 0))
            obs = f"comercial 44h; entrada mediana real {pad['mediana'].strftime('%H:%M')} Manaus"
        else:
            inicio, obs = time(7, 0), "comercial 44h; sem historico — inicio padrao 07:00"
        plano.append((emp_id, nome, post_id, "comercial", inicio, None, None, obs))

# AGPs sem histórico → preencher lacuna de cobertura do posto
SLOTS = [("diurno", "impar"), ("diurno", "par"), ("noturno", "impar"), ("noturno", "par")]
for i, item in enumerate(plano):
    if item[3] != "agp_pendente":
        continue
    emp_id, nome, post_id = item[0], item[1], item[2]
    ocupados = cobertura.get(post_id, {})
    slot = next((s for s in SLOTS if s not in ocupados), ("diurno", "impar"))
    turno, paridade = slot
    inicio = time(7, 0) if turno == "diurno" else time(19, 0)
    fim = (datetime.combine(date.today(), inicio) + timedelta(hours=12)).time()
    cobertura.setdefault(post_id, {})[slot] = nome
    plano[i] = (emp_id, nome, post_id, f"12x36_{turno}", inicio, fim, paridade,
                f"sem historico — alocado p/ cobrir {turno}/{paridade}")

# ── 5. Substituir shifts de julho ──────────────────────────────────────────
del_result = db.execute(
    text("DELETE FROM shifts WHERE scale_id::text = ANY(:ids)"),
    {"ids": list(scales.values())},
)
print(f"shifts antigos removidos: {del_result.rowcount}")

INSERT = text(
    """
    INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date,
        planned_start_time, planned_end_time, planned_break_minutes,
        status, is_holiday, is_night_shift, is_overtime, is_off_day,
        needs_substitution, planned_hours, actual_hours, overtime_hours, night_hours,
        base_pay, overtime_pay, night_bonus, holiday_bonus, total_pay,
        notes, is_active, created_at, updated_at)
    VALUES (:id, CAST(:scale_id AS uuid), CAST(:emp AS uuid), CAST(:post AS uuid), :dia,
        :ini, :fim, :pausa, 'scheduled', false, :noturno, false, false,
        false, :horas, 0, 0, 0, 0, 0, 0, 0, 0, :notes, true, now(), now())
    """
)

criados = 0
resumo = Counter()
for emp_id, nome, post_id, tipo, inicio, fim, paridade, obs in plano:
    scale_id = scales[post_id]
    for d in range(1, DIAS_MES + 1):
        dia = date(ANO, MES, d)
        if tipo.startswith("12x36"):
            if (d % 2 == 1) != (paridade == "impar"):
                continue
            noturno = "noturno" in tipo
            horas, pausa, fim_d = 12.0, 60, fim
        else:  # comercial 44h: seg(0)-sex(4) 8h, sab(5) 4h, dom folga
            dow = dia.weekday()
            if dow == 6:
                continue
            if dow == 5:
                horas, pausa = 4.0, 0
                fim_d = (datetime.combine(dia, inicio) + timedelta(hours=4)).time()
            else:
                horas, pausa = 8.0, 60
                fim_d = (datetime.combine(dia, inicio) + timedelta(hours=9)).time()
            noturno = False
        db.execute(INSERT, {
            "id": str(uuid.uuid4()), "scale_id": scale_id, "emp": emp_id, "post": post_id,
            "dia": dia, "ini": inicio, "fim": fim_d, "pausa": pausa,
            "noturno": noturno, "horas": horas,
            "notes": f"escala real 2026-07-08: {tipo} ({obs})",
        })
        criados += 1
    resumo[tipo] += 1

# ── 6. Métricas das escalas + nota ─────────────────────────────────────────
db.execute(text(
    """
    UPDATE scales s SET
      total_shifts = q.n, filled_shifts = q.n, total_hours = q.horas,
      notes = COALESCE(s.notes,'') || ' | Regenerada 2026-07-08 pelo padrao real de batidas (AGP 12x36; demais 44h comercial).',
      updated_at = now()
    FROM (SELECT scale_id, count(*) AS n, COALESCE(sum(planned_hours),0) AS horas
          FROM shifts WHERE scale_id::text = ANY(:ids) AND is_active GROUP BY scale_id) q
    WHERE s.id = q.scale_id
    """
), {"ids": list(scales.values())})

db.commit()
print(f"shifts criados: {criados}")
print("por tipo:", dict(resumo))
if sem_historico:
    print("AGPs sem historico (slot de cobertura):", [n for _, n, _, _ in sem_historico])
