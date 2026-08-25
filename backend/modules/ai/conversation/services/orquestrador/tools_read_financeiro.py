"""Tools READ do Financeiro (Fase 6, balde VER) — módulo financeiro, scope_kind="org".

No chat escopado, quem tem o módulo `financeiro` (diretoria) CONSULTA o financeiro
como faria navegando as telas: KPIs do dashboard, contas a receber e a pagar (listas
e resumos), inadimplência (títulos vencidos), saldos das contas bancárias e os
pagamentos PIX. Cada handler chama a COROUTINE do controller REAL in-process, com a
IDENTIDADE do usuário logado (o `db`/`user` reais) — NUNCA a conta de serviço, NUNCA HTTP.

Molde idêntico ao tools_read_crm.py / tools_read_dp.py (commits 9d0da02e / 7d64a0ff).

NÃO duplica o que já existe: DRE, balancete, fluxo de caixa e aging já são GERA-DOC
(tools_financeiro_doc.py) e o resumo rápido de caixa/folha já é `panorama_financeiro`
(tools_modulos.py). Aqui ficam só as LEITURAS que faltavam (listas/resumos/saldos).

Paredes (inegociáveis):
- RBAC na fonte: chamar o controller direto PULA o Depends(require_permission) dele,
  então TODO handler faz `_gate(user)` primeiro (re-checa user_has_module(user,"financeiro")).
  O belt (tools_for_modules) já filtra por módulo; o _gate é o suspenders.
- SÓ LEITURA: só coroutines de rota GET entram aqui. Nada cria/edita/aprova/move dinheiro.
- Nunca fabricar: devolve o resultado REAL do banco; vazio real = vazio, não número inventado.
- Multi-CNPJ: receivable/payable NÃO têm empresa_id (chaveiam por condomínio/cliente) →
  visão consolidada do grupo, rotulada honestamente. Saldos bancários saem por CONTA
  (Inter=Eletrônica, Cora=Patrimonial): cada linha é seu próprio banco, não há mistura.

SQL: os controllers/serviços reusados usam parâmetros ligados (`.ilike(bind)` / `:param`),
nenhum f-string com input do usuário — verificado ao curar.
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .read_dispatcher import registrar_read


def _gate(user) -> None:
    # Suspenders: o controller GET normalmente gateia via Depends no mount do router;
    # chamado direto isso é pulado, então re-checamos o módulo aqui na fonte. (O dispatcher
    # também gateia antes de despachar; aqui é a 2ª cinta caso o handler seja chamado direto.)
    if not user_has_module(user, "financeiro"):
        raise PermissionError("financeiro")


def _dump(obj):
    """Pydantic → dict JSON-able (o engine faz json.dumps(default=str); Pydantic cru viraria repr)."""
    return obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj


# ---- handlers (assinaturas heterogêneas dos controllers → handlers explícitos) ----

async def _dashboard(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.financial.controllers.financial_dashboard_controller import get_financial_dashboard
    # condominio_id=None → visão consolidada (todas as contas ativas); dados reais, sem mistura de CNPJ.
    return await get_financial_dashboard(condominio_id=None, current_user=user, db=db)


async def _contas_a_receber(db, user, scope, *, status=None, search=None, is_overdue=None,
                            skip=0, limit=100, **_) -> dict[str, Any]:
    _gate(user)
    from modules.financial.controllers.receivable_controller import list_accounts
    from modules.financial.services.receivable_service import ReceivableService
    res = await list_accounts(
        condominio_id=None, search=search, customer_id=None, unidade_id=None, category_id=None,
        status_filter=status, due_date_start=None, due_date_end=None, is_recurring=None,
        is_overdue=is_overdue, min_value=None, max_value=None, skip=skip, limit=limit,
        service=ReceivableService(db), current_user=user)
    return {"data": [_dump(a) for a in res.get("data", [])], "meta": res.get("meta", {})}


async def _contas_a_pagar(db, user, scope, *, status=None, search=None, is_overdue=None,
                          skip=0, limit=100, **_) -> dict[str, Any]:
    _gate(user)
    from modules.financial.controllers.payable_controller import list_accounts
    from modules.financial.services.payable_service import PayableService
    res = await list_accounts(
        condominio_id=None, search=search, supplier_id=None, category_id=None,
        status_filter=status, due_date_start=None, due_date_end=None, is_recurring=None,
        is_overdue=is_overdue, min_value=None, max_value=None, skip=skip, limit=limit,
        service=PayableService(db), current_user=user)
    return {"data": [_dump(a) for a in res.get("data", [])], "meta": res.get("meta", {})}


async def _resumo_receber(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.financial.controllers.receivable_controller import get_stats
    from modules.financial.services.receivable_service import ReceivableService
    return _dump(await get_stats(condominio_id=None, service=ReceivableService(db), current_user=user))


async def _resumo_pagar(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.financial.controllers.payable_controller import get_stats
    from modules.financial.services.payable_service import PayableService
    return _dump(await get_stats(condominio_id=None, service=PayableService(db), current_user=user))


async def _inadimplencia(db, user, scope, *, limit=100, **_) -> dict[str, Any]:
    _gate(user)
    from modules.financial.controllers.receivable_controller import get_overdue
    from modules.financial.services.receivable_service import ReceivableService
    vencidas = await get_overdue(condominio_id=None, limit=limit,
                                 service=ReceivableService(db), current_user=user)
    return {"titulos_vencidos": [_dump(a) for a in vencidas]}


async def _saldos_bancos(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.financial.controllers.bank_account_controller import list_bank_accounts
    from modules.financial.repositories import BankAccountRepository
    contas = await list_bank_accounts(
        condominio_id=None, account_type=None, account_status=None, is_main=None,
        skip=0, limit=500, repo=BankAccountRepository(db), current_user=user)
    # Cada conta é seu próprio banco (Inter/Cora → CNPJ1/CNPJ2): visão por conta, sem mistura.
    return {"contas": [_dump(a) for a in contas]}


async def _listar_pagamentos(db, user, scope, *, status=None, payment_type=None, limit=100, **_) -> dict[str, Any]:
    _gate(user)
    # Leitura da lista de pagamentos PIX (inter_payments). READ-ONLY: só lista o que já existe —
    # não prepara, aprova nem executa (isso é gate-OTP na tool de ação da 5.4).
    from modules.integrations.inter.payment_controller import listar_pagamentos
    return await listar_pagamentos(status_filter=status, payment_type=payment_type,
                                   from_date=None, to_date=None, limit=limit, db=db, current_user=user)


async def _inter_saldo(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.integrations.inter.inter_controller import get_saldo
    return _dump(await get_saldo(current_user=user))


async def _inter_extrato_resumo(db, user, scope, *, dias=30, **_) -> Any:
    _gate(user)
    from modules.integrations.inter.inter_controller import resumo_extrato
    return _dump(await resumo_extrato(dias=int(dias), db=db, current_user=user))


async def _pix_recebidos(db, user, scope, *, limit=50, **_) -> Any:
    _gate(user)
    from modules.integrations.inter.inter_controller import listar_pix_recebidos
    return _dump(await listar_pix_recebidos(limit=int(limit), db=db, current_user=user))


async def _cobrancas_inter(db, user, scope, *, status=None, limit=50, **_) -> Any:
    _gate(user)
    from modules.integrations.inter.inter_controller import listar_cobrancas
    return _dump(await listar_cobrancas(status=status, limit=int(limit), db=db, current_user=user))


async def _teto_diario_pagamentos(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.integrations.inter.payment_controller import saldo_limite
    return _dump(await saldo_limite(db=db, current_user=user))


async def _previsao_custos_mensais(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.financial.cfo_controller import previsao_custos
    return _dump(await previsao_custos(current_user=user, db=db))


async def _runway(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.ai.conversation.controllers.executivo_controller import runway
    return _dump(await runway(db=db, user=user))


async def _margem_por_condominio(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.ai.conversation.controllers.executivo_controller import margem_condominio
    return _dump(await margem_condominio(db=db, user=user))


async def _resumo_financeiro(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.crm.controllers.growth_controller import financeiro_endpoint
    return _dump(await financeiro_endpoint(db=db))


async def _reembolsos(db, user, scope, *, status=None, **_) -> Any:
    _gate(user)
    from modules.reimbursement.controllers.reimbursement_controller import list_reimbursements
    return _dump(await list_reimbursements(user=user, condominio_id=None, db=db, status_filter=status))


async def _beneficiarios_pix(db, user, scope, *, q="", limite=12, **_) -> Any:
    _gate(user)
    from modules.financial.beneficiarios_controller import listar
    return _dump(await listar(q=str(q or ""), limite=int(limite), current_user=user, db=db))


async def _cfo_panorama(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.financial.cfo_controller import obter_panorama
    return _dump(await obter_panorama(current_user=user, db=db))


async def _recebido_por_cliente(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.financial.cfo_controller import recebido_por_cliente
    return _dump(await recebido_por_cliente(current_user=user, db=db))


async def _adimplencia_clientes(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.financial.cfo_controller import adimplencia_clientes
    return _dump(await adimplencia_clientes(current_user=user, db=db))


async def _projecao_caixa(db, user, scope, *, meses=6, **_) -> Any:
    _gate(user)
    from modules.financial.cfo_controller import projecao_caixa
    return _dump(await projecao_caixa(meses=int(meses), current_user=user, db=db))


async def _custos_recorrentes(db, user, scope, **_) -> Any:
    _gate(user)
    # LISTAR (read). Criar já é ação em agir_financeiro; remover NÃO entra aqui.
    from modules.financial.cfo_controller import custos_listar
    return _dump(await custos_listar(current_user=user, db=db))


async def _briefing_executivo(db, user, scope, **_) -> Any:
    _gate(user)
    # Briefing executivo cross-módulo (caixa por CNPJ + COO + certidões + CRM), cada número com
    # source. Gate de diretoria via módulo financeiro. Só leitura.
    from modules.ai.conversation.controllers.executivo_controller import briefing
    return _dump(await briefing(db=db, user=user))


# ---- registro das ops READ no dispatcher consultar_financeiro (filtros vão em `filtros`) ----

registrar_read("financeiro", "dashboard",
               "KPIs do dashboard financeiro (dados reais): saldo bancário consolidado, entradas e "
               "saídas do mês, total a receber e a pagar. Visão do grupo.", _dashboard)
registrar_read("financeiro", "contas_a_receber",
               "Lista contas a receber (títulos). Grupo consolidado. Filtros: status, search, "
               "is_overdue, skip, limit. Vazio real = sem títulos, não fabrica.", _contas_a_receber)
registrar_read("financeiro", "contas_a_pagar",
               "Lista contas a pagar (títulos). Grupo consolidado. READ-ONLY: só lista, não aprova "
               "nem paga. Filtros: status, search, is_overdue, skip, limit.", _contas_a_pagar)
registrar_read("financeiro", "resumo_receber",
               "Resumo/estatísticas de contas a receber (totais por situação: em aberto, vencido, "
               "pago). Grupo consolidado, números reais.", _resumo_receber)
registrar_read("financeiro", "resumo_pagar",
               "Resumo/estatísticas de contas a pagar (totais por situação: em aberto, vencido, "
               "pago). Grupo consolidado, números reais.", _resumo_pagar)
registrar_read("financeiro", "inadimplencia",
               "Títulos a receber VENCIDOS (inadimplência), do mais antigo ao mais recente. Grupo "
               "consolidado. Filtro: limit. Sem vencidos = lista vazia real, não fabrica.",
               _inadimplencia)
registrar_read("financeiro", "saldos_bancos",
               "Saldos das contas bancárias, uma linha por conta (Inter=Eletrônica, Cora=Patrimonial) "
               "— sem misturar CNPJ. Dados reais das contas ativas.", _saldos_bancos)
registrar_read("financeiro", "pagamentos",
               "Lista pagamentos PIX (inter_payments). READ-ONLY: só mostra o que existe — NÃO "
               "prepara, aprova nem executa pagamento (isso é gate-OTP). Filtros: status, "
               "payment_type, limit.", _listar_pagamentos)
registrar_read("financeiro", "inter_saldo",
               "Saldo atual da conta Banco Inter (Eletrônica), leitura em tempo real. Sem filtros.",
               _inter_saldo)
registrar_read("financeiro", "inter_extrato_resumo",
               "Resumo do extrato Inter: totais de crédito/débito por tipo nos últimos N dias. "
               "Filtro: dias (default 30).", _inter_extrato_resumo)
registrar_read("financeiro", "pix_recebidos",
               "PIX recebidos na conta Inter (entradas identificadas em inter_pix_recebidos). "
               "Filtro: limit. Vazio real = sem PIX, não fabrica.", _pix_recebidos)
registrar_read("financeiro", "cobrancas_inter",
               "Cobranças/boletos emitidos pelo Inter e seus status (inter_cobrancas). Filtros: "
               "status, limit.", _cobrancas_inter)
registrar_read("financeiro", "teto_diario_pagamentos",
               "Teto diário de pagamentos (CONECTA_LIMITE_DIARIO) vs quanto já saiu hoje: "
               "consumido e disponível. READ-ONLY. Sem filtros.", _teto_diario_pagamentos)
registrar_read("financeiro", "previsao_custos_mensais",
               "Previsibilidade de custos mensais: folha, FGTS, ISS, diaristas, fornecedores, "
               "reembolsos e custos recorrentes registrados — cada valor com a fonte. Sem filtros.",
               _previsao_custos_mensais)
registrar_read("financeiro", "runway_ao_vivo",
               "Runway de caixa AO VIVO por CNPJ: saldo do banco vivo ÷ folha mensal = meses, com "
               "as_of. Não mistura contas; onde falta saldo/folha vem 'aguardando dado'. Sem filtros.",
               _runway)
registrar_read("financeiro", "margem_por_condominio",
               "Margem por contrato: receita (contrato) − folha alocada (best-effort). Onde o "
               "cruzamento não fecha, a folha vem 'aguardando dado', nunca estimada. Sem filtros.",
               _margem_por_condominio)
registrar_read("financeiro", "resumo_financeiro",
               "Retrato financeiro: MRR, MRR anualizado, recebíveis previstos, inadimplência, "
               "caixa do mês (entradas/saídas/saldo) e faturamento NFS-e. Sem filtros.",
               _resumo_financeiro)
registrar_read("financeiro", "reembolsos",
               "Lista solicitações de REEMBOLSO (paginado). READ-ONLY: só lista, não aprova nem "
               "paga. Filtro: status.", _reembolsos)
registrar_read("financeiro", "beneficiarios_pix",
               "Agenda de beneficiários PIX salvos (nome → chave). Filtros: q (busca parcial por "
               "nome/chave/CPF-CNPJ), limite.", _beneficiarios_pix)
registrar_read("financeiro", "panorama",
               "Panorama CFO: fotografia financeira real do ERP agora (caixa, MRR, recebíveis, "
               "custos, tributos) — âncora do consultor financeiro. Sem filtros.", _cfo_panorama)
registrar_read("financeiro", "recebido_por_cliente",
               "Quanto CADA cliente pagou de verdade no banco (recebimentos identificados no "
               "extrato Inter: PIX/boleto com nome do cliente) + total. Sem filtros.",
               _recebido_por_cliente)
registrar_read("financeiro", "adimplencia_clientes",
               "MRR contratado × recebido no banco, POR cliente (quem está em dia / em atraso). "
               "Números reais. Sem filtros.", _adimplencia_clientes)
registrar_read("financeiro", "projecao_caixa",
               "Projeção de caixa recorrente (saldo atual + MRR − custos mensais) nos próximos N "
               "meses. Filtro: meses (default 6, máx 24).", _projecao_caixa)
registrar_read("financeiro", "custos_recorrentes",
               "Lista os custos recorrentes registrados (tributos, parcelamentos, acordos, fixos, "
               "fornecedores). READ-ONLY: só lista — criar/remover é ação. Sem filtros.",
               _custos_recorrentes)
registrar_read("financeiro", "briefing_executivo",
               "Briefing executivo cross-módulo (1-card): caixa DISCRIMINADA por CNPJ "
               "(Inter/Eletrônica + Cora/Patrimonial + consolidado), postos descobertos (COO), "
               "certidões vencendo (fiscal) e deals quentes (CRM) — cada número com source. "
               "Gate de diretoria. Sem filtros.", _briefing_executivo)


# ── VIABILIDADE DE CONTRATAÇÃO (12ª das 14 — leitura) ────────────────────────────────
# Rota POST /consultores/mcp/executivo/viabilidade-contratacao ·
# `ai/conversation/controllers/executivo_controller.py:214`.
# É POST porque recebe parâmetros no corpo, mas NÃO PERSISTE nada — é cálculo. Entra no balde
# de leitura de propósito (mesma exceção declarada no `POST_DE_CONSULTA` do conector).
# Fica em `financeiro` porque a restrição é dinheiro: saldo e runway é que dizem se cabe.
async def _viabilidade_contratacao(db, user, scope, *, quantidade=None, cargo="", **_) -> Any:
    _gate(user)
    from modules.ai.conversation.controllers.executivo_controller import (
        ViabilidadeIn, viabilidade_contratacao,
    )

    try:
        qtd = int(quantidade)
    except (TypeError, ValueError):
        return {"status": "recusado",
                "motivo": "informe quantidade (quantas pessoas) e cargo"}
    if not str(cargo or "").strip():
        return {"status": "recusado", "motivo": "informe o cargo (ex.: 'Agente de Portaria')"}
    return _dump(await viabilidade_contratacao(
        payload=ViabilidadeIn(qtd=qtd, cargo=str(cargo).strip()), db=db, user=user))


registrar_read("financeiro", "viabilidade_contratacao",
               "\"Posso contratar N pessoas do cargo X?\" — cruza saldo/runway (CFO), postos "
               "descobertos (COO) e o custo real de folha (piso da CCT + encargos). Filtros: "
               "quantidade (obrig.), cargo (obrig.). Só cálculo sobre dado real, não contrata "
               "ninguém.", _viabilidade_contratacao)
