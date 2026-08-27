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


async def _listar_leads(db, user, scope, *, status=None, source=None, is_hot=None,
                        company=None, search=None, page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.lead_controller import list_leads
    # rota tem Query(...) nos params; chamando direto passamos tudo explícito p/ não vazar Query objects.
    res = await list_leads(current_user=user, db=db, page=page, page_size=page_size,
                           status_filter=status, source=source, assigned_to_id=None,
                           min_score=None, max_score=None, is_hot=is_hot,
                           company=company, search=search)
    return res.model_dump(mode="json")


async def _pipeline(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.opportunity_controller import get_pipeline_stats
    res = await get_pipeline_stats(current_user=user, db=db, owner_id=None)
    return res.model_dump(mode="json")


async def _reunioes(db, user, scope, *, futuras=True, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.growth_controller import listar_reunioes_ep
    return await listar_reunioes_ep(db=db, futuras=futuras)


async def _followups_pendentes(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.growth_controller import followups_pendentes
    return await followups_pendentes(db=db)


async def _historico_followup(db, user, scope, *, deal_id=None, **_) -> dict[str, Any]:
    _gate(user)
    if not deal_id:
        return {"status": "informe deal_id para ver o histórico de follow-up"}
    from modules.crm.controllers.growth_controller import followups_historico
    return await followups_historico(deal_id=str(deal_id), db=db)


async def _painel_negociacoes(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.growth_controller import listar_negociacoes
    return await listar_negociacoes(db=db)


async def _resumo_comercial(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.growth_controller import relatorio_comercial_endpoint
    return await relatorio_comercial_endpoint(db=db)


async def _sequencias(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import list_sequences
    return await list_sequences(db=db)


async def _campanhas(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.marketing_controller import listar_campanhas
    return await listar_campanhas(current_user=user, db=db)


async def _contatos(db, user, scope, *, client_id=None, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.contact_controller import listar_contatos
    return await listar_contatos(current_user=user, client_id=client_id, db=db)


async def _atividades(db, user, scope, *, client_id=None, limit=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.contact_controller import listar_atividades
    return await listar_atividades(current_user=user, client_id=client_id, limit=limit, db=db)


async def _tarefas(db, user, scope, *, status=None, assigned_to_id=None, lead_id=None,
                   opportunity_id=None, client_id=None, overdue=None, **_) -> dict[str, Any]:
    _gate(user)
    from modules.crm.controllers.contact_controller import listar_tarefas
    return await listar_tarefas(current_user=user, status=status, assigned_to_id=assigned_to_id,
                                lead_id=lead_id, opportunity_id=opportunity_id,
                                client_id=client_id, overdue=overdue, db=db)


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
registrar_read("crm", "leads",
               "Lista leads com paginação. Filtros: status, source, is_hot, company, search, "
               "page, page_size.", _listar_leads)
registrar_read("crm", "pipeline",
               "Estatísticas do pipeline de vendas: valor total, valor ponderado, win rate, "
               "tempo médio de fechamento.", _pipeline)
registrar_read("crm", "reunioes",
               "Lista as reuniões comerciais (por padrão só as futuras). Filtro: futuras "
               "(true/false).", _reunioes)
registrar_read("crm", "followups_pendentes",
               "Follow-ups (toques) agendados/a fazer: deal, cliente, canal e data.",
               _followups_pendentes)
registrar_read("crm", "historico_followup",
               "Histórico de follow-ups + respostas de UM deal. Filtro obrigatório: deal_id.",
               _historico_followup)
registrar_read("crm", "painel_negociacoes",
               "Painel das negociações em aberto: cliente, proposta, quem conduz, última "
               "resposta.", _painel_negociacoes)
registrar_read("crm", "resumo_comercial",
               "Raio-x de vendas: win/loss, conversão do funil, motivos de perda, ROI por canal, "
               "ranking de MRR e ciclo médio.", _resumo_comercial)
registrar_read("crm", "sequencias",
               "Lista as sequências de cadência comercial (crm_sequences).", _sequencias)
registrar_read("crm", "campanhas",
               "Lista campanhas de marketing com total de leads, convertidos e ROI.", _campanhas)
registrar_read("crm", "contatos",
               "Lista contatos CRM (pessoas). Filtro opcional: client_id.", _contatos)
registrar_read("crm", "atividades",
               "Lista atividades CRM (interações). Filtros: client_id, limit.", _atividades)
registrar_read("crm", "tarefas",
               "Lista tarefas CRM. Filtros: status, assigned_to_id, lead_id, opportunity_id, "
               "client_id, overdue.", _tarefas)


# ── LEITURAS COMERCIAIS QUE SÓ O MCP TINHA (lacunas 14–19) ───────────────────────────
# Todas as rotas já existiam MONTADAS e sem superfície no chat: era LIGAR, não construir.
# Cada handler chama a corrotina do controller real, com a identidade de quem pergunta.
# ⚠️ MÓDULO: `crm/controllers/growth_controller.py` em todas — conferido pelo caminho.


def _dump(res: Any) -> Any:
    """Pydantic → dict; dict passa direto. O engine serializa em JSON depois."""
    return res.model_dump(mode="json") if hasattr(res, "model_dump") else res


async def _leads_frios(db, user, scope, *, dias=14, **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import leads_frios_endpoint

    return _dump(await leads_frios_endpoint(db=db, dias=int(dias)))


async def _cross_sell(db, user, scope, *, cliente="", **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import cross_sell_endpoint

    if not str(cliente or "").strip():
        return {"status": "recusado",
                "motivo": "informe o cliente — cross-sell sai dos contratos REAIS dele, "
                          "não de sugestão genérica"}
    return _dump(await cross_sell_endpoint(cliente=str(cliente).strip(), db=db))


async def _simular_fechamento(db, user, scope, *, deals=None, estagio="negotiation", **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import SimularIn2, simular_fechamento_endpoint

    lista = deals if isinstance(deals, list) else (
        [d.strip() for d in str(deals).split(";") if d.strip()] if deals else None)
    # POST que só CALCULA: não persiste nada. Entra no balde de leitura pela mesma exceção
    # declarada que o conector usa em `POST_DE_CONSULTA`.
    return _dump(await simular_fechamento_endpoint(
        data=SimularIn2(deals=lista, estagio=estagio or "negotiation"), db=db))


async def _resumo_nps(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import nps_resumo

    return _dump(await nps_resumo(db=db))


async def _reunioes(db, user, scope, *, futuras=True, **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import listar_reunioes_ep

    return _dump(await listar_reunioes_ep(db=db, futuras=bool(futuras)))


async def _relatorios_visita(db, user, scope, *, visita="", **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import listar_visitas, visita_detalhe

    ref = str(visita or "").strip()
    # Sem `visita` lista tudo; com, abre o detalhe daquela. Uma consulta que serve às duas
    # perguntas que a pessoa faz ("quais visitas?" e "o que teve na da VEGA?").
    if ref:
        return _dump(await visita_detalhe(ref=ref, db=db))
    return _dump(await listar_visitas(db=db))


registrar_read("crm", "leads_frios",
               "Leads que ESFRIARAM — sem interação há N dias e ainda abertos. Filtros: dias "
               "(padrão 14).", _leads_frios)
registrar_read("crm", "cross_sell",
               "A partir dos contratos REAIS de um cliente, o que ele ainda não tem. Filtros: "
               "cliente (obrigatório).", _cross_sell)
registrar_read("crm", "simular_fechamento",
               "What-if: 'se eu fechar estes deals, como fica o mês?'. Filtros: deals (ids "
               "separados por ';') ou estagio (padrão negotiation). Só calcula — não fecha "
               "nada.", _simular_fechamento)
registrar_read("crm", "resumo_nps",
               "NPS consolidado: respostas, média, promotores/neutros/detratores.", _resumo_nps)
registrar_read("crm", "reunioes",
               "Reuniões agendadas. Filtros: futuras (padrão true; false traz as passadas).",
               _reunioes)
registrar_read("crm", "relatorios_visita",
               "Relatórios de visita: sem filtro lista todos; com `visita` (id ou nome do "
               "cliente) abre o detalhe daquele. Filtros: visita.", _relatorios_visita)
