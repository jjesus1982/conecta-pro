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


_ICO_DOC = "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 15h6M9 11h6"
_ICO_CHAT = "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
_ICO_CAL = "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"

EXTRA_MENU: list[dict] = [
    {"id": "novo-contrato", "label": "Novo contrato", "icon": _ICO_DOC},
    # Ficha viva / negociação
    {"id": "cliente-anotar", "label": "Anotar na ficha", "icon": _ICO_CHAT},
    {"id": "negociacao-responsavel", "label": "Quem conduz", "icon": _ICO_CHAT},
    {"id": "whatsapp-cadastrar", "label": "Cadastrar WhatsApp", "icon": _ICO_CHAT},
    # Reuniões
    {"id": "reuniao-sugerir", "label": "Sugerir reunião", "icon": _ICO_CAL},
    {"id": "reuniao-confirmar", "label": "Confirmar reunião", "icon": _ICO_CAL},
    {"id": "reuniao-cancelar", "label": "Cancelar reunião", "icon": _ICO_CAL},
    # Visitas
    {"id": "visita-montar", "label": "Montar relatório de visita", "icon": _ICO_DOC},
    {"id": "visita-registrar-lead", "label": "Lead a partir da visita", "icon": _ICO_DOC},
    # Documento
    {"id": "doc-ordem-servico", "label": "Ordem de serviço (PDF)", "icon": _ICO_DOC},
    # Follow-up / contato com o cliente
    {"id": "followup-tocar", "label": "Tocar cliente", "icon": _ICO_CHAT},
    {"id": "followup-lote", "label": "Tocar em lote", "icon": _ICO_CHAT},
    {"id": "followup-resposta", "label": "Registrar retorno", "icon": _ICO_CHAT},
    {"id": "followup-optout", "label": "Opt-out (não perturbe)", "icon": _ICO_CHAT},
    {"id": "nps-enviar", "label": "Enviar NPS", "icon": _ICO_CHAT},
    {"id": "reativar-lead", "label": "Reativar lead frio", "icon": _ICO_CHAT},
    # Análise
    {"id": "simular-fechamento", "label": "Simular fechamento", "icon": _ICO_DOC},
    {"id": "consultor-comercial", "label": "Consultor comercial", "icon": _ICO_CHAT},
    {"id": "consultor-comercial-arquivo", "label": "Consultor comercial — com anexo", "icon": _ICO_CHAT},
    {"id": "doc-orcamento", "label": "Orçamento (PDF)", "icon": _ICO_DOC},
    {"id": "apresentacao-gerar", "label": "Gerar apresentacao", "icon": _ICO_DOC},
    {"id": "visita-achados", "label": "Anexar achados a visita", "icon": _ICO_DOC},
    {"id": "asset-upload", "label": "Enviar logo/selo", "icon": _ICO_DOC},
    {"id": "expurgar-teste", "label": "Arquivar documentos de teste", "icon": _ICO_DOC},
]

# Toda rota de contato tem `confirmar`: False = PREVIEW (resolve o número, não envia).
# O select nasce vazio e campo intocado nao e enviado -> o default do backend (False) vale,
# entao o caminho preguicoso do usuario e o SEGURO: simula. Enviar exige escolha explicita.
_CONFIRMAR = [
    {"value": "false", "label": "Só simular — mostra o que seria enviado (padrão)"},
    {"value": "true", "label": "ENVIAR de verdade ao cliente"},
]


