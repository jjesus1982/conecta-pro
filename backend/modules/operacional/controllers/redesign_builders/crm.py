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


def _brl_norm(s) -> str:
    """Normaliza dinheiro DIGITADO em formulário para string numérica ("1920.50").
    Aceita "1.920,50", "1920,50", "1920.50", "R$ 1.920,50" e "1920". O antigo
    `.replace(".", "").replace(",", ".")` tratava TODO ponto como milhar: "1920.50"
    virava 192050 — o simulador de preço do CRM devolveu R$ 476 mil por posto
    (medido 07/09/2026 pelo navegador)."""
    s = str(s or "").replace("R$", "").replace(" ", "").strip()
    if "," in s:
        return s.replace(".", "").replace(",", ".")
    if s.count(".") == 1 and 1 <= len(s.split(".")[1]) <= 2:
        return s
    return s.replace(".", "")

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
        monthly = float(_brl_norm(str(payload.get("monthly_value") or payload.get("valor") or "0")))
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


# ── LIGAR 08/09/2026: formulários que precisam de {id} no caminho da rota do CRM ─────────
def _num(v, default=0.0) -> float:
    try:
        return float(_brl_norm(str(v))) if v not in (None, "") else default
    except (ValueError, TypeError):
        return default


@router.post("/action/contrato-item-novo")
async def rd_action_contrato_item_novo(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from modules.crm.repositories.contract_repository import ContractRepository
    from modules.crm.schemas.contract import ContractItemCreate
    cid = (payload.get("contract_id") or "").strip()
    if len(cid) != 36:
        raise HTTPException(status_code=400, detail="Selecione o contrato.")
    try:
        data = ContractItemCreate(service_type=payload.get("service_type") or "security", service_name=(payload.get("service_name") or "").strip(),
                                  description=(payload.get("description") or "").strip() or None,
                                  quantity=int(_num(payload.get("quantity"), 1) or 1), unit_price=str(_num(payload.get("unit_price"))))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    item = await ContractRepository(db).add_item(cid, data)
    if not item:
        raise HTTPException(status_code=400, detail="Contrato não encontrado ou não aceita itens neste status.")
    return {"ok": True, "id": str(item.id), "message": "Item adicionado ao contrato"}


@router.post("/action/aditivo-novo")
async def rd_action_aditivo_novo(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from modules.crm.repositories.contract_repository import ContractRepository
    from modules.crm.schemas.contract import ContractAddendumCreate
    cid = (payload.get("contract_id") or "").strip()
    if len(cid) != 36:
        raise HTTPException(status_code=400, detail="Selecione o contrato.")
    try:
        data = ContractAddendumCreate(
            addendum_type=payload.get("addendum_type") or "other", effective_date=payload.get("effective_date"),
            description=(payload.get("description") or "").strip(), reason=(payload.get("reason") or "").strip() or None,
            new_value=str(_num(payload["new_value"])) if payload.get("new_value") not in (None, "") else None,
            adjustment_percent=str(_num(payload["adjustment_percent"])) if payload.get("adjustment_percent") not in (None, "") else None)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    add = await ContractRepository(db).create_addendum(cid, data, created_by_id=str(current_user.id))
    if not add:
        raise HTTPException(status_code=400, detail="Contrato não encontrado.")
    return {"ok": True, "id": str(add.id), "message": f"Aditivo nº {getattr(add, 'addendum_number', '')} registrado"}


@router.post("/action/proposta-item-novo")
async def rd_action_proposta_item_novo(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from modules.crm.repositories.proposal_repository import ProposalRepository
    from modules.crm.schemas.proposal import ProposalItemCreate
    pid = (payload.get("proposal_id") or "").strip()
    if len(pid) != 36:
        raise HTTPException(status_code=400, detail="Selecione a proposta.")
    try:
        data = ProposalItemCreate(code=None, name=(payload.get("name") or "").strip(), description=(payload.get("description") or "").strip() or None,
                                  unit=(payload.get("unit") or "un").strip(), quantity=_num(payload.get("quantity"), 1) or 1,
                                  unit_price=_num(payload.get("unit_price")), discount_percent=_num(payload.get("discount_percent")))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    item = await ProposalRepository(db).add_item(pid, data)
    if not item:
        raise HTTPException(status_code=400, detail="Proposta não encontrada ou já enviada.")
    return {"ok": True, "id": str(item.id), "message": "Item adicionado à proposta"}


def _clients_service():
    from core.database.session import SyncSessionLocal
    from modules.clients.services.client_service import ClientService
    sess = SyncSessionLocal()
    return sess, ClientService(sess)


@router.post("/action/condominio-novo")
async def rd_action_condominio_novo(current_user: CurrentActiveUser, payload: dict = Body(...)) -> dict:
    import asyncio
    from uuid import UUID as _U
    from modules.clients.schemas.client_schemas import CondominiumCreate
    cid = (payload.get("client_id") or "").strip()
    if len(cid) != 36 or len((payload.get("name") or "").strip()) < 2:
        raise HTTPException(status_code=400, detail="Selecione o cliente e informe o nome.")
    campos = {k: (str(payload.get(k)).strip() or None) for k in ("cnpj", "address_street", "address_number", "address_neighborhood", "address_city", "address_state", "syndic_name", "syndic_phone") if payload.get(k)}
    # 09/09 (kit de teste Conecta Village): CondominiumCreate exige address_state e o form não tinha o campo → 400 sempre
    campos.setdefault("address_state", "AM"); campos.setdefault("address_city", "Manaus"); campos.setdefault("address_street", campos.get("address_street") or "—")
    if payload.get("total_units"):
        campos["total_units"] = int(_num(payload["total_units"]))
    def _run():
        sess, svc = _clients_service()
        try:
            data = CondominiumCreate(client_id=_U(cid), name=payload["name"].strip()[:200], **campos)
            c = svc.create_condominium(data, created_by=_U(str(current_user.id)))
            sess.commit()
            return str(c.id), c.name
        finally:
            sess.close()
    try:
        oid, nome = await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Não foi possível criar: {e}")
    return {"ok": True, "id": oid, "message": f"Condomínio {nome} criado"}


@router.post("/action/cliente-inadimplente")
async def rd_action_cliente_inadimplente(current_user: CurrentActiveUser, payload: dict = Body(...)) -> dict:
    import asyncio
    from decimal import Decimal
    from uuid import UUID as _U
    cid = (payload.get("client_id") or "").strip(); valor = _num(payload.get("debt_amount"))
    if len(cid) != 36 or valor <= 0:
        raise HTTPException(status_code=400, detail="Selecione o cliente e informe o valor em aberto (> 0).")
    def _run():
        sess, svc = _clients_service()
        try:
            c = svc.set_defaulter(_U(cid), Decimal(str(round(valor, 2))), updated_by=_U(str(current_user.id)))
            if not c:
                return None
            sess.commit(); return c.name
        finally:
            sess.close()
    nome = await asyncio.to_thread(_run)
    if not nome:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return {"ok": True, "message": f"{nome} marcado como inadimplente (R$ {valor:,.2f})"}


@router.post("/action/contrato-reajuste-calcular")
async def rd_action_contrato_reajuste_calcular(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from datetime import date as _date
    from modules.crm.controllers.contract_controller import calculate_adjustment
    cid = (payload.get("contract_id") or "").strip()
    if len(cid) != 36:
        raise HTTPException(status_code=400, detail="Selecione o contrato.")
    pct = _num(payload.get("custom_percent"))
    if pct <= 0:
        raise HTTPException(status_code=422, detail="Informe o percentual de reajuste (o índice não é consultado automaticamente).")
    ed = payload.get("effective_date") or None
    res = await calculate_adjustment(cid, current_user, db, custom_percent=pct, effective_date=_date.fromisoformat(ed) if ed else None)
    d = res.model_dump() if hasattr(res, "model_dump") else dict(res)
    return {"ok": True, "message": "Só simulação — nada foi alterado no contrato.", **{k: (str(v) if not isinstance(v, (int, float, str, type(None))) else v) for k, v in d.items()}}



@router.post("/action/cliente-ficha-360")
async def rd_action_cliente_ficha_360(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Reusa GET /crm/clients/{id}/360 (o form do redesign só faz POST)."""
    from uuid import UUID as _U
    from modules.crm.controllers.contact_controller import visao_360_cliente
    cid = (payload.get("client_id") or "").strip()
    if len(cid) != 36:
        raise HTTPException(status_code=400, detail="Selecione o cliente.")
    res = await visao_360_cliente(_U(cid), current_user, db)
    d = res.model_dump() if hasattr(res, "model_dump") else res
    return {"ok": True, "message": "Ficha 360 carregada", **(d if isinstance(d, dict) else {"ficha": d})}


@router.post("/action/consultar-cnpj-cep")
async def rd_action_consultar_cnpj_cep(current_user: CurrentActiveUser, payload: dict = Body(...)) -> dict:
    """Reusa GET /crm/enrichment/cnpj/{cnpj} e /cep/{cep} (BrasilAPI com cache)."""
    from fastapi import Response
    from modules.crm.controllers.enrichment_controller import enrich_cep, enrich_cnpj
    tipo = (payload.get("tipo") or "cnpj").strip().lower()
    valor = "".join(ch for ch in str(payload.get("valor") or "") if ch.isdigit())
    if tipo == "cep" and len(valor) != 8:
        raise HTTPException(status_code=422, detail="CEP precisa ter 8 dígitos.")
    if tipo == "cnpj" and len(valor) != 14:
        raise HTTPException(status_code=422, detail="CNPJ precisa ter 14 dígitos.")
    fn = enrich_cep if tipo == "cep" else enrich_cnpj
    res = await fn(valor, Response(), current_user)
    d = res.model_dump() if hasattr(res, "model_dump") else res
    return {"ok": True, "message": f"{tipo.upper()} consultado", **(d if isinstance(d, dict) else {"dados": d})}

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
    # PRIMEIRA da lista de propósito: é a fila do que já foi vendido e ainda não está
    # assinado. Sem entrada no menu a tela existe em `screens`, responde por HTTP e
    # NINGUÉM chega nela — o defeito mais comum desta casa.
    {"id": "contratos-a-emitir", "label": "Central de contratos", "icon": _ICO_DOC},
    {"id": "jose-luis-dashboard", "label": "José Luís — painel do agente", "icon": "M3 3v18h18"},
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
    # LIGAR 08/09/2026 (revisão 100%): rotas que existiam sem tela no redesign
    {"id": "contato-novo", "label": "Novo contato", "icon": _ICO_CHAT},
    {"id": "produtos", "label": "Produtos (catálogo)", "icon": _ICO_DOC},
    {"id": "produto-novo", "label": "Novo produto", "icon": _ICO_DOC},
    {"id": "timeline-nota", "label": "Anotar na timeline", "icon": _ICO_CHAT},
    {"id": "tarefas", "label": "Tarefas", "icon": _ICO_CAL},
    {"id": "contrato-itens", "label": "Itens de contrato", "icon": _ICO_DOC},
    {"id": "contrato-item-novo", "label": "Novo item de contrato", "icon": _ICO_DOC},
    {"id": "aditivos", "label": "Aditivos", "icon": _ICO_DOC},
    {"id": "aditivo-novo", "label": "Novo aditivo", "icon": _ICO_DOC},
    {"id": "modelos-contrato", "label": "Modelos de contrato", "icon": _ICO_DOC},
    {"id": "modelo-contrato-novo", "label": "Novo modelo de contrato", "icon": _ICO_DOC},
    {"id": "proposta-itens", "label": "Itens de proposta", "icon": _ICO_DOC},
    {"id": "proposta-item-novo", "label": "Novo item de proposta", "icon": _ICO_DOC},
    {"id": "condominios", "label": "Condomínios", "icon": _ICO_DOC},
    {"id": "condominio-novo", "label": "Novo condomínio", "icon": _ICO_DOC},
    {"id": "cliente-inadimplente", "label": "Marcar inadimplência", "icon": _ICO_CHAT},
    {"id": "contrato-reajuste-calcular", "label": "Calcular reajuste de contrato", "icon": _ICO_DOC},
    {"id": "cliente-ficha-360", "label": "Ficha 360 do cliente", "icon": _ICO_CHAT},
    {"id": "consultar-cnpj-cep", "label": "Consultar CNPJ / CEP", "icon": _ICO_DOC},
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
    pid = r[0]
    if (r[5] or "").lower() == "sent":  # LIGAR 08/09/2026: aceite gera comissão + contrato
        return [
            {"title": f"Cliente ACEITOU a proposta {r[1]}", "sub": "Gera a comissão e o contrato a partir da proposta.",
             "endpoint": f"/api/v1/crm/proposals/{pid}/accept", "method": "POST", "btnLabel": "Aceita",
             "submitLabel": "Registrar aceite", "btnStyle": "primary", "okMsg": "Aceite registrado. Recarregue.", "fields": []},
            {"title": f"Cliente RECUSOU a proposta {r[1]}",
             "endpoint": f"/api/v1/crm/proposals/{pid}/reject", "method": "POST", "btnLabel": "Recusada",
             "submitLabel": "Registrar recusa", "btnStyle": "outline", "okMsg": "Recusa registrada. Recarregue.", "fields": []},
        ]
    if (r[5] or "").lower() not in ("draft", "approved"):
        return None
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


def _fila_actions(r):
    """A ação que DESTRAVA a linha da central — uma só, a do estado atual.

    Reusa os endpoints que já existem (`contrato-da-proposta`, `contrato-abrir-assinatura`,
    `contrato-enviar-link`); a central não inventa caminho novo, só descobre em que ponto
    cada negócio parou e oferece o botão certo ali.

    Oportunidade ganha não ganha botão de propósito: sem proposta não há valor, itens nem
    modalidade, e gerar contrato a partir do nada é exatamente o molde vazio que o render
    recusa. O passo é humano, e a linha diz qual é.
    """
    tipo, ref = r[6], r[1]
    if tipo == "proposta":
        return [{"title": "Gerar o contrato desta proposta",
                 "endpoint": "/api/v1/redesign/action/contrato-da-proposta",
                 "method": "POST", "btnLabel": "Gerar contrato",
                 "submitLabel": "Criar contrato", "btnStyle": "primary",
                 "okMsg": "Contrato criado (rascunho). Recarregue para emitir o instrumento.",
                 "fields": [{"key": "proposal_id", "type": "hidden", "value": ref}]}]
    if tipo == "contrato":
        situacao = r[4]
        if situacao == "Instrumento pronto":
            return [{"title": f"Abrir assinatura eletrônica de {ref}",
                     "endpoint": "/api/v1/redesign/action/contrato-abrir-assinatura",
                     "method": "POST", "btnLabel": "Abrir assinatura",
                     "submitLabel": "Abrir assinatura", "btnStyle": "primary",
                     "okMsg": "Assinatura aberta. A Conecta Mais assina primeiro.",
                     "fields": [
                         {"key": "contrato", "type": "hidden", "value": ref},
                         {"key": "email_cliente", "label": "E-mail do cliente (se não cadastrado)",
                          "type": "text", "span": "span 2", "value": "",
                          "ph": "presidencia@cliente.com.br"}]}]
        if situacao == "Assinatura cancelada":
            # reabrir é o MESMO endpoint de abrir: o serviço cria solicitações novas.
            return [{"title": f"Reabrir a assinatura de {ref}",
                     "endpoint": "/api/v1/redesign/action/contrato-abrir-assinatura",
                     "method": "POST", "btnLabel": "Reabrir assinatura",
                     "submitLabel": "Reabrir", "btnStyle": "primary",
                     "okMsg": "Assinatura reaberta. A Conecta Mais assina primeiro.",
                     "fields": [
                         {"key": "contrato", "type": "hidden", "value": ref},
                         {"key": "email_cliente", "label": "E-mail do cliente (se não cadastrado)",
                          "type": "text", "span": "span 2", "value": "",
                          "ph": "presidencia@cliente.com.br"}]}]
        if situacao == "Assinado, fora de vigência":
            # assinado por todos e ainda `draft`: o contrato existe, vale, e NÃO conta no
            # MRR. É o estado mais fácil de esquecer, porque tudo parece pronto.
            return [{"title": f"Ativar {ref} — coloca em vigência e no faturamento",
                     "endpoint": "/api/v1/redesign/action/contract-activate",
                     "method": "POST", "btnLabel": "Ativar", "submitLabel": "Confirmar ativação",
                     "btnStyle": "primary", "okMsg": "Contrato ativado.",
                     "fields": [{"key": "confirmar", "label": "Digite ATIVAR para confirmar",
                                 "type": "text", "span": "span 2", "value": ""}]}]
        if situacao == "Em assinatura":
            return [{"title": f"Mandar o link de assinatura de {ref}",
                     "endpoint": "/api/v1/redesign/action/contrato-enviar-link",
                     "method": "POST", "btnLabel": "Enviar link",
                     "submitLabel": "Enviar", "btnStyle": "outline",
                     "okMsg": "Convite enviado.",
                     "fields": [
                         {"key": "contrato", "type": "hidden", "value": ref},
                         {"key": "parte", "label": "Para quem", "type": "select", "span": "span 1",
                          "value": "cliente",
                          "options": [{"value": "cliente", "label": "Cliente (CONTRATANTE)"},
                                      {"value": "empresa", "label": "Conecta Mais (CONTRATADA)"}]},
                         {"key": "email", "label": "E-mail (vazio = o cadastrado)",
                          "type": "text", "span": "span 2", "value": ""}]}]
    return []


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
    if st == "active":  # LIGAR 08/09/2026
        acts.append({"title": f"Suspender contrato {r[1]}", "endpoint": f"/api/v1/crm/contracts/{r[0]}/suspend",
                     "method": "POST", "btnLabel": "Suspender", "submitLabel": "Suspender", "btnStyle": "outline",
                     "okMsg": "Contrato suspenso. Recarregue.", "fields": []})
        acts.append({"title": f"Renovar contrato {r[1]}",
                     "sub": "Informe a nova data de fim e, se houver, o percentual de reajuste (o índice não é consultado automaticamente).",
                     "endpoint": f"/api/v1/crm/contracts/{r[0]}/renew", "method": "POST", "btnLabel": "Renovar",
                     "submitLabel": "Calcular renovação", "btnStyle": "outline", "okMsg": "Renovação calculada — veja a mensagem.",
                     "fields": [{"key": "new_end_date", "label": "Nova data de fim*", "type": "date", "span": "span 1", "value": ""},
                                {"key": "adjustment_percent", "label": "Reajuste (%)", "type": "number", "span": "span 1", "value": ""},
                                {"key": "new_monthly_value", "label": "Novo valor mensal (R$)", "type": "number", "span": "span 1", "value": ""}]})
    if st in ("active", "suspended"):
        acts.append({"title": f"ENCERRAR contrato {r[1]}", "sub": "Encerra a vigência. Sai do MRR.",
                     "endpoint": f"/api/v1/crm/contracts/{r[0]}/terminate", "method": "POST", "btnLabel": "Encerrar",
                     "submitLabel": "Encerrar contrato", "btnStyle": "outline", "okMsg": "Contrato encerrado. Recarregue.", "fields": []})
    if st in ("draft", "pending_signature", "active"):
        acts.append({"title": f"Cancelar contrato {r[1]}",
                     "endpoint": f"/api/v1/redesign/action/contract-cancel?cid={r[0]}",
                     "method": "POST", "btnLabel": "Cancelar", "submitLabel": "Cancelar contrato",
                     "btnStyle": "outline", "okMsg": "Contrato cancelado. Recarregue.",
                     "fields": [{"key": "reason", "label": "Motivo do cancelamento (obrigatório)",
                                 "type": "textarea", "span": "span 2", "value": ""}]})
    return acts or None


def _cliente_actions(r):
    """Status do cliente por linha (LIGAR 08/09/2026). r[6]=id, r[5]=status, r[7]=inadimplente."""
    cid, st = r[6], (r[5] or "").lower()
    def _a(titulo, rota, label, style="outline", sub=None):
        return {"title": f"{titulo} — {r[0]}", "sub": sub, "endpoint": f"/api/v1/clients/{cid}/{rota}", "method": "POST",
                "btnLabel": label, "submitLabel": label, "btnStyle": style, "okMsg": f"{label}: feito. Recarregue.", "fields": []}
    acts = []
    if st != "active":
        acts.append(_a("Ativar cliente", "activate", "Ativar", "primary"))
    if st == "active":
        acts.append(_a("Suspender cliente", "suspend", "Suspender"))
    if st not in ("blocked",):
        acts.append(_a("Bloquear cliente", "block", "Bloquear", sub="Bloqueio comercial (inadimplência grave, litígio)."))
    if r[7]:
        acts.append(_a("Limpar inadimplência", "clear-defaulter", "Regularizar", "primary"))
    return acts


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
        "SELECT name, coalesce(company,'—'), coalesce(source,'—'), coalesce(expected_value,0), coalesce(status::text,'—'), id::text "
        "FROM leads ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]),
                   b((r[2] or '—').replace('_', ' ').capitalize(), "mut"), t(brl(r[3]), 600),
                   b((r[4] or '—').replace('_', ' ').capitalize(), _LEAD_TONE.get((r[4] or '').lower(), "info"))],
        actionsfn=lambda r: [{"title": f"Mudar status — {r[0]}", "sub": "Registra a nota e recalcula o score do lead.",
                              "endpoint": f"/api/v1/crm/leads/{r[5]}/status", "method": "PATCH", "btnLabel": "Status",
                              "submitLabel": "Salvar", "btnStyle": "outline", "okMsg": "Status do lead atualizado. Recarregue.",
                              "fields": [{"key": "status", "label": "Novo status*", "type": "select", "span": "span 1", "value": (r[4] or "new").lower(),
                                          "options": [{"value": v, "label": l} for v, l in (("new", "Novo"), ("contacted", "Contatado"), ("qualified", "Qualificado"), ("proposal", "Proposta enviada"), ("negotiation", "Em negociação"), ("won", "Ganho"), ("lost", "Perdido"))]},
                                         {"key": "notes", "label": "Observação", "type": "textarea", "span": "span 2", "value": ""}]},
                             {"title": f"Arquivar lead {r[0]}", "sub": "Some da lista; não apaga o histórico.",
                              "endpoint": f"/api/v1/crm/leads/{r[5]}", "method": "DELETE", "btnLabel": "Arquivar",
                              "submitLabel": "Arquivar", "btnStyle": "outline", "confirm": f"Arquivar o lead {r[0]}?",
                              "okMsg": "Lead arquivado. Recarregue.", "fields": []}]))

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
        "coalesce(nullif(c.phone,''), c.whatsapp, '—'), c.is_primary, c.id::text, coalesce(c.role,''), coalesce(c.email,''), "
        "coalesce(c.phone,''), coalesce(c.whatsapp,''), coalesce(c.notes,'') "
        "FROM crm_contacts c LEFT JOIN clients cl ON cl.id=c.client_id "
        "ORDER BY c.is_primary DESC NULLS LAST, c.name LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t((r[2] or '—').capitalize()),
                   t(r[3]), t(r[4]), b("Principal", "ok") if r[5] else b("—", "mut")],
        actionsfn=lambda r: [  # LIGAR 08/09/2026
            {"title": f"Editar contato {r[0]}", "endpoint": f"/api/v1/crm/contacts/{r[6]}", "method": "PATCH",
             "btnLabel": "Editar", "submitLabel": "Salvar", "btnStyle": "outline", "okMsg": "Contato atualizado. Recarregue.",
             "fields": [{"key": "name", "label": "Nome*", "type": "text", "span": "span 2", "value": r[0]},
                        {"key": "role", "label": "Cargo", "type": "text", "span": "span 1", "value": r[7]},
                        {"key": "email", "label": "E-mail", "type": "text", "span": "span 1", "value": r[8]},
                        {"key": "phone", "label": "Telefone", "type": "text", "span": "span 1", "value": r[9]},
                        {"key": "whatsapp", "label": "WhatsApp", "type": "text", "span": "span 1", "value": r[10]},
                        {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "value": r[11]}]},
            {"title": f"Remover contato {r[0]}", "endpoint": f"/api/v1/crm/contacts/{r[6]}", "method": "DELETE",
             "btnLabel": "Remover", "submitLabel": "Remover", "btnStyle": "outline", "confirm": f"Remover {r[0]}?",
             "okMsg": "Contato removido. Recarregue.", "fields": []}]))

    # ---- Clientes (clients) ----
    _cl_tot = await _scalar(db, "SELECT count(*) FROM clients WHERE ativo=true")
    _cl_ativos = await _scalar(db, "SELECT count(*) FROM clients WHERE status::text='active'")
    _cl_cond = await _scalar(db, "SELECT count(*) FROM clients WHERE ativo=true AND client_type::text='condominium'")
    _cl_bloq = await _scalar(db, "SELECT count(*) FROM clients WHERE ativo=true AND coalesce(is_defaulter,false)=true")
    await safe("clientes", tbl(
        "Clientes",
        f"{_cl_tot} clientes · Ativos {_cl_ativos} · Condomínios {_cl_cond} · Bloqueados {_cl_bloq}",
        "—", ["Cliente", "CNPJ", "Email", "Segmento", "MRR", "Status"], "1.8fr 1.3fr 1.8fr 1.1fr 1fr 0.8fr",
        "SELECT name, coalesce(document_number,'—'), coalesce(email,'—'), coalesce(segment::text,'—'), coalesce(mrr,0), status::text, "
        "id::text, coalesce(is_defaulter,false), coalesce(phone,''), coalesce(mobile,''), coalesce(whatsapp,''), coalesce(website,''), coalesce(financial_contact_name,''), "
        "coalesce(address_street,''), coalesce(address_number,''), coalesce(address_city,''), coalesce(address_zipcode,'') "
        "FROM clients ORDER BY mrr DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(_cnpj(r[1])), t(r[2]), t((r[3] or '—').capitalize()),
                   t(brl(r[4]), 600), b("Ativo", "ok") if r[5] == "active" else b((r[5] or '—').capitalize(), "mut")],
        actionsfn=_cliente_actions,
        # PUT /clients/{id} — editar o cadastro (ClientUpdate: todos opcionais; vazio não altera)
        editfn=lambda r: {"title": f"Editar cadastro — {r[0]}", "endpoint": f"/api/v1/clients/{r[6]}", "method": "PUT",
                          "fields": [{"key": "name", "label": "Razão social", "type": "text", "value": r[0]}, {"key": "email", "label": "E-mail", "type": "text", "value": "" if r[2] == "—" else r[2]},
                                     {"key": "phone", "label": "Telefone", "type": "text", "value": r[8]}, {"key": "mobile", "label": "Celular", "type": "text", "value": r[9]},
                                     {"key": "whatsapp", "label": "WhatsApp", "type": "text", "value": r[10]}, {"key": "website", "label": "Site", "type": "text", "value": r[11]},
                                     {"key": "financial_contact_name", "label": "Contato financeiro", "type": "text", "value": r[12]},
                                     {"key": "address_street", "label": "Logradouro", "type": "text", "value": r[13]}, {"key": "address_number", "label": "Número", "type": "text", "value": r[14]},
                                     {"key": "address_city", "label": "Cidade", "type": "text", "value": r[15]}, {"key": "address_zipcode", "label": "CEP", "type": "text", "value": r[16]}]}))

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
            # A coluna era "Mensal" e mostrava só `monthly_value`. `total_value` já vinha na
            # consulta e era JOGADO FORA — então todo contrato de serviço único (fornecimento
            # + instalação) aparecia como "R$ 0,00" numa lista que o dono usa para conferir
            # quanto vale a carteira. Agora cada linha mostra o valor da SUA natureza e diz
            # qual é: "/mês" para o recorrente, "único" para o de valor fechado.
            ["Contrato", "Cliente", "Serviço", "Valor", "Status", "Assinatura"],
            "1.1fr 1.5fr 1fr 1fr 0.8fr 1.1fr",
            "SELECT ct.id, coalesce(ct.contract_number,'—'), coalesce(cl.name, ct.name, '—'), "
            "coalesce(ct.monthly_value,0), coalesce(ct.total_value,0), ct.status::text, "
            "ct.template_id::text, "
            "(SELECT count(*) FROM sig_signature_requests s WHERE s.reference_code = ct.contract_number), "
            "(SELECT count(*) FROM sig_signature_requests s WHERE s.reference_code = ct.contract_number AND s.signed_at IS NOT NULL), "
            "coalesce(ct.tipo_servico::text,'—'), coalesce(ct.contract_type::text,'recurring') "
            "FROM contracts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.start_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t((r[2] or '—')[:32]), t((r[9] or '—').replace('_', ' ')),
                       t(f"{brl(r[4])} único" if (r[10] or "") == "one_time" else f"{brl(r[3])}/mês"),
                       b("Ativo", "ok") if (r[5] or "").lower() in ("active", "ativo", "vigente") else b(r[5] or "—", "mut"),
                       (b("Não aberta", "mut") if not r[7]
                        else b(f"{r[8]}/{r[7]} assinada(s)", "ok" if r[8] and r[8] == r[7] else "warn"))],
            docsfn=lambda r: ([doc("Contrato completo (PDF)",
                                   f"/api/v1/crm/contracts/{r[1]}/pdf-modelo", fmt="pdf")] if r[6]
                              else [doc("Resumo (sem modelo vinculado)",
                                        f"/api/v1/crm/contracts/{r[0]}/pdf", fmt="pdf")]),
            actionsfn=_contrato_actions))
        # ── CENTRAL DE CONTRATOS: a fila do que foi FECHADO e ainda não virou instrumento
        # assinado. Pedido do Jordan em 09/09/2026, nas palavras dele: "não posso ficar o
        # tempo no terminal, tenho que fazer pelo sistema".
        #
        # O que existia eram telas soltas — gerar-da-proposta, abrir-assinatura,
        # enviar-link — cada uma com um seletor. Funcionavam, mas exigiam que ele
        # SOUBESSE em que etapa cada negócio parou. Aqui o sistema é que sabe: cada linha
        # diz onde travou e oferece só a ação que destrava, na própria linha.
        #
        # Quatro estados, na ordem em que o dinheiro anda:
        #   oportunidade ganha  → falta a proposta (não há o que gerar ainda)
        #   proposta aceita     → gerar o contrato
        #   contrato rascunho   → emitir o instrumento pelo modelo
        #   instrumento pronto  → abrir assinatura / mandar o link
        await safe("contratos-a-emitir", tbl(
            "Central de contratos",
            "O que já foi fechado e ainda não está assinado — e o passo que falta em cada um",
            "", ["Origem", "Cliente", "Valor", "Situação", "Próximo passo"],
            "0.9fr 1.6fr 1fr 1.1fr 1.6fr",
            """
            SELECT 'Oportunidade' AS origem, o.id::text AS ref,
                   coalesce(o.company_name, o.title, '—') AS cliente,
                   coalesce(o.value,0) AS valor, 'Ganha, sem proposta' AS situacao,
                   'Monte a proposta comercial — o contrato nasce dela' AS passo,
                   'oportunidade' AS tipo, '' AS extra
              FROM opportunities o
             WHERE o.stage::text = 'closed_won'
               AND NOT EXISTS (SELECT 1 FROM contracts c WHERE c.opportunity_id = o.id)
               AND NOT EXISTS (SELECT 1 FROM proposals p WHERE p.opportunity_id = o.id
                                 AND p.status::text IN ('accepted','aceita','approved'))
            UNION ALL
            SELECT 'Proposta', p.id::text, coalesce(p.client_name,'—'),
                   coalesce(p.total,0), 'Aceita pelo cliente',
                   'Gerar o contrato a partir da proposta', 'proposta',
                   coalesce(p.client_email,'')
              FROM proposals p
             WHERE p.status::text IN ('accepted','aceita','approved')
               AND NOT EXISTS (SELECT 1 FROM contracts c WHERE c.proposal_id = p.id)
            UNION ALL
            SELECT 'Contrato', c.contract_number, coalesce(cl.name,c.name,'—'),
                   CASE WHEN c.contract_type::text='one_time' THEN coalesce(c.total_value,0)
                        ELSE coalesce(c.monthly_value,0) END,
                   CASE WHEN c.template_id IS NULL THEN 'Rascunho, sem modelo'
                        WHEN sr.abertas = 0 AND sr.total > 0 THEN 'Assinatura cancelada'
                        WHEN sr.abertas = 0 THEN 'Instrumento pronto'
                        WHEN sr.assinadas < sr.abertas THEN 'Em assinatura'
                        ELSE 'Assinado, fora de vigência' END,
                   CASE WHEN c.template_id IS NULL THEN 'Escolha o modelo e emita o instrumento'
                        WHEN sr.abertas = 0 AND sr.total > 0
                          THEN 'A assinatura foi cancelada — reabra para colher de novo'
                        WHEN sr.abertas = 0 THEN 'Abrir a assinatura eletrônica'
                        WHEN sr.assinadas < sr.abertas
                          THEN 'Faltam ' || (sr.abertas - sr.assinadas) || ' assinatura(s) — mande o link'
                        ELSE 'Ativar o contrato — sem isso ele não entra no faturamento' END,
                   'contrato', c.contract_type::text
              FROM contracts c
              LEFT JOIN clients cl ON cl.id = c.client_id
              LEFT JOIN LATERAL (
                    -- CANCELADA/EXPIRADA não é pendência: é assinatura que precisa ser
                    -- REABERTA. Medido em 09/09/2026 — o CTR-2026-00019 tinha as duas
                    -- solicitações CANCELLED desde 23/08 e a fila dizia "faltam 2
                    -- assinaturas, mande o link". O link de uma solicitação cancelada
                    -- ainda serve o PDF pela rota pública: mandá-lo é convidar o cliente
                    -- a assinar o que a casa cancelou.
                    SELECT count(*) FILTER (
                             WHERE upper(coalesce(s.status::text,'')) NOT IN
                                   ('CANCELLED','CANCELED','CANCELADA','EXPIRED','EXPIRADA')
                           ) AS abertas,
                           count(*) FILTER (WHERE s.signed_at IS NOT NULL) AS assinadas,
                           count(*) AS total
                      FROM sig_signature_requests s
                     WHERE s.reference_code = c.contract_number) sr ON true
             WHERE c.status::text = 'draft' OR (sr.abertas > 0 AND sr.assinadas < sr.abertas)
                OR (sr.total > 0 AND sr.abertas = 0)
             ORDER BY 1, 3
            """,
            lambda r: [
                b(r[0], "info" if r[6] == "contrato" else "mut"),
                t((r[2] or "—")[:34]),
                t(brl(r[3]) + (" único" if r[7] == "one_time" else "")),
                b(r[4], "ok" if r[4] == "Assinado"
                        else ("warn" if r[4] in ("Em assinatura", "Instrumento pronto") else "mut")),
                t(r[5]),
            ],
            actionsfn=_fila_actions))

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

    await _ligar_20260908(db, out, tbl)
    await _ligar_lote4_20260908(db, out)
    return out


async def _ligar_20260908(db, out: dict, tbl) -> None:
    """Rotas que existiam sem tela (revisão 100%, 08/09/2026): contatos, produtos, timeline, tarefas,
    itens/aditivos/modelos de contrato, itens de proposta, condomínios, inadimplência, reajuste."""
    async def _opts(sql):
        try:
            return [{"value": str(a), "label": str(b_)} for a, b_ in (await db.execute(text(sql))).fetchall()]
        except Exception:  # noqa: BLE001
            await db.rollback(); return []
    cli = await _opts("SELECT id, name FROM clients WHERE coalesce(ativo,true) ORDER BY name LIMIT 300")
    ctr = await _opts("SELECT ct.id, coalesce(ct.contract_number,'—') || ' · ' || coalesce(cl.name, ct.name, '—') FROM contracts ct "
                      "LEFT JOIN clients cl ON cl.id=ct.client_id WHERE ct.status::text IN ('draft','pending_signature','active','suspended') "
                      "ORDER BY ct.contract_number DESC LIMIT 300")
    prop = await _opts("SELECT id, coalesce(number,'—') || ' · ' || coalesce(client_name,'—') FROM proposals "
                       "WHERE coalesce(is_active,true) AND status::text IN ('draft','approved') ORDER BY created_at DESC LIMIT 200")
    _sel = lambda key, label, opts, span="span 2": {"key": key, "label": label, "type": "select", "span": span, "ph": "Selecione", "options": opts}  # noqa: E731
    _ST = [{"value": v, "label": l} for v, l in (("security", "Segurança/portaria"), ("cleaning", "Limpeza"), ("electronic_security", "Segurança eletrônica"),
                                                ("remote_gatehouse", "Portaria remota"), ("facilities", "Facilities"), ("gardening", "Jardinagem"), ("maintenance", "Manutenção"))]

    out["contato-novo"] = {
        "title": "Novo contato", "sub": "Pessoa de contato num cliente (síndico, zelador, financeiro).", "cta": "Salvar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/contacts/", "okMsg": "Contato criado"},
        "fields": [_sel("client_id", "Cliente*", cli), {"key": "name", "label": "Nome*", "type": "text", "span": "span 2"},
                   {"key": "role", "label": "Cargo", "type": "text", "span": "span 1"}, {"key": "email", "label": "E-mail", "type": "text", "span": "span 1"},
                   {"key": "phone", "label": "Telefone", "type": "text", "span": "span 1"}, {"key": "whatsapp", "label": "WhatsApp", "type": "text", "span": "span 1"},
                   {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2"}]}
    try:
        out["produtos"] = await tbl(
            "Produtos (catálogo)", f"{await _scalar(db, 'SELECT count(*) FROM crm_products WHERE coalesce(is_active,true)')} produtos e serviços — base dos itens de proposta", "Novo produto",
            ["Produto", "SKU", "Categoria", "Unidade", "Preço", "Recorrente"], "2fr 1fr 1fr 0.7fr 1fr 0.8fr",
            "SELECT name, coalesce(sku,'—'), coalesce(category,'—'), coalesce(unit,'un'), coalesce(unit_price,0), coalesce(is_recurring,false), id::text, "
            "coalesce(description,''), coalesce(service_type,'') FROM crm_products WHERE coalesce(is_active,true) ORDER BY category, name LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(r[3]), t(brl(r[4]), 600), b("Mensal", "ok") if r[5] else b("Único", "mut")],
            actionsfn=lambda r: [
                {"title": f"Editar {r[0]}", "endpoint": f"/api/v1/crm/products/{r[6]}", "method": "PUT", "btnLabel": "Editar", "submitLabel": "Salvar",
                 "btnStyle": "outline", "okMsg": "Produto atualizado. Recarregue.",
                 "fields": [{"key": "name", "label": "Nome*", "type": "text", "span": "span 2", "value": r[0]},
                            {"key": "sku", "label": "SKU", "type": "text", "span": "span 1", "value": "" if r[1] == "—" else r[1]},
                            {"key": "category", "label": "Categoria", "type": "text", "span": "span 1", "value": "" if r[2] == "—" else r[2]},
                            {"key": "unit", "label": "Unidade", "type": "text", "span": "span 1", "value": r[3]},
                            {"key": "unit_price", "label": "Preço (R$)", "type": "number", "span": "span 1", "value": str(r[4])},
                            {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "value": r[7]}]},
                {"title": f"Desativar {r[0]}", "endpoint": f"/api/v1/crm/products/{r[6]}", "method": "DELETE", "btnLabel": "Desativar",
                 "submitLabel": "Desativar", "btnStyle": "outline", "confirm": f"Desativar {r[0]}?", "okMsg": "Produto desativado. Recarregue.", "fields": []}])
        out["produtos"]["ctaTo"] = "produto-novo"
    except Exception:  # noqa: BLE001
        await db.rollback()
    out["produto-novo"] = {
        "title": "Novo produto", "sub": "Entra no catálogo e pode ser usado como item de proposta.", "cta": "Salvar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/products", "okMsg": "Produto criado"},
        "fields": [{"key": "name", "label": "Nome*", "type": "text", "span": "span 2"}, {"key": "sku", "label": "SKU", "type": "text", "span": "span 1"},
                   {"key": "category", "label": "Categoria", "type": "text", "span": "span 1"}, {"key": "unit", "label": "Unidade", "type": "text", "span": "span 1", "ph": "un"},
                   {"key": "unit_price", "label": "Preço (R$)*", "type": "number", "span": "span 1"},
                   {"key": "is_recurring", "label": "Recorrente (mensal)?", "type": "select", "span": "span 1", "ph": "Não",
                    "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]},
                   {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2"}]}
    out["timeline-nota"] = {
        "title": "Anotar na timeline", "sub": "Registra uma nota/ligação/reunião no histórico do cliente ou do lead.", "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/activities/timeline", "okMsg": "Registrado na timeline"},
        "fields": [{"key": "subject", "label": "Assunto*", "type": "text", "span": "span 2"},
                   {"key": "type", "label": "Tipo", "type": "select", "span": "span 1", "ph": "Nota",
                    "options": [{"value": v, "label": l} for v, l in (("note", "Nota"), ("call", "Ligação"), ("meeting", "Reunião"), ("email", "E-mail"), ("whatsapp", "WhatsApp"), ("visit", "Visita"))]},
                   _sel("client_id", "Cliente", cli, "span 1"), {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2"}]}
    try:
        out["tarefas"] = await tbl(
            "Tarefas", f"{await _scalar(db, 'SELECT count(*) FROM crm_tasks')} tarefas comerciais", "Nova tarefa",
            ["Tarefa", "Cliente", "Prioridade", "Vencimento", "Status"], "2fr 1.4fr 0.9fr 1fr 0.9fr",
            "SELECT coalesce(tk.title,'—'), coalesce(cl.name,'—'), coalesce(tk.priority::text,'—'), tk.due_date, coalesce(tk.status::text,'—'), tk.id::text "
            "FROM crm_tasks tk LEFT JOIN clients cl ON cl.id=tk.client_id ORDER BY (tk.status::text='done'), tk.due_date NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), b((r[2] or '—').capitalize(), "info"), t(_fmtdate(r[3])),
                       b("Concluída", "ok") if r[4] == "done" else b((r[4] or '—').capitalize(), "warn")],
            actionsfn=lambda r: ([{"title": f"Concluir tarefa — {r[0]}", "endpoint": f"/api/v1/crm/tasks/{r[5]}", "method": "PATCH",
                                   "btnLabel": "Concluir", "submitLabel": "Marcar concluída", "btnStyle": "primary", "okMsg": "Tarefa concluída. Recarregue.",
                                   "fields": [{"key": "status", "label": "Status", "type": "text", "span": "span 1", "value": "done"}]}] if r[4] != "done" else [])
                                + [{"title": f"Excluir tarefa — {r[0]}", "endpoint": f"/api/v1/crm/tasks/{r[5]}", "method": "DELETE", "btnLabel": "Excluir",
                                    "submitLabel": "Excluir", "btnStyle": "outline", "confirm": "Excluir a tarefa?", "okMsg": "Tarefa excluída. Recarregue.", "fields": []}])
        out["tarefas"]["ctaTo"] = "nova-tarefa"
    except Exception:  # noqa: BLE001
        await db.rollback()
    try:
        out["contrato-itens"] = await tbl(
            "Itens de contrato", f"{await _scalar(db, 'SELECT count(*) FROM contract_items WHERE coalesce(is_active,true)')} itens (postos/serviços por contrato)", "Novo item",
            ["Contrato", "Serviço", "Tipo", "Qtd", "Unitário", "Total"], "1.4fr 2fr 1fr 0.6fr 1fr 1fr",
            "SELECT coalesce(ct.contract_number,'—'), coalesce(i.service_name,'—'), coalesce(i.service_type::text,'—'), coalesce(i.quantity,0), "
            "coalesce(i.unit_price,0), coalesce(i.total_price, i.quantity*i.unit_price, 0), i.id::text, ct.id::text, coalesce(i.description,'') "
            "FROM contract_items i JOIN contracts ct ON ct.id=i.contract_id WHERE coalesce(i.is_active,true) ORDER BY ct.contract_number DESC, i.service_name LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t((r[2] or '—').replace('_', ' ').capitalize()), t(str(r[3])), t(brl(r[4])), t(brl(r[5]), 600)],
            actionsfn=lambda r: [
                {"title": f"Editar item — {r[1]}", "endpoint": f"/api/v1/crm/contracts/{r[7]}/items/{r[6]}", "method": "PUT", "btnLabel": "Editar",
                 "submitLabel": "Salvar", "btnStyle": "outline", "okMsg": "Item atualizado. Recarregue.",
                 "fields": [{"key": "service_name", "label": "Serviço*", "type": "text", "span": "span 2", "value": r[1]},
                            {"key": "quantity", "label": "Quantidade", "type": "number", "span": "span 1", "value": str(r[3])},
                            {"key": "unit_price", "label": "Unitário (R$)", "type": "number", "span": "span 1", "value": str(r[4])},
                            {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "value": r[8]}]},
                {"title": f"Remover item — {r[1]}", "endpoint": f"/api/v1/crm/contracts/{r[7]}/items/{r[6]}", "method": "DELETE", "btnLabel": "Remover",
                 "submitLabel": "Remover", "btnStyle": "outline", "confirm": "Remover o item do contrato?", "okMsg": "Item removido. Recarregue.", "fields": []}])
        out["contrato-itens"]["ctaTo"] = "contrato-item-novo"
    except Exception:  # noqa: BLE001
        await db.rollback()
    out["contrato-item-novo"] = {
        "title": "Novo item de contrato", "sub": "Posto ou serviço que compõe o valor do contrato.", "cta": "Adicionar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/contrato-item-novo", "okMsg": "Item adicionado"},
        "fields": [_sel("contract_id", "Contrato*", ctr), {"key": "service_name", "label": "Serviço*", "type": "text", "span": "span 2"},
                   {"key": "service_type", "label": "Tipo*", "type": "select", "span": "span 1", "ph": "Selecione", "options": _ST},
                   {"key": "quantity", "label": "Quantidade*", "type": "number", "span": "span 1", "ph": "1"},
                   {"key": "unit_price", "label": "Unitário (R$)*", "type": "number", "span": "span 1"},
                   {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2"}]}
    try:
        out["aditivos"] = await tbl(
            "Aditivos", f"{await _scalar(db, 'SELECT count(*) FROM contract_addendums WHERE coalesce(is_active,true)')} aditivos contratuais", "Novo aditivo",
            ["Contrato", "Nº", "Tipo", "Vigência", "Novo valor", "Assinado"], "1.4fr 0.7fr 1.2fr 1fr 1fr 0.8fr",
            "SELECT coalesce(ct.contract_number,'—'), coalesce(a.addendum_number::text,'—'), coalesce(a.addendum_type::text,'—'), a.effective_date, "
            "a.new_value, coalesce(a.signed,false), a.id::text, coalesce(a.description,'') "
            "FROM contract_addendums a JOIN contracts ct ON ct.id=a.contract_id WHERE coalesce(a.is_active,true) ORDER BY a.effective_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t((r[2] or '—').replace('_', ' ').capitalize()), t(_fmtdate(r[3])),
                       t(brl(r[4]) if r[4] is not None else '—'), b("Sim", "ok") if r[5] else b("Pendente", "warn")],
            actionsfn=lambda r: [] if r[5] else [{"title": f"Registrar assinatura do aditivo {r[1]} — {r[0]}",
                                                  "sub": "Informe o id do documento assinado (assinatura universal).",
                                                  "endpoint": f"/api/v1/crm/contracts/addendums/{r[6]}/sign", "method": "POST", "btnLabel": "Assinado",
                                                  "submitLabel": "Registrar assinatura", "btnStyle": "outline", "okMsg": "Aditivo assinado. Recarregue.",
                                                  "fields": [{"key": "signature_document_id", "label": "Documento assinado (id)*", "type": "text", "span": "span 2", "value": ""}]}])
        out["aditivos"]["ctaTo"] = "aditivo-novo"
    except Exception:  # noqa: BLE001
        await db.rollback()
    out["aditivo-novo"] = {
        "title": "Novo aditivo", "sub": "Reajuste, mudança de escopo/equipe/prazo. Só registra — o PDF sai em «Documentos».", "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/aditivo-novo", "okMsg": "Aditivo registrado"},
        "fields": [_sel("contract_id", "Contrato*", ctr),
                   {"key": "addendum_type", "label": "Tipo*", "type": "select", "span": "span 1", "ph": "Selecione",
                    "options": [{"value": v, "label": l} for v, l in (("adjustment", "Reajuste"), ("scope_change", "Escopo"), ("team_change", "Equipe"), ("term_change", "Prazo"), ("equipment_change", "Equipamentos"), ("other", "Outro"))]},
                   {"key": "effective_date", "label": "Vigência a partir de*", "type": "date", "span": "span 1"},
                   {"key": "description", "label": "Descrição* (mín. 10 caracteres)", "type": "textarea", "span": "span 2"},
                   {"key": "reason", "label": "Motivo", "type": "text", "span": "span 2"},
                   {"key": "new_value", "label": "Novo valor mensal (R$)", "type": "number", "span": "span 1"},
                   {"key": "adjustment_percent", "label": "Reajuste (%)", "type": "number", "span": "span 1"}]}
    try:
        out["modelos-contrato"] = await tbl(
            "Modelos de contrato", f"{await _scalar(db, 'SELECT count(*) FROM contract_templates')} modelos — base do «Contrato completo» (pdf-modelo)", "Novo modelo",
            ["Modelo", "Serviço", "Aprovado", "Cláusulas"], "2fr 1.2fr 0.8fr 0.8fr",
            "SELECT name, coalesce(service_type::text,'—'), coalesce(approved_by_legal,false), "
            "CASE WHEN jsonb_typeof(clauses)='array' THEN jsonb_array_length(clauses) ELSE 0 END, id::text, coalesce(description,'') "
            "FROM contract_templates WHERE coalesce(is_active,true) ORDER BY name LIMIT 100",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ').capitalize()), b("Sim", "ok") if r[2] else b("Não", "warn"), t(str(r[3]))],
            actionsfn=lambda r: ([] if r[2] else [{"title": f"Aprovar modelo {r[0]}", "endpoint": f"/api/v1/crm/contracts/templates/{r[4]}/approve", "method": "POST",
                                                   "btnLabel": "Aprovar", "submitLabel": "Aprovar", "btnStyle": "primary", "okMsg": "Modelo aprovado. Recarregue.", "fields": []}])
                                + [{"title": f"Editar modelo {r[0]}", "endpoint": f"/api/v1/crm/contracts/templates/{r[4]}", "method": "PUT", "btnLabel": "Editar",
                                    "submitLabel": "Salvar", "btnStyle": "outline", "okMsg": "Modelo atualizado. Recarregue.",
                                    "fields": [{"key": "name", "label": "Nome*", "type": "text", "span": "span 2", "value": r[0]},
                                               {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "value": r[5]}]},
                                   {"title": f"Excluir modelo {r[0]}", "endpoint": f"/api/v1/crm/contracts/templates/{r[4]}", "method": "DELETE", "btnLabel": "Excluir",
                                    "submitLabel": "Excluir", "btnStyle": "outline", "confirm": f"Excluir o modelo {r[0]}?", "okMsg": "Modelo excluído. Recarregue.", "fields": []}])
        out["modelos-contrato"]["ctaTo"] = "modelo-contrato-novo"
    except Exception:  # noqa: BLE001
        await db.rollback()
    out["modelo-contrato-novo"] = {
        "title": "Novo modelo de contrato", "sub": "Texto-base com variáveis {{cliente}}, {{valor}}… Precisa ser aprovado antes de usar.", "cta": "Salvar", "type": "form",
        "submit": {"endpoint": "/api/v1/crm/contracts/templates", "okMsg": "Modelo criado (pendente de aprovação)"},
        "fields": [{"key": "name", "label": "Nome*", "type": "text", "span": "span 2"},
                   {"key": "service_type", "label": "Serviço", "type": "select", "span": "span 1", "ph": "Selecione", "options": _ST},
                   {"key": "description", "label": "Descrição", "type": "text", "span": "span 1"},
                   {"key": "content_template", "label": "Texto do contrato* (mín. 100 caracteres)", "type": "textarea", "span": "span 2"}]}
    try:
        out["proposta-itens"] = await tbl(
            "Itens de proposta", f"{await _scalar(db, 'SELECT count(*) FROM proposal_items WHERE coalesce(is_active,true)')} itens — o que compõe cada proposta", "Novo item",
            ["Proposta", "Item", "Qtd", "Unitário", "Desc. %", "Total", "Opcional"], "1.4fr 2fr 0.5fr 1fr 0.6fr 1fr 0.7fr",
            "SELECT coalesce(p.number,'—'), coalesce(i.name,'—'), coalesce(i.quantity,0), coalesce(i.unit_price,0), coalesce(i.discount_percent,0), "
            "coalesce(i.total,0), coalesce(i.is_optional,false), i.id::text, p.id::text, p.status::text "
            "FROM proposal_items i JOIN proposals p ON p.id=i.proposal_id WHERE coalesce(i.is_active,true) AND coalesce(p.is_active,true) "
            "ORDER BY p.created_at DESC, i.sort_order LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(str(r[2])), t(brl(r[3])), t(str(r[4])), t(brl(r[5]), 600), b("Sim", "info") if r[6] else b("—", "mut")],
            actionsfn=lambda r: [{"title": f"Remover item — {r[1]} ({r[0]})", "endpoint": f"/api/v1/crm/proposals/{r[8]}/items/{r[7]}", "method": "DELETE",
                                  "btnLabel": "Remover", "submitLabel": "Remover", "btnStyle": "outline", "confirm": "Remover o item da proposta?",
                                  "okMsg": "Item removido. Recarregue.", "fields": []}] if (r[9] or "") in ("draft", "approved") else [])
        out["proposta-itens"]["ctaTo"] = "proposta-item-novo"
    except Exception:  # noqa: BLE001
        await db.rollback()
    out["proposta-item-novo"] = {
        "title": "Novo item de proposta", "sub": "Só em proposta em rascunho/aprovada (ainda não enviada).", "cta": "Adicionar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/proposta-item-novo", "okMsg": "Item adicionado"},
        "fields": [_sel("proposal_id", "Proposta*", prop), {"key": "name", "label": "Item*", "type": "text", "span": "span 2"},
                   {"key": "unit", "label": "Unidade*", "type": "text", "span": "span 1", "ph": "posto / un / mês"},
                   {"key": "quantity", "label": "Quantidade*", "type": "number", "span": "span 1"},
                   {"key": "unit_price", "label": "Unitário (R$)*", "type": "number", "span": "span 1"},
                   {"key": "discount_percent", "label": "Desconto (%)", "type": "number", "span": "span 1", "ph": "0"},
                   {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2"}]}
    try:
        out["condominios"] = await tbl(
            "Condomínios", f"{await _scalar(db, 'SELECT count(*) FROM condominiums WHERE coalesce(ativo,true)')} condomínios atendidos (dado do cliente)", "Novo condomínio",
            ["Condomínio", "Cliente", "CNPJ", "Bairro", "Unidades", "Status"], "2fr 1.6fr 1.2fr 1fr 0.7fr 0.8fr",
            "SELECT c.name, coalesce(cl.name,'—'), coalesce(c.cnpj,'—'), coalesce(c.address_neighborhood,'—'), coalesce(c.total_units,0), coalesce(c.status::text,'—'), "
            "c.id::text, coalesce(c.syndic_name,''), coalesce(c.syndic_phone,''), coalesce(c.address_street,''), coalesce(c.address_number,'') "
            "FROM condominiums c LEFT JOIN clients cl ON cl.id=c.client_id WHERE coalesce(c.ativo,true) ORDER BY c.name LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(_cnpj(r[2]) if r[2] != '—' else '—'), t(r[3]), t(str(r[4])), b((r[5] or '—').capitalize(), "info")],
            actionsfn=lambda r: [
                {"title": f"Editar condomínio {r[0]}", "endpoint": f"/api/v1/clients/condominiums/{r[6]}", "method": "PUT", "btnLabel": "Editar",
                 "submitLabel": "Salvar", "btnStyle": "outline", "okMsg": "Condomínio atualizado. Recarregue.",
                 "fields": [{"key": "name", "label": "Nome*", "type": "text", "span": "span 2", "value": r[0]},
                            {"key": "syndic_name", "label": "Síndico", "type": "text", "span": "span 1", "value": r[7]},
                            {"key": "syndic_phone", "label": "Telefone do síndico", "type": "text", "span": "span 1", "value": r[8]},
                            {"key": "address_street", "label": "Logradouro", "type": "text", "span": "span 1", "value": r[9]},
                            {"key": "address_number", "label": "Número", "type": "text", "span": "span 1", "value": r[10]},
                            {"key": "total_units", "label": "Unidades", "type": "number", "span": "span 1", "value": str(r[4])}]},
                {"title": f"Remover condomínio {r[0]}", "endpoint": f"/api/v1/clients/condominiums/{r[6]}", "method": "DELETE", "btnLabel": "Remover",
                 "submitLabel": "Remover", "btnStyle": "outline", "confirm": f"Remover {r[0]}?", "okMsg": "Condomínio removido. Recarregue.", "fields": []}])
        out["condominios"]["ctaTo"] = "condominio-novo"
    except Exception:  # noqa: BLE001
        await db.rollback()
    out["condominio-novo"] = {
        "title": "Novo condomínio", "sub": "Condomínio atendido, vinculado ao cliente (administradora ou o próprio condomínio).", "cta": "Salvar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/condominio-novo", "okMsg": "Condomínio criado"},
        "fields": [_sel("client_id", "Cliente*", cli), {"key": "name", "label": "Nome*", "type": "text", "span": "span 2"},
                   {"key": "cnpj", "label": "CNPJ", "type": "text", "span": "span 1"}, {"key": "total_units", "label": "Unidades", "type": "number", "span": "span 1"},
                   {"key": "address_street", "label": "Logradouro", "type": "text", "span": "span 1"}, {"key": "address_number", "label": "Número", "type": "text", "span": "span 1"},
                   {"key": "address_neighborhood", "label": "Bairro", "type": "text", "span": "span 1"}, {"key": "address_city", "label": "Cidade", "type": "text", "span": "span 1", "ph": "Manaus"},
                   {"key": "syndic_name", "label": "Síndico", "type": "text", "span": "span 1"}, {"key": "syndic_phone", "label": "Telefone do síndico", "type": "text", "span": "span 1"}]}
    out["cliente-inadimplente"] = {
        "title": "Marcar inadimplência", "sub": "Marca o cliente como inadimplente com o valor em aberto. Para regularizar, use o botão na linha do cliente.",
        "cta": "Marcar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/cliente-inadimplente", "okMsg": "Cliente marcado como inadimplente", "confirm": "Marcar o cliente como inadimplente?"},
        "fields": [_sel("client_id", "Cliente*", cli), {"key": "debt_amount", "label": "Valor em aberto (R$)*", "type": "number", "span": "span 1"}]}
    out["cliente-ficha-360"] = {
        "title": "Ficha 360 do cliente", "sub": "Contratos, NFS-e, oportunidades, atividades e contatos do cliente numa consulta só. Só lê.",
        "cta": "Ver ficha", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/cliente-ficha-360", "okMsg": "Ficha carregada", "showResult": True},
        "fields": [_sel("client_id", "Cliente*", cli)]}
    out["consultar-cnpj-cep"] = {
        "title": "Consultar CNPJ / CEP", "sub": "Busca os dados cadastrais (Receita/BrasilAPI) para preencher cliente ou condomínio sem digitar tudo. Só consulta.",
        "cta": "Consultar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/consultar-cnpj-cep", "okMsg": "Consulta feita", "showResult": True},
        "fields": [_sel("tipo", "O que consultar*", [{"value": "cnpj", "label": "CNPJ"}, {"value": "cep", "label": "CEP"}], "span 1"),
                   {"key": "valor", "label": "Número*", "type": "text", "span": "span 1", "ph": "só dígitos"}]}
    out["contrato-reajuste-calcular"] = {
        "title": "Calcular reajuste de contrato", "sub": "Só calcula e mostra — não altera o contrato. Informe o percentual (o índice não é consultado automaticamente).",
        "cta": "Calcular", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/contrato-reajuste-calcular", "okMsg": "Reajuste calculado", "showResult": True},
        "fields": [_sel("contract_id", "Contrato*", ctr), {"key": "custom_percent", "label": "Percentual (%)*", "type": "number", "span": "span 1"},
                   {"key": "effective_date", "label": "Vigência", "type": "date", "span": "span 1"}]}


async def _ligar_lote4_20260908(db, out: dict) -> None:
    """LIGAR lote 4 (08/09/2026): rotas que existiam sem tela (vereditos B e C). Blocos independentes (try/except + rollback).
    Regra da casa: a página nunca chama Drive/robô/governo — leituras do Drive viram formulários GET que o usuário dispara."""
    import logging as _lg
    from datetime import date as _dt
    from sqlalchemy import text as _T
    from modules.operacional.controllers.redesign_data_controller import _helpers, t, b, brl
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]
    hoje = _dt.today()

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback(); return 0

    def _consulta(key, titulo, sub, endpoint, fields, method="GET"):
        """Form de CONSULTA: dispara o GET com query e mostra o resultado (a página não chama nada ao abrir)."""
        out[key] = {"title": titulo, "sub": sub, "cta": "Consultar", "type": "form",
                    "submit": {"endpoint": endpoint, "method": method, "query": True, "okMsg": "Consulta feita — veja o resultado.", "showResult": True},
                    "fields": fields}

    _consulta("jose-luis-dashboard", "José Luís — painel do agente (WhatsApp)", "Conversas, respostas, leads, visitas e OS por dia nos últimos N dias (cwi_message_log).",
              "/api/v1/whatsapp/agent/dashboard", [{"key": "dias", "label": "Dias (1–90)", "type": "number", "span": "span 1", "value": 14}])
