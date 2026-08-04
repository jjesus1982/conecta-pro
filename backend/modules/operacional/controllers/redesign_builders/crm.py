"""
redesign_builders/crm.py — T4.
Sobrescreve _build_crm: reusa a base e ADICIONA clientes, growth (funil de
atividades) e consultor comercial (histórico de interações). Só leitura.
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text  # noqa: F401

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _build_crm as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    doc,
    initials,
    t,
)

SLUG = "crm"

# Nota: o base _build_crm JÁ tem os forms de escrita (novo-lead, nova-tarefa,
# nova-proposta, mover-oportunidade, anotar-cliente, simular-preco). Não duplicar.


async def _build_precificacao(db, tbl_t, tbl_b, tbl_brl):
    """Tabela de preços por função com custo/preço/margem — reusa o MESMO
    calcular_funcao do clássico /crm/pricing/funcoes (0,01s p/ 10 funções, A5)."""
    from modules.crm.services.pricing_cct import calcular_funcao
    rows = (await db.execute(text("SELECT * FROM crm_pricing_funcoes WHERE ativo ORDER BY ordem"))).mappings().all()
    cells = []
    for r in rows:
        c = await calcular_funcao(db, dict(r))
        cells.append({"cells": [
            tbl_t(c["funcao"], 600, "#0F1B3A"), tbl_t(tbl_brl(c["salario_base"]), 600),
            tbl_t(tbl_brl(c["custo_total"])), tbl_t(tbl_brl(c["preco"]), 600, "#16A34A"),
            tbl_b(f"{float(c['markup_pct']) * 100:.2f}%", "ok"),
        ]})
    return {"title": "Precificação", "sub": f"{len(rows)} funções · CCT 2026 · custo/preço/margem por função (PricingEngine)",
            "cta": "—", "type": "table", "searchHint": "Buscar…",
            "grid": "2fr 1fr 1.2fr 1.2fr 1fr", "cols": ["Função", "Piso", "Custo", "Preço", "Margem"], "rows": cells}


_LEAD_TONE = {"novo": "info", "new": "info", "em_contato": "warn", "contacted": "warn",
              "qualificado": "ok", "qualified": "ok", "convertido": "ok", "converted": "ok",
              "perdido": "bad", "lost": "bad"}


def _cnpj(v) -> str:
    d = "".join(ch for ch in (v or "") if ch.isdigit())
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return v or "—"


# ─────────────────────────────────────── EXECUÇÃO no redesign (lado que EFETIVA) ──
# Propostas (criar já existe no base; aqui religamos + enviar) e Contratos (criar/enviar/
# ativar/cancelar). TODA escrita passa pelo op_write (identidade real + idempotência) e
# REUSA os MESMOS services dos endpoints clássicos /crm/proposals|contracts/*. Nunca
# reimplementa lógica; ativar contrato é HEAVY → gate reforçado (confirmação digitada).
router = APIRouter()


async def _crm_gate(db, rec_id, coro_factory, ok_msg, noun="registro", idem=None):
    """Choke-point das ações CRM: valida id, roteia pelo op_write (identidade real +
    idempotência), reflete o status REAL do service. None do repo = estado inválido."""
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    if not (rec_id or "").strip():
        raise HTTPException(status_code=400, detail=f"Selecione o {noun}.")
    try:
        res = await op_write(db, real_write=coro_factory, idempotency_key=idem)
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    if res is None:
        raise HTTPException(status_code=400,
                            detail=f"{noun.capitalize()} não encontrado ou em estado inválido para esta ação.")
    return {"ok": True, "id": str(getattr(res, "id", rec_id)),
            "status": str(getattr(res, "status", "") or ""), "message": ok_msg}


@router.post("/action/contract")
async def rd_action_contract_create(current_user: CurrentActiveUser, payload: dict = Body(...),
                                    db=Depends(get_db)) -> dict:
    """Cria contrato REAL (rascunho) via ContractRepository.create — o MESMO do clássico
    POST /crm/contracts. Escrita operacional → op_write (idempotência)."""
    from datetime import date as _date
    from decimal import Decimal

    from modules.crm.repositories.contract_repository import ContractRepository
    from modules.crm.schemas.contract import ContractCreate
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write

    client_id = (payload.get("client_id") or "").strip()
    if len(client_id) != 36:
        raise HTTPException(status_code=400, detail="Selecione o cliente do contrato.")
    name = (payload.get("name") or payload.get("title") or "").strip()
    if len(name) < 3:
        raise HTTPException(status_code=400, detail="Informe o nome do contrato (mín. 3 caracteres).")
    try:
        monthly = float(str(payload.get("monthly_value") or payload.get("valor") or "0").replace(".", "").replace(",", "."))
    except (ValueError, TypeError):
        monthly = 0.0
    try:
        data = ContractCreate(
            client_id=client_id, name=name[:200], monthly_value=Decimal(str(monthly)),
            start_date=payload.get("start_date") or _date.today().isoformat(),
            description=(payload.get("description") or "").strip() or None)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    repo = ContractRepository(db)
    try:
        c = await op_write(db, real_write=lambda: repo.create(data, created_by_id=str(current_user.id)),
                           idempotency_key=f"contract-create:{client_id}:{name[:60]}:{monthly}")
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    return {"ok": True, "id": str(c.id), "number": getattr(c, "contract_number", None),
            "message": "Contrato criado (rascunho)"}


@router.post("/action/contract-submit")
async def rd_action_contract_submit(current_user: CurrentActiveUser, cid: str, db=Depends(get_db)) -> dict:
    """Envia contrato para assinatura (DRAFT→PENDING_SIGNATURE) — reusa o handler clássico
    submit_contract_for_signature."""
    from modules.crm.controllers.contract_controller import submit_contract_for_signature
    return await _crm_gate(db, cid,
        lambda: submit_contract_for_signature(contract_id=cid, current_user=current_user, db=db),
        "Contrato enviado para assinatura", "contrato")


@router.post("/action/contract-activate")
async def rd_action_contract_activate(current_user: CurrentActiveUser, cid: str,
                                      payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """ATIVAR contrato — HEAVY (coloca em vigência + lança MRR + publishers). Gate REFORÇADO:
    exige confirmação explícita DIGITADA ('ATIVAR') além do op_write (idempotência). Reusa o
    handler clássico activate_contract → mesmo efeito do POST /crm/contracts/{id}/activate."""
    from modules.crm.controllers.contract_controller import activate_contract
    if (payload.get("confirmar") or "").strip().upper() != "ATIVAR":
        raise HTTPException(status_code=400,
                            detail="Confirmação necessária: digite ATIVAR para colocar o contrato em vigência.")
    return await _crm_gate(db, cid,
        lambda: activate_contract(contract_id=cid, current_user=current_user, db=db),
        "Contrato ativado (em vigência)", "contrato", idem=f"contract-activate:{cid}")


@router.post("/action/contract-cancel")
async def rd_action_contract_cancel(current_user: CurrentActiveUser, cid: str,
                                    payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """Cancela contrato — reusa ContractRepository.update_status(CANCELLED) (serviço real; a
    transição é validada no repo)."""
    from modules.crm.models.contract import ContractStatus
    from modules.crm.repositories.contract_repository import ContractRepository
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="Informe o motivo do cancelamento (mín. 5 caracteres).")
    repo = ContractRepository(db)
    return await _crm_gate(db, cid,
        lambda: repo.update_status(cid, ContractStatus.CANCELLED, user_id=str(current_user.id)),
        "Contrato cancelado", "contrato")


@router.post("/action/proposal-send")
async def rd_action_proposal_send(current_user: CurrentActiveUser, pid: str, db=Depends(get_db)) -> dict:
    """Envia proposta ao cliente — reusa o handler clássico send_proposal (mesmo POST
    /crm/proposals/{id}/send). Efeito EXTERNO: dispara e-mail ao cliente."""
    from modules.crm.controllers.proposal_controller import send_proposal
    return await _crm_gate(db, pid,
        lambda: send_proposal(proposal_id=pid, current_user=current_user, db=db),
        "Proposta enviada ao cliente", "proposta")


EXTRA_MENU: list[dict] = [
    {"id": "novo-contrato", "label": "Novo contrato",
     "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 15h6M9 11h6"},
]


def _proposta_actions(r):
    """Enviar proposta ao cliente (externo) — só quando faz sentido (rascunho/aprovada)."""
    if (r[5] or "").lower() not in ("draft", "approved"):
        return None
    return [{"title": f"Enviar proposta {r[1]} ao cliente",
             "endpoint": f"/api/v1/redesign/action/proposal-send?pid={r[0]}",
             "method": "POST", "btnLabel": "Enviar", "submitLabel": "Enviar ao cliente (e-mail)",
             "btnStyle": "primary", "okMsg": "Proposta enviada ao cliente (e-mail). Recarregue a tela.",
             "fields": []}]


def _contrato_actions(r):
    """Ciclo de vida do contrato por-linha — só a ação válida p/ o status atual."""
    st = (r[5] or "").lower()
    acts = []
    if st == "draft":
        acts.append({"title": f"Enviar contrato {r[1]} para assinatura",
                     "endpoint": f"/api/v1/redesign/action/contract-submit?cid={r[0]}",
                     "method": "POST", "btnLabel": "Enviar", "submitLabel": "Enviar para assinatura",
                     "btnStyle": "outline", "okMsg": "Contrato enviado para assinatura. Recarregue.", "fields": []})
    if st == "pending_signature":
        acts.append({"title": f"ATIVAR contrato {r[1]} — coloca em vigência (MRR)",
                     "endpoint": f"/api/v1/redesign/action/contract-activate?cid={r[0]}",
                     "method": "POST", "btnLabel": "Ativar", "submitLabel": "Confirmar ativação",
                     "btnStyle": "primary", "okMsg": "Contrato ativado (em vigência). Recarregue.",
                     "fields": [{"key": "confirmar", "label": "Digite ATIVAR para confirmar a vigência",
                                 "type": "text", "span": "span 2", "value": ""}]})
    if st in ("draft", "pending_signature", "active"):
        acts.append({"title": f"Cancelar contrato {r[1]}",
                     "endpoint": f"/api/v1/redesign/action/contract-cancel?cid={r[0]}",
                     "method": "POST", "btnLabel": "Cancelar", "submitLabel": "Cancelar contrato",
                     "btnStyle": "outline", "okMsg": "Contrato cancelado. Recarregue.",
                     "fields": [{"key": "reason", "label": "Motivo do cancelamento (obrigatório)",
                                 "type": "textarea", "span": "span 2", "value": ""}]})
    return acts or None


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- Precificação (custo/preço/margem por função — reusa calcular_funcao) ----
    try:
        out["precificacao"] = await _build_precificacao(db, t, b, brl)
    except Exception:  # noqa: BLE001
        await db.rollback()

    # ---- Leads (override: + coluna Origem, que o clássico mostra e a base não) ----
    await safe("leads", tbl(
        "Leads", f"{await _scalar(db, 'SELECT count(*) FROM leads')} leads", "Novo lead",
        ["Lead", "Empresa", "Origem", "Valor estimado", "Status"], "2fr 1.5fr 1fr 1fr 0.9fr",
        "SELECT name, coalesce(company,'—'), coalesce(source,'—'), coalesce(expected_value,0), coalesce(status::text,'—') "
        "FROM leads ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]),
                   b((r[2] or '—').replace('_', ' ').capitalize(), "mut"), t(brl(r[3]), 600),
                   b((r[4] or '—').replace('_', ' ').capitalize(), _LEAD_TONE.get((r[4] or '').lower(), "info"))]))

    # ---- Fidelidade: oportunidades e propostas mostram KPIs de resumo no clássico.
    #      Tela 'table' não tem KPI-card (não edito ModuleView) → trago no subtítulo. ----
    try:
        _ot = await _scalar(db, "SELECT count(*) FROM opportunities")
        _oneg = await _scalar(db, "SELECT count(*) FROM opportunities WHERE stage::text='negotiation'")
        _oprop = await _scalar(db, "SELECT count(*) FROM opportunities WHERE stage::text='proposal'")
        _opipe = await _scalar(db, "SELECT coalesce(sum(value),0) FROM opportunities WHERE stage::text NOT IN ('closed_won','closed_lost')")
        if isinstance(out.get("oportunidades"), dict):
            out["oportunidades"]["sub"] = f"{_ot} oportunidades · Em negociação {_oneg} · Em proposta {_oprop} · Pipeline {brl(_opipe)}"
        _pt = await _scalar(db, "SELECT count(*) FROM proposals")
        _pd = await _scalar(db, "SELECT count(*) FROM proposals WHERE status::text='draft'")
        _ps = await _scalar(db, "SELECT count(*) FROM proposals WHERE status::text='sent'")
        _pa = await _scalar(db, "SELECT count(*) FROM proposals WHERE status::text='accepted'")
        if isinstance(out.get("propostas"), dict):
            out["propostas"]["sub"] = f"{_pt} propostas · Rascunho {_pd} · Enviadas {_ps} · Aprovadas {_pa}"
        _ct = await _scalar(db, "SELECT count(*) FROM commissions")
        _cval = await _scalar(db, "SELECT coalesce(sum(final_commission),0) FROM commissions")
        _cpend = await _scalar(db, "SELECT count(*) FROM commissions WHERE status::text NOT IN ('paid','pago','cancelled','cancelada')")
        if isinstance(out.get("comissoes"), dict):
            out["comissoes"]["sub"] = f"{_ct} comissões · Valor total {brl(_cval)} · Pendentes {_cpend}"
    except Exception:  # noqa: BLE001
        await db.rollback()

    # ---- Contatos (override: + Email e Principal, que o clássico mostra) ----
    await safe("contatos", tbl(
        "Contatos", f"{await _scalar(db, 'SELECT count(*) FROM crm_contacts')} contatos",
        "—", ["Contato", "Cliente", "Cargo", "Email", "Telefone", "Principal"], "1.6fr 1.8fr 1fr 1.8fr 1.1fr 0.8fr",
        "SELECT c.name, coalesce(cl.name,'—'), coalesce(c.role,'—'), coalesce(c.email,'—'), "
        "coalesce(nullif(c.phone,''), c.whatsapp, '—'), c.is_primary "
        "FROM crm_contacts c LEFT JOIN clients cl ON cl.id=c.client_id "
        "ORDER BY c.is_primary DESC NULLS LAST, c.name LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t((r[2] or '—').capitalize()),
                   t(r[3]), t(r[4]), b("Principal", "ok") if r[5] else b("—", "mut")]))

    # ---- Clientes (clients) ----
    _cl_tot = await _scalar(db, "SELECT count(*) FROM clients WHERE ativo=true")
    _cl_ativos = await _scalar(db, "SELECT count(*) FROM clients WHERE status::text='active'")
    _cl_cond = await _scalar(db, "SELECT count(*) FROM clients WHERE ativo=true AND client_type::text='condominium'")
    _cl_bloq = await _scalar(db, "SELECT count(*) FROM clients WHERE ativo=true AND coalesce(is_defaulter,false)=true")
    await safe("clientes", tbl(
        "Clientes",
        f"{_cl_tot} clientes · Ativos {_cl_ativos} · Condomínios {_cl_cond} · Bloqueados {_cl_bloq}",
        "—", ["Cliente", "CNPJ", "Email", "Segmento", "MRR", "Status"], "1.8fr 1.3fr 1.8fr 1.1fr 1fr 0.8fr",
        "SELECT name, coalesce(document_number,'—'), coalesce(email,'—'), coalesce(segment::text,'—'), coalesce(mrr,0), status::text "
        "FROM clients ORDER BY mrr DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(_cnpj(r[1])), t(r[2]), t((r[3] or '—').capitalize()),
                   t(brl(r[4]), 600), b("Ativo", "ok") if r[5] == "active" else b((r[5] or '—').capitalize(), "mut")]))

    # ---- Growth · funil de atividades (crm_activities agregado — real) ----
    await safe("growth", tbl(
        "Growth (Automação)", "Funil de atividades comerciais por tipo",
        "—", ["Tipo de atividade", "Quantidade", "Última"], "2fr 1fr 1.2fr",
        "SELECT coalesce(type,'—'), count(*), max(coalesce(completed_at, scheduled_at, created_at)) "
        "FROM crm_activities GROUP BY type ORDER BY count(*) DESC",
        lambda r: [t((r[0] or '—').replace('_', ' ').capitalize(), 600, "#0F1B3A"),
                   b(f"{r[1]}", "info"), t(_fmtdate(r[2]))]))

    # ---- Consultor Comercial IA · histórico de interações (crm_activities READ) ----
    await safe("consultor", tbl(
        "Consultor Comercial IA", f"{await _scalar(db, 'SELECT count(*) FROM crm_activities')} interações comerciais",
        "—", ["Assunto", "Tipo", "Resultado", "Data"], "2fr 1fr 1.2fr 1fr",
        "SELECT coalesce(subject,'—'), coalesce(type,'—'), coalesce(outcome,'—'), coalesce(completed_at, scheduled_at, created_at) "
        "FROM crm_activities ORDER BY coalesce(completed_at, scheduled_at, created_at) DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').replace('_', ' ').capitalize(), "info"),
                   t((r[2] or '—').capitalize()), t(_fmtdate(r[3]))]))

    # ---- DOCUMENTOS: proposta e contrato em PDF por-linha (rotas curl-provadas 200 application/pdf)
    # /api/v1/crm/proposals/{id}/pdf e /api/v1/crm/contracts/{id}/pdf. Rebuild das telas base
    # (mesmas colunas) + id na 1ª coluna do SELECT + docsfn.
    try:
        # Botão PDF SÓ nas propostas is_active=true — a rota (ProposalRepository.get_by_id) filtra
        # is_active e 404 nas inativas. Sem isso, 17 de 30 dariam botão-404. (bug pego no E2E)
        await safe("propostas", tbl("Propostas", f"{await _scalar(db, 'SELECT count(*) FROM proposals')} propostas", "Nova proposta",
            ["Número", "Cliente", "Título", "Valor", "Status"], "1fr 1.6fr 1.6fr 1fr 0.9fr",
            "SELECT id, coalesce(number,'—'), coalesce(client_name,'—'), coalesce(title,'—'), coalesce(total,subtotal,0), status::text, coalesce(is_active,false) "
            "FROM proposals ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t(r[2]), t(r[3]), t(brl(r[4]), 600), b(r[5] or "—", "info")],
            docsfn=lambda r: [doc("Proposta", f"/api/v1/crm/proposals/{r[0]}/pdf", fmt="pdf")] if r[6] else [],
            actionsfn=_proposta_actions))
        # Religa o botão CRIAR (a tela-form 'nova-proposta' já existe no base + já está no menu).
        out["propostas"]["ctaTo"] = "nova-proposta"
    except Exception:  # noqa: BLE001
        await db.rollback()
    try:
        await safe("contratos", tbl("Contratos", f"{await _scalar(db, 'SELECT count(*) FROM contracts')} contratos", "Novo contrato",
            ["Contrato", "Cliente", "Mensal", "Total", "Status"], "1.2fr 1.6fr 1fr 1fr 0.9fr",
            "SELECT ct.id, coalesce(ct.contract_number,'—'), coalesce(cl.name, ct.name, '—'), coalesce(ct.monthly_value,0), coalesce(ct.total_value,0), ct.status::text "
            "FROM contracts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.start_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t(r[2]), t(brl(r[3])), t(brl(r[4]), 600),
                       b("Ativo", "ok") if (r[5] or "").lower() in ("active", "ativo", "vigente") else b(r[5] or "—", "mut")],
            docsfn=lambda r: [doc("Contrato", f"/api/v1/crm/contracts/{r[0]}/pdf", fmt="pdf")],
            actionsfn=_contrato_actions))
        # CRIAR contrato (rascunho): tela-form + religa o botão da tabela.
        cli_opts = (await db.execute(text(
            "SELECT id, name FROM clients WHERE coalesce(ativo,true)=true ORDER BY name LIMIT 500"))).fetchall()
        out["novo-contrato"] = {
            "title": "Novo contrato", "sub": "Criar um contrato (rascunho)", "cta": "Criar contrato",
            "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/contract", "okMsg": "Contrato criado (rascunho)"},
            "fields": [
                {"key": "client_id", "label": "Cliente*", "type": "select", "span": "span 2",
                 "ph": "Selecione o cliente",
                 "options": [{"value": str(i), "label": n} for i, n in cli_opts]},
                {"key": "name", "label": "Nome do contrato*", "type": "text", "span": "span 2",
                 "ph": "Ex.: Contrato de portaria — Cond. X"},
                {"key": "monthly_value", "label": "Valor mensal (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
                {"key": "start_date", "label": "Início da vigência", "type": "date", "span": "span 1"},
                {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2",
                 "ph": "Objeto/observações do contrato…"},
            ],
        }
        out["contratos"]["ctaTo"] = "novo-contrato"
    except Exception:  # noqa: BLE001
        await db.rollback()

    return out
