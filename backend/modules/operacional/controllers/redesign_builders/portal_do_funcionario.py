"""Redesign builder — Portal do Funcionário.

Estende `_build_portal_funcionario` (base: dashboard, contracheque, ferias,
documentos) e liga as 5 telas sem wiring, lendo tabelas REAIS (visão admin/
preview; o portal real é escopado por colaborador logado).
Telas novas: ponto · beneficios · escalas · treinamentos · dados-pessoais.
"""

import uuid

from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    IC,
    S,
    _ICF,
    _helpers,
    _scalar,
    b,
    brl,
    doc,
    initials,
    t,
)

SLUG = "portal-do-funcionario"
EXTRA_MENU: list[dict] = [
    {"id": "ouvidoria", "label": "Ouvidoria", "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"},
]
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


async def _resolve_me(db, current_user) -> str | None:
    """employee_id do usuário logado: users.employee_id → fallback e-mail. None se não vinculado.
    É a PAREDE self-only do portal: sem employee resolvido, nenhuma tela mostra dado de terceiro."""
    if current_user is None:
        return None
    me = None
    uid = getattr(current_user, "id", None)
    if uid is not None:
        row = (await db.execute(text("SELECT CAST(employee_id AS TEXT) FROM users WHERE id::text=:i"),
                                {"i": str(uid)})).first()
        if row and row[0]:
            me = row[0]
    if not me:
        em = getattr(current_user, "email", None)
        if em:
            r2 = (await db.execute(text("SELECT CAST(id AS TEXT) FROM employees WHERE lower(email)=lower(:e) LIMIT 1"),
                                   {"e": em})).first()
            if r2 and r2[0]:
                me = r2[0]
    if me:
        try:
            uuid.UUID(str(me))  # valida antes de in-linar no SQL (defesa em profundidade)
        except Exception:
            me = None
    return me


