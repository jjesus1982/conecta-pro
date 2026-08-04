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
    {"id": "assinar-documentos", "label": "Assinar documentos", "icon": "M15.232 5.232l3.536 3.536M4 20h4l10.5-10.5a2.5 2.5 0 0 0-3.536-3.536L4.5 16.5V20z"},
]


def _obr_tone(s):
    return {"atrasada": "bad", "pendente": "warn", "concluida": "ok", "concluída": "ok"}.get((s or "").lower(), "info")


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
    _pend = (await db.execute(text(
        "SELECT r.id::text, r.title, coalesce(r.document_type,'—'), to_char(r.created_at,'DD/MM/YYYY') "
        "FROM sig_signature_requests r WHERE r.signer_type='company' AND upper(coalesce(r.status,''))='PENDING' "
        "ORDER BY r.created_at DESC LIMIT 100"))).fetchall()
    _opts = [{"value": p[0], "label": f"{p[1]}"} for p in _pend]
    out["assinar-documentos"] = {
        "title": "Assinar documentos da empresa",
        "sub": (f"{len(_opts)} documento(s) aguardando a assinatura da empresa (ICP-Brasil A1). "
                "Ao confirmar, você recebe um código OTP no e-mail para liberar a assinatura."
                if _opts else "Nenhum documento aguardando a assinatura da empresa no momento."),
        "cta": "Assinar como empresa", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/assinar-doc-empresa",
                   "okMsg": "Documento assinado pela empresa (ICP-Brasil)."},
        "fields": [
            {"key": "documento", "label": "Documento a assinar*", "type": "select", "span": "span 2",
             "options": _opts, "ph": "Selecione o documento"},
            {"key": "otp_code", "label": "Código OTP (chega no seu e-mail após confirmar)", "type": "text",
             "span": "span 2", "ph": "Deixe em branco na 1ª vez — o código é enviado ao confirmar"},
        ],
        # tabela de apoio: o que está pendente (visibilidade antes de assinar)
        "rows": [{"cells": [t(p[1], 600, "#0F1B3A"), b((p[2] or '—'), "info"), t(p[3])]} for p in _pend],
        "cols": ["Documento", "Tipo", "Criado em"], "grid": "2.4fr 1fr 1fr",
    }

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
    row = (await db.execute(text(
        "SELECT title, signer_type, upper(coalesce(status,'')), document_path "
        "FROM sig_signature_requests WHERE id::text = :i"), {"i": req_id})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Documento não encontrado.")
    if row[1] != "company":
        raise HTTPException(status_code=400, detail="Este documento não é uma assinatura da empresa.")
    if row[2] != "PENDING":
        raise HTTPException(status_code=400, detail="Este documento já foi assinado (ou não está pendente).")

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
