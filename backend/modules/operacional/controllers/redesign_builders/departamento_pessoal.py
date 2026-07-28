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
    {"id": "fechar-mes-ponto", "label": "Fechar mês (ponto)",
     "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"},
    {"id": "importar-cadastro", "label": "Importar cadastro (CSV)",
     "icon": "M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"},
    {"id": "nova-admissao", "label": "Nova admissão",
     "icon": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8M19 8v6M22 11h-6"},
    {"id": "sync-ferias-solides", "label": "Sincronizar férias (Sólides)",
     "icon": "M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16"},
    {"id": "prestadores-pj", "label": "Prestadores PJ",
     "icon": "M9 7a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM3 20v-1a6 6 0 0 1 12 0v1M16 3.13a4 4 0 0 1 0 7.75M21 20v-1a6 6 0 0 0-4-5.65"},
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


# Prestadores PJ — status do autocadastro (gerador de link). pj_ativo = autocadastro concluído
# pela pessoa; qualquer outro (pj_pendente etc.) = link ainda aguardando preenchimento.
def _pj_status(v):
    return b("Concluído", "ok") if (v or "").lower() == "pj_ativo" else b("Aguardando", "warn")


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
    # AÇÃO por-linha "Gerir" = altera SÓ o status do benefício (PATCH /benefits/{id} {status})
    # — Ativo/Suspenso/Cancelado. Single-field (sem risco de clobber/422 de data/float vazios).
    await safe("beneficios", tbl(
        "Gestão de Benefícios", "Benefícios por colaborador — operadora, valores e vigência", "—",
        ["Colaborador", "Tipo", "Operadora", "Plano", "Empresa", "Desconto", "Vigência", "Status"],
        "1.7fr 1.1fr 1.1fr 1.1fr 0.8fr 0.8fr 1.2fr 0.9fr",
        "SELECT e.nome, coalesce(bf.type,'—'), coalesce(bf.provider,'—'), coalesce(bf.plan_name,'—'), "
        "bf.company_contribution, bf.employee_contribution, bf.start_date, bf.end_date, "
        "coalesce(bf.status,'—'), CAST(bf.id AS TEXT) "
        "FROM employee_benefits bf LEFT JOIN employees e ON e.id=bf.employee_id ORDER BY e.nome, bf.type LIMIT 400",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_ben_type(r[1])), t(r[2]), t(r[3]),
                   t(brl(r[4])), t(brl(r[5])),
                   t(f"{_d(r[6])} – {'Indeterminado' if not r[7] else _d(r[7])}"), _ben_status(r[8])],
        actionsfn=lambda r: [
            {
                "title": f"Benefício — {r[0] or '—'} ({_ben_type(r[1])})",
                "endpoint": f"/api/v1/people-management/hr/benefits/{r[9]}",
                "method": "PATCH", "btnLabel": "Gerir", "submitLabel": "Salvar status",
                "okMsg": "Benefício atualizado. Recarregue a tela.",
                "fields": [
                    {"key": "status", "label": "Status do benefício", "type": "select", "span": "span 2",
                     "value": (r[8] or "active"), "options": [
                         {"value": "active", "label": "Ativo"},
                         {"value": "suspended", "label": "Suspenso"},
                         {"value": "cancelled", "label": "Cancelado"}]},
                ]},
            {
                "title": f"Remover benefício — {r[0] or '—'}",
                "endpoint": f"/api/v1/people-management/hr/benefits/{r[9]}",
                "method": "DELETE", "btnLabel": "Remover", "btnStyle": "outline",
                "submitLabel": "Remover", "okMsg": "Benefício removido. Recarregue a tela.",
                "fields": []},
        ]))

    # 0e) Rescisão — SOBRESCREVE p/ ler de termination_processes (MESMA fonte do clássico
    #     /terminations), com Tipo/Status/Valor. A base lia employees WHERE status='demitido'
    #     (fonte errada, sem valores). Colunas iguais ao clássico: Colaborador/Tipo/Status/Último Dia/Valor.
    await safe("rescisao", _rescisao_screen(db))

    # 1) Admissão — admission_processes
    # AÇÃO por-linha "Concluir" (POST /admissions/{id}/complete) — CRIA o Employee e dispara
    # onboarding/GEDEON. Só p/ status ≠ cancelada/concluída. Form pré-preenchido do candidato
    # (nome/cpf/depto do processo); cargo/salário/datas o backend deriva da admissão + CCT.
    await safe("admissao", tbl(
        "Admissão", "Processos de admissão", "Nova admissão",
        ["Candidato", "CPF", "Cargo", "Departamento", "Início previsto", "Status"],
        "1.8fr 1.1fr 1.3fr 1.1fr 1fr 0.9fr",
        "SELECT coalesce(candidate_name,'—'), cpf, coalesce(position,'—'), "
        "coalesce(department,'—'), expected_start_date, coalesce(status,'—'), CAST(id AS TEXT) "
        "FROM admission_processes ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_cpf_fmt(r[1])),
                   t(r[2]), t(r[3]), t(_d(r[4])), _adm_status(r[5])],
        editfn=lambda r: ({"title": f"Concluir admissão — {r[0] or '—'}",
                           "endpoint": f"/api/v1/people-management/hr/admissions/{r[6]}/complete",
                           "method": "POST", "btnLabel": "Concluir", "submitLabel": "Concluir admissão",
                           "btnStyle": "primary", "okMsg": "Admissão concluída — colaborador criado. Recarregue.",
                           "fields": [
                               {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2", "value": r[0] or ""},
                               {"key": "cpf", "label": "CPF*", "type": "text", "span": "span 1", "value": r[1] or ""},
                               {"key": "departamento", "label": "Departamento", "type": "text", "span": "span 1",
                                "value": (r[3] if r[3] not in (None, "—") else "")},
                               {"key": "email", "label": "E-mail", "type": "text", "span": "span 1", "value": ""},
                               {"key": "telefone", "label": "Telefone", "type": "text", "span": "span 1", "value": ""},
                               {"key": "matricula", "label": "Matrícula", "type": "text", "span": "span 1", "value": ""},
                           ]}
                          if (r[5] or "").lower() not in ("cancelled", "cancelada", "completed", "concluida", "concluída") else None)))

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
    # AÇÃO por-linha "Propor transmissão eSocial (S-2230)": afastamento = fonte do S-2230.
    # Chama o hook do T1 (propor→sino→humano aprova+OTP+transmite no fluxo SST). SÓ PROPÕE,
    # NUNCA transmite. referencia = id do afastamento (idempotência c/ tipo_evento); empresa
    # derivada do colaborador (só mostra o botão se houver empresa). Gate=T3/T1 (Fase 5.4).
    await safe("licencas", tbl(
        "Licenças", "Afastamentos e licenças", "—",
        ["Colaborador", "Tipo", "CID", "Início", "Status"],
        "2fr 1.2fr 0.8fr 1fr 0.9fr",
        "SELECT coalesce(a.employee_nome,'—'), coalesce(a.tipo,'—'), coalesce(a.cid,'—'), "
        "a.data_inicio, coalesce(a.status,'—'), CAST(a.id AS TEXT), CAST(e.empresa_id AS TEXT), "
        "CAST(a.employee_id AS TEXT) FROM sst_afastamentos a "
        "LEFT JOIN employees e ON e.id = a.employee_id "
        "ORDER BY a.data_inicio DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                   t((r[1] or "—").replace("_", " ")), t(r[2]), t(_d(r[3])),
                   _lic_status(r[4])],
        actionsfn=lambda r: ([{
            "title": f"Propor transmissão eSocial (S-2230) — {r[0] or '—'}",
            "endpoint": "/api/v1/consultores/mcp/propor-esocial-sst",
            "method": "POST", "btnLabel": "Propor eSocial", "btnStyle": "outline",
            "submitLabel": "Propor transmissão",
            "okMsg": "Proposta enviada ao sino — aguardando aprovação humana. Nada foi transmitido ao governo.",
            "fixed": {"tipo_evento": "S-2230", "referencia": f"afast-{r[5]}",
                      "empresa_id": r[6], "employee_id": r[7]},
            "fields": []}] if r[6] else None)))

    # 6) Reembolsos — reimbursement_requests
    # Reembolsos — reimbursement_requests. AÇÕES por-linha "Aprovar" + "Analisar" só p/ status 'pendente'
    # (POST /reimbursements/{id}/approve → move p/ 'aprovado'; POST /reimbursements/{id}/analyze → move p/ 'em_analise';
    # NÃO paga — pagamento é passo separado, OTP-gated, T1). Mesma tabela do display e do endpoint (id bate, sem mismatch).
    # Anexos (attachments) deferred — reimbursement_attachments vazio (0 rows); docsfn/upload adiam para T4 refine.
    await safe("reembolsos", tbl(
        "Reembolsos", "Solicitações de reembolso", "Solicitar reembolso",
        ["Código", "Título", "Valor", "Enviado", "Status"],
        "0.9fr 2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(code,'—'), coalesce(title,'—'), coalesce(total_amount,0), "
        "submitted_at, coalesce(status,'—'), CAST(id AS TEXT) FROM reimbursement_requests "
        "WHERE coalesce(is_active,true) ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0]), t(r[1] or "—", 600, _ND), t(brl(r[2]), 600),
                   t(_d(r[3])), _rei_status(r[4])],
        actionsfn=lambda r: (
            [
                {"title": f"Aprovar reembolso {r[0]}",
                 "endpoint": f"/api/v1/reimbursements/{r[5]}/approve",
                 "method": "POST", "btnLabel": "Aprovar", "submitLabel": "Aprovar",
                 "btnStyle": "primary", "okMsg": "Reembolso aprovado. Recarregue a tela.",
                 "fields": []},
                {"title": f"Analisar reembolso {r[0]}",
                 "endpoint": f"/api/v1/reimbursements/{r[5]}/analyze",
                 "method": "POST", "btnLabel": "Analisar", "btnStyle": "outline",
                 "submitLabel": "Analisar", "okMsg": "Reembolso em análise. Recarregue a tela.",
                 "fields": []},
            ] if (r[4] or "").lower() == "pendente" else None)))

    # 7) Contratos — employment_contracts
    # AÇÕES por-linha "Gerar contrato" + "Gerar aviso-prévio de férias": geradores de documento
    # (POST /contracts/employee/{employee_id}/gerar-*-html → salva HTML em /uploads e devolve ref).
    # O doc gerado fica disponível no fluxo de download; sucesso confirma. employee_id = r[7].
    await safe("contratos", tbl(
        "Contratos", "Contratos de trabalho", "—",
        ["Colaborador", "Tipo", "Cargo", "Início", "Salário base", "Vigente"],
        "1.8fr 1fr 1.3fr 1fr 1fr 0.8fr",
        "SELECT coalesce(e.nome,'—'), coalesce(c.type,'—'), coalesce(c.job_title,'—'), "
        "c.start_date, coalesce(c.base_salary,0), coalesce(c.is_current,false), CAST(c.id AS TEXT), "
        "CAST(c.employee_id AS TEXT) "
        "FROM employment_contracts c LEFT JOIN employees e ON e.id = c.employee_id "
        "ORDER BY c.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(_contract_type(r[1])), t(r[2]),
                   t(_d(r[3])), t(brl(r[4])),
                   _badge_bool(r[5], "Vigente", "Encerrado", "ok", "mut")],
        docsfn=lambda r: [doc("Contrato CLT", f"/api/v1/people-management/hr/contracts/{r[6]}/pdf", fmt="pdf", gate="dp")],
        actionsfn=lambda r: ([
            {"title": f"Gerar contrato de trabalho — {r[0] or '—'}",
             "endpoint": f"/api/v1/people-management/hr/contracts/employee/{r[7]}/gerar-contrato-html",
             "method": "POST", "btnLabel": "Gerar contrato", "btnStyle": "outline",
             "submitLabel": "Gerar contrato", "okMsg": "Contrato gerado — disponível no download/GED.", "fields": []},
            {"title": f"Gerar aviso-prévio de férias — {r[0] or '—'}",
             "endpoint": f"/api/v1/people-management/hr/contracts/employee/{r[7]}/gerar-aviso-previo-ferias-html",
             "method": "POST", "btnLabel": "Gerar aviso férias", "btnStyle": "outline",
             "submitLabel": "Gerar aviso", "okMsg": "Aviso-prévio de férias gerado.", "fields": []},
        ] if r[7] else None)))

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
    # AÇÃO por-linha "Certificar" (PATCH /certifications/{id}/certify) só p/ status 'pendente'.
    # Assinatura humana (rastreável: quem/quando/hash). RBAC CERTIFIER_ROLES é imposto no backend.
    await safe("certificacao", tbl(
        "Certificação", "Certificação de cálculos", "—",
        ["Competência", "Tipo de cálculo", "Valor", "Divergência", "Status"],
        "1fr 1.6fr 1fr 1fr 0.9fr",
        "SELECT coalesce(competencia,'—'), coalesce(tipo_calculo,'—'), "
        "coalesce(calculado_valor,0), coalesce(divergencia,false), coalesce(status,'—'), CAST(id AS TEXT) "
        "FROM hr_certifications ORDER BY competencia DESC NULLS LAST, created_at DESC LIMIT 300",
        lambda r: [t(r[0]), t((r[1] or "—").replace("_", " ")), t(brl(r[2])),
                   _badge_bool(r[3], "Sim", "Não", "bad", "ok"), _cert_status(r[4])],
        actionsfn=lambda r: (
            [
                {"title": f"Certificar — {r[0]} · {(r[1] or '').replace('_', ' ')}",
                 "endpoint": f"/api/v1/people-management/certifications/{r[5]}/certify",
                 "method": "PATCH", "btnLabel": "Certificar", "submitLabel": "Assinar certificação",
                 "btnStyle": "primary", "okMsg": "Certificação assinada. Recarregue a tela.",
                 "fields": [{"key": "observacao", "label": "Observação (opcional)",
                             "type": "textarea", "span": "span 2", "value": ""}]},
                {"title": f"Rejeitar certificação — {r[0]}",
                 "endpoint": f"/api/v1/people-management/certifications/{r[5]}/reject",
                 "method": "PATCH", "btnLabel": "Rejeitar", "btnStyle": "outline",
                 "submitLabel": "Rejeitar", "okMsg": "Certificação rejeitada. Recarregue a tela.",
                 "fields": [{"key": "observacao", "label": "Motivo (obrigatório)", "type": "textarea",
                             "span": "span 2", "value": ""}]}
            ] if (r[4] or "").lower() == "pendente" else None)))

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

    # ── Task 7: Prestadores PJ — GERADOR de link de autocadastro (RH/admin). Lê a MESMA fonte do
    #    endpoint clássico (GET /prestadores-pj): employees tipo_contrato='pj' com token gerado.
    #    AÇÃO por-linha "Regenerar link" (POST .../{id}/regenerar-link, sem body) — útil se o link
    #    vazou; o backend recusa se já concluído (pj_ativo), então a ação some pra esses (honesto,
    #    evita 409 óbvio). CTA da tela abre o form de cadastro (ctaTo="novo-prestador-pj").
    await safe("prestadores-pj", tbl(
        "Prestadores PJ", "Prestadores PJ com link de autocadastro gerado", "Novo prestador",
        ["Prestador", "Papel", "Empresa", "Status", "CNPJ", "Cadastro"],
        "2fr 1.1fr 1.3fr 1fr 1.1fr 1fr",
        "SELECT e.id::text, e.nome, coalesce(e.papel_pj,'—'), coalesce(e.status,'—'), "
        "coalesce(e.cnpj, case when e.cnpj_pendente then 'pendente' else '—' end), "
        "e.autocadastro_token, coalesce(emp.nome_fantasia,'—'), e.created_at "
        "FROM employees e LEFT JOIN empresas emp ON emp.id=e.empresa_id "
        "WHERE e.tipo_contrato='pj' AND e.autocadastro_token IS NOT NULL "
        "ORDER BY e.created_at DESC NULLS LAST LIMIT 300",
        lambda r: [t(r[1] or "—", 600, _ND, initials(r[1] or "")), t(r[2]), t(r[6]),
                   _pj_status(r[3]), t(r[4]), t(_d(r[7]))],
        actionsfn=lambda r: (
            [{"title": f"Regenerar link — {r[1] or '—'}",
              "endpoint": f"/api/v1/people-management/human-resources/prestadores-pj/{r[0]}/regenerar-link",
              "method": "POST", "btnLabel": "Regenerar link", "btnStyle": "outline",
              "submitLabel": "Regenerar link",
              "okMsg": "Link regenerado. Recarregue a tela.", "fields": []}]
            if (r[3] or "").lower() != "pj_ativo" else None)))
    if out.get("prestadores-pj"):
        out["prestadores-pj"]["ctaTo"] = "novo-prestador-pj"

    # Novo prestador PJ — form (POST /prestadores-pj, NovoPrestadorBody: nome*/empresa*/papel/cpf).
    # empresa = slug fixo (_EMPRESAS no controller) — 2 opções reais (Eletrônica/Patrimonial), o
    # backend seta empresa_id EXPLÍCITO (nunca o DEFAULT cego). Devolve o link pronto (gerado no
    # backend); a tela recarrega e o prestador aparece na tabela acima com o link pra recopiar.
    out["novo-prestador-pj"] = {
        "title": "Novo prestador PJ", "type": "form",
        "sub": "Cadastra um prestador PJ e gera o link de autocadastro",
        "cta": "Cadastrar",
        "submit": {"endpoint": "/api/v1/people-management/human-resources/prestadores-pj",
                   "okMsg": "Prestador cadastrado"},
        "fields": [
            {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2", "ph": "Nome completo"},
            {"key": "empresa", "label": "Empresa*", "type": "select", "span": "span 1", "ph": "Selecione",
             "options": [
                 {"value": "eletronica", "label": "Conecta Mais Eletrônica"},
                 {"value": "patrimonial", "label": "Conecta Mais Patrimonial"},
             ]},
            {"key": "papel", "label": "Papel/Função", "type": "text", "span": "span 1", "ph": "Opcional"},
            {"key": "cpf", "label": "CPF", "type": "text", "span": "span 1", "ph": "Opcional"},
        ],
    }

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

        # ── Task 8: Fechar mês de ponto (AÇÃO de efeito em massa, irreversível).
        # Closes the timekeeping month for all active employees. Requires confirmation before firing.
        # Mês/ano são selects fixos (NÃO usa _copts) — a competência de ponto independe da folha.
        out["fechar-mes-ponto"] = {
            "title": "Fechar mês (ponto)",
            "sub": "Fecha o ponto de TODOS os colaboradores ativos na competência — ação de efeito em massa, praticamente irreversível. Horários no fuso de Manaus (UTC no banco).",
            "cta": "Fechar mês", "type": "form",
            "submit": {"endpoint": "/api/v1/people-management/ponto/fechamento-mes",
                       "okMsg": "Mês de ponto fechado",
                       "confirm": "Isto FECHA o ponto de TODOS os ativos na competência selecionada. Confirme para prosseguir."},
            "fields": [
                {"key": "mes", "label": "Mês*", "type": "select", "span": "span 1",
                 "ph": "Selecione o mês", "options": [
                     {"value": "1", "label": "Janeiro"}, {"value": "2", "label": "Fevereiro"},
                     {"value": "3", "label": "Março"}, {"value": "4", "label": "Abril"},
                     {"value": "5", "label": "Maio"}, {"value": "6", "label": "Junho"},
                     {"value": "7", "label": "Julho"}, {"value": "8", "label": "Agosto"},
                     {"value": "9", "label": "Setembro"}, {"value": "10", "label": "Outubro"},
                     {"value": "11", "label": "Novembro"}, {"value": "12", "label": "Dezembro"}]},
                {"key": "ano", "label": "Ano*", "type": "select", "span": "span 1",
                 "ph": "Selecione o ano", "options": [
                     {"value": "2026", "label": "2026"}, {"value": "2025", "label": "2025"}]},
            ],
        }

        # Gerar certificações em lote (fila hr_certifications de TODOS os holerites da competência,
        # idempotente). Mesma lista de competências com folha (_copts, já buscada acima). AÇÃO de
        # efeito em massa → confirmação humana (submit.confirm), handler fino rd_action_cert_gerar_folha.
        out["gerar-certificacoes"] = {
            "title": "Gerar certificações",
            "sub": "Gera a fila de certificações da folha de uma competência (idempotente)",
            "cta": "Gerar", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/cert-gerar-folha",
                       "okMsg": "Certificações geradas",
                       "confirm": "Isto gera a fila de certificações de TODOS os holerites da competência"},
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

    # Religa o CTA da tela "fechamento-ponto" (estava "—") → aponta p/ o form fechar-mes-ponto.
    # Só religa se o form-alvo existir (se o try acima abortou, não cria CTA morto).
    if out.get("fechamento-ponto") and not out["fechamento-ponto"].get("ctaTo") and out.get("fechar-mes-ponto"):
        out["fechamento-ponto"]["cta"] = "Fechar mês"
        out["fechamento-ponto"]["ctaTo"] = "fechar-mes-ponto"

    # Religa o CTA da tela "certificacao" (estava "—") → aponta p/ o form gerar-certificacoes.
    if out.get("certificacao") and not out["certificacao"].get("ctaTo") and out.get("gerar-certificacoes"):
        out["certificacao"]["cta"] = "Gerar certificações"
        out["certificacao"]["ctaTo"] = "gerar-certificacoes"

    # Sincronizar férias do Sólides (gatilho direto, sem params — o endpoint real aceita
    # periodo_inicio/periodo_fim opcionais via query; fields=[] = form de confirmação só).
    out["sync-ferias-solides"] = {
        "title": "Sincronizar férias do Sólides",
        "sub": "Importa/atualiza as solicitações de férias a partir do Sólides",
        "cta": "Sincronizar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/hr/vacations/sync-solides",
                   "okMsg": "Férias sincronizadas",
                   "confirm": "Isto busca e atualiza as férias a partir do Sólides"},
        "fields": [],
    }

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

        # ── Task 3: beneficios — form "Adicionar benefício" (POST /hr/benefits, BenefitCreate).
        # employee_id = mesmo select de colaboradores ativos (_eopts). type = BenefitType enum.
        out["nova-beneficio"] = {
            "title": "Adicionar benefício", "type": "form",
            "sub": "Cadastra um benefício para o colaborador",
            "cta": "Adicionar benefício",
            "submit": {"endpoint": "/api/v1/people-management/hr/benefits",
                       "okMsg": "Benefício adicionado"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
                 "ph": "Selecione o colaborador" if _eopts else "Nenhum colaborador ativo",
                 "options": _eopts},
                {"key": "type", "label": "Tipo de benefício*", "type": "select", "span": "span 1",
                 "ph": "Selecione", "options": [
                     {"value": "vale_transporte", "label": "Vale-transporte"},
                     {"value": "vale_refeicao", "label": "Vale-refeição"},
                     {"value": "vale_alimentacao", "label": "Vale-alimentação"},
                     {"value": "plano_saude", "label": "Plano de saúde"},
                     {"value": "plano_odontologico", "label": "Plano odontológico"},
                     {"value": "seguro_vida", "label": "Seguro de vida"},
                     {"value": "auxilio_creche", "label": "Auxílio-creche"},
                     {"value": "gym_pass", "label": "Gympass"},
                     {"value": "other", "label": "Outro"},
                 ]},
                {"key": "provider", "label": "Operadora", "type": "text", "span": "span 1", "ph": "Opcional"},
                {"key": "plan_name", "label": "Plano", "type": "text", "span": "span 1", "ph": "Opcional"},
                {"key": "company_contribution", "label": "Valor empresa", "type": "text", "span": "span 1", "ph": "Ex.: 150.00"},
                {"key": "employee_contribution", "label": "Valor desconto", "type": "text", "span": "span 1", "ph": "Ex.: 50.00"},
                {"key": "start_date", "label": "Início", "type": "date", "span": "span 1"},
                {"key": "end_date", "label": "Fim (vigência)", "type": "date", "span": "span 1"},
                {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional"},
            ],
        }
        if out.get("beneficios") and not out["beneficios"].get("ctaTo"):
            out["beneficios"]["cta"] = "Adicionar benefício"
            out["beneficios"]["ctaTo"] = "nova-beneficio"

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

        # ── Task 5: ferias — reconcilia p/ tabela CANÔNICA hr_vacation_requests. A base lia a
        # legada employee_vacation_requests, cujo id NÃO bate com /vacations/{id}/approve (approve
        # grava hr_vacation_requests) → aprovar por ali erraria o registro. Aqui LÊ a canônica e
        # liga a AÇÃO por-linha "Aprovar" (POST /vacations/{id}/approve) só p/ SUBMITTED.
        # Aprovar dispara kit GEDEON no backend → happy-path NÃO testado (provado por 404 em id fake).
        _FER_ST = {"submitted": ("Pendente", "warn"), "approved": ("Aprovada", "ok"),
                   "rejected": ("Rejeitada", "bad"), "cancelled": ("Cancelada", "mut"),
                   "canceled": ("Cancelada", "mut")}

        def _fer_row(r):
            lbl, tone = _FER_ST.get((r[5] or "").lower(), (r[5] or "—", "info"))
            return [t(r[1] or "—", 600, _ND, initials(r[1] or "")), t(_d(r[2])), t(_d(r[3])),
                    t(str(r[4]) if r[4] is not None else "—"), b(lbl, tone)]

        # Task 1: Aprovar + Rejeitar por-linha (actionsfn substitui editfn — mesma condição SUBMITTED,
        # 2 botões em vez de 1). Rejeitar chama o handler fino rd_action_vacation_reject (id vai na
        # query ?vid= do endpoint, motivo vai no body {reason} preenchido pelo modal).
        def _fer_acts(r):
            if (r[5] or "").upper() != "SUBMITTED":
                return None
            aprovar = {"title": f"Aprovar férias de {r[1] or '—'}",
                       "endpoint": f"/api/v1/people-management/hr/vacations/{r[0]}/approve",
                       "method": "POST", "btnLabel": "Aprovar", "submitLabel": "Aprovar",
                       "btnStyle": "primary", "okMsg": "Férias aprovadas. Recarregue a tela.",
                       "fields": []}
            rejeitar = {"title": f"Rejeitar férias de {r[1] or '—'}",
                        "endpoint": f"/api/v1/redesign/action/vacation-reject?vid={r[0]}",
                        "method": "POST", "btnLabel": "Rejeitar", "submitLabel": "Rejeitar",
                        "btnStyle": "outline", "okMsg": "Férias rejeitada",
                        "fields": [
                            {"key": "reason", "label": "Motivo (obrigatório)", "type": "textarea",
                             "span": "span 2", "value": ""},
                        ]}
            return [aprovar, rejeitar]

        _n_fer = (await db.execute(_sqltext("SELECT count(*) FROM hr_vacation_requests"))).scalar() or 0
        await safe("ferias", tbl(
            "Férias", f"{_n_fer} solicitações (fonte canônica)", "Solicitar férias",
            ["Colaborador", "Início", "Fim", "Dias", "Status"], "2fr 1fr 1fr 0.6fr 1fr",
            "SELECT v.id, coalesce(e.nome,'—'), v.start_date, v.end_date, v.days_requested, "
            "coalesce(v.status::text,'—') FROM hr_vacation_requests v "
            "LEFT JOIN employees e ON e.id=v.employee_id ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
            _fer_row, actionsfn=_fer_acts))
        if out.get("ferias") and not out["ferias"].get("ctaTo"):
            out["ferias"]["ctaTo"] = "solicitar-ferias"

        # ── Task 5: documentos — form de UPLOAD multipart → GED (mesmo endpoint/pasta do clássico:
        # /ged/documents/upload, folder Funcionários, category 'rh'). DP anexa doc de qualquer
        # colaborador ativo. document_type = valores REAIS do enum DocumentType (sem rg/cpf).
        out["nova-documento"] = {
            "title": "Enviar documento", "type": "form",
            "sub": "Anexa um documento ao colaborador — arquiva no GED (pasta Funcionários)",
            "cta": "Enviar documento",
            "submit": {"endpoint": "/api/v1/ged/documents/upload", "okMsg": "Documento enviado",
                       "multipart": True, "titleFromFile": True,
                       "fixed": {"folder_id": "abcbebd2-88af-419e-8907-43b11f38f90b", "category": "rh"}},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2",
                 "ph": "Selecione o colaborador" if _eopts else "Nenhum colaborador ativo", "options": _eopts},
                {"key": "document_type", "label": "Tipo*", "type": "select", "span": "span 1", "ph": "Selecione",
                 "options": [
                     {"value": "comprovante", "label": "Comprovante (RG/CPF/residência)"},
                     {"value": "contrato", "label": "Contrato"},
                     {"value": "certidao", "label": "Certidão"},
                     {"value": "laudo", "label": "Laudo/ASO"},
                     {"value": "outro", "label": "Outro"}]},
                {"key": "valid_until", "label": "Validade", "type": "date", "span": "span 1"},
                {"key": "file", "label": "Arquivo*", "type": "file", "span": "span 2", "accept": ".pdf,.jpg,.jpeg,.png"},
                {"key": "description", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional"},
            ],
        }
        if out.get("documentos") and not out["documentos"].get("ctaTo"):
            out["documentos"]["cta"] = "Enviar documento"
            out["documentos"]["ctaTo"] = "nova-documento"

        # ── Task 6: funcionarios — form "Importar cadastro" (multipart CSV upload).
        # POST /api/v1/people-management/hr/employees/import-cadastro — arquivo CSV do contador/Onvio.
        # Reusa FormScreen type:file + submit.multipart (já baked). Sem campos fixos.
        out["importar-cadastro"] = {
            "title": "Importar cadastro",
            "type": "form",
            "sub": "Importa colaboradores a partir de uma planilha CSV (contador/Onvio)",
            "cta": "Importar",
            "submit": {
                "endpoint": "/api/v1/people-management/hr/employees/import-cadastro",
                "okMsg": "Cadastro importado",
                "multipart": True,
                "confirm": "Isto importa/atualiza colaboradores a partir da planilha"
            },
            "fields": [
                {"key": "file", "label": "Planilha CSV*", "type": "file", "span": "span 2", "accept": ".csv"}
            ],
        }

        # ── Task 5: visao drilldown — KPIs viram clicáveis → tela de detalhe (frontend DashScreen
        # navega com k.to). Aditivo: KPI sem 'to' continua não-clicável.
        _kpi_to = {"colaboradores ativos": "funcionarios", "folha líquida": "folha",
                   "solicitações de férias": "ferias", "admissões em processo": "admissao"}
        _v = out.get("visao")
        if _v and isinstance(_v.get("kpis"), list):
            for _k in _v["kpis"]:
                _lbl = (_k.get("l") or "").lower()
                for _pref, _dest in _kpi_to.items():
                    if _lbl.startswith(_pref) and out.get(_dest):
                        _k["to"] = _dest
                        break
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    return out