async def build(db, current_user=None) -> dict:
    """Portal PESSOAL — escopado ao colaborador logado (parede self-only / LGPD).

    NÃO chama a base `_build_portal_funcionario` (visão admin agregada: vazaria holerite/
    ponto/benefícios de TODOS). Toda tela filtra por `employee_id = <usuário logado>`. Sem
    vínculo employee → telas vazias com aviso, NUNCA dado de terceiro. `me` é UUID validado,
    vindo do nosso banco (users/employees), não do request → in-lining seguro."""
    out, safe, tbl = _helpers(db)
    me = await _resolve_me(db, current_user)
    _vinc = me is not None
    # sem vínculo → literal que não casa nada → todas as queries voltam vazias
    me_lit = f"'{me}'" if _vinc else "'00000000-0000-0000-0000-000000000000'"
    _nota = "" if _vinc else " — vincule seu cadastro de colaborador ao usuário"

    # dashboard PESSOAL (substitui o dash agregado da base, que vazava totais da empresa)
    async def _dash():
        comp = (await db.execute(text(
            f"SELECT reference_year, reference_month, net_salary FROM hr_payslips "
            f"WHERE employee_id={me_lit} ORDER BY reference_year DESC, reference_month DESC LIMIT 1"))).fetchone()
        comp_lbl = f"{comp[1]:02d}/{comp[0]}" if comp and comp[1] else "—"
        meu_liq = brl(comp[2]) if comp and comp[2] is not None else "—"
        n_pay = await _scalar(db, f"SELECT count(*) FROM hr_payslips WHERE employee_id={me_lit}")
        # hr_vacation_requests é a AUTORITATIVA (test_oraculo_ferias_autoritativa, 13/08); a cópia
        # employee_vacation_requests parou em 01/04 com 14 pedidos presos em SUBMITTED — o portal
        # mostrava ao colaborador um pedido "enviado" que o DP já tinha aprovado (achado 07/09).
        n_fer = await _scalar(db, f"SELECT count(*) FROM hr_vacation_requests WHERE employee_id={me_lit}")
        n_ben = await _scalar(db, f"SELECT count(*) FROM employee_benefits WHERE employee_id={me_lit}")
        n_doc = await _scalar(db, f"SELECT count(*) FROM ged_kit_documents WHERE employee_id={me_lit}")
        fr = (await db.execute(text(
            f"SELECT coalesce(status::text,'—'), count(*) FROM hr_vacation_requests "
            f"WHERE employee_id={me_lit} GROUP BY 1 ORDER BY 2 DESC LIMIT 5"))).fetchall()
        return {"title": "Início", "sub": "Meu portal — dados pessoais" + _nota, "cta": "Atualizar",
                "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_pay), "l": "Meus holerites", "icon": _ICF["money"], "color": "#0F1B3A"},
                    {"v": str(n_fer), "l": "Minhas férias", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_ben), "l": "Benefícios", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": str(n_doc), "l": "Documentos", "icon": IC["users"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": f"Meu holerite — {comp_lbl}", "rows": [{"left": "Líquido", "right": meu_liq, **S["ok"]}]},
                    {"title": "Minhas férias por status", "rows": [
                        {"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in fr]
                        or [{"left": "Sem férias", "right": "0", **S["mut"]}]},
                ]}
    await safe("dashboard", _dash())

    # Contracheque — só MEUS holerites + botão Holerite PDF por-linha
    await safe("contracheque", tbl(
        "Contracheque", "Meus holerites" + _nota, "—",
        ["Competência", "Líquido", "Status"], "1.4fr 1fr 0.9fr",
        f"SELECT p.reference_month, p.reference_year, p.net_salary, "
        f"coalesce(p.status::text,'—'), CAST(p.id AS TEXT) "
        f"FROM hr_payslips p WHERE p.employee_id={me_lit} "
        f"ORDER BY p.reference_year DESC, p.reference_month DESC LIMIT 200",
        lambda r: [t(f"{r[0]:02d}/{r[1]}" if r[0] else "—"),
                   t(brl(r[2]) if r[2] is not None else "—"), b((r[3] or "—").capitalize(), "info")],
        docsfn=lambda r: [doc("Holerite", f"/api/v1/people-management/dp/payslips/{r[4]}/pdf", fmt="pdf", gate="financeiro")]))

    # Minhas férias
    await safe("ferias", tbl(
        "Minhas férias", "Minhas solicitações" + _nota, "—",
        ["Início", "Fim", "Dias", "Status"], "1fr 1fr 0.7fr 0.9fr",
        f"SELECT v.start_date, v.end_date, v.days_requested, coalesce(v.status::text,'—') "
        f"FROM hr_vacation_requests v WHERE v.employee_id={me_lit} "
        f"ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(_d(r[0])), t(_d(r[1])), t(str(r[2] or "—")), _pf_status(r[3])]))

    # Meu ponto
    await safe("ponto", tbl(
        "Meu ponto", "Minhas batidas" + _nota, "—",
        ["Tipo", "Data/hora", "Posto", "Facial"], "1fr 1.2fr 1.4fr 0.8fr",
        f"SELECT coalesce(p.punch_type,'—'), p.punch_timestamp, coalesce(p.posto_nome,'—'), p.facial_match "
        f"FROM gp_clock_punches p WHERE p.employee_id={me_lit} "
        f"ORDER BY p.punch_timestamp DESC LIMIT 300",
        lambda r: [t(_PUNCH.get((r[0] or "").lower(), (r[0] or "—").capitalize())),
                   t(_d(r[1], "%d/%m/%Y %H:%M")), t(r[2]),
                   (b("OK", "ok") if r[3] else b("—", "mut"))]))

    # Meus benefícios
    await safe("beneficios", tbl(
        "Benefícios", "Meus benefícios" + _nota, "—",
        ["Tipo", "Provedor", "Plano", "Status"], "1fr 1.2fr 1.2fr 0.9fr",
        f"SELECT coalesce(x.type::text,'—'), coalesce(x.provider,'—'), "
        f"coalesce(x.plan_name,'—'), coalesce(x.status::text,'—') "
        f"FROM employee_benefits x WHERE x.employee_id={me_lit} "
        f"ORDER BY x.created_at DESC LIMIT 200",
        lambda r: [t((r[0] or "—").replace("_", " ").capitalize()), t(r[1]), t(r[2]), _pf_status(r[3])]))

    # Minha escala
    await safe("escalas", tbl(
        "Minha escala", "Meus turnos" + _nota, "—",
        ["Data", "Início", "Fim", "Status"], "1fr 0.8fr 0.8fr 0.9fr",
        f"SELECT s.shift_date, to_char(s.planned_start_time,'HH24:MI'), "
        f"to_char(s.planned_end_time,'HH24:MI'), coalesce(s.status::text,'—') "
        f"FROM shifts s WHERE s.employee_id::text={me_lit} "
        f"ORDER BY s.shift_date DESC NULLS LAST LIMIT 300",
        lambda r: [t(_d(r[0])), t(r[1] or "—"), t(r[2] or "—"), _pf_status(r[3])]))

    # Meus documentos (base vazava TODOS → aqui só os meus)
    await safe("documentos", tbl(
        "Meus documentos", "Meus documentos" + _nota, "—",
        ["Documento", "Tipo", "Assinado"], "2fr 1.4fr 0.9fr",
        f"SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), g.is_signed "
        f"FROM ged_kit_documents g WHERE g.employee_id={me_lit} "
        f"ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t((r[1] or "—").replace("_", " ")),
                   b("Assinado", "ok") if r[2] else b("Pendente", "warn")]))

    # Meus treinamentos (via matrícula training_enrollments)
    await safe("treinamentos", tbl(
        "Treinamentos", "Meus treinamentos" + _nota, "—",
        ["Treinamento", "Início", "Fim", "Status"], "2fr 1fr 1fr 0.9fr",
        f"SELECT coalesce(title,'—'), start_date, end_date, coalesce(status::text,'—') "
        f"FROM trainings WHERE id IN (SELECT training_id FROM training_enrollments WHERE employee_id={me_lit}) "
        f"ORDER BY start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(_d(r[1])), t(_d(r[2])), _pf_status(r[3])]))

    # Meus dados pessoais (só o MEU cadastro)
    await safe("dados-pessoais", tbl(
        "Dados pessoais", "Meu cadastro" + _nota, "—",
        ["Nome", "CPF", "RG", "Nascimento", "Estado civil", "Cargo", "Telefone"],
        "1.8fr 1.1fr 1fr 1fr 1fr 1.3fr 1.1fr",
        f"SELECT coalesce(nome,'—'), coalesce(cpf,'—'), coalesce(rg,'—'), data_nascimento, "
        f"coalesce(estado_civil::text,'—'), coalesce(cargo,'—'), coalesce(telefone,'—') "
        f"FROM employees WHERE id::text={me_lit} LIMIT 1",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_cpf(r[1])), t(r[2]),
                   t(_d(r[3])), t((r[4] or "—").replace("_", " ")), t(r[5]), t(r[6])]))

    # Ouvidoria (2026-08-10): responder leva {manifestacao_id} no caminho -> acao por LINHA.
    # A mensagem do colaborador aparece; a resposta fica visivel a ele.
    await safe("ouvidoria", tbl(
        "Ouvidoria", "Manifestações dos colaboradores", "—",
        ["Protocolo", "Categoria", "Mensagem", "Anônima", "Status"],
        "1fr 1.1fr 2.2fr 0.8fr 0.9fr",
        "SELECT id, coalesce(protocolo,'—'), coalesce(categoria::text,'—'), coalesce(mensagem,'—'), "
        "coalesce(anonimo,false), coalesce(status::text,'aberta') "
        "FROM ouvidoria_manifestacoes ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, "#0F1B3A"), t((r[2] or '—').capitalize()), t((r[3] or '—')[:90]),
                   b("Sim", "warn") if r[4] else b("Não", "mut"),
                   b((r[5] or '—').capitalize(), "ok" if (r[5] or '').lower() in ("respondida", "encerrada") else "warn")],
        actionsfn=lambda r: [
            {"title": f"Responder a manifestação {r[1]}",
             "sub": "A resposta fica VISÍVEL ao autor. Se for anônima, você responde sem saber quem é.",
             "endpoint": f"/api/v1/people-management/portal/ouvidoria-admin/{r[0]}/responder",
             "method": "POST", "btnLabel": "Responder", "submitLabel": "Enviar resposta",
             "btnStyle": "primary", "okMsg": "Resposta registrada. Recarregue a tela.",
             "fields": [
                 {"key": "resposta", "label": "Resposta ao colaborador*", "type": "textarea",
                  "span": "span 2", "value": ""},
                 {"key": "status", "label": "Novo status", "type": "select", "span": "span 2",
                  "value": "", "options": [{"value": "respondida", "label": "Respondida"},
                                           {"value": "encerrada", "label": "Encerrada"}]},
             ]},
        ]))

    return out
