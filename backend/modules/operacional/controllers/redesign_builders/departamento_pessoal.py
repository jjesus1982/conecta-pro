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


# Completude do cadastro (S-2200) — MESMA fórmula do clássico (dp/funcionarios/page.tsx):
# 15 campos eSocial; % = preenchidos/15; mostra os campos faltantes (fidelidade).
_ESOCIAL_15 = 15


async def _scalar_dp(db):
    from sqlalchemy import text as _sqltext
    try:
        r = await db.execute(_sqltext("SELECT count(*) FROM employees WHERE status='ativo'"))
        return r.scalar() or 0
    except Exception:
        return 0


_BEN_ST = {"active": ("Ativo", "ok"), "ativo": ("Ativo", "ok"), "cancelled": ("Cancelado", "mut"),
           "canceled": ("Cancelado", "mut"), "cancelado": ("Cancelado", "mut"),
           "inactive": ("Inativo", "mut"), "suspended": ("Suspenso", "warn")}


def _ben_status(v):
    lbl, tone = _BEN_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _fer_status(status, cancelled_at):
    """Status de férias em PT, mesma derivação do clássico (enum é SUBMITTED/APPROVED)."""
    if cancelled_at:
        return b("Cancelado", "mut")
    s = (status or "").upper()
    if s == "APPROVED":
        return b("Aprovado", "ok")
    if s == "REJECTED":
        return b("Rejeitado", "bad")
    if s == "CANCELLED":
        return b("Cancelado", "mut")
    return b("Pendente", "warn")


# Rescisão — espelham tipoConfig/statusConfig do clássico (dp/rescisao/page.tsx)
_TERM_TYPE = {"voluntary": "Voluntária", "involuntary": "Involuntária", "just_cause": "Justa Causa",
              "mutual_agreement": "Acordo Mútuo", "contract_end": "Fim de Contrato",
              "retirement": "Aposentadoria"}
_TERM_ST = {"initiated": ("Iniciado", "info"), "notice_period": ("Aviso Prévio", "warn"),
            "calculating": ("Calculando", "warn"), "pending_payment": ("Pgto Pendente", "warn"),
            "completed": ("Concluída", "ok"), "cancelled": ("Cancelada", "mut")}


def _term_status(v):
    lbl, tone = _TERM_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Admissão/Onboarding — espelha statusConfig do clássico (dp/admissao/page.tsx)
_ADM_ST = {"documents_pending": ("Documentos Pendentes", "warn"), "medical_exam": ("Exame Médico", "info"),
           "contract_signing": ("Assinatura de Contrato", "warn"), "in_progress": ("Em Andamento", "info"),
           "completed": ("Concluída", "ok"), "cancelled": ("Cancelada", "mut")}


def _adm_status(v):
    lbl, tone = _ADM_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _cpf_fmt(v):
    d = "".join(ch for ch in (v or "") if ch.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}" if len(d) == 11 else (v or "—")


# Contratos — espelha contractTypeLabels do clássico (dp/contratos/page.tsx)
_CONTRACT_TYPE = {"clt_indeterminate": "CLT Indeterminado", "clt_determinate": "CLT Determinado",
                  "temporary": "Temporário", "internship": "Estágio", "apprentice": "Aprendiz",
                  "clt": "CLT"}


def _contract_type(v):
    return _CONTRACT_TYPE.get((v or "").lower(), v or "—")


# Documentos — espelha statusConfig do clássico (dp/documentos/page.tsx)
_DOC_ST = {"draft": ("Rascunho", "warn"), "active": ("Ativo", "ok"), "ativo": ("Ativo", "ok"),
           "valid": ("Válido", "ok"), "valido": ("Válido", "ok"), "expired": ("Vencido", "bad"),
           "vencido": ("Vencido", "bad"), "pending": ("Pendente", "warn"), "pendente": ("Pendente", "warn"),
           "archived": ("Arquivado", "mut")}


def _doc_status(v):
    lbl, tone = _DOC_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Reembolsos — espelha statusConfig do clássico (dp/reembolsos/page.tsx, PT + sinônimos EN)
