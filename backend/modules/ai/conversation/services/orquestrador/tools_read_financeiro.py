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

from .tool_registry import ToolDef, register


def _gate(user) -> None:
    # Suspenders: o controller GET normalmente gateia via Depends no mount do router;
    # chamado direto isso é pulado, então re-checamos o módulo aqui na fonte.
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


# ---- schemas (SÓ filtros de negócio; nunca db/user/scope — o registry proíbe) ----

_NO_ARGS = {"type": "object", "properties": {}}

_S_RECEBER = {"type": "object", "properties": {
    "status": {"type": "string", "description": "Status: pendente, paga, vencida, cancelada, negociada."},
    "search": {"type": "string", "description": "Busca por descrição, número do documento ou código."},
    "is_overdue": {"type": "boolean", "description": "Apenas títulos vencidos."},
    "skip": {"type": "integer"}, "limit": {"type": "integer"},
}}

_S_PAGAR = {"type": "object", "properties": {
    "status": {"type": "string", "description": "Status: pendente, aprovada, paga, vencida, cancelada."},
    "search": {"type": "string", "description": "Busca por descrição do título."},
    "is_overdue": {"type": "boolean", "description": "Apenas títulos vencidos."},
    "skip": {"type": "integer"}, "limit": {"type": "integer"},
}}

_S_LIMIT = {"type": "object", "properties": {
    "limit": {"type": "integer", "description": "Máximo de registros (1-500)."},
}}

_S_PAGAMENTOS = {"type": "object", "properties": {
    "status": {"type": "string", "description": "Status do pagamento (ex.: preparado, aprovado, executado, cancelado)."},
    "payment_type": {"type": "string", "description": "Tipo (ex.: pix, boleto)."},
    "limit": {"type": "integer"},
}}


register(ToolDef("fin_dashboard", "financeiro",
                 "KPIs do dashboard financeiro (dados reais): saldo bancário consolidado, entradas e "
                 "saídas do mês, total a receber e a pagar. Visão do grupo.",
                 _NO_ARGS, _dashboard, scope_kind="org"))
register(ToolDef("fin_contas_a_receber", "financeiro",
                 "Lista contas a receber (títulos), com filtros (status, busca, só vencidas) e paginação. "
                 "Grupo consolidado. Vazio real = sem títulos, não fabrica.",
                 _S_RECEBER, _contas_a_receber, scope_kind="org"))
register(ToolDef("fin_contas_a_pagar", "financeiro",
                 "Lista contas a pagar (títulos), com filtros (status, busca, só vencidas) e paginação. "
                 "Grupo consolidado. READ-ONLY: só lista, não aprova nem paga.",
                 _S_PAGAR, _contas_a_pagar, scope_kind="org"))
register(ToolDef("fin_resumo_receber", "financeiro",
                 "Resumo/estatísticas de contas a receber (totais por situação: em aberto, vencido, pago). "
                 "Grupo consolidado, números reais.",
                 _NO_ARGS, _resumo_receber, scope_kind="org"))
register(ToolDef("fin_resumo_pagar", "financeiro",
                 "Resumo/estatísticas de contas a pagar (totais por situação: em aberto, vencido, pago). "
                 "Grupo consolidado, números reais.",
                 _NO_ARGS, _resumo_pagar, scope_kind="org"))
register(ToolDef("fin_inadimplencia", "financeiro",
                 "Títulos a receber VENCIDOS (inadimplência), do mais antigo ao mais recente. "
                 "Grupo consolidado. Sem vencidos = lista vazia real, não fabrica.",
                 _S_LIMIT, _inadimplencia, scope_kind="org"))
register(ToolDef("fin_saldos_bancos", "financeiro",
                 "Saldos das contas bancárias, uma linha por conta (Inter=Eletrônica, Cora=Patrimonial) — "
                 "sem misturar CNPJ. Dados reais das contas ativas.",
                 _NO_ARGS, _saldos_bancos, scope_kind="org"))
register(ToolDef("fin_listar_pagamentos", "financeiro",
                 "Lista pagamentos PIX (inter_payments) com filtros (status, tipo). READ-ONLY: só mostra "
                 "o que existe — NÃO prepara, aprova nem executa pagamento (isso é gate-OTP).",
                 _S_PAGAMENTOS, _listar_pagamentos, scope_kind="org"))
