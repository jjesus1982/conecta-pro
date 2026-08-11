"""
redesign_builders/empresas.py — T4.
Sobrescreve _build_empresas: reusa a base e ADICIONA demonstrativos (faturamento
por competência), rentabilidade (clientes por MRR/receita), liminares fiscais e
migrador (segmentação CNPJ1→CNPJ2). Só leitura — migração é curada pelo Jordan.
"""
from fastapi import APIRouter, Body, Depends, HTTPException  # noqa: F401
from sqlalchemy import text  # noqa: F401

from core.auth.dependencies import CurrentActiveUser, require_permission  # noqa: F401
from core.database import get_db  # noqa: F401
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _build_empresas as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    doc,
    initials,
    t,
)

SLUG = "empresas"

EXTRA_MENU: list[dict] = [
    {"id": "nova-liminar", "label": "Nova Liminar", "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 15h6M9 11h6"},
    {"id": "resumo-contabil", "label": "Resumo contábil do mês", "icon": "M3 3v18h18M7 16l4-4 3 3 5-6"},
    {"id": "gerar-docs-mes", "label": "Gerar documentos do mês", "icon": "M12 4v16m8-8H4"},
    {"id": "assinar-holerites", "label": "Assinar holerites", "icon": "M9 12h6m-6 4h6m2 5H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"},
    {"id": "assinar-espelhos", "label": "Assinar espelhos de ponto", "icon": "M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0z"},
    {"id": "assinar-recibos", "label": "Assinar recibos VT/VR", "icon": "M4 4h16v12H5.17L4 17.17V4zm4 4h8M8 11h5"},
    {"id": "assinar-documentos", "label": "Assinar — outros", "icon": "M15.232 5.232l3.536 3.536M4 20h4l10.5-10.5a2.5 2.5 0 0 0-3.536-3.536L4.5 16.5V20z"},
    {"id": "documentos-assinados", "label": "Documentos assinados", "icon": "M9 12l2 2 4-4M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z"},
    {"id": "ciencia-comunicados", "label": "Ciência dos comunicados", "icon": "M17 20h5v-2a4 4 0 0 0-3-3.87M9 20H4v-2a4 4 0 0 1 3-3.87m6-1.13a4 4 0 1 0-4-4 4 4 0 0 0 4 4z"},
    {"id": "reorganizacao-juridico", "label": "Reorganização (jurídico)", "icon": "M3 6l9-4 9 4M4 10v8m16-8v8M2 18h20M8 10v5m4-5v5m4-5v5"},
    {"id": "empresas-lista", "label": "Empresas do grupo", "icon": "M3 21h18M5 21V7l7-4 7 4v14M9 9h.01M9 13h.01M9 17h.01M15 9h.01M15 13h.01M15 17h.01"},
]


def _obr_tone(s):
    return {"atrasada": "bad", "pendente": "warn", "concluida": "ok", "concluída": "ok"}.get((s or "").lower(), "info")


