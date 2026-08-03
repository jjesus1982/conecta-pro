"""Tools READ do CRM (Fase 6, balde VER) — módulo crm, scope_kind="org".

No chat escopado, quem tem o módulo `crm` CONSULTA o comercial como faria navegando
as telas: lista clientes, ficha de cliente, funil, forecast, deals, propostas,
contratos, negociações pendentes. Cada handler chama a COROUTINE do controller REAL
in-process, com a IDENTIDADE do usuário logado (o `db`/`user` reais) — NUNCA a conta
de serviço, NUNCA HTTP.

Paredes (inegociáveis):
- RBAC na fonte: chamar o controller direto PULA o Depends(require_permission) dele,
  então TODO handler faz `_gate(user)` primeiro (re-checa user_has_module(user,"crm")).
  O belt (tools_for_modules) já filtra por módulo; o _gate é o suspenders.
- SÓ LEITURA: só coroutines de rota GET entram aqui. Nada cria/edita/apaga/envia.
- Nunca fabricar: devolve o resultado REAL do banco; vazio real = vazio, não número inventado.
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register


def _gate(user) -> None:
    # Suspenders: o controller GET normalmente gateia via Depends no mount do router;
    # chamado direto isso é pulado, então re-checamos o módulo aqui na fonte.
    if not user_has_module(user, "crm"):
        raise PermissionError("crm")


# ---- handlers (assinaturas heterogêneas dos controllers → 8 handlers explícitos) ----

async def _listar_clientes(db, user, scope, *, status=None, segment=None, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.client_controller import listar_clientes
    return await listar_clientes(current_user=user, db=db, status=status, segment=segment)


async def _ficha_cliente(db, user, scope, *, cliente=None, **_) -> dict[str, Any]:
    _gate(user)
    if not cliente:
        return {"status": "informe o cliente (nome ou CNPJ) para abrir a ficha"}
    from modules.crm.controllers.growth_controller import ficha_cliente_ep
    return await ficha_cliente_ep(ref=str(cliente), db=db)


async def _funil(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import funil
    return await funil(db=db)


async def _forecast(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import forecast
    return await forecast(db=db)


async def _listar_deals(db, user, scope, *, stage=None, search=None, is_open=None,
                        page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.opportunity_controller import list_opportunities
    # min_value/max_value têm default Query(...) na rota; chamando direto (sem FastAPI)
    # é preciso passá-los explicitamente como None, senão o Query() vira valor e quebra o filtro.
    res = await list_opportunities(current_user=user, db=db, stage=stage, search=search,
                                   is_open=is_open, page=page, page_size=page_size,
                                   min_value=None, max_value=None)
    return res.model_dump(mode="json")  # Pydantic → dict p/ o engine serializar em JSON


async def _listar_propostas(db, user, scope, *, status=None, search=None,
                            page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.proposal_controller import list_proposals
    res = await list_proposals(current_user=user, db=db, status_filter=status, search=search,
                               page=page, page_size=page_size, min_value=None, max_value=None)
    return res.model_dump(mode="json")


async def _listar_contratos(db, user, scope, *, status=None, search=None,
                            page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.contract_controller import list_contracts
    res = await list_contracts(current_user=user, db=db, status_filter=status, search=search,
                               page=page, page_size=page_size, min_value=None, max_value=None)
    return res.model_dump(mode="json")


async def _negociacoes_pendentes(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.growth_controller import negociacoes_pendentes
    return await negociacoes_pendentes(db=db)


# ---- schemas (SÓ filtros de negócio; nunca db/user/scope — o registry proíbe) ----

_NO_ARGS = {"type": "object", "properties": {}}

_S_CLIENTES = {"type": "object", "properties": {
    "status": {"type": "string", "description": "Filtrar por status (ex.: active, inactive)."},
    "segment": {"type": "string", "description": "Filtrar por segmento."},
}}

_S_FICHA = {"type": "object", "properties": {
    "cliente": {"type": "string", "description": "Nome ou CNPJ do cliente."},
}, "required": ["cliente"]}

_S_DEALS = {"type": "object", "properties": {
    "stage": {"type": "string", "description": "Estágio do funil: qualification, needs_analysis, "
              "proposal, negotiation, closed_won, closed_lost."},
    "is_open": {"type": "boolean", "description": "Só oportunidades em aberto."},
    "search": {"type": "string", "description": "Busca por título, contato, e-mail ou empresa."},
    "page": {"type": "integer"}, "page_size": {"type": "integer"},
}}

_S_PROPOSTAS = {"type": "object", "properties": {
    "status": {"type": "string", "description": "Status: draft, pending_review, pending_approval, "
               "approved, sent, viewed, accepted, rejected, expired, cancelled."},
    "search": {"type": "string", "description": "Busca por número, título ou cliente."},
    "page": {"type": "integer"}, "page_size": {"type": "integer"},
}}

_S_CONTRATOS = {"type": "object", "properties": {
    "status": {"type": "string", "description": "Status: draft, pending_signature, active, "
               "suspended, cancelled, terminated."},
    "search": {"type": "string", "description": "Busca por número/cliente."},
    "page": {"type": "integer"}, "page_size": {"type": "integer"},
}}


register(ToolDef("crm_listar_clientes", "crm",
                 "Lista os clientes da base oficial (com MRR e contratos ativos). Filtros opcionais "
                 "por status e segmento.", _S_CLIENTES, _listar_clientes, scope_kind="org"))
register(ToolDef("crm_ficha_cliente", "crm",
                 "Abre a ficha viva de UM cliente (dados + anotações + último status de negociação) "
                 "por nome ou CNPJ.", _S_FICHA, _ficha_cliente, scope_kind="org"))
register(ToolDef("crm_consultar_funil", "crm",
                 "Funil comercial unificado (primeiro contato → fechamento) por etapa, com gargalo "
                 "e quem está parado há mais tempo.", _NO_ARGS, _funil, scope_kind="org"))
register(ToolDef("crm_consultar_forecast", "crm",
                 "Forecast: previsão ponderada do pipeline aberto por estágio, total ponderado e "
                 "metas do mês.", _NO_ARGS, _forecast, scope_kind="org"))
register(ToolDef("crm_listar_deals", "crm",
                 "Lista oportunidades/deals do pipeline, com filtros (estágio, em aberto, busca) e "
                 "paginação.", _S_DEALS, _listar_deals, scope_kind="org"))
register(ToolDef("crm_listar_propostas", "crm",
                 "Lista propostas comerciais, com filtros (status, busca) e paginação.",
                 _S_PROPOSTAS, _listar_propostas, scope_kind="org"))
register(ToolDef("crm_listar_contratos", "crm",
                 "Lista contratos, com filtros (status, busca) e paginação.",
                 _S_CONTRATOS, _listar_contratos, scope_kind="org"))
register(ToolDef("crm_negociacoes_pendentes", "crm",
                 "Propostas enviadas SEM resposta do cliente (negociações pendentes, com dias "
                 "parados).", _NO_ARGS, _negociacoes_pendentes, scope_kind="org"))