def _proposta_actions(r):
    """Ações da proposta por LINHA. As 3 rotas de envio levam {proposal_id} no CAMINHO —
    é aqui que elas cabem: o id vem da linha, não de um UUID colado à mão numa tela solta.
    Só aparecem em rascunho/aprovada, que é quando enviar faz sentido (a rota 404 no resto)."""
    if (r[5] or "").lower() not in ("draft", "approved"):
        return None
    pid = r[0]
    return [
        {"title": f"Enviar proposta {r[1]} ao cliente",
         "endpoint": f"/api/v1/redesign/action/proposal-send?pid={pid}",
         "method": "POST", "btnLabel": "Enviar", "submitLabel": "Enviar ao cliente (e-mail)",
         "btnStyle": "primary", "okMsg": "Proposta enviada ao cliente (e-mail). Recarregue a tela.",
         "fields": []},
        {"title": f"Enviar {r[1]} pelo WhatsApp do José Luís",
         "sub": "PDF + link de assinatura, com rastreio de leitura.",
         "endpoint": f"/api/v1/crm/proposals/{pid}/send-whatsapp",
         "method": "POST", "btnLabel": "WhatsApp", "submitLabel": "Enviar por WhatsApp agora",
         "btnStyle": "outline", "okMsg": "Proposta enviada por WhatsApp. Recarregue a tela.",
         "fields": []},
        {"title": f"Enviar {r[1]} por e-mail E WhatsApp",
         "sub": "Manda os dois; o WhatsApp cita o e-mail para o cliente não achar que é golpe.",
         "endpoint": f"/api/v1/crm/proposals/{pid}/send-completo",
         "method": "POST", "btnLabel": "E-mail + Zap", "submitLabel": "Enviar pelos dois canais",
         "btnStyle": "outline", "okMsg": "Proposta enviada por e-mail e WhatsApp. Recarregue.",
         "fields": []},
        {"title": f"Marcar {r[1]} como enviada (sem reenviar)",
         "sub": "Use quando você mandou por fora — WhatsApp pessoal, impressa, em reunião. "
                "Só acerta o status; NÃO manda nada ao cliente.",
         "endpoint": f"/api/v1/crm/proposals/{pid}/marcar-enviada",
         "method": "POST", "btnLabel": "Já enviei", "submitLabel": "Marcar como enviada",
         "btnStyle": "outline", "okMsg": "Proposta marcada como enviada. Recarregue a tela.",
         "fields": []},
    ]


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
    # Assinatura eletrônica na PRÓPRIA linha. r[6]=tem modelo · r[7]=solicitações abertas
    # · r[8]=já assinadas. Sem modelo não há instrumento para assinar, então nem oferece.
    if r[6]:
        if not r[7]:
            acts.append({"title": f"Abrir assinatura eletrônica de {r[1]}",
                         "endpoint": "/api/v1/redesign/action/contrato-abrir-assinatura",
                         "method": "POST", "btnLabel": "Assinatura", "submitLabel": "Abrir assinatura",
                         "btnStyle": "primary",
                         "okMsg": "Assinatura aberta — os links estão na mensagem. Recarregue.",
                         "fields": [{"key": "contrato", "label": "Contrato", "type": "text",
                                     "span": "span 2", "value": r[1]},
                                    {"key": "email_cliente", "label": "E-mail do cliente (opcional)",
                                     "type": "text", "span": "span 2", "value": ""}]})
        elif r[8] < r[7]:
            acts.append({"title": f"Enviar link de assinatura de {r[1]}",
                         "endpoint": "/api/v1/redesign/action/contrato-enviar-link",
                         "method": "POST", "btnLabel": "Enviar link", "submitLabel": "Enviar",
                         "btnStyle": "outline",
                         "okMsg": "Link enviado/gerado — veja a mensagem.",
                         "fields": [{"key": "contrato", "label": "Contrato", "type": "text",
                                     "span": "span 2", "value": r[1]},
                                    {"key": "parte", "label": "Para quem (cliente | empresa)",
                                     "type": "text", "span": "span 1", "value": "cliente"},
                                    {"key": "email", "label": "E-mail (vazio devolve o link)",
                                     "type": "text", "span": "span 1", "value": ""}]})
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
        # ⚠️ `coalesce(is_active,true)` nas QUATRO, e isso não é detalhe: 16 das 33
        # propostas estão soft-deleted (28/08/2026). Sem o filtro a TELA dizia "33
        # propostas · Rascunho 22" enquanto o chat, já corrigido, dizia 16 e 7 — duas
        # verdades sobre o mesmo funil, e quem abre a tela e pergunta ao José Luís recebe
        # números diferentes no mesmo minuto.
        # Regra da casa: valor de status novo (ou filtro novo) tem consumidor; conferir
        # TODOS antes de declarar consertado — foi assim que 68 plantões sumiram do
        # holerite.
        _viva = " coalesce(is_active, true)"
        _pt = await _scalar(db, "SELECT count(*) FROM proposals WHERE" + _viva)
        _pd = await _scalar(db, "SELECT count(*) FROM proposals WHERE status::text='draft'"
                                " AND" + _viva)
        _ps = await _scalar(db, "SELECT count(*) FROM proposals WHERE status::text='sent'"
                                " AND" + _viva)
        _pa = await _scalar(db, "SELECT count(*) FROM proposals WHERE status::text='accepted'"
                                " AND" + _viva)
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
        # 23/08: o botão apontava para /pdf — o MOLDE de 3 páginas — e não para /pdf-modelo,
        # que renderiza o instrumento do modelo cadastrado. Quem clicasse recebia um resumo
        # achando que era o contrato. Agora o instrumento só aparece em quem TEM modelo; sem
        # modelo, o molde continua oferecido mas dizendo o que é.
        # A coluna Assinatura vem de sig_signature_requests — o banco dizendo quem firmou,
        # nunca inferência a partir do status do contrato.
        await safe("contratos", tbl("Contratos", f"{await _scalar(db, 'SELECT count(*) FROM contracts')} contratos · baixe o instrumento e acompanhe a assinatura", "Novo contrato",
            ["Contrato", "Cliente", "Serviço", "Mensal", "Status", "Assinatura"],
            "1.1fr 1.5fr 1fr 0.9fr 0.8fr 1.1fr",
            "SELECT ct.id, coalesce(ct.contract_number,'—'), coalesce(cl.name, ct.name, '—'), "
            "coalesce(ct.monthly_value,0), coalesce(ct.total_value,0), ct.status::text, "
            "ct.template_id::text, "
            "(SELECT count(*) FROM sig_signature_requests s WHERE s.reference_code = ct.contract_number), "
            "(SELECT count(*) FROM sig_signature_requests s WHERE s.reference_code = ct.contract_number AND s.signed_at IS NOT NULL), "
            "coalesce(ct.tipo_servico::text,'—') "
            "FROM contracts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.start_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t((r[2] or '—')[:32]), t((r[9] or '—').replace('_', ' ')),
                       t(brl(r[3])),
                       b("Ativo", "ok") if (r[5] or "").lower() in ("active", "ativo", "vigente") else b(r[5] or "—", "mut"),
                       (b("Não aberta", "mut") if not r[7]
                        else b(f"{r[8]}/{r[7]} assinada(s)", "ok" if r[8] and r[8] == r[7] else "warn"))],
            docsfn=lambda r: ([doc("Contrato completo (PDF)",
                                   f"/api/v1/crm/contracts/{r[1]}/pdf-modelo", fmt="pdf")] if r[6]
                              else [doc("Resumo (sem modelo vinculado)",
                                        f"/api/v1/crm/contracts/{r[0]}/pdf", fmt="pdf")]),
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

    # ────────────────────────────────────────────────────────────────────────────────
    # FIOS SOLTOS DO CRM (2026-08-10) — 16 capacidades que o backend ja tinha e o
    # redesign nao alcancava. Medido com backend-recon; contratos extraidos por
    # introspecao dos modelos Pydantic (eval_str), nao adivinhados.
    #
    # DE FORA ficaram, de proposito:
    #   · /docs/orcamento/pdf e /visitas/achados — exigem LISTA DE OBJETOS (itens,
    #     achados) e o renderizador de form so tem campo escalar. Form mentiroso e
    #     pior que ausencia de form.
    #   · /apresentacoes/gerar — mesma razao (estrutura de slides).
    #   · /docs/expurgar-teste — soft-delete em MASSA. Botao para isso e convite a
    #     acidente; se for preciso, que seja com gate proprio.
    #   · /assets/upload — infra (logo/selo), nao fluxo de usuario.
    #   · /proposals/{id}/send-* — sao por-proposta: lugar certo e a acao por linha da
    #     tabela de propostas (_proposta_actions), nao uma tela solta pedindo o UUID.
    # ────────────────────────────────────────────────────────────────────────────────
    out["cliente-anotar"] = {
        "title": "Anotar na ficha do cliente",
        "sub": "A anotação entra na ficha viva — o José Luís lê e usa no atendimento.",
        "cta": "Anotar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/clientes/anotar", "okMsg": "Anotação registrada"},
        "fields": [
            {"key": "ref", "label": "Cliente (CNPJ, nome ou id)*", "type": "text", "span": "span 2",
             "ph": "Ex.: 12.345.678/0001-90 ou CONDOMINIO LIFE CENTRO"},
            {"key": "nota", "label": "Anotação*", "type": "textarea", "span": "span 2",
             "ph": "O que aconteceu / o que combinaram / o que observar da próxima vez"},
        ],
    }
    out["negociacao-responsavel"] = {
        "title": "Definir quem conduz a negociação",
        "sub": "'jordan' PAUSA o acompanhamento automático do José Luís nesse cliente.",
        "cta": "Definir", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/negociacoes/responsavel", "okMsg": "Responsável definido"},
        "fields": [
            {"key": "cliente", "label": "Cliente (CNPJ, nome ou id)*", "type": "text", "span": "span 2"},
            {"key": "responsavel", "label": "Quem conduz*", "type": "select", "span": "span 2",
             "ph": "Selecione", "options": [
                 {"value": "jordan", "label": "Jordan — pausa o José Luís neste cliente"},
                 {"value": "jose_luis", "label": "José Luís — acompanhamento automático"}]},
        ],
    }
    out["whatsapp-cadastrar"] = {
        "title": "Cadastrar WhatsApp do cliente",
        "sub": "Normaliza para E.164. Só grava o número — não envia nada.",
        "cta": "Cadastrar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/whatsapp/cadastrar", "okMsg": "WhatsApp cadastrado"},
        "fields": [
            {"key": "cnpj_ou_id", "label": "Cliente — CNPJ ou id*", "type": "text", "span": "span 1"},
            {"key": "numero", "label": "Número*", "type": "text", "span": "span 1",
             "ph": "(92) 99999-9999 ou +5592999999999"},
        ],
    }
    out["reuniao-sugerir"] = {
        "title": "Sugerir reunião",
        "sub": "Entra como 'sugerido' — só vira agendada quando você confirma.",
        "cta": "Sugerir", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/reunioes", "okMsg": "Reunião sugerida"},
        "fields": [
            {"key": "titulo", "label": "Título*", "type": "text", "span": "span 2",
             "ph": "Ex.: Apresentação da proposta — Cond. Life Centro"},
            {"key": "quando_iso", "label": "Quando* (AAAA-MM-DDTHH:MM)", "type": "text", "span": "span 1",
             "ph": "2026-08-15T14:30"},
            {"key": "cliente_nome", "label": "Cliente", "type": "text", "span": "span 1"},
            {"key": "local", "label": "Local", "type": "text", "span": "span 1",
             "ph": "Presencial (endereço) ou link"},
            {"key": "tipo", "label": "Tipo", "type": "select", "span": "span 1", "ph": "Selecione",
             "options": [{"value": "presencial", "label": "Presencial"},
                         {"value": "online", "label": "Online"},
                         {"value": "telefone", "label": "Telefone"}]},
            {"key": "notes", "label": "Pauta / observações", "type": "textarea", "span": "span 2"},
        ],
    }
    for _sid, _tit, _ep, _cta, _ok in (
        ("reuniao-confirmar", "Confirmar reunião", "confirmar", "Confirmar", "Reunião confirmada"),
        ("reuniao-cancelar", "Cancelar reunião", "cancelar", "Cancelar reunião", "Reunião cancelada"),
    ):
        out[_sid] = {
            "title": _tit, "sub": "O id da reunião está na tela de reuniões/agenda.",
            "cta": _cta, "type": "form",
            "submit": {"endpoint": f"/api/v1/crm/reunioes/{_ep}", "okMsg": _ok},
            "fields": [{"key": "meeting_id", "label": "ID da reunião*", "type": "text", "span": "span 2",
                        "ph": "cole o id da reunião"}],
        }
    out["visita-montar"] = {
        "title": "Montar relatório de visita",
        "sub": "Persiste o relatório sintetizado da visita técnica.",
        "cta": "Gravar relatório", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/visitas/montar", "okMsg": "Relatório gravado"},
        "fields": [
            {"key": "ref", "label": "Visita — id ou referência*", "type": "text", "span": "span 2"},
            {"key": "situacao_atual", "label": "Situação atual", "type": "textarea", "span": "span 2",
             "ph": "O que existe hoje no cliente"},
            {"key": "diagnostico_tecnico", "label": "Diagnóstico técnico", "type": "textarea", "span": "span 2"},
            {"key": "oportunidade_comercial", "label": "Oportunidade comercial", "type": "textarea", "span": "span 2"},
            {"key": "proximos_passos", "label": "Próximos passos", "type": "textarea", "span": "span 2"},
        ],
    }
    out["visita-registrar-lead"] = {
        "title": "Criar lead a partir da visita",
        "sub": "Cria/atualiza lead + oportunidade. Passa pelo dedup por telefone — cliente "
               "que já existe é reaproveitado, não duplicado.",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/visitas/registrar-lead", "okMsg": "Lead registrado"},
        "fields": [
            {"key": "ref", "label": "Visita — id ou referência*", "type": "text", "span": "span 2"},
            {"key": "telefone", "label": "Telefone", "type": "text", "span": "span 1"},
            {"key": "cnpj", "label": "CNPJ", "type": "text", "span": "span 1"},
            {"key": "valor_estimado", "label": "Valor estimado (R$)", "type": "text", "span": "span 1",
             "ph": "0,00"},
        ],
    }
    out["doc-ordem-servico"] = {
        "title": "Ordem de serviço (PDF)",
        "sub": "Gera a OS no padrão-ouro com selo. O gerador já existia e não tinha botão.",
        "cta": "Gerar PDF", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/docs/ordem-servico/pdf", "okMsg": "Ordem de serviço gerada"},
        "fields": [
            {"key": "cliente", "label": "Cliente*", "type": "text", "span": "span 2"},
            {"key": "servico", "label": "Serviço*", "type": "text", "span": "span 2",
             "ph": "Ex.: Instalação de CFTV — 8 câmeras"},
            {"key": "descricao", "label": "Descrição", "type": "textarea", "span": "span 2"},
            {"key": "endereco", "label": "Endereço", "type": "text", "span": "span 2"},
            {"key": "responsavel", "label": "Responsável", "type": "text", "span": "span 1"},
            {"key": "valor", "label": "Valor (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "prazo", "label": "Prazo", "type": "text", "span": "span 1", "ph": "Ex.: 5 dias úteis"},
            {"key": "numero", "label": "Número da OS", "type": "text", "span": "span 1",
             "ph": "vazio = automático"},
            {"key": "documento", "label": "CNPJ/CPF do cliente", "type": "text", "span": "span 1"},
            {"key": "observacoes", "label": "Observações", "type": "textarea", "span": "span 2"},
        ],
    }
    out["followup-tocar"] = {
        "title": "Tocar cliente (follow-up manual)",
        "sub": "Toque do José Luís por WhatsApp. Deixe 'só simular' para ver o texto e o número "
               "resolvido ANTES de enviar.",
        "cta": "Executar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/followups", "okMsg": "Follow-up processado",
                   "confirm": "Se você escolheu ENVIAR, uma mensagem real sai para o cliente agora. Confirma?"},
        "fields": [
            {"key": "mensagem", "label": "Mensagem*", "type": "textarea", "span": "span 2"},
            {"key": "cliente", "label": "Cliente (CNPJ, nome ou id)", "type": "text", "span": "span 1"},
            {"key": "deal_id", "label": "Oportunidade (id)", "type": "text", "span": "span 1"},
            {"key": "lead_id", "label": "Lead (id)", "type": "text", "span": "span 1"},
            {"key": "proposal_id", "label": "Proposta (id)", "type": "text", "span": "span 1"},
            {"key": "confirmar", "label": "Enviar de verdade?", "type": "select", "span": "span 2",
             "ph": "Só simular (padrão)", "options": _CONFIRMAR},
        ],
    }
    out["followup-lote"] = {
        "title": "Tocar em lote — propostas pendentes",
        "sub": "Atinge TODOS os clientes com proposta pendente. Simule primeiro: a prévia diz "
               "quantos e quais seriam tocados.",
        "cta": "Executar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/followups/lote", "okMsg": "Lote processado",
                   "confirm": "LOTE: se você escolheu ENVIAR, isto dispara mensagens reais para "
                              "TODOS os clientes com proposta pendente. Confirma?"},
        "fields": [
            {"key": "mensagem", "label": "Mensagem (vazio = template padrão)", "type": "textarea",
             "span": "span 2"},
            {"key": "confirmar", "label": "Enviar de verdade?", "type": "select", "span": "span 2",
             "ph": "Só simular (padrão)", "options": _CONFIRMAR},
        ],
    }
    out["followup-resposta"] = {
        "title": "Registrar retorno do cliente",
        "sub": "Para quando o cliente respondeu por fora (ligação, presencial) e o inbound "
               "automático não capturou.",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/followups/resposta", "okMsg": "Retorno registrado"},
        "fields": [
            {"key": "deal_id", "label": "Oportunidade (id)", "type": "text", "span": "span 1"},
            {"key": "followup_id", "label": "Follow-up (id)", "type": "text", "span": "span 1"},
            {"key": "status", "label": "Status", "type": "select", "span": "span 1", "ph": "Selecione",
             "options": [{"value": "respondido", "label": "Respondeu"},
                         {"value": "sem_resposta", "label": "Sem resposta"},
                         {"value": "recusou", "label": "Recusou"}]},
            {"key": "classificacao", "label": "Classificação", "type": "text", "span": "span 1",
             "ph": "Ex.: quente / morno / frio"},
            {"key": "nota", "label": "O que o cliente disse", "type": "textarea", "span": "span 2"},
        ],
    }
    out["followup-optout"] = {
        "title": "Opt-out — não perturbe",
        "sub": "Marca o número para NÃO receber mais follow-ups. Protege o cliente e a operação.",
        "cta": "Marcar opt-out", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/followups/optout", "okMsg": "Número marcado como opt-out"},
        "fields": [
            {"key": "numero", "label": "Número*", "type": "text", "span": "span 1",
             "ph": "(92) 99999-9999"},
            {"key": "motivo", "label": "Motivo", "type": "text", "span": "span 1",
             "ph": "Ex.: pediu para não receber"},
        ],
    }
    out["nps-enviar"] = {
        "title": "Enviar pesquisa NPS",
        "sub": "Pergunta de 0 a 10 por WhatsApp. Simule antes para conferir o número.",
        "cta": "Executar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/nps/enviar", "okMsg": "NPS processado",
                   "confirm": "Se você escolheu ENVIAR, a pesquisa sai agora para o cliente. Confirma?"},
        "fields": [
            {"key": "ref", "label": "Cliente (CNPJ, nome ou id)*", "type": "text", "span": "span 2"},
            {"key": "confirmar", "label": "Enviar de verdade?", "type": "select", "span": "span 2",
             "ph": "Só simular (padrão)", "options": _CONFIRMAR},
        ],
    }
    out["reativar-lead"] = {
        "title": "Reativar lead frio",
        "sub": "Reengaja por WhatsApp um lead parado. Simule antes.",
        "cta": "Executar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/reativar-lead", "okMsg": "Reativação processada",
                   "confirm": "Se você escolheu ENVIAR, a mensagem sai agora para o lead. Confirma?"},
        "fields": [
            {"key": "ref", "label": "Lead (id, telefone ou nome)*", "type": "text", "span": "span 2"},
            {"key": "mensagem", "label": "Mensagem (vazio = template padrão)", "type": "textarea",
             "span": "span 2"},
            {"key": "confirmar", "label": "Enviar de verdade?", "type": "select", "span": "span 2",
             "ph": "Só simular (padrão)", "options": _CONFIRMAR},
        ],
    }
    out["simular-fechamento"] = {
        "title": "Simular fechamento (what-if)",
        "sub": "Se estes negócios fecharem, como fica ganho × meta. Não altera nada.",
        "cta": "Simular", "type": "form",
        # showResult: sem ele a tela diria "Simulação executada" e jogaria fora o numero — que
        # e o produto inteiro de um what-if. A flag e opt-in no ModuleView; enquanto o front nao
        # subir ela e ignorada (chave desconhecida), entao ligar agora e seguro e ja nasce certo.
        "submit": {"endpoint": "/api/v1/crm/simular-fechamento", "okMsg": "Simulação executada",
                   "showResult": True},
        "fields": [
            {"key": "estagio", "label": "Estágio inteiro", "type": "text", "span": "span 1",
             "ph": "Ex.: proposta — simula todos desse estágio"},
            {"key": "deals", "label": "Ou negócios específicos (ids separados por vírgula)",
             "type": "text", "span": "span 1"},
        ],
    }
    out["consultor-comercial"] = {
        "title": "Consultor comercial",
        "sub": "Pergunta ancorada no funil e nos contratos reais. É consulta — não altera nada.",
        "cta": "Perguntar", "type": "form",
        "submit": {"endpoint": "/api/v1/comercial/consultor/perguntar",
                   "okMsg": "Consulta respondida", "showResult": True},
        "fields": [
            {"key": "area", "label": "Área*", "type": "text", "span": "span 2",
             "ph": "Ex.: funil, propostas, contratos, metas"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2",
             "ph": "Ex.: quais propostas estão paradas há mais de 15 dias?"},
        ],
    }

    out["consultor-comercial-arquivo"] = {
        "title": "Consultor comercial — com anexo",
        "sub": "Anexe edital, proposta do concorrente ou contrato e pergunte sobre ele. O arquivo é lido para responder, não fica guardado.",
        "cta": "Analisar", "type": "form",
        "submit": {"endpoint": "/api/v1/comercial/consultor/perguntar-arquivo",
                   "multipart": True, "query": True,
                   "okMsg": "Análise concluída", "showResult": True},
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            {"key": "area", "label": "Área", "type": "text", "span": "span 2", "ph": "Ex.: funil, propostas, contratos"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }

    # ── Rotas que pedem LISTA DE OBJETOS (2026-08-10) ───────────────────────────────
    # Destravadas pelo campo `type: json` do ModuleView: o textarea e parseado antes do
    # envio. O placeholder mostra a FORMA esperada — sem isso o usuario adivinha.
    out["doc-orcamento"] = {
        "title": "Orçamento / proposta (PDF)",
        "sub": "Gera o orçamento no padrão-ouro com selo. Os itens vao em lista — o exemplo "
               "no campo mostra o formato.",
        "cta": "Gerar PDF", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/docs/orcamento/pdf", "okMsg": "Orçamento gerado"},
        "fields": [
            {"key": "cliente", "label": "Cliente*", "type": "text", "span": "span 2"},
            {"key": "titulo", "label": "Titulo", "type": "text", "span": "span 1"},
            {"key": "numero", "label": "Numero", "type": "text", "span": "span 1",
             "ph": "vazio = automático"},
            {"key": "documento", "label": "CNPJ/CPF do cliente", "type": "text", "span": "span 1"},
            {"key": "cidade", "label": "Cidade", "type": "text", "span": "span 1"},
            {"key": "objeto", "label": "Objeto", "type": "textarea", "span": "span 2"},
            {"key": "itens", "label": "Itens*", "type": "json", "span": "span 2",
             "ph": '[{"descricao": "Camera IP 4MP", "quantidade": 8, "valor_unitario": 450.00}, '
                   '{"descricao": "Instalacao", "quantidade": 1, "valor_unitario": 1200.00}]'},
            {"key": "desconto_avista_pct", "label": "Desconto a vista (%)", "type": "number",
             "span": "span 1"},
            {"key": "parcelas", "label": "Parcelas", "type": "number", "span": "span 1"},
            {"key": "entrada", "label": "Entrada (R$)", "type": "number", "span": "span 1"},
            {"key": "observacao", "label": "Observacao", "type": "textarea", "span": "span 2"},
        ],
    }
    out["apresentacao-gerar"] = {
        "title": "Gerar apresentacao",
        "sub": "Apresentacao no padrão Conecta PRO. Os slides vao em lista — cada um com "
               "título e conteudo.",
        "cta": "Gerar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/apresentacoes/gerar", "okMsg": "Apresentacao gerada"},
        "fields": [
            {"key": "titulo", "label": "Titulo*", "type": "text", "span": "span 2"},
            {"key": "subtitulo", "label": "Subtitulo", "type": "text", "span": "span 2"},
            {"key": "cliente", "label": "Cliente", "type": "text", "span": "span 1"},
            {"key": "local", "label": "Local", "type": "text", "span": "span 1"},
            {"key": "data", "label": "Data", "type": "text", "span": "span 1", "ph": "DD/MM/AAAA"},
            {"key": "slides", "label": "Slides", "type": "json", "span": "span 2",
             "ph": '[{"titulo": "Quem somos", "conteudo": "Texto do slide"}, '
                   '{"titulo": "Proposta", "conteudo": "..."}]'},
        ],
    }
    out["visita-achados"] = {
        "title": "Anexar achados ao relatório de visita",
        "sub": "Analises de foto, audio, video ou notas. Vao em lista, um achado por objeto.",
        "cta": "Anexar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/visitas/achados", "okMsg": "Achados anexados"},
        "fields": [
            {"key": "ref", "label": "Visita — id ou referência*", "type": "text", "span": "span 2"},
            {"key": "achados", "label": "Achados*", "type": "json", "span": "span 2",
             "ph": '[{"tipo": "foto", "descricao": "Portao sem fechadura eletrônica"}, '
                   '{"tipo": "nota", "descricao": "Cliente pediu orçamento de CFTV"}]'},
        ],
    }
    out["asset-upload"] = {
        "title": "Enviar logo ou selo",
        "sub": "Grava a imagem no volume persistente, para os documentos usarem. O conteudo "
               "vai em base64 — util quando não da para subir arquivo.",
        "cta": "Enviar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/assets/upload", "okMsg": "Asset gravado",
                   "showResult": True},
        "fields": [
            {"key": "tipo", "label": "Tipo", "type": "select", "span": "span 1", "ph": "Selecione",
             "options": [{"value": "logo", "label": "Logo"}, {"value": "selo", "label": "Selo"}]},
            {"key": "nome", "label": "Nome do arquivo", "type": "text", "span": "span 1",
             "ph": "ex.: logo_patrimonial.png"},
            {"key": "conteudo_base64", "label": "Conteudo em base64*", "type": "textarea",
             "span": "span 2", "ph": "cole o base64 da imagem"},
        ],
    }
    out["expurgar-teste"] = {
        "title": "Arquivar documentos de teste",
        "sub": "Arquiva (soft-delete) TODOS os documentos marcados como teste. Não toca em "
               "documento real. Sem confirmar, a rota so mostra o que seria arquivado.",
        "cta": "Executar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/docs/expurgar-teste", "query": True,
                   "okMsg": "Expurgo processado", "showResult": True,
                   "confirm": "Se você marcou CONFIRMAR, todos os documentos de teste são "
                              "arquivados agora. Confirma?"},
        "fields": [
            {"key": "confirmar", "label": "Confirmar de verdade?", "type": "select",
             "span": "span 2", "ph": "Não — so mostrar (padrão)",
             "options": [{"value": "false", "label": "Não — so mostrar o que seria arquivado"},
                         {"value": "true", "label": "SIM — arquivar agora"}]},
        ],
    }

    return out
