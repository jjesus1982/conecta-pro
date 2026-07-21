"""Redesign builder — Departamento Pessoal.

Estende o `_build_dp` do monólito (base: visão, funcionários, folha, rubricas,
férias, benefícios, rescisão + ferramentas) e LIGA as 10 telas que estavam
sem wiring, lendo SEMPRE as MESMAS tabelas clássicas (dado real; vazio-real =
"aguardando dado", nunca mock).

Telas novas: admissao · aviso-previo · ponto · fechamento-ponto · licencas ·
reembolsos · contratos · documentos · certificacao · esocial.
"""

from modules.operacional.controllers.redesign_data_controller import (
    _build_dp,
    _helpers,
    b,
    brl,
    initials,
    t,
)

SLUG = "departamento-pessoal"
EXTRA_MENU: list[dict] = []

# datas: as tabelas usam date/timestamp; formatador defensivo local
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _badge_status(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "concluido", "concluida", "fechado", "fechada",
             "aprovado", "aprovada", "paga", "processed", "processada",
             "transmitida", "publicado", "published", "assinado"):
        return b(v or "—", "ok")
    if s in ("pendente", "em_andamento", "aguardando", "em_analise", "submitted",
             "nao_transmitida", "rascunho", "draft", "aberto"):
        return b(v or "—", "warn")
    if s in ("rejeitado", "reprovado", "cancelado", "erro", "vencido", "rejected"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


def _badge_bool(v, sim="Sim", nao="Não", tone_sim="ok", tone_nao="mut"):
    return b(sim, tone_sim) if v else b(nao, tone_nao)


async def build(db) -> dict:
    # Base = tudo que o _build_dp já entrega (telas VIVAS + ferramentas).
    out = await _build_dp(db)
    # tbl é apenas um construtor query→dict ligado a este db; safe local grava no `out` base.
    _out2, _safe2, tbl = _helpers(db)

    async def safe(key, coro):
        try:
            out[key] = await coro
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

    # 1) Admissão — admission_processes
    await safe("admissao", tbl(
        "Admissão", "Processos de admissão", "Nova admissão",
        ["Candidato", "Cargo", "Departamento", "Início previsto", "Status"],
        "2fr 1.4fr 1.2fr 1fr 0.9fr",
        "SELECT coalesce(candidate_name,'—'), coalesce(position,'—'), "
        "coalesce(department,'—'), expected_start_date, coalesce(status,'—') "
        "FROM admission_processes ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(r[2]),
                   t(_d(r[3])), _badge_status(r[4])]))

    # 2) Aviso prévio — employees em aviso (query real; hoje 0 = honesto "nenhum")
    await safe("aviso-previo", tbl(
        "Aviso prévio", "Colaboradores em aviso prévio", "—",
        ["Colaborador", "Cargo", "Admissão", "Situação"],
        "2fr 1.4fr 1fr 0.9fr",
        "SELECT nome, coalesce(cargo,'—'), data_admissao, status::text "
        "FROM employees WHERE status IN ('aviso_previo','aviso') ORDER BY nome LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]),
                   t(_d(r[2])), _badge_status(r[3])]))

    # 3) Ponto — gp_clock_punches
    await safe("ponto", tbl(
        "Ponto", "Últimas batidas", "—",
        ["Colaborador", "Tipo", "Data/hora", "Posto", "Facial"],
        "2fr 1fr 1.2fr 1.4fr 0.8fr",
        "SELECT coalesce(e.nome, p.employee_id::text), coalesce(p.punch_type,'—'), "
        "p.punch_timestamp, coalesce(p.posto_nome,'—'), p.facial_match "
        "FROM gp_clock_punches p LEFT JOIN employees e ON e.id = p.employee_id "
        "ORDER BY p.punch_timestamp DESC LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]),
                   t(_d(r[2], "%d/%m/%Y %H:%M")), t(r[3]),
                   _badge_bool(r[4], "OK", "—", "ok", "mut")]))

    # 4) Fechamento de ponto — gp_monthly_closings (employee_id é varchar → cast no join)
    await safe("fechamento-ponto", tbl(
        "Fechamento de ponto", "Espelhos mensais", "—",
        ["Colaborador", "Competência", "Horas", "Faltas", "Status"],
        "2fr 1fr 1fr 0.8fr 0.9fr",
        "SELECT coalesce(e.nome, c.employee_id), c.month, c.year, "
        "coalesce(c.total_horas_trabalhadas,0), coalesce(c.total_faltas,0), coalesce(c.fechado,false) "
        "FROM gp_monthly_closings c LEFT JOIN employees e ON e.id::text = c.employee_id "
        "ORDER BY c.year DESC, c.month DESC LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t(f"{(r[1] or 0):02d}/{r[2] or ''}"), t(f"{r[3]:.0f}h"),
                   t(str(r[4])), _badge_bool(r[5], "Fechado", "Aberto", "ok", "warn")]))

    # 5) Licenças / afastamentos — sst_afastamentos (nome/cargo denormalizados)
    await safe("licencas", tbl(
        "Licenças", "Afastamentos e licenças", "—",
        ["Colaborador", "Tipo", "CID", "Início", "Status"],
        "2fr 1.2fr 0.8fr 1fr 0.9fr",
        "SELECT coalesce(employee_nome,'—'), coalesce(tipo,'—'), coalesce(cid,'—'), "
        "data_inicio, coalesce(status,'—') FROM sst_afastamentos "
        "ORDER BY data_inicio DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t((r[1] or "—").replace("_", " ")), t(r[2]), t(_d(r[3])),
                   _badge_status(r[4])]))

    # 6) Reembolsos — reimbursement_requests
    await safe("reembolsos", tbl(
        "Reembolsos", "Solicitações de reembolso", "Solicitar reembolso",
        ["Código", "Título", "Valor", "Enviado", "Status"],
        "0.9fr 2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(code,'—'), coalesce(title,'—'), coalesce(total_amount,0), "
        "submitted_at, coalesce(status,'—') FROM reimbursement_requests "
        "WHERE coalesce(is_active,true) ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0]), t(r[1] or "—", 600, _ND), t(brl(r[2]), 600),
                   t(_d(r[3])), _badge_status(r[4])]))

    # 7) Contratos — employment_contracts
    await safe("contratos", tbl(
        "Contratos", "Contratos de trabalho", "—",
        ["Colaborador", "Tipo", "Cargo", "Início", "Salário base", "Vigente"],
        "1.8fr 1fr 1.3fr 1fr 1fr 0.8fr",
        "SELECT coalesce(e.nome,'—'), coalesce(c.type,'—'), coalesce(c.job_title,'—'), "
        "c.start_date, coalesce(c.base_salary,0), coalesce(c.is_current,false) "
        "FROM employment_contracts c LEFT JOIN employees e ON e.id = c.employee_id "
        "ORDER BY c.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(r[2]),
                   t(_d(r[3])), t(brl(r[4])),
                   _badge_bool(r[5], "Vigente", "Encerrado", "ok", "mut")]))

    # 8) Documentos — hr_employee_documents
    await safe("documentos", tbl(
        "Documentos", "Documentos dos colaboradores", "—",
        ["Colaborador", "Documento", "Tipo", "Status", "Publicado"],
        "1.6fr 1.8fr 1fr 0.9fr 0.8fr",
        "SELECT coalesce(e.nome,'—'), coalesce(d.title, d.file_name, '—'), "
        "coalesce(d.document_type,'—'), coalesce(d.status,'—'), coalesce(d.is_published,false) "
        "FROM hr_employee_documents d LEFT JOIN employees e ON e.id = d.employee_id "
        "ORDER BY d.created_at DESC LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]),
                   t((r[2] or "—").replace("_", " ")), _badge_status(r[3]),
                   _badge_bool(r[4], "Sim", "Não", "ok", "mut")]))

    # 9) Certificação — hr_certifications (certificação de cálculos DP)
    await safe("certificacao", tbl(
        "Certificação", "Certificação de cálculos", "—",
        ["Competência", "Tipo de cálculo", "Valor", "Divergência", "Status"],
        "1fr 1.6fr 1fr 1fr 0.9fr",
        "SELECT coalesce(competencia,'—'), coalesce(tipo_calculo,'—'), "
        "coalesce(calculado_valor,0), coalesce(divergencia,false), coalesce(status,'—') "
        "FROM hr_certifications ORDER BY competencia DESC NULLS LAST, created_at DESC LIMIT 300",
        lambda r: [t(r[0]), t((r[1] or "—").replace("_", " ")), t(brl(r[2])),
                   _badge_bool(r[3], "Sim", "Não", "bad", "ok"), _badge_status(r[4])]))

    # 10) eSocial — esocial_eventos_espelho (espelho do ambiente nacional)
    await safe("esocial", tbl(
        "eSocial", "Eventos transmitidos (espelho)", "—",
        ["Evento", "Tipo", "CPF", "Data evento", "Recibo"],
        "1.2fr 1fr 1.2fr 1fr 1.4fr",
        "SELECT coalesce(id_evento,'—'), coalesce(tipo,'—'), coalesce(cpf_trabalhador,'—'), "
        "dt_evento, coalesce(nr_recibo,'—') FROM esocial_eventos_espelho "
        "ORDER BY dt_evento DESC NULLS LAST, dt_recepcao DESC NULLS LAST LIMIT 300",
        lambda r: [t(r[0], 600, _ND), t(r[1]), t(r[2]), t(_d(r[3])), t(r[4])]))

    return out