def _pdf_valido(path: str | None) -> bool:
    """True se document_path aponta para um PDF REAL no disco (assinável em ICP-Brasil).
    Assinatura qualificada precisa do PDF; sem arquivo (ou corrompido) não há o que assinar."""
    import os as _os

    if not path or not _os.path.exists(path):
        return False
    try:
        with open(path, "rb") as _fh:
            return _fh.read(5).startswith(b"%PDF")
    except Exception:  # noqa: BLE001
        return False


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- Obrigações fiscais multi-empresa (reusa o MESMO agente do clássico
    #      /empresas/obrigacoes/calendario/grupo — computação pura, 0ms, A5-safe) ----
    try:
        from datetime import date as _date
        from modules.empresas.agents.obligations_monitor import ObligationsMonitorAgent
        _h = _date.today()
        _cal = ObligationsMonitorAgent().gerar_calendario_grupo(_h.month, _h.year)
        out["obrigacoes"] = {
            "title": "Obrigações fiscais (multi-empresa)",
            "sub": f"{_cal.total_obrigacoes} obrigações · Atrasadas {_cal.atrasadas} · Pendentes {_cal.pendentes} · Concluídas {_cal.concluidas}",
            "cta": "—", "type": "table", "searchHint": "Buscar…",
            "grid": "1.4fr 1.2fr 2fr 1fr 1fr", "cols": ["Empresa", "Tipo", "Descrição", "Vencimento", "Status"],
            "rows": [{"cells": [
                t(o.empresa_nome, 600, "#0F1B3A"), b((o.tipo or "—").replace("_", " "), "info"),
                t(o.descricao), t(o.data_vencimento.strftime("%d/%m/%Y") if o.data_vencimento else "—"),
                b((o.status or "—").capitalize(), _obr_tone(o.status)),
            ]} for o in _cal.consolidado],
        }
    except Exception:  # noqa: BLE001 — nunca quebra o módulo
        await db.rollback()

    # ---- Demonstrativos (faturamento NFS-e por competência — DRE-ish real) ----
    await safe("demonstrativos", tbl(
        "Demonstrativos", "Faturamento por competência (NFS-e emitidas)",
        "—", ["Competência", "NFS-e", "Faturado", "Líquido"], "1.2fr 1fr 1.2fr 1.2fr",
        "SELECT coalesce(competencia,'—'), count(*), coalesce(sum(valor_servicos),0), coalesce(sum(valor_liquido),0) "
        "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false GROUP BY competencia ORDER BY competencia DESC LIMIT 24",
        lambda r: [t(r[0], 600, "#0F1B3A"), b(f"{r[1]}", "info"), t(brl(r[2]), 600), t(brl(r[3]))]))
    # Demonstrativos em PDF: REUSA as rotas reais do financeiro (marca Conecta, gerar_relatorio_pdf),
    # que servem a empresa principal do grupo (Eletrônica/Lucro Real). Rotas curl-provadas 200 pdf.
    from datetime import date as _dt
    _ano = _dt.today().year
    if "demonstrativos" in out and isinstance(out["demonstrativos"], dict):
        out["demonstrativos"]["docs"] = [
            doc("DRE (PDF)", f"/api/v1/financial/relatorios/dre/pdf?ano={_ano}", fmt="pdf", gate="financeiro"),
            doc("Balancete (PDF)", f"/api/v1/financial/relatorios/balancete/pdf?ano={_ano}", fmt="pdf", gate="financeiro"),
            doc("Fluxo de Caixa (PDF)", f"/api/v1/financial/relatorios/fluxo-caixa/pdf?ano={_ano}", fmt="pdf", gate="financeiro"),
        ]

    # ---- Rentabilidade (clientes por MRR/receita/health) ----
    await safe("rentabilidade", tbl(
        "Rentabilidade", "Rentabilidade por cliente (MRR × receita)",
        "—", ["Cliente", "MRR", "Receita total", "Health"], "2fr 1fr 1.2fr 1fr",
        "SELECT name, coalesce(mrr,0), coalesce(total_revenue,0), health_score FROM clients WHERE ativo=true ORDER BY mrr DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(brl(r[1]), 600), t(brl(r[2])),
                   b(f"{float(r[3]):.0f}" if r[3] is not None else '—',
                     "ok" if (r[3] or 0) >= 70 else ("warn" if (r[3] or 0) >= 40 else "bad"))]))

    # ---- Liminares (fiscal_liminares) ----
    await safe("liminares", tbl(
        "Liminares", f"{await _scalar(db, 'SELECT count(*) FROM fiscal_liminares')} liminares fiscais",
        "—", ["Empresa", "Tributo", "Descrição", "Processo", "Status"], "1.2fr 1fr 2.2fr 1.3fr 0.9fr",
        "SELECT coalesce(empresa,'—'), coalesce(tributo,'—'), coalesce(descricao, tipo, '—'), coalesce(processo,'—'), coalesce(status,'—') "
        "FROM fiscal_liminares ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').upper(), "info"), t(r[2]),
                   t(r[3]), b((r[4] or '—').capitalize(), "ok" if (r[4] or '').lower() in ("deferida", "ativa", "vigente") else "warn")]))

    # ---- Migrador (segmentação CNPJ1→CNPJ2 por tipo de contrato — visibilidade) ----
    await safe("migrador", tbl(
        "Migrador CNPJ", "Segmentação de colaboradores para migração CNPJ1→CNPJ2 (curada pelo Jordan)",
        "—", ["Tipo de contrato", "Colaboradores"], "2fr 1fr",
        "SELECT coalesce(tipo_contrato,'—'), count(*) FROM employees WHERE is_active=true GROUP BY tipo_contrato ORDER BY count(*) DESC",
        lambda r: [t((r[0] or '—').upper(), 600, "#0F1B3A"), b(f"{r[1]} colaboradores", "info")]))
    # Export Domínio: plano de contas é GET real (curl 200 text/plain) → botão TXT ligado.
    # Lançamentos/NFS-e Domínio são POST com payload HARDCODED (sem dados reais no GET) e o
    # "Exportar Agora" do clássico não tem onClick → botões honestos off.
    if "migrador" in out:
        out["migrador"]["docs"] = [
            doc("Plano de contas (Domínio TXT)", "/api/v1/empresas/dominio/download/plano-contas/conectamais", fmt="txt"),
            doc("Lançamentos Domínio (indisponível)", disabled=True,
                motivo="Export por POST com payload hardcoded — sem dados reais para baixar"),
            doc("NFS-e Domínio (indisponível)", disabled=True,
                motivo="Export por POST com payload hardcoded — sem dados reais para baixar"),
        ]

    # ---- ESCRITA op_write: registrar liminar (aditivo, sem dinheiro/OTP) ----
    out["nova-liminar"] = {
        "title": "Nova Liminar", "sub": "Registrar uma liminar/decisão tributária (escrita real)",
        "cta": "Registrar liminar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/nova-liminar", "okMsg": "Liminar registrada."},
        "fields": [
            {"key": "tributo", "label": "Tributo*", "type": "text", "span": "span 1", "ph": "PIS/COFINS, INSS, ISS…"},
            {"key": "empresa", "label": "Empresa", "type": "text", "span": "span 1", "ph": "Patrimonial / Eletrônica"},
            {"key": "tipo", "label": "Tipo", "type": "text", "span": "span 1", "ph": "liminar / decisão"},
            {"key": "processo", "label": "Processo", "type": "text", "span": "span 1", "ph": "nº do processo"},
            {"key": "descricao", "label": "Descrição*", "type": "textarea", "span": "span 2", "ph": "Base legal / o que a liminar garante"},
        ],
    }

    # ---- ASSINAR DOCUMENTOS DA EMPRESA (COMPANY) — assinatura qualificada ICP-Brasil ----
    # Lista as solicitações COMPANY pendentes (comunicado/contrato/…) e deixa o Jordan
    # assinar com o cert A1 do CNPJ (Patrimonial/Eletrônica, resolvido no assinador).
    # Trava OTP humano (e-mail ao Jordan) — a assinatura da razão social é ato sensível.
    _pend_raw = (await db.execute(text(
        "SELECT r.id::text, r.title, coalesce(r.document_type,'—'), to_char(r.created_at,'DD/MM/YYYY'), coalesce(r.document_path,'') "
        "FROM sig_signature_requests r WHERE r.signer_type='company' AND upper(coalesce(r.status,''))='PENDING' "
        "ORDER BY r.created_at DESC LIMIT 500"))).fetchall()
    # Só documentos com PDF REAL no disco são assináveis. Agrupa POR TIPO em telas separadas.
    _pend = [p for p in _pend_raw if _pdf_valido(p[4])]

    def _tela_assinar(bucket, titulo, tag):
        _o = [{"value": p[0], "label": p[1]} for p in bucket]
        if _o:
            _o = [{"value": f"__ALL__:{tag}", "label": f"⚡ TODOS ({len(bucket)}) — assinar em lote"}] + _o
        return {
            "title": titulo,
            "sub": (f"{len(bucket)} documento(s) aguardando a sua assinatura (empresa, ICP-Brasil A1). "
                    "Selecione um ou 'TODOS' para assinar em lote; o código OTP chega no e-mail ao confirmar. "
                    "Veja o PDF de cada um nos botões abaixo."
                    if bucket else "Nenhum documento deste tipo aguardando a sua assinatura no momento."),
            "cta": "Assinar como empresa", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/assinar-doc-empresa",
                       "okMsg": "Documento assinado pela empresa (ICP-Brasil)."},
            "fields": [
                {"key": "documento", "label": "Documento a assinar*", "type": "select", "span": "span 2",
                 "options": _o, "ph": "Selecione o documento"},
                {"key": "otp_code", "label": "Código OTP (chega no seu e-mail após confirmar)", "type": "text",
                 "span": "span 2", "ph": "Deixe em branco na 1ª vez — o código é enviado ao confirmar"},
            ],
            "docs": [doc(f"Ver: {(p[1] or '')[:44]}",
                         f"/api/v1/redesign/action/documento-empresa/{p[0]}", fmt="pdf")
                     for p in bucket],
        }

    _hol = [p for p in _pend if p[2] == "payslip"]
    _esp = [p for p in _pend if p[2] == "espelho_ponto"]
    _rec = [p for p in _pend if p[2] == "recibo_vt_vr"]
    _oth = [p for p in _pend if p[2] not in ("payslip", "espelho_ponto", "recibo_vt_vr")]
    out["assinar-holerites"] = _tela_assinar(_hol, "Assinar holerites", "payslip")
    out["assinar-espelhos"] = _tela_assinar(_esp, "Assinar espelhos de ponto", "espelho_ponto")
    out["assinar-recibos"] = _tela_assinar(_rec, "Assinar recibos de VT/VR", "recibo_vt_vr")
    out["assinar-documentos"] = _tela_assinar(_oth, "Assinar — outros documentos", "outros")

    # ---- DOCUMENTOS JÁ ASSINADOS PELA EMPRESA (baixar o PDF assinado ICP-Brasil) ----
    _ass = (await db.execute(text(
        "SELECT r.id::text, r.title, coalesce(r.document_type,'—'), "
        "to_char(coalesce(r.signed_at, r.updated_at),'DD/MM/YYYY HH24:MI'), "
        "(r.signed_document_path IS NOT NULL) "
        "FROM sig_signature_requests r WHERE r.signer_type='company' "
        "AND upper(coalesce(r.status,'')) IN ('SIGNED','COMPLETED') "
        "ORDER BY coalesce(r.signed_at, r.updated_at) DESC NULLS LAST LIMIT 200"))).fetchall()
    out["documentos-assinados"] = {
        "title": "Documentos assinados (empresa)",
        "sub": f"{len(_ass)} documento(s) assinados pela empresa (ICP-Brasil A1). Baixe o PDF assinado.",
        "cta": "—", "type": "table", "searchHint": "Buscar documento…",
        "grid": "2.6fr 1fr 1.3fr", "cols": ["Documento", "Tipo", "Assinado em"],
        "rows": [{
            "cells": [t(a[1], 600, "#0F1B3A"), b((a[2] or '—'), "info"), t(a[3] or '—')],
            "docs": [doc("Baixar assinado" if a[4] else "Ver documento",
                         f"/api/v1/redesign/action/documento-empresa/{a[0]}", fmt="pdf")],
        } for a in _ass],
    }

    # ---- CIÊNCIA DOS COMUNICADOS (quantos funcionários já assinaram a ciência) ----
    _cie = (await db.execute(text(
        "SELECT r.title, "
        "count(*) FILTER (WHERE r.signer_type='employee') AS total, "
        "count(*) FILTER (WHERE r.signer_type='employee' AND upper(coalesce(r.status,'')) IN ('SIGNED','COMPLETED')) AS assinou, "
        "bool_or(r.signer_type='company' AND upper(coalesce(r.status,'')) IN ('SIGNED','COMPLETED')) AS empresa_ok "
        "FROM sig_signature_requests r WHERE r.document_type='comunicado' "
        "GROUP BY r.title ORDER BY r.title"))).fetchall()

    def _cie_row(c):
        total = int(c[1] or 0)
        assinou = int(c[2] or 0)
        pct = round(100 * assinou / total) if total else 0
        tone = "ok" if total and assinou >= total else ("warn" if assinou else "bad")
        return {"cells": [
            t(c[0], 600, "#0F1B3A"),
            b("Empresa ✓" if c[3] else "Empresa pendente", "ok" if c[3] else "warn"),
            t(f"{assinou}/{total}", 600),
            b(f"{pct}%", tone),
            t(f"{total - assinou} faltam" if total else "—", 500, "#64748B"),
        ]}

    out["ciencia-comunicados"] = {
        "title": "Ciência dos comunicados",
        "sub": ("Quantos funcionários já assinaram a ciência de cada comunicado. "
                "Meta: 100% da equipe ciente." if _cie else "Nenhum comunicado publicado para ciência."),
        "cta": "—", "type": "table", "searchHint": "Buscar comunicado…",
        "grid": "2.6fr 1.1fr 0.8fr 0.7fr 1fr",
        "cols": ["Comunicado", "Empresa", "Ciência", "%", "Pendentes"],
        "rows": [_cie_row(c) for c in _cie],
    }

    # ---- REORGANIZAÇÃO (documentos do jurídico) — abrir/baixar em PDF no timbrado ----
    import os as _os
    _JUR = {"mapa": "Mapa_Empregados_Patrimonial.pdf", "minutas": "Minutas_Revisadas_Comunicados.pdf"}
    _mapa_assinado = (await db.execute(text(
        "SELECT 1 FROM sig_signature_requests WHERE document_type='mapa_empregados' "
        "AND signer_type='company' AND signed_document_path IS NOT NULL LIMIT 1"))).first() is not None
    _jur_rows = []
    if _os.path.exists(f"/app/uploads/juridico/{_JUR['mapa']}"):
        _jur_rows.append({
            "cells": [t("Mapa dos Empregados" + (" — assinado ✓" if _mapa_assinado else ""), 600, "#0F1B3A"),
                      t("Versão ASSINADA (selo ICP-Brasil) — clique para baixar" if _mapa_assinado
                        else "Empregados CLT · nome, cargo, admissão · para o setor jurídico")],
            "docs": [doc("Baixar assinado (PDF)" if _mapa_assinado else "Abrir/Baixar (PDF)",
                         "/api/v1/redesign/action/doc-juridico/mapa", fmt="pdf")]})
    if _os.path.exists(f"/app/uploads/juridico/{_JUR['minutas']}"):
        _jur_rows.append({
            "cells": [t("Minutas revisadas dos comunicados", 600, "#0F1B3A"),
                      t("Rascunhos corrigidos (orientações do jurídico) — sujeitos à validação")],
            "docs": [doc("Abrir/Baixar (PDF)", "/api/v1/redesign/action/doc-juridico/minutas", fmt="pdf")]})
    out["reorganizacao-juridico"] = {
        "title": "Reorganização — documentos do jurídico",
        "sub": ("Documentos sobre a troca de empregador (Eletrônica → Patrimonial), no timbrado da empresa. "
                "Os 3 comunicados anteriores foram RETIRADOS por orientação do jurídico; estes apoiam a reescrita."),
        "cta": "—", "type": "table", "searchHint": "Buscar…",
        "grid": "1.6fr 2.4fr", "cols": ["Documento", "O que é"],
        "rows": _jur_rows,
    }

    # ---- GERAR DOCUMENTOS DO MÊS (holerite/espelho/recibo) direto no sistema ----
    out["gerar-docs-mes"] = {
        "title": "Gerar documentos do mês para assinatura",
        "sub": ("Gera os documentos do mês (holerite, espelho de ponto, recibo de VT/VR) de TODOS os "
                "funcionários CLT ativos da Patrimonial e cria cada um no fluxo de co-assinatura "
                "(funcionário + empresa). Roda em segundo plano; os documentos aparecem em 'Assinar "
                "documentos' e no Meu Espaço de cada funcionário. Idempotente — rodar de novo não duplica."),
        "cta": "Gerar documentos", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/gerar-docs-mes",
                   "okMsg": "Geração iniciada — os documentos aparecerão em alguns minutos."},
        "fields": [
            {"key": "competencia", "label": "Competência (MM/AAAA)*", "type": "text", "span": "span 1", "ph": "07/2026"},
            {"key": "tipo", "label": "Tipo", "type": "select", "span": "span 1", "options": [
                {"value": "todos", "label": "Todos (holerite + espelho + recibo)"},
                {"value": "holerite", "label": "Só holerites"},
                {"value": "espelho", "label": "Só espelhos de ponto"},
                {"value": "recibo", "label": "Só recibos de VT/VR"},
            ]},
        ],
    }

    # Fio solto (2026-08-10): o resumo contábil mensal existia no backend sem tela.
    out["resumo-contabil"] = {
        "title": "Resumo contábil do mês",
        "sub": "Consolida receitas, folha, impostos e despesas administrativas da empresa "
               "no período. Os valores em branco são buscados do sistema.",
        "cta": "Gerar resumo", "type": "form",
        "submit": {"endpoint": "/api/v1/empresas/contabilidade/resumo-mensal",
                   "okMsg": "Resumo gerado", "showResult": True},
        "fields": [
            {"key": "empresa_slug", "label": "Empresa*", "type": "select", "span": "span 1",
             "ph": "Selecione", "options": [
                 {"value": "eletronica", "label": "ConectaMais Eletrônica"},
                 {"value": "patrimonial", "label": "ConectaMais Patrimonial"}]},
            {"key": "periodo", "label": "Competência*", "type": "text", "span": "span 1",
             "ph": "AAAA-MM"},
            {"key": "receitas", "label": "Receitas (R$) — sobrepor", "type": "number", "span": "span 1"},
            {"key": "custos_folha", "label": "Folha (R$) — sobrepor", "type": "number", "span": "span 1"},
            {"key": "impostos", "label": "Impostos (R$) — sobrepor", "type": "number", "span": "span 1"},
            {"key": "despesas_admin", "label": "Despesas admin. (R$) — sobrepor", "type": "number",
             "span": "span 1"},
        ],
    }

    # Empresas do grupo + simular regime (2026-08-10): a rota leva {empresa_id} no CAMINHO,
    # entao vive como acao por LINHA. Sao 2 CNPJs; hardcodar id seria fragil.
    await safe("empresas-lista", tbl(
        "Empresas do grupo", "Os CNPJs e o regime de cada um", "—",
        ["Empresa", "CNPJ", "Regime", "Anexo"], "2fr 1.4fr 1.2fr 0.8fr",
        "SELECT id, coalesce(nome_fantasia, razao_social, '—'), coalesce(cnpj,'—'), "
        "coalesce(regime_tributario::text,'—'), coalesce(anexo_simples::text,'—') "
        "FROM empresas ORDER BY razao_social",
        lambda r: [t(r[1], 600, "#0F1B3A"), t(r[2]),
                   b((r[3] or '—').replace('_', ' ').capitalize(), "info"), t(r[4])],
        actionsfn=lambda r: [
            {"title": f"Simular outro regime para {r[1]}",
             "sub": "Compara o que se pagaria em outro regime, para a receita anual informada. "
                    "Simulacao — não muda o regime da empresa.",
             "endpoint": f"/api/v1/empresas/{r[0]}/simular-regime",
             "method": "POST", "btnLabel": "Simular", "submitLabel": "Simular regime",
             "btnStyle": "outline", "okMsg": "Simulacao concluida.",
             "fields": [
                 {"key": "novo_regime", "label": "Regime a simular*", "type": "select", "value": "",
                  "span": "span 2",
                  "options": [{"value": "simples_nacional", "label": "Simples Nacional"},
                              {"value": "lucro_presumido", "label": "Lucro Presumido"},
                              {"value": "lucro_real", "label": "Lucro Real"}]},
                 {"key": "faturamento_anual", "label": "Faturamento anual (R$)*", "type": "number",
                  "value": "", "span": "span 2"},
             ]},
        ]))

    return out


