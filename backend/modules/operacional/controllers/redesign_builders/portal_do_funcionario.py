"""Redesign builder — Portal do Funcionário.

Estende `_build_portal_funcionario` (base: dashboard, contracheque, ferias,
documentos) e liga as 5 telas sem wiring, lendo tabelas REAIS (visão admin/
preview; o portal real é escopado por colaborador logado).
Telas novas: ponto · beneficios · escalas · treinamentos · dados-pessoais.
"""

from modules.operacional.controllers.redesign_data_controller import (
    _build_portal_funcionario,
    _helpers,
    b,
    initials,
    t,
)

SLUG = "portal-do-funcionario"
EXTRA_MENU: list[dict] = []
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _bs(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "concluido", "concluida", "presente", "trabalhado", "aprovado", "completed", "gozada"):
        return b(v or "—", "ok")
    if s in ("pendente", "agendado", "planned", "scheduled", "em_andamento", "andamento", "solicitada"):
        return b(v or "—", "warn")
    if s in ("falta", "ausente", "cancelado", "rejeitado", "off", "folga"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


# Status em PT — espelha os label maps do clássico (meu-espaco): benefícios/escala/treinamento
_PF_ST = {"active": ("Ativo", "ok"), "ativo": ("Ativo", "ok"),
          "inactive": ("Inativo", "mut"), "inativo": ("Inativo", "mut"),
          "cancelled": ("Cancelado", "bad"), "canceled": ("Cancelado", "bad"), "cancelado": ("Cancelado", "bad"),
          "scheduled": ("Agendado", "warn"), "agendado": ("Agendado", "warn"),
          "completed": ("Concluído", "ok"), "concluido": ("Concluído", "ok"),
          "in_progress": ("Em andamento", "warn"), "confirmed": ("Confirmado", "ok"),
          "absent": ("Falta", "bad"), "suspended": ("Suspenso", "warn"),
          "approved": ("Aprovado", "ok"), "aprovado": ("Aprovado", "ok"),
          "submitted": ("Pendente", "warn"), "pending": ("Pendente", "warn"),
          "rejected": ("Rejeitado", "bad"), "rejeitado": ("Rejeitado", "bad")}


def _pf_status(v):
    lbl, tone = _PF_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _cpf(v):
    d = "".join(c for c in (v or "") if c.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}" if len(d) == 11 else (v or "—")


_PUNCH = {"entrada": "Entrada", "saida": "Saída", "saída": "Saída",
          "intervalo": "Intervalo", "retorno": "Retorno"}


async def build(db) -> dict:
    out = await _build_portal_funcionario(db)
    _o2, _s2, tbl = _helpers(db)

    async def safe(key, coro):
        try:
            out[key] = await coro
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

    # 0) Férias — SOBRESCREVE a base (Status vinha cru 'Approved') → PT
    await safe("ferias", tbl(
        "Minhas férias", "Solicitações de férias", "—",
        ["Colaborador", "Início", "Fim", "Dias", "Status"], "2fr 1fr 1fr 0.7fr 0.9fr",
        "SELECT e.nome, v.start_date, v.end_date, v.days_requested, coalesce(v.status::text,'—') "
        "FROM employee_vacation_requests v LEFT JOIN employees e ON e.id=v.employee_id "
        "ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_d(r[1])), t(_d(r[2])),
                   t(str(r[3] or "—")), _pf_status(r[4])]))

    # 1) Meu ponto — gp_clock_punches
    await safe("ponto", tbl(
        "Meu ponto", "Batidas registradas", "—",
        ["Colaborador", "Tipo", "Data/hora", "Posto", "Facial"],
        "2fr 1fr 1.2fr 1.4fr 0.8fr",
        "SELECT coalesce(e.nome, p.employee_id::text), coalesce(p.punch_type,'—'), "
        "p.punch_timestamp, coalesce(p.posto_nome,'—'), p.facial_match "
        "FROM gp_clock_punches p LEFT JOIN employees e ON e.id = p.employee_id "
        "ORDER BY p.punch_timestamp DESC LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t(_PUNCH.get((r[1] or "").lower(), (r[1] or "—").capitalize())),
                   t(_d(r[2], "%d/%m/%Y %H:%M")), t(r[3]),
                   (b("OK", "ok") if r[4] else b("—", "mut"))]))

    # 2) Benefícios — employee_benefits
    await safe("beneficios", tbl(
        "Benefícios", "Benefícios do colaborador", "—",
        ["Colaborador", "Tipo", "Provedor", "Plano", "Status"],
        "1.8fr 1fr 1.2fr 1.2fr 0.9fr",
        "SELECT coalesce(e.nome, x.employee_id::text), coalesce(x.type::text,'—'), "
        "coalesce(x.provider,'—'), coalesce(x.plan_name,'—'), coalesce(x.status::text,'—') "
        "FROM employee_benefits x LEFT JOIN employees e ON e.id = x.employee_id "
        "ORDER BY x.created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t((r[1] or "—").replace("_", " ").capitalize()),
                   t(r[2]), t(r[3]), _pf_status(r[4])]))

    # 3) Minha escala — shifts
    await safe("escalas", tbl(
        "Minha escala", "Turnos planejados", "—",
        ["Colaborador", "Data", "Início", "Fim", "Status"],
        "2fr 1fr 0.8fr 0.8fr 0.9fr",
        "SELECT coalesce(e.nome, s.employee_id::text), s.shift_date, "
        "to_char(s.planned_start_time,'HH24:MI'), to_char(s.planned_end_time,'HH24:MI'), "
        "coalesce(s.status::text,'—') FROM shifts s LEFT JOIN employees e ON e.id::text = s.employee_id::text "
        "ORDER BY s.shift_date DESC NULLS LAST LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_d(r[1])),
                   t(r[2] or "—"), t(r[3] or "—"), _pf_status(r[4])]))

    # 4) Treinamentos — trainings
    await safe("treinamentos", tbl(
        "Treinamentos", "Turmas de treinamento", "—",
        ["Treinamento", "Início", "Fim", "Participantes", "Status"],
        "2fr 1fr 1fr 1fr 0.9fr",
        "SELECT coalesce(title,'—'), start_date, end_date, coalesce(current_participants,0), "
        "coalesce(status::text,'—') FROM trainings ORDER BY start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(_d(r[1])), t(_d(r[2])), t(str(r[3])), _pf_status(r[4])]))

    # 5) Dados pessoais — employees
    await safe("dados-pessoais", tbl(
        "Dados pessoais", "Cadastro do colaborador", "—",
        ["Colaborador", "CPF", "RG", "Nascimento", "Estado civil", "Cargo", "Telefone"],
        "1.8fr 1.1fr 1fr 1fr 1fr 1.3fr 1.1fr",
        "SELECT coalesce(nome,'—'), coalesce(cpf,'—'), coalesce(rg,'—'), data_nascimento, "
        "coalesce(estado_civil::text,'—'), coalesce(cargo,'—'), coalesce(telefone,'—') "
        "FROM employees WHERE status='ativo' AND coalesce(nome,'') !~ '^[0-9]+$' ORDER BY nome LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_cpf(r[1])), t(r[2]),
                   t(_d(r[3])), t((r[4] or "—").replace("_", " ")), t(r[5]), t(r[6])]))

    return out
