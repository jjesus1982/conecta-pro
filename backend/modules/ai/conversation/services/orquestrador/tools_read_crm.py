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

from .read_dispatcher import registrar_read


def _gate(user) -> None:
    # Suspenders: o controller GET normalmente gateia via Depends no mount do router;
    # chamado direto isso é pulado, então re-checamos o módulo aqui na fonte. (O dispatcher
    # também gateia antes de despachar; aqui é a 2ª cinta caso o handler seja chamado direto.)
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


# ---- registro das ops READ no dispatcher consultar_crm (filtros vão em `filtros`) ----

registrar_read("crm", "clientes",
               "Lista os clientes da base oficial (com MRR e contratos ativos). Filtros opcionais: "
               "status, segment.", _listar_clientes)
registrar_read("crm", "ficha_cliente",
               "Abre a ficha viva de UM cliente (dados + anotações + último status de negociação). "
               "Filtro obrigatório: cliente (nome ou CNPJ).", _ficha_cliente)
registrar_read("crm", "funil",
               "Funil comercial unificado (primeiro contato → fechamento) por etapa, com gargalo "
               "e quem está parado há mais tempo.", _funil)
registrar_read("crm", "forecast",
               "Forecast: previsão ponderada do pipeline aberto por estágio, total ponderado e "
               "metas do mês.", _forecast)
registrar_read("crm", "deals",
               "Lista oportunidades/deals do pipeline. Filtros: stage, is_open, search, page, "
               "page_size.", _listar_deals)
registrar_read("crm", "propostas",
               "Lista propostas comerciais. Filtros: status, search, page, page_size.",
               _listar_propostas)
registrar_read("crm", "contratos",
               "Lista contratos. Filtros: status, search, page, page_size.", _listar_contratos)
registrar_read("crm", "negociacoes_pendentes",
               "Propostas enviadas SEM resposta do cliente (negociações pendentes, com dias "
               "parados).", _negociacoes_pendentes)
