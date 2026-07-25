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
    doc,
    initials,
    t,
)

SLUG = "departamento-pessoal"
# Item de nav da tela de ação "Aviso prévio de férias" (form → gera doc). É SOMADO ao EXTRA_MENU
# global do slug (redesign_data_controller._discover_module_builders), sem tocar a fundação.
EXTRA_MENU: list[dict] = [
    {"id": "aviso-ferias", "label": "Aviso de férias",
     "icon": "M17 8C8 10 5.9 16.2 3.8 21.7c-.3.7.3 1.3 1 1L8 21c9-2 11-8 13-13M12 2v4M20 6l-2 2"},
    {"id": "contracheques-lote", "label": "Contracheques em lote",
     "icon": "M9 7h6M9 11h6M9 15h4M5 3h14a1 1 0 0 1 1 1v16H4V4a1 1 0 0 1 1-1z"},
    {"id": "nova-admissao", "label": "Nova admissão",
     "icon": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8M19 8v6M22 11h-6"},
]

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


_BEN_TYPE = {"vale_refeicao": "Vale Refeição", "vale_transporte": "Vale Transporte",
             "vr": "Vale Refeição", "vt": "Vale Transporte", "plano_saude": "Plano de Saúde",
             "plano_odontologico": "Plano Odontológico", "seguro_vida": "Seguro de Vida",
             "emprestimo_consignado": "Empréstimo Consignado"}


def _ben_type(v):
    return _BEN_TYPE.get((v or "").lower(), (v or "—").replace("_", " ").capitalize() if "_" in (v or "") else (v or "—"))


# Folha — espelha statusConfig do clássico (dp/folha/page.tsx): published→Calculada
_FOLHA_ST = {"published": ("Calculada", "ok"), "calculada": ("Calculada", "ok"),
             "calculated": ("Calculada", "ok"), "contested": ("Contestada", "warn"),
             "processing": ("Processando", "info"), "paid": ("Pago", "ok"),
             "draft": ("Rascunho", "mut"), "closed": ("Fechada", "ok")}


def _folha_status(v):
    lbl, tone = _FOLHA_ST.get((v or "").lower(), (v or "—", "info"))
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


# Licenças — espelha statusConfig + synonyms EN do clássico (dp/licencas/page.tsx)
_LIC_ST = {"ativo": ("Ativo", "info"), "ativa": ("Ativo", "info"), "active": ("Ativo", "info"),
           "em_andamento": ("Em Andamento", "warn"), "in_progress": ("Em Andamento", "warn"),
           "ongoing": ("Em Andamento", "warn"),
           "encerrado": ("Encerrado", "mut"), "encerrada": ("Encerrado", "mut"),
           "ended": ("Encerrado", "mut"), "closed": ("Encerrado", "mut"),
           "cancelado": ("Cancelado", "bad"), "cancelada": ("Cancelado", "bad"),
           "cancelled": ("Cancelado", "bad"), "canceled": ("Cancelado", "bad")}


def _lic_status(v):
    lbl, tone = _LIC_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Fechamento de ponto — MESMA derivação do painel do clássico (espelho_ponto_service.painel_fechamento):
# status fechado = enum ∈ STATUS_FECHADO; assinatura via sig_signature_requests.
_STATUS_FECHADO = {"fechado", "aprovado", "revisado", "enviado_folha"}


def _hm(minutes):
    m = int(minutes or 0)
    return f"{m // 60:02d}:{m % 60:02d}"


def _fech_status(status, anomalias, approved, sig_status, sig_signed):
    """Deriva o badge igual ao clássico: Homologado / Aguardando assinatura / Fechado / N anomalia(s) / Calculado."""
    fechado = (status or "").lower() in _STATUS_FECHADO
    assinado = bool(approved) or (str(sig_status or "").lower() in ("signed", "completed")) or bool(sig_signed)
    if fechado and assinado:
        return b("Homologado", "ok")
    if fechado and sig_status is not None:
        return b("Aguardando assinatura", "info")
    if fechado:
        return b("Fechado", "info")
    if (anomalias or 0) > 0:
        return b(f"{anomalias} anomalia(s)", "warn")
    return b("Calculado", "mut")


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


async def _rescisao_screen(db):
    """Rescisão — MESMA fonte (termination_processes) e MESMO cálculo do clássico:
    quando total_amount é NULL (todos hoje), o clássico computa ao vivo via
    service.calculate_severance. Replico isso (senão exibia R$ 0,00 = NULL como zero)."""
    from sqlalchemy import text as _sqltext
    rows = (await db.execute(_sqltext(
        "SELECT CAST(tp.employee_id AS TEXT), e.nome, tp.type::text, tp.status::text, "
        "tp.last_working_day, tp.total_amount, CAST(tp.id AS TEXT) "
        "FROM termination_processes tp LEFT JOIN employees e ON e.id=tp.employee_id "
        "ORDER BY tp.last_working_day DESC NULLS LAST, tp.created_at DESC LIMIT 200"))).all()
    svc = TT = None
    try:
        from modules.people_management.hr.services.termination_service import TerminationService
        from modules.people_management.hr.models.termination import TerminationType as _TT
        svc, TT = TerminationService(db), _TT
    except Exception:
        pass
    out_rows = []
    for emp_id, nome, tp_type, tp_status, lwd, total, tid in rows:
        val = float(total) if total not in (None,) else None
        if (val is None or val == 0) and svc and emp_id and lwd:
            try:
                try:
                    _tp = TT(tp_type)
                except Exception:
                    _tp = TT.INVOLUNTARY
                calc = await svc.calculate_severance(employee_id=emp_id, termination_type=_tp, last_working_day=lwd)
                v = calc.get("total_liquido") or calc.get("total_proventos")
                val = float(v) if v is not None else None
            except Exception:
                val = None
        out_rows.append({"cells": [
            t(nome or "—", 600, _ND, initials(nome or "")),
            t(_TERM_TYPE.get((tp_type or "").lower(), tp_type or "—")),
            _term_status(tp_status), t(_d(lwd)),
            t(brl(val) if val is not None else "a calcular", 600)],
            "docs": [
                doc("TRCT", f"/api/v1/people-management/hr/terminations/{tid}/trct/pdf", fmt="pdf", gate="dp"),
                doc("Aviso prévio", f"/api/v1/people-management/hr/terminations/{tid}/aviso-previo/pdf", fmt="pdf", gate="dp"),
            ]})
    return {"title": "Rescisão", "sub": "Processos de desligamento — tipo, status e verbas",
            "cta": "Nova rescisão", "type": "table", "searchHint": "Buscar…",
            "grid": "2fr 1.2fr 1fr 1fr 1.1fr",
            "cols": ["Colaborador", "Tipo", "Status", "Último Dia", "Valor Total"],
            "rows": out_rows}


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
        "SELECT nome, coalesce(cargo,'—'), data_admissao, status::text, " + _FALTANTES_SQL + " AS faltantes, "
        "CAST(id AS TEXT), coalesce(cpf,''), coalesce(email,''), coalesce(celular,''), coalesce(departamento,''), salario_base "
        "FROM employees WHERE status='ativo' ORDER BY nome LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(_d(r[2])),
                   _completude_cell(r[4]), _badge_status(r[3])],
        editfn=lambda r: {
            "title": f"Editar — {r[0]}",
            "endpoint": f"/api/v1/people-management/hr/employees/{r[5]}", "method": "PATCH",
            "fields": [
                {"key": "nome", "label": "Nome", "type": "text", "span": "span 2", "value": r[0] or ""},
                {"key": "cpf", "label": "CPF", "type": "text", "value": r[6] or ""},
                {"key": "cargo", "label": "Cargo", "type": "text", "value": (r[1] if r[1] != "—" else "")},
                {"key": "departamento", "label": "Departamento", "type": "text", "value": r[9] or ""},
                {"key": "email", "label": "E-mail", "type": "text", "value": r[7] or ""},
                {"key": "celular", "label": "Celular", "type": "text", "value": r[8] or ""},
                {"key": "salario_base", "label": "Salário base", "type": "text", "value": (str(r[10]) if r[10] is not None else "")},
            ],
        }))

    # 0b) Folha — SOBRESCREVE a base p/ trazer o BREAKDOWN do clássico (INSS/FGTS/Descontos),
    #     que o redesign perdeu (só mostrava base+líquido). Mesmas colunas do clássico.
    # Folha: TODAS as competências (ordenadas desc) + seletor de competência (filterCol=0).
    # r[12]=competência 'MM/YYYY'; a coluna 0 vira o filtro; per-linha Holerite/Recibo p/ qualquer mês.
    await safe("folha", tbl(
        "Folha de pagamento", "Proventos, encargos e descontos — selecione a competência", "—",
        ["Competência", "Colaborador", "Cargo", "Salário base", "INSS", "FGTS 8%", "Descontos", "Líquido", "Status"],
        "0.9fr 1.8fr 1.2fr 1fr 0.9fr 0.9fr 1fr 1fr 0.9fr",
        "SELECT e.nome, coalesce(e.cargo,'—'), p.base_salary, p.inss_value, p.fgts_value, "
        "p.total_deductions, p.net_salary, p.status::text, "
        "CAST(p.id AS TEXT), CAST(p.employee_id AS TEXT), p.reference_month, p.reference_year, "
        "to_char(make_date(p.reference_year, p.reference_month, 1),'MM/YYYY') "
        "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
        "ORDER BY p.reference_year DESC, p.reference_month DESC, e.nome LIMIT 500",
        lambda r: [t(r[12], 600, _ND), t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(brl(r[2])),
                   t(brl(r[3])), t(brl(r[4])), t(brl(r[5])), t(brl(r[6]), 600), _folha_status(r[7])],
        docsfn=lambda r: [
            doc("Holerite", f"/api/v1/people-management/dp/payslips/{r[8]}/pdf", fmt="pdf", gate="financeiro"),
            doc("Recibo VT/VR", f"/api/v1/people-management/folha/recibo-vt-vr/{r[9]}/{r[10]}/{r[11]}/pdf", fmt="pdf", gate="financeiro"),
        ]))
    # marca o seletor de competência (coluna 0) — o ModuleView renderiza o dropdown e filtra client-side
    if out.get("folha"):
        out["folha"]["filterCol"] = 0
        out["folha"]["filterLabel"] = "Competência"
    # Folha — docs de TELA (consolidada do mês + export Domínio), na última competência real
    try:
        from sqlalchemy import text as _sqltext
        _cmp = (await db.execute(_sqltext(
            "SELECT reference_month, reference_year FROM hr_payslips "
            "ORDER BY reference_year DESC, reference_month DESC LIMIT 1"))).first()
        if _cmp and out.get("folha"):
            _m, _a = int(_cmp[0]), int(_cmp[1])
            out["folha"]["docs"] = [
                doc("Folha consolidada (PDF)", f"/api/v1/people-management/folha/{_m}/{_a}/pdf", fmt="pdf", gate="financeiro"),
                doc("Export Domínio (TXT)", f"/api/v1/people-management/hr/payroll-export/dominio/{_a}-{_m:02d}", fmt="txt", gate="financeiro"),
            ]
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # 0c) Férias — SOBRESCREVE p/ traduzir o status (redesign mostrava cru SUBMITTED/APPROVED)
    #     e trazer a data de solicitação, como o clássico. Status derivado igual ao clássico:
    #     cancelled_at→Cancelado; APPROVED→Aprovado; senão Pendente.
    # MESMA fonte do clássico (/hr/vacations = hr_vacation_requests), NÃO employee_vacation_requests
    # (que a base usava e tem outro dataset). Tipo constante "Férias"; status via _fer_status (APPROVED→Aprovado).
    await safe("ferias", tbl(
        "Gestão de Férias", "Solicitações de férias dos colaboradores", "—",
        ["Colaborador", "Tipo", "Período", "Dias", "Status", "Criado em"],
        "1.8fr 0.9fr 1.6fr 0.6fr 1fr 1.1fr",
        "SELECT e.nome, h.start_date, h.end_date, h.days_requested, h.status::text, h.cancelled_at, "
        "to_char(h.created_at AT TIME ZONE 'America/Manaus','DD/MM/YYYY HH24:MI') AS criado "
        "FROM hr_vacation_requests h LEFT JOIN employees e ON e.id=h.employee_id "
        "ORDER BY h.created_at DESC LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t("Férias"),
                   t(f"{_d(r[1])} – {_d(r[2])}"), t(str(r[3] or "—")),
                   _fer_status(r[4], r[5]), t(r[6] or "—")]))

    # 0d) Benefícios — SOBRESCREVE p/ trazer operadora + valores (empresa/desconto) + vigência,
    #     que o clássico mostra e o redesign resumia (só tipo/plano/status). employee_benefits.
    await safe("beneficios", tbl(
        "Gestão de Benefícios", "Benefícios por colaborador — operadora, valores e vigência", "—",
        ["Colaborador", "Tipo", "Operadora", "Plano", "Empresa", "Desconto", "Vigência", "Status"],
        "1.7fr 1.1fr 1.1fr 1.1fr 0.8fr 0.8fr 1.2fr 0.9fr",
        "SELECT e.nome, coalesce(bf.type,'—'), coalesce(bf.provider,'—'), coalesce(bf.plan_name,'—'), "
        "bf.company_contribution, bf.employee_contribution, bf.start_date, bf.end_date, coalesce(bf.status,'—') "
        "FROM employee_benefits bf LEFT JOIN employees e ON e.id=bf.employee_id ORDER BY e.nome, bf.type LIMIT 400",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_ben_type(r[1])), t(r[2]), t(r[3]),
                   t(brl(r[4])), t(brl(r[5])),
                   t(f"{_d(r[6])} – {'Indeterminado' if not r[7] else _d(r[7])}"), _ben_status(r[8])]))

    # 0e) Rescisão — SOBRESCREVE p/ ler de termination_processes (MESMA fonte do clássico
    #     /terminations), com Tipo/Status/Valor. A base lia employees WHERE status='demitido'
    #     (fonte errada, sem valores). Colunas iguais ao clássico: Colaborador/Tipo/Status/Último Dia/Valor.
    await safe("rescisao", _rescisao_screen(db))

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
    # Ponto — registro DIÁRIO como o clássico (/hr/time-records): batidas de gp_clock_punches
    # pareadas por (colaborador, dia) → Entrada/Saída/Total. Não 1 linha por batida. Exclui homologação.
    # punch_timestamp é Manaus-local naive (writers usam now()) → NÃO converter fuso.
    _ENT = "lower(coalesce(punch_type,'')) LIKE 'entrada%'"
    _SAI = "(lower(coalesce(punch_type,'')) LIKE 'saida%' OR lower(coalesce(punch_type,'')) LIKE 'saída%')"
    await safe("ponto", tbl(
        "Ponto", "Registros diários — entrada, saída e total", "—",
        ["Colaborador", "Data", "Entrada", "Saída", "Total Horas"],
        "2fr 1fr 0.9fr 0.9fr 1fr",
        "SELECT e.nome, d.dia, d.entrada, d.saida, d.total_min FROM ("
        "  SELECT employee_id, (punch_timestamp)::date AS dia, "
        f"    min(punch_timestamp) FILTER (WHERE {_ENT}) AS entrada, "
        f"    max(punch_timestamp) FILTER (WHERE {_SAI}) AS saida, "
        f"    (extract(epoch FROM (max(punch_timestamp) FILTER (WHERE {_SAI}) "
        f"       - min(punch_timestamp) FILTER (WHERE {_ENT})))/60)::int AS total_min "
        "  FROM gp_clock_punches "
        "  WHERE employee_id NOT IN (SELECT id FROM employees WHERE coalesce(is_homologacao,false)=true) "
        "  GROUP BY employee_id, (punch_timestamp)::date"
        ") d LEFT JOIN employees e ON e.id = d.employee_id "
        "ORDER BY d.dia DESC, e.nome LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_d(r[1])),
                   t(r[2].strftime("%H:%M") if r[2] else "--:--"),
                   t(r[3].strftime("%H:%M") if r[3] else "--:--"),
                   t(_hm(r[4]) if (r[4] is not None and r[4] > 0) else "--:--")]))

    # 4) Fechamento de ponto — MESMA fonte do clássico (time_sheets via painel_fechamento), NÃO
    #    gp_monthly_closings. Última competência com dado; status derivado (Homologado/Aguardando
    #    assinatura/Fechado/N anomalia(s)/Calculado). Assinatura via sig_signature_requests. Exclui homologação.
    await safe("fechamento-ponto", tbl(
        "Fechamento de ponto", "Espelhos mensais — última competência", "—",
        ["Colaborador", "Posto", "Horas", "Extras", "Faltas", "Status"],
        "1.8fr 1.4fr 1fr 1fr 0.8fr 1.3fr",
        "SELECT ts.employee_name, coalesce(ts.condominium_name,'—'), ts.reference_year, ts.status, "
        "ts.hours_worked_minutes, ts.overtime_total_minutes, ts.absent_days, "
        "greatest(coalesce(ts.anomaly_count,0)-coalesce(ts.anomaly_resolved_count,0),0) AS anomalias, "
        "ts.approved_by_employee, sig.status AS sig_status, sig.signed_at AS sig_signed, "
        "CAST(ts.employee_id AS TEXT) AS emp, ts.reference_month AS mes, "
        # has_punches: só oferece a Folha de ponto (batidas) quando há batida na competência
        # (o endpoint folha-pdf 404 se vazio) — botão honesto, nunca quebrado.
        "EXISTS(SELECT 1 FROM gp_clock_punches gcp WHERE CAST(gcp.employee_id AS TEXT)=CAST(ts.employee_id AS TEXT) "
        "  AND to_char(gcp.punch_timestamp,'MM.YYYY')=to_char(make_date(ts.reference_year::int, ts.reference_month::int, 1),'MM.YYYY')) AS has_punches "
        "FROM time_sheets ts "
        "LEFT JOIN LATERAL (SELECT status, signed_at FROM sig_signature_requests s "
        "  WHERE s.document_type='espelho_ponto' AND s.signer_type='employee' "
        "  AND (CAST(s.document_id AS TEXT)=CAST(ts.id AS TEXT) "
        "       OR s.custom_fields->>'document_id_raw'=CAST(ts.id AS TEXT)) "
        "  ORDER BY s.created_at DESC LIMIT 1) sig ON true "
        "WHERE coalesce(ts.is_deleted,false)=false "
        "  AND (ts.reference_year, ts.reference_month) = (SELECT reference_year, reference_month "
        "       FROM time_sheets WHERE coalesce(is_deleted,false)=false "
        "       ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
        "  AND ts.employee_id NOT IN (SELECT CAST(id AS TEXT) FROM employees WHERE coalesce(is_homologacao,false)=true) "
        "ORDER BY ts.employee_name LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t(r[1] or "—"), t(_hm(r[4])), t(_hm(r[5])),
                   t(str(r[6] or 0)), _fech_status(r[3], r[7], r[8], r[9], r[10])],
        docsfn=lambda r: [doc("Espelho de ponto (671)", f"/api/v1/people-management/hr/ponto/espelho/{r[11]}/{r[12]}/{r[2]}/pdf", fmt="pdf", gate="dp")]
        + ([doc("Folha de ponto (batidas)", f"/api/v1/people-management/ponto/folha-pdf/{r[11]}/download?mes_ref={int(r[12]):02d}.{int(r[2])}", fmt="html", gate="dp")] if r[13] else [])))

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
                   _lic_status(r[4])]))

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
        "c.start_date, coalesce(c.base_salary,0), coalesce(c.is_current,false), CAST(c.id AS TEXT) "
        "FROM employment_contracts c LEFT JOIN employees e ON e.id = c.employee_id "
        "ORDER BY c.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_contract_type(r[1])), t(r[2]),
                   t(_d(r[3])), t(brl(r[4])),
                   _badge_bool(r[5], "Vigente", "Encerrado", "ok", "mut")],
        docsfn=lambda r: [doc("Contrato CLT", f"/api/v1/people-management/hr/contracts/{r[6]}/pdf", fmt="pdf", gate="dp")]))

    # 8) Documentos — hr_employee_documents
    await safe("documentos", tbl(
        "Documentos", "Documentos dos colaboradores", "—",
        ["Colaborador", "Documento", "Tipo", "Status", "Publicado"],
        "1.6fr 1.8fr 1fr 0.9fr 0.8fr",
        "SELECT coalesce(e.nome,'—'), coalesce(d.title, d.file_name, '—'), "
        "coalesce(d.document_type,'—'), coalesce(d.status,'—'), coalesce(d.is_published,false), "
        "CAST(d.id AS TEXT), nullif(trim(coalesce(d.file_path,'')),'') "
        "FROM hr_employee_documents d LEFT JOIN employees e ON e.id = d.employee_id "
        "ORDER BY d.created_at DESC LIMIT 300",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]),
                   t((r[2] or "—").replace("_", " ")), _doc_status(r[3]),
                   _badge_bool(r[4], "Sim", "Não", "ok", "mut")],
        docsfn=lambda r: ([doc("Documento", f"/api/v1/people-management/hr/documents/{r[5]}/download", fmt="pdf", gate="dp")]
                          if r[6] else [])))

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
    # eSocial — XML transmitido, mas SEM rota de preview/download no backend (só POST evento).
    # Honesto: botão desabilitado até o backend expor GET do XML (sinalizado ao orquestrador).
    if out.get("esocial"):
        out["esocial"]["docs"] = [doc("XML do evento", disabled=True,
                                      motivo="XML transmitido, sem rota de preview no backend — pendente criar GET do XML do evento")]

    # Aviso prévio de férias (form → gera doc). Só férias FUTURAS aprovadas/submetidas (o gerador
    # recusa data no passado). Select value = 'empId|YYYY-MM-DD|dias' → POST /redesign/action/aviso-
    # ferias → retorna {doc} p/ o FormScreen abrir (gancho d.doc). Sem digitação livre: dados reais
    # de hr_vacation_requests. Se não há férias futura, o select fica vazio (honesto, não fabrica).
    try:
        from sqlalchemy import text as _sqltext
        # Janela: férias recentes (últimos 120 dias) + futuras, aprovadas/submetidas. O gerador
        # aceita data passada (registro formal), então incluímos as já iniciadas (ex.: Francisco).
        _avf = (await db.execute(_sqltext(
            "SELECT v.employee_id, coalesce(e.nome,'—'), v.start_date, coalesce(v.days_requested,30) "
            "FROM hr_vacation_requests v LEFT JOIN employees e ON e.id=v.employee_id "
            "WHERE v.start_date IS NOT NULL "
            "AND v.start_date >= (now() AT TIME ZONE 'America/Manaus')::date - INTERVAL '120 days' "
            "AND upper(coalesce(v.status,'')) IN ('APPROVED','SUBMITTED') "
            "ORDER BY v.start_date DESC LIMIT 200"))).fetchall()
        _opts = [{"value": f"{r[0]}|{r[2].strftime('%Y-%m-%d')}|{int(r[3])}",
                  "label": f"{r[1]} · início {r[2].strftime('%d/%m/%Y')} · {int(r[3])}d"} for r in _avf]
        out["aviso-ferias"] = {
            "title": "Aviso prévio de férias",
            "sub": "Gera o Aviso Prévio de Férias (HTML) de uma férias aprovada — dados reais, abre ao gerar",
            "cta": "Gerar aviso", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/aviso-ferias", "okMsg": "Aviso prévio de férias gerado"},
            "fields": [
                {"key": "ferias", "label": "Férias (recentes e próximas)*", "type": "select", "span": "span 2",
                 "ph": "Selecione a férias" if _opts else "Nenhuma férias aprovada/submetida nos últimos 120 dias",
                 "options": _opts},
            ],
        }
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # Contracheques em lote (AÇÃO de efeito em massa: gera PDF de todos os ativos + arquiva GED +
    # publica eventos). Vai atrás de CONFIRMAÇÃO humana (submit.confirm). Competências = as que têm
    # folha (hr_payslips). Ligado ao fix do filtro status (case-insensitive) no payroll_export.
    try:
        from sqlalchemy import text as _sqltext
        _comps = (await db.execute(_sqltext(
            "SELECT DISTINCT reference_year, reference_month FROM hr_payslips "
            "WHERE reference_year IS NOT NULL "
            "ORDER BY reference_year DESC, reference_month DESC LIMIT 12"))).fetchall()
        _copts = [{"value": f"{int(r[0])}-{int(r[1]):02d}", "label": f"{int(r[1]):02d}/{int(r[0])}"} for r in _comps]
        out["contracheques-lote"] = {
            "title": "Contracheques em lote",
            "sub": "Gera o contracheque (PDF) de TODOS os funcionários ativos da competência e arquiva no GED",
            "cta": "Gerar contracheques", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/contracheques-batch",
                       "okMsg": "Contracheques gerados",
                       "confirm": "Isto gera o contracheque de TODOS os ativos da competência e arquiva no GED"},
            "fields": [
                {"key": "competencia", "label": "Competência*", "type": "select", "span": "span 2",
                 "ph": "Selecione a competência" if _copts else "Sem competência com folha registrada",
                 "options": _copts},
            ],
        }
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # Nova admissão — FORM que abre processo de admissão (POST /hr/admissions, dados básicos do
    # candidato). O restante do fluxo (documentos, exames, completar) segue na tela de admissão.
    out["nova-admissao"] = {
        "title": "Nova admissão", "type": "form",
        "sub": "Abrir processo de admissão — dados do candidato (documentos e exames no fluxo seguinte)",
        "cta": "Abrir admissão",
        "submit": {"endpoint": "/api/v1/people-management/hr/admissions", "okMsg": "Processo de admissão aberto"},
        "fields": [
            {"key": "candidate_name", "label": "Nome do candidato*", "type": "text", "span": "span 2", "ph": "Nome completo"},
            {"key": "cpf", "label": "CPF*", "type": "text", "span": "span 1", "ph": "000.000.000-00"},
            {"key": "birth_date", "label": "Nascimento", "type": "date", "span": "span 1"},
            {"key": "position", "label": "Cargo*", "type": "text", "span": "span 1", "ph": "Ex.: Agente de portaria"},
            {"key": "department", "label": "Departamento", "type": "text", "span": "span 1", "ph": "Opcional"},
            {"key": "salary_proposed", "label": "Salário proposto", "type": "text", "span": "span 1", "ph": "Ex.: 1670.00"},
            {"key": "expected_start_date", "label": "Início previsto", "type": "date", "span": "span 1"},
            {"key": "contract_type", "label": "Tipo de contrato", "type": "select", "span": "span 1",
             "ph": "CLT", "options": [{"value": "CLT", "label": "CLT"}, {"value": "PJ", "label": "PJ"},
                                      {"value": "Estágio", "label": "Estágio"}, {"value": "Temporário", "label": "Temporário"}]},
            {"key": "pis_pasep", "label": "PIS/PASEP", "type": "text", "span": "span 1", "ph": "Opcional"},
            {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional"},
        ],
    }
    # Religa os CTAs "Nova admissão" (estavam mortos, ctaTo=None) → apontam p/ o form nova-admissao.
    for _k in ("visao", "funcionarios", "admissao"):
        if out.get(_k) and (out[_k].get("cta") or "").lower().startswith("nova admiss"):
            out[_k]["ctaTo"] = "nova-admissao"

    # ── Task 4: religar os CTAs mortos restantes ─────────────────────────────
    # reembolsos: CTA "Solicitar reembolso" → form registrar-reembolso (JÁ existe no menu).
    if out.get("reembolsos") and not out["reembolsos"].get("ctaTo") and out.get("registrar-reembolso"):
        out["reembolsos"]["ctaTo"] = "registrar-reembolso"

    # rescisao: CTA "Nova rescisão" → novo form nova-rescisao (POST /hr/terminations, dado real).
    # employee_id = select de colaboradores ATIVOS (sem base de homologação). Verbas/TRCT/aviso
    # seguem no fluxo seguinte (docs por-linha já existem na tela de rescisão).
    try:
        from sqlalchemy import text as _sqltext
        _emp = (await db.execute(_sqltext(
            "SELECT id, nome FROM employees WHERE status='ativo' "
            "AND coalesce(is_homologacao,false)=false ORDER BY nome LIMIT 300"))).fetchall()
        _eopts = [{"value": str(r[0]), "label": r[1] or "—"} for r in _emp]
        out["nova-rescisao"] = {
            "title": "Nova rescisão", "type": "form",
            "sub": "Abrir processo de rescisão — verbas, TRCT e aviso prévio seguem no fluxo",
            "cta": "Abrir rescisão",
            "submit": {"endpoint": "/api/v1/people-management/hr/terminations",
                       "okMsg": "Processo de rescisão aberto",
                       "confirm": "Isto abre um processo FORMAL de rescisão para o colaborador selecionado"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
                 "ph": "Selecione o colaborador" if _eopts else "Nenhum colaborador ativo",
                 "options": _eopts},
                {"key": "type", "label": "Tipo de rescisão*", "type": "select", "span": "span 1",
                 "ph": "Selecione", "options": [
                     {"value": "involuntary", "label": "Dispensa sem justa causa"},
                     {"value": "voluntary", "label": "Pedido de demissão"},
                     {"value": "just_cause", "label": "Dispensa por justa causa"},
                     {"value": "mutual_agreement", "label": "Acordo mútuo (comum acordo)"},
                     {"value": "contract_end", "label": "Fim de contrato"},
                     {"value": "retirement", "label": "Aposentadoria"},
                 ]},
                {"key": "notice_type", "label": "Aviso prévio", "type": "select", "span": "span 1",
                 "ph": "—", "options": [
                     {"value": "trabalhado", "label": "Trabalhado"},
                     {"value": "indenizado", "label": "Indenizado"},
                 ]},
                {"key": "notice_period_days", "label": "Dias de aviso", "type": "text", "span": "span 1", "ph": "Ex.: 30"},
                {"key": "notice_start_date", "label": "Início do aviso", "type": "date", "span": "span 1"},
                {"key": "last_working_day", "label": "Último dia trabalhado", "type": "date", "span": "span 1"},
                {"key": "reason", "label": "Motivo", "type": "text", "span": "span 1", "ph": "Opcional"},
                {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional"},
            ],
        }
        if out.get("rescisao") and not out["rescisao"].get("ctaTo"):
            out["rescisao"]["ctaTo"] = "nova-rescisao"

        # ── Task 5: licencas — form "Registrar afastamento" (POST /hr/leaves, dado real).
        # Grava em sst_afastamentos (estabilidade acidentária derivada no backend). Tipos = enum
        # TipoAfastamento; reusa o mesmo select de colaboradores ativos (_eopts).
        out["nova-licenca"] = {
            "title": "Registrar afastamento", "type": "form",
            "sub": "Registra licença/afastamento do colaborador — estabilidade acidentária é derivada automaticamente",
            "cta": "Registrar afastamento",
            "submit": {"endpoint": "/api/v1/people-management/hr/leaves",
                       "okMsg": "Afastamento registrado"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
                 "ph": "Selecione o colaborador" if _eopts else "Nenhum colaborador ativo",
                 "options": _eopts},
                {"key": "leave_type", "label": "Tipo de afastamento*", "type": "select", "span": "span 1",
                 "ph": "Selecione", "options": [
                     {"value": "doenca", "label": "Doença (auxílio-doença)"},
                     {"value": "acidente_trabalho", "label": "Acidente de trabalho"},
                     {"value": "acidente_trajeto", "label": "Acidente de trajeto"},
                     {"value": "licenca_maternidade", "label": "Licença-maternidade"},
                     {"value": "licenca_paternidade", "label": "Licença-paternidade"},
                     {"value": "outro", "label": "Outro"},
                 ]},
                {"key": "cid", "label": "CID", "type": "text", "span": "span 1", "ph": "Ex.: S82 (opcional)"},
                {"key": "start_date", "label": "Início*", "type": "date", "span": "span 1"},
                {"key": "end_date", "label": "Fim previsto", "type": "date", "span": "span 1"},
                {"key": "motivo", "label": "Motivo/observação", "type": "textarea", "span": "span 2", "ph": "Opcional"},
            ],
        }
        if out.get("licencas") and not out["licencas"].get("ctaTo"):
            out["licencas"]["cta"] = "Registrar afastamento"
            out["licencas"]["ctaTo"] = "nova-licenca"
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    return out
