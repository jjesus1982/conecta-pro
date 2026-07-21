"""Operacional (T1) — delega ao _build_operacional e ESTENDE com telas de LEITURA
(presença ao vivo, escalas, turnos, reembolsos). Operacional é curado pelo Jordan →
SÓ visibilidade, NUNCA escreve/altera escala/alocação. Reembolso é read-only (sem aprovar/pagar)."""
from modules.operacional.controllers.redesign_data_controller import (
    _build_operacional, _fmtdate, _helpers, b, brl, t,
)

SLUG = "operacional"
EXTRA_MENU: list[dict] = []


async def build(db) -> dict:
    out = await _build_operacional(db)
    _, _safe, tbl = _helpers(db)

    # Presença ao vivo — gp_clock_punches (batidas; punch_timestamp=UTC → -4h Manaus)
    try:
        out["presenca"] = await tbl(
            "Presença ao vivo", "Batidas recentes (horário de Manaus)", "—",
            ["Colaborador", "Tipo", "Horário", "Facial", "Geofence"], "1.8fr 0.9fr 1fr 0.8fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), coalesce(p.punch_type::text,'—'), "
            "to_char(p.punch_timestamp - interval '4 hours','DD/MM HH24:MI'), p.facial_match, p.dentro_geofence "
            "FROM gp_clock_punches p LEFT JOIN employees e ON e.id=p.employee_id "
            "ORDER BY p.punch_timestamp DESC LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').capitalize(), "ok" if r[1] == "entrada" else "info"),
                       t(r[2] or '—'), b("OK", "ok") if r[3] else t("—"),
                       (b("Dentro", "ok") if r[4] else b("Fora", "warn")) if r[4] is not None else t("—")])
    except Exception:  # noqa: BLE001
        pass

    # Escalas — solides_work_schedules (curado; leitura)
    try:
        out["escalas"] = await tbl(
            "Escalas", "Escalas de trabalho (Sólides)", "—",
            ["Escala", "Código", "Tipo", "Carga/sem", "Status"], "1.8fr 1fr 1fr 0.9fr 0.9fr",
            "SELECT coalesce(nome,'—'), coalesce(codigo,'—'), coalesce(tipo::text,'—'), carga_horaria_semanal, coalesce(is_active,true) "
            "FROM solides_work_schedules ORDER BY nome LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t((r[2] or '—').replace('_', ' ')),
                       t(f"{r[3]}h" if r[3] is not None else '—'), b("Ativa", "ok") if r[4] else b("Inativa", "mut")])
    except Exception:  # noqa: BLE001
        pass

    # Turnos — shifts (instâncias de turno planejadas/realizadas; leitura)
    _tt = {"scheduled": "info", "planejado": "info", "completed": "ok", "concluido": "ok", "absent": "bad", "falta": "bad", "in_progress": "warn", "em_andamento": "warn"}
    try:
        out["turnos"] = await tbl(
            "Turnos", "Turnos planejados/realizados", "—",
            ["Colaborador", "Data", "Início", "Fim", "Horas", "Status"], "1.6fr 0.9fr 0.8fr 0.8fr 0.7fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), s.shift_date, s.planned_start_time, s.planned_end_time, s.planned_hours, coalesce(s.status::text,'—') "
            "FROM shifts s LEFT JOIN employees e ON e.id=s.employee_id ORDER BY s.shift_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(_fmtdate(r[1])), t(str(r[2])[:5] if r[2] else '—'), t(str(r[3])[:5] if r[3] else '—'),
                       t(f"{float(r[4]):.0f}h" if r[4] is not None else '—'), b((r[5] or '—').replace('_', ' ').capitalize(), _tt.get((r[5] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001
        pass

    # Reembolsos — reimbursement_requests (READ-ONLY: sem aprovar/pagar aqui)
    _rt = {"aprovado": "ok", "pago": "ok", "reembolsado": "ok", "pendente": "warn", "em_analise": "warn", "submetido": "warn", "rejeitado": "bad", "negado": "bad"}
    try:
        out["reembolsos"] = await tbl(
            "Reembolsos", "Solicitações de reembolso (visibilidade)", "—",
            ["Código", "Descrição", "Valor", "Status"], "1fr 2fr 1fr 0.9fr",
            "SELECT coalesce(code,'—'), coalesce(title,'—'), total_amount, coalesce(status::text,'—') "
            "FROM reimbursement_requests ORDER BY submitted_at DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—')[:60]), t(brl(r[2]) if r[2] is not None else '—', 600),
                       b((r[3] or '—').replace('_', ' ').capitalize(), _rt.get((r[3] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001
        pass

    return out