_REI_ST = {"rascunho": ("Rascunho", "mut"), "pendente": ("Pendente", "warn"), "aprovado": ("Aprovado", "ok"),
           "rejeitado": ("Rejeitado", "bad"), "pago": ("Pago", "info"),
           "submitted": ("Pendente", "warn"), "pending": ("Pendente", "warn"), "approved": ("Aprovado", "ok"),
           "rejected": ("Rejeitado", "bad"), "paid": ("Pago", "info")}


def _rei_status(v):
    lbl, tone = _REI_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Certificação — espelha statusBadge do clássico (dp/certificacao/page.tsx)
_CERT_ST = {"pendente": ("Pendente", "warn"), "certificado": ("Certificado", "ok"),
            "rejeitado": ("Rejeitado", "bad")}


def _cert_status(v):
    lbl, tone = _CERT_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _completude_cell(faltantes):
    """faltantes = array (do SQL) com os rótulos dos campos vazios."""
    fal = [x for x in (faltantes or []) if x]
    pct = round((_ESOCIAL_15 - len(fal)) / _ESOCIAL_15 * 100)
    if not fal:
        return t("100% · completo", 600, "#0E7C57")
    lbl = ", ".join(fal[:3]) + (f" +{len(fal) - 3}" if len(fal) > 3 else "")
    cor = "#0E7C57" if pct >= 80 else "#B4690E" if pct >= 50 else "#DC2626"
    return t(f"{pct}% · {lbl}", 600, cor)


