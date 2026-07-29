"""
Módulo FINANCEIRO — Agregador
Unifica: financial (completo)

Routers re-exportados dos módulos de implementação.
API URLs inalteradas.
Data migração: 2026-03-11

Controle de acesso por módulo (§92 — CPRO12 T1-PERMISSOES):
  - financeiro: apenas Jordan Jesus (INV-4)
  - fiscal: Jordan + Pyetra Jesus
"""

from core.permissions import requer_modulo

# --- Financial Core ---
from modules.financial.controllers import (
    accounting_router,
    bank_account_router,
    bank_reconciliation_router,
    bank_transaction_router,
    billing_rule_router,
    cashflow_router,
    customer_router,
    financial_ai_router,
    fiscal_router,
    inventory_router,
    payable_router,
    purchase_router,
    receivable_category_router,
    receivable_router,
    relatorios_router,
    supplier_router,
)

# --- NFS-e Entrada + Fiscal Stats + Conciliacao + Custos ---
try:
    from modules.financial.controllers.nfse_entrada_controller import (
        router as nfse_entrada_router,
    )
except Exception:
    nfse_entrada_router = None

# --- Proteção por módulo (aplicada antes do include_router em main_production.py) ---
# FastAPI 0.115.6: include_router NÃO propaga router.dependencies — apenas route.dependencies.
# Solução: injetar a dependency em CADA ROTA individual dos routers.
# INV-4: financeiro = apenas Jordan
_dep_financeiro = requer_modulo("financeiro")
_dep_fiscal = requer_modulo("fiscal")

_routers_financeiro = [
    accounting_router,
    bank_account_router,
    bank_reconciliation_router,
    bank_transaction_router,
    billing_rule_router,
    cashflow_router,
    customer_router,
    financial_ai_router,
    inventory_router,
    payable_router,
    purchase_router,
    receivable_category_router,
    receivable_router,
    relatorios_router,
    supplier_router,
]
if nfse_entrada_router:
    _routers_financeiro.append(nfse_entrada_router)

for _r in _routers_financeiro:
    for _route in _r.routes:
        _route.dependencies.append(_dep_financeiro)

# fiscal: Jordan + Pyetra (module:fiscal)
for _route in fiscal_router.routes:
    _route.dependencies.append(_dep_fiscal)

__all__ = [
    "accounting_router",
    "supplier_router",
    "payable_router",
    "customer_router",
    "receivable_category_router",
    "receivable_router",
    "billing_rule_router",
    "bank_account_router",
    "bank_transaction_router",
    "bank_reconciliation_router",
    "cashflow_router",
    "purchase_router",
    "inventory_router",
    "fiscal_router",
    "financial_ai_router",
    "relatorios_router",
    "nfse_entrada_router",
]