# ── ESCRITA op_write (router incluído pelo registry) ──
router = APIRouter()


@router.post("/action/nova-liminar", dependencies=[Depends(require_permission("module:fiscal"))])
async def _rd_nova_liminar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Registra uma liminar em fiscal_liminares (op_write — cria registro, reversível)."""
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    tributo = (payload.get("tributo") or "").strip()
    descricao = (payload.get("descricao") or "").strip()
    if not tributo or len(descricao) < 5:
        raise HTTPException(status_code=400, detail="Informe o tributo e a descrição (mín. 5 caracteres).")

    async def _write():
        r = await db.execute(text(
            "INSERT INTO fiscal_liminares (tipo, tributo, empresa, descricao, processo, status, created_at, updated_at) "
            "VALUES (:tipo, :trib, :emp, :desc, :proc, :st, now(), now()) RETURNING id"),
            {"tipo": (payload.get("tipo") or "liminar").strip()[:60], "trib": tributo[:60],
             "emp": (payload.get("empresa") or "").strip()[:120] or None, "desc": descricao,
             "proc": (payload.get("processo") or "").strip()[:120] or None, "st": "a_solicitar"})
        new_id = r.scalar()
        await db.commit()
        return {"ok": True, "id": new_id, "message": "Liminar registrada com sucesso."}

    try:
        return await op_write(db, real_write=_write)
    except GateError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/action/assinar-doc-empresa")
async def _rd_assinar_doc_empresa(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Assina um documento EM NOME DA EMPRESA (COMPANY) com o certificado A1 ICP-Brasil
    do CNPJ (Patrimonial/Eletrônica — resolvido pelo empresa_slug gravado no request).
    Ato sensível (razão social, fé pública) → SÓ admin + trava OTP humano (money_gov)."""
    from uuid import UUID as _UUID

    from modules.operacional.controllers.redesign_write_gate import GateError, OTPRequired, money_gov
    from modules.signatures.services.universal_signature_service import (
        SignatureLevel,
        SignerType,
        UniversalSignatureService,
    )

    # Gate de acesso: assinatura da empresa é exclusiva de admin autorizado (Jordan/Pyetra).
    if (getattr(current_user, "role", "") or "") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Assinatura em nome da empresa exige usuário administrador.")

    req_id = (payload.get("documento") or "").strip()
    if not req_id:
        raise HTTPException(status_code=400, detail="Selecione o documento a assinar.")
    otp_code = (payload.get("otp_code") or "").strip()

    # ---- LOTE por TIPO: "__ALL__:<tipo>" assina todos os pendentes daquele tipo com 1 OTP.
    #      "__ALL__:outros" = tudo que não é holerite/espelho/recibo. "__ALL__" = todos. ----
    if req_id.startswith("__ALL__"):
        _tag = req_id.split(":", 1)[1] if ":" in req_id else None
        _sql = ("SELECT id::text, coalesce(document_path,'') FROM sig_signature_requests "
                "WHERE signer_type='company' AND upper(coalesce(status,''))='PENDING'")
        _params: dict = {}
        if _tag == "outros":
            _sql += " AND coalesce(document_type,'') NOT IN ('payslip','espelho_ponto','recibo_vt_vr')"
        elif _tag:
            _sql += " AND document_type = :dt"
            _params = {"dt": _tag}
        pend_raw = (await db.execute(text(_sql), _params)).fetchall()
        pend = [p for p in pend_raw if _pdf_valido(p[1])]  # só os com PDF real (assináveis)
        if not pend:
            raise HTTPException(status_code=400, detail="Nenhum documento com PDF disponível para assinar.")
        ref = (payload.get("_gate_ref") or "").strip() or f"assinatura-empresa-lote:{_tag or 'all'}"

        async def _dispatch_all():
            svc = UniversalSignatureService(db)
            ok = 0
            fail = 0
            for pid, ppath in pend:
                try:
                    await svc.assinar(
                        request_id=_UUID(pid), signer_type=SignerType.COMPANY,
                        signer_id=getattr(current_user, "id", None),
                        signer_name=getattr(current_user, "full_name", None) or "JORDAN JESUS",
                        level=SignatureLevel.QUALIFIED,
                        certificate_ref={"pdf_path": ppath} if ppath else None)
                    ok += 1
                except Exception:  # noqa: BLE001 — um doc problemático não derruba o lote
                    await db.rollback()
                    fail += 1
            return {"ok": True, "message": f"{ok} documento(s) assinados em lote pela empresa"
                    + (f" · {fail} falharam (assine individualmente)" if fail else "") + "."}

        try:
            res = await money_gov(db, ref=ref, amount=None, otp_code=otp_code, real_dispatch=_dispatch_all,
                                  label="assinatura_empresa_lote", dest=f"{len(pend)} documentos")
        except OTPRequired as e:
            return {"otp_required": True, "ref": e.ref,
                    "message": f"Assinatura EM LOTE de {len(pend)} documento(s) preparada. {e.message}"}
        except GateError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return res

    row = (await db.execute(text(
        "SELECT title, signer_type, upper(coalesce(status,'')), document_path "
        "FROM sig_signature_requests WHERE id::text = :i"), {"i": req_id})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Documento não encontrado.")
    if row[1] != "company":
        raise HTTPException(status_code=400, detail="Este documento não é uma assinatura da empresa.")
    if row[2] != "PENDING":
        raise HTTPException(status_code=400, detail="Este documento já foi assinado (ou não está pendente).")
    if not _pdf_valido(row[3]):
        raise HTTPException(status_code=400,
                            detail="O PDF deste documento não está disponível — gere/reenvie o documento antes de assinar.")

    otp_code = (payload.get("otp_code") or "").strip()
    ref = (payload.get("_gate_ref") or "").strip() or f"assinatura-empresa:{req_id}"

    async def _dispatch():
        res = await UniversalSignatureService(db).assinar(
            request_id=_UUID(req_id),
            signer_type=SignerType.COMPANY,
            signer_id=getattr(current_user, "id", None),
            signer_name=getattr(current_user, "full_name", None) or "JORDAN JESUS",
            level=SignatureLevel.QUALIFIED,
            certificate_ref={"pdf_path": row[3]} if row[3] else None,
        )
        cert = (res.get("certificate") or {}).get("subject") or ""
        return {"ok": True, "message": f"Documento assinado pela empresa (ICP-Brasil). {cert}".strip()}

    try:
        res = await money_gov(db, ref=ref, amount=None, otp_code=otp_code, real_dispatch=_dispatch,
                              label="assinatura_empresa", dest=(row[0] or "")[:48])
    except OTPRequired as e:
        return {"otp_required": True, "ref": e.ref,
                "message": f"Assinatura de '{(row[0] or '')[:48]}' preparada. {e.message}"}
    except GateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return res


@router.get("/action/documento-empresa/{request_id}")
async def _rd_documento_empresa(request_id: str, current_user: CurrentActiveUser, db=Depends(get_db)):
    """Serve o PDF de uma solicitação de assinatura da EMPRESA (para revisar antes de assinar).
    Gated: só admin/operator. Retorna o document_path (PDF já assinado se houver, senão o original)."""
    import os as _os

    from fastapi.responses import FileResponse

    if (getattr(current_user, "role", "") or "") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Acesso restrito à administração.")
    row = (await db.execute(text(
        "SELECT title, coalesce(signed_document_path, document_path), signer_type "
        "FROM sig_signature_requests WHERE id::text = :i"), {"i": request_id})).first()
    if not row or row[2] != "company":
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    path = row[1]
    if not path or not _os.path.exists(path):
        raise HTTPException(status_code=404, detail="Arquivo PDF não disponível para este documento.")
    safe_name = "".join(ch for ch in (row[0] or "documento") if ch.isalnum() or ch in " -_")[:60].strip() or "documento"
    return FileResponse(path, media_type="application/pdf", filename=f"{safe_name}.pdf")


@router.get("/action/doc-juridico/{slug}")
async def _rd_doc_juridico(slug: str, current_user: CurrentActiveUser, db=Depends(get_db)):
    """Serve os PDFs (timbrados) da reorganização para o jurídico: mapa de empregados e minutas.
    Whitelist fixa (não aceita caminho arbitrário). Gated: só admin/operator.
    Se o documento já foi ASSINADO pela empresa, entrega a versão assinada (com selo)."""
    import os as _os

    from fastapi.responses import FileResponse

    if (getattr(current_user, "role", "") or "") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Acesso restrito à administração.")
    files = {"mapa": "Mapa_Empregados_Patrimonial.pdf", "minutas": "Minutas_Revisadas_Comunicados.pdf"}
    dtypes = {"mapa": "mapa_empregados"}  # documentos que passam pelo fluxo de assinatura
    fn = files.get(slug)
    if not fn:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    path = f"/app/uploads/juridico/{fn}"
    if slug in dtypes:  # já assinado? entrega a versão ASSINADA (com selo ICP-Brasil)
        signed = (await db.execute(text(
            "SELECT signed_document_path FROM sig_signature_requests "
            "WHERE document_type=:d AND signer_type='company' AND signed_document_path IS NOT NULL "
            "ORDER BY coalesce(signed_at, updated_at) DESC LIMIT 1"), {"d": dtypes[slug]})).scalar()
        if signed and _os.path.exists(signed):
            path, fn = signed, f"{fn[:-4]}_assinado.pdf"
    if not _os.path.exists(path):
        raise HTTPException(status_code=404, detail="Arquivo ainda não disponível.")
    return FileResponse(path, media_type="application/pdf", filename=fn)


@router.post("/action/gerar-docs-mes")
async def _rd_gerar_docs_mes(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Gera os documentos do mês (holerite/espelho/recibo) de todos os CLT ativos da
    Patrimonial e cria cada um no fluxo de co-assinatura. Roda em THREAD (não trava a API);
    retorna na hora. Gated: só admin/operator."""
    import asyncio
    import logging
    import re as _re

    if (getattr(current_user, "role", "") or "") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Acesso restrito à administração.")

    m = _re.match(r"^\s*(\d{1,2})\s*/\s*(\d{4})\s*$", payload.get("competencia") or "")
    if not m:
        raise HTTPException(status_code=400, detail="Informe a competência no formato MM/AAAA (ex.: 07/2026).")
    mes, ano = int(m.group(1)), int(m.group(2))
    if not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="Mês inválido (1 a 12).")
    tipo = (payload.get("tipo") or "todos").strip()
    tipos = {"holerite", "espelho", "recibo"} if tipo == "todos" else {tipo}

    from modules.people_management.folha.services.gerar_docs_mes_service import gerar_docs_mes

    async def _bg() -> None:
        try:
            await asyncio.to_thread(gerar_docs_mes, mes, ano, tipos)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).error("gerar-docs-mes bg falhou (%02d/%d): %s", mes, ano, exc)

    asyncio.create_task(_bg())
    return {"ok": True, "message": (f"Geração de '{tipo}' para {mes:02d}/{ano} iniciada. Os documentos "
                                    "aparecerão em 'Assinar documentos' e no Meu Espaço em alguns minutos.")}