# SQL que devolve os rótulos faltantes (ordem/nomes iguais ao FIELD_LABELS do clássico)
_FALTANTES_SQL = (
    "array_remove(ARRAY["
    "CASE WHEN nullif(trim(coalesce(nome,'')),'') IS NULL THEN 'Nome' END,"
    "CASE WHEN nullif(trim(coalesce(cpf,'')),'') IS NULL THEN 'CPF' END,"
    "CASE WHEN data_nascimento IS NULL THEN 'Data de Nascimento' END,"
    "CASE WHEN nullif(trim(coalesce(sexo,'')),'') IS NULL THEN 'Sexo' END,"
    "CASE WHEN nullif(trim(coalesce(estado_civil,'')),'') IS NULL THEN 'Estado Civil' END,"
    "CASE WHEN nullif(trim(coalesce(nome_mae,'')),'') IS NULL THEN 'Nome da Mãe' END,"
    "CASE WHEN nullif(trim(coalesce(rg,'')),'') IS NULL THEN 'RG' END,"
    "CASE WHEN nullif(trim(coalesce(pis,'')),'') IS NULL THEN 'PIS/PASEP' END,"
    "CASE WHEN nullif(trim(coalesce(ctps_numero,'')),'') IS NULL THEN 'CTPS Número' END,"
    "CASE WHEN nullif(trim(coalesce(nacionalidade,'')),'') IS NULL THEN 'Nacionalidade' END,"
    "CASE WHEN nullif(trim(coalesce(naturalidade,'')),'') IS NULL THEN 'Naturalidade' END,"
    "CASE WHEN nullif(trim(coalesce(cep,'')),'') IS NULL THEN 'CEP' END,"
    "CASE WHEN nullif(trim(coalesce(logradouro,'')),'') IS NULL THEN 'Logradouro' END,"
    "CASE WHEN nullif(trim(coalesce(cidade,'')),'') IS NULL THEN 'Cidade' END,"
    "CASE WHEN nullif(trim(coalesce(uf,'')),'') IS NULL THEN 'UF' END"
    "], NULL)"
)


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

    # 0) Funcionários — SOBRESCREVE a tela base p/ trazer a COMPLETUDE do cadastro (%/faltantes),
    #    que o clássico mostra e o redesign não (fidelidade). Mesma fórmula: 15 campos S-2200.
    await safe("funcionarios", tbl(
        "Funcionários", f"{await _scalar_dp(db)} ativos", "Nova admissão",
        ["Colaborador", "Cargo", "Admissão", "Cadastro (eSocial)", "Status"],
        "2fr 1.3fr 1fr 1.7fr 0.9fr",
        "SELECT nome, coalesce(cargo,'—'), data_admissao, status::text, " + _FALTANTES_SQL + " AS faltantes "
        "FROM employees WHERE status='ativo' ORDER BY nome LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(_d(r[2])),
                   _completude_cell(r[4]), _badge_status(r[3])]))

    # 0b) Folha — SOBRESCREVE a base p/ trazer o BREAKDOWN do clássico (INSS/FGTS/Descontos),
    #     que o redesign perdeu (só mostrava base+líquido). Mesmas colunas do clássico.
    await safe("folha", tbl(
        "Folha de pagamento", "Última competência — proventos, encargos e descontos", "—",
        ["Colaborador", "Cargo", "Salário base", "INSS", "FGTS 8%", "Descontos", "Líquido", "Status"],
        "1.8fr 1.3fr 1fr 0.9fr 0.9fr 1fr 1fr 0.9fr",
        "SELECT e.nome, coalesce(e.cargo,'—'), p.base_salary, p.inss_value, p.fgts_value, "
        "p.total_deductions, p.net_salary, p.status::text "
        "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
        "WHERE (p.reference_year,p.reference_month)=(SELECT reference_year,reference_month FROM hr_payslips "
        "ORDER BY reference_year DESC, reference_month DESC LIMIT 1) ORDER BY e.nome LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(brl(r[2])),
                   t(brl(r[3])), t(brl(r[4])), t(brl(r[5])), t(brl(r[6]), 600), _badge_status(r[7])]))

    # 0c) Férias — SOBRESCREVE p/ traduzir o status (redesign mostrava cru SUBMITTED/APPROVED)
    #     e trazer a data de solicitação, como o clássico. Status derivado igual ao clássico:
    #     cancelled_at→Cancelado; APPROVED→Aprovado; senão Pendente.
    await safe("ferias", tbl(
        "Gestão de Férias", "Solicitações de férias dos colaboradores", "—",
        ["Colaborador", "Período", "Dias", "Status", "Solicitado em"],
        "2fr 1.8fr 0.6fr 1fr 1.1fr",
        "SELECT e.nome, r.start_date, r.end_date, r.days_requested, r.status::text, r.cancelled_at, "
        "(coalesce(r.submitted_at, r.created_at) AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus') AS sol "
        "FROM employee_vacation_requests r LEFT JOIN employees e ON e.id=r.employee_id "
        "ORDER BY coalesce(r.submitted_at, r.created_at) DESC LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t(f"{_d(r[1])} – {_d(r[2])}"), t(str(r[3] or "—")),
                   _fer_status(r[4], r[5]), t(_d(r[6], "%d/%m/%Y %H:%M"))]))

    # 0d) Benefícios — SOBRESCREVE p/ trazer operadora + valores (empresa/desconto) + vigência,
    #     que o clássico mostra e o redesign resumia (só tipo/plano/status). employee_benefits.
    await safe("beneficios", tbl(
        "Gestão de Benefícios", "Benefícios por colaborador — operadora, valores e vigência", "—",
        ["Colaborador", "Tipo", "Operadora", "Plano", "Empresa", "Desconto", "Vigência", "Status"],
        "1.7fr 1.1fr 1.1fr 1.1fr 0.8fr 0.8fr 1.2fr 0.9fr",
        "SELECT e.nome, coalesce(bf.type,'—'), coalesce(bf.provider,'—'), coalesce(bf.plan_name,'—'), "
        "bf.company_contribution, bf.employee_contribution, bf.start_date, bf.end_date, coalesce(bf.status,'—') "
        "FROM employee_benefits bf LEFT JOIN employees e ON e.id=bf.employee_id ORDER BY e.nome, bf.type LIMIT 400",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(r[2]), t(r[3]),
                   t(brl(r[4])), t(brl(r[5])),
                   t(f"{_d(r[6])} – {'Indeterminado' if not r[7] else _d(r[7])}"), _ben_status(r[8])]))

    # 0e) Rescisão — SOBRESCREVE p/ ler de termination_processes (MESMA fonte do clássico
    #     /terminations), com Tipo/Status/Valor. A base lia employees WHERE status='demitido'
    #     (fonte errada, sem valores). Colunas iguais ao clássico: Colaborador/Tipo/Status/Último Dia/Valor.
    await safe("rescisao", tbl(
        "Rescisão", "Processos de desligamento — tipo, status e verbas", "Nova rescisão",
        ["Colaborador", "Tipo", "Status", "Último Dia", "Valor Total"],
        "2fr 1.2fr 1fr 1fr 1.1fr",
        "SELECT e.nome, tp.type::text, tp.status::text, tp.last_working_day, tp.total_amount "
        "FROM termination_processes tp LEFT JOIN employees e ON e.id=tp.employee_id "
        "ORDER BY tp.last_working_day DESC NULLS LAST, tp.created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t(_TERM_TYPE.get((r[1] or "").lower(), r[1] or "—")),
                   _term_status(r[2]), t(_d(r[3])), t(brl(r[4]), 600)]))

    # 1) Admissão — admission_processes
    await safe("admissao", tbl(
        "Admissão", "Processos de admissão", "Nova admissão",
        ["Candidato", "CPF", "Cargo", "Departamento", "Início previsto", "Status"],
        "1.8fr 1.1fr 1.3fr 1.1fr 1fr 0.9fr",
        "SELECT coalesce(candidate_name,'—'), cpf, coalesce(position,'—'), "
        "coalesce(department,'—'), expected_start_date, coalesce(status,'—') "
        "FROM admission_processes ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_cpf_fmt(r[1])),
                   t(r[2]), t(r[3]), t(_d(r[4])), _adm_status(r[5])]))

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
                   t(_d(r[3])), _rei_status(r[4])]))

    # 7) Contratos — employment_contracts
    await safe("contratos", tbl(
        "Contratos", "Contratos de trabalho", "—",
        ["Colaborador", "Tipo", "Cargo", "Início", "Salário base", "Vigente"],
        "1.8fr 1fr 1.3fr 1fr 1fr 0.8fr",
        "SELECT coalesce(e.nome,'—'), coalesce(c.type,'—'), coalesce(c.job_title,'—'), "
        "c.start_date, coalesce(c.base_salary,0), coalesce(c.is_current,false) "
        "FROM employment_contracts c LEFT JOIN employees e ON e.id = c.employee_id "
        "ORDER BY c.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_contract_type(r[1])), t(r[2]),
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
                   t((r[2] or "—").replace("_", " ")), _doc_status(r[3]),
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
                   _badge_bool(r[3], "Sim", "Não", "bad", "ok"), _cert_status(r[4])]))

    # 10) eSocial — esocial_eventos_espelho (espelho do ambiente nacional)
    await safe("esocial", tbl(
        "eSocial", "Eventos transmitidos (espelho)", "—",
        ["Evento", "Tipo", "Colaborador", "CPF", "Data evento", "Recibo"],
        "1.2fr 0.8fr 1.6fr 1.1fr 1fr 1.4fr",
        "SELECT coalesce(ev.id_evento,'—'), coalesce(ev.tipo,'—'), e.nome, ev.cpf_trabalhador, "
        "ev.dt_evento, coalesce(ev.nr_recibo,'—') FROM esocial_eventos_espelho ev "
        "LEFT JOIN employees e ON regexp_replace(coalesce(e.cpf,''),'\\D','','g') "
        "= regexp_replace(coalesce(ev.cpf_trabalhador,''),'\\D','','g') "
        "ORDER BY ev.dt_evento DESC NULLS LAST, ev.dt_recepcao DESC NULLS LAST LIMIT 300",
        lambda r: [t(r[0], 600, _ND), t(r[1]),
                   t(r[2] or "—", 600, _ND, initials(r[2] or "")), t(_cpf_fmt(r[3])),
                   t(_d(r[4])), t(r[5])]))

    return out
