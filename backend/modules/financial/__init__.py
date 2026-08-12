"""
Module: financial
Description: Modulo Financeiro Completo - Conecta PRO
Author: Conecta PRO Team
Date: 2026-01-10

DEPRECATED: Use 'modules.financeiro' instead for router imports.
Deprecation date: 2026-03-11. Removal target: 2026-05-11.
"""

import warnings

warnings.warn(
    "Importing from 'modules.financial' is deprecated. "
    "Use 'modules.financeiro' for router access. "
    "This module will be removed after 2026-05-11.",
    DeprecationWarning,
    stacklevel=2,
)

from fastapi import APIRouter  # noqa: E402

# =============================================================================
# ROUTERS DOS CONTROLLERS PRINCIPAIS
# =============================================================================
from modules.financial.controllers import (  # noqa: E402
    # Contabilidade
    accounting_router,
    # Fluxo de Caixa
    bank_account_router,
    bank_reconciliation_router,
    bank_transaction_router,
    billing_rule_router,
    cashflow_router,
    # Contas a Receber
    customer_router,
    # Fiscal
    fiscal_router,
    # Estoque
    inventory_router,
    payable_router,
    # Compras
    purchase_router,
    receivable_category_router,
    receivable_router,
    # Contas a Pagar
    supplier_router,
)

# Models do Custeio
from modules.financial.costing.models import (  # noqa: E402
    CostActivity,
    CostAllocation,
    CostAnalysis,
    CostDriver,
    CostObject,
    CostPool,
)

# Repositories do Custeio
from modules.financial.costing.repositories import (  # noqa: E402
    CostActivityRepository,
    CostAllocationRepository,
    CostAnalysisRepository,
    CostDriverRepository,
    CostObjectRepository,
    CostPoolRepository,
)

# Services do Custeio
from modules.financial.costing.services import (  # noqa: E402
    ABCService,
    AllocationService,
    CostAIService,
)

# =============================================================================
# MODELS PRINCIPAIS (Re-exports para acesso direto)
# =============================================================================
from modules.financial.models import (  # noqa: E402
    CFOP,
    NCM,
    AccountingAccount,
    AccountingPeriod,
    # === Fluxo de Caixa ===
    BankAccount,
    BankAccountStatus,
    BankAccountType,
    BankReconciliation,
    BankTransaction,
    BillingRule,
    CashFlowEntry,
    CashFlowForecast,
    # === Contabilidade ===
    ChartOfAccounts,
    CostCenter,
    # === Contas a Receber ===
    Customer,
    CustomerStatus,
    CustomerType,
    FiscalObligation,
    GoodsReceipt,
    JournalEntry,
    NFe,
    NFSe,
    PayableAccount,
    PayableInstallment,
    PayablePayment,
    PayableStatus,
    PayableType,
    PaymentMethod,
    # === Compras ===
    Product,
    ProductCategory,
    PurchaseApproval,
    PurchaseOrder,
    PurchaseQuotation,
    PurchaseRequisition,
    ReceivableAccount,
    ReceivableInstallment,
    ReceivablePayment,
    ReceivableStatus,
    ReceivableType,
    SPEDFile,
    StockInventory,
    StockItem,
    StockMovement,
    StockReservation,
    # === Contas a Pagar ===
    Supplier,
    SupplierStatus,
    SupplierType,
    # === Fiscal ===
    TaxConfiguration,
    TransactionType,
    TrialBalance,
    # === Estoque ===
    Warehouse,
)

# =============================================================================
# REPOSITORIES PRINCIPAIS (Re-exports para acesso direto)
# =============================================================================
from modules.financial.repositories import (  # noqa: E402
    AccountingAccountRepository,
    AccountingPeriodRepository,
    # Fluxo de Caixa
    BankAccountRepository,
    BankReconciliationRepository,
    BankTransactionRepository,
    BillingRuleRepository,
    CashFlowEntryRepository,
    CashFlowForecastRepository,
    # Contabilidade
    ChartOfAccountsRepository,
    CostCenterRepository,
    # Contas a Receber
    CustomerRepository,
    # Fiscal
    FiscalRepository,
    GoodsReceiptRepository,
    JournalEntryRepository,
    PayableAccountRepository,
    PayableInstallmentRepository,
    PayablePaymentRepository,
    # Compras
    ProductCategoryRepository,
    ProductRepository,
    PurchaseApprovalRepository,
    PurchaseOrderRepository,
    PurchaseQuotationRepository,
    PurchaseRequisitionRepository,
    ReceivableAccountRepository,
    ReceivableCategoryRepository,
    ReceivableInstallmentRepository,
    ReceivablePaymentRepository,
    StockInventoryRepository,
    StockItemRepository,
    StockMovementRepository,
    StockReservationRepository,
    # Contas a Pagar
    SupplierRepository,
    TrialBalanceRepository,
    # Estoque
    WarehouseRepository,
)

# =============================================================================
# SERVICES PRINCIPAIS (Re-exports para acesso direto)
# =============================================================================
from modules.financial.services import (  # noqa: E402
    CashFlowAIService,
    # Fluxo de Caixa
    CashFlowService,
    # Fiscal
    FiscalAIService,
    PayableAIService,
    # Contas a Pagar
    PayableService,
    # Compras
    PurchaseAIService,
    SupplierService,
)

# =============================================================================
# ROUTER PRINCIPAL AGREGADOR
# =============================================================================

# Cria router principal que agrega todos os sub-routers
financial_router = APIRouter(prefix="/financial", tags=["Financial"])

# === Contas a Pagar ===
financial_router.include_router(supplier_router)
financial_router.include_router(payable_router)

# === Contas a Receber ===
financial_router.include_router(customer_router)
financial_router.include_router(receivable_category_router)
financial_router.include_router(receivable_router)
financial_router.include_router(billing_rule_router)

# === Fluxo de Caixa ===
financial_router.include_router(bank_account_router)
financial_router.include_router(bank_transaction_router)
financial_router.include_router(bank_reconciliation_router)
financial_router.include_router(cashflow_router)

# === Compras ===
financial_router.include_router(purchase_router)

# === Estoque ===
financial_router.include_router(inventory_router)

# === Contabilidade ===
financial_router.include_router(accounting_router)

# === Fiscal ===
financial_router.include_router(fiscal_router)

# === Custeio ABC ===

# Alias para compatibilidade
router = financial_router

# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # =========================================================================
    # ROUTERS
    # =========================================================================
    "financial_router",
    "router",
    # Routers individuais - Contas a Pagar
    "supplier_router",
    "payable_router",
    # Routers individuais - Contas a Receber
    "customer_router",
    "receivable_category_router",
    "receivable_router",
    "billing_rule_router",
    # Routers individuais - Fluxo de Caixa
    "bank_account_router",
    "bank_transaction_router",
    "bank_reconciliation_router",
    "cashflow_router",
    # Routers individuais - Compras/Estoque
    "purchase_router",
    "inventory_router",
    # Routers individuais - Contabilidade/Fiscal
    "accounting_router",
    "fiscal_router",
    # Routers submodulos
    # =========================================================================
    # MODELS - Contas a Pagar
    # =========================================================================
    "Supplier",
    "SupplierType",
    "SupplierStatus",
    "PayableAccount",
    "PayableStatus",
    "PayableType",
    "PayableInstallment",
    "PayablePayment",
    "PaymentMethod",
    # =========================================================================
    # MODELS - Contas a Receber
    # =========================================================================
    "Customer",
    "CustomerType",
    "CustomerStatus",
    "ReceivableAccount",
    "ReceivableStatus",
    "ReceivableType",
    "ReceivableInstallment",
    "ReceivablePayment",
    "BillingRule",
    # =========================================================================
    # MODELS - Fluxo de Caixa
    # =========================================================================
    "BankAccount",
    "BankAccountType",
    "BankAccountStatus",
    "BankTransaction",
    "TransactionType",
    "BankReconciliation",
    "CashFlowEntry",
    "CashFlowForecast",
    # =========================================================================
    # MODELS - Compras
    # =========================================================================
    "Product",
    "ProductCategory",
    "PurchaseRequisition",
    "PurchaseQuotation",
    "PurchaseOrder",
    "GoodsReceipt",
    "PurchaseApproval",
    # =========================================================================
    # MODELS - Estoque
    # =========================================================================
    "Warehouse",
    "StockItem",
    "StockMovement",
    "StockInventory",
    "StockReservation",
    # =========================================================================
    # MODELS - Contabilidade
    # =========================================================================
    "ChartOfAccounts",
    "AccountingAccount",
    "CostCenter",
    "AccountingPeriod",
    "JournalEntry",
    "TrialBalance",
    # =========================================================================
    # MODELS - Fiscal
    # =========================================================================
    "TaxConfiguration",
    "NFe",
    "NFSe",
    "SPEDFile",
    "FiscalObligation",
    "CFOP",
    "NCM",
    # =========================================================================
    # MODELS - Custeio ABC
    # =========================================================================
    "CostDriver",
    "CostActivity",
    "CostPool",
    "CostObject",
    "CostAllocation",
    "CostAnalysis",
    # =========================================================================
    # SERVICES - Principais
    # =========================================================================
    "PayableService",
    "SupplierService",
    "PayableAIService",
    "CashFlowService",
    "CashFlowAIService",
    "PurchaseAIService",
    "FiscalAIService",
    # =========================================================================
    # SERVICES - Custeio ABC
    # =========================================================================
    "ABCService",
    "AllocationService",
    "CostAIService",
    # =========================================================================
    # REPOSITORIES - Contas a Pagar
    # =========================================================================
    "SupplierRepository",
    "PayableAccountRepository",
    "PayableInstallmentRepository",
    "PayablePaymentRepository",
    # =========================================================================
    # REPOSITORIES - Contas a Receber
    # =========================================================================
    "CustomerRepository",
    "ReceivableCategoryRepository",
    "ReceivableAccountRepository",
    "ReceivableInstallmentRepository",
    "ReceivablePaymentRepository",
    "BillingRuleRepository",
    # =========================================================================
    # REPOSITORIES - Fluxo de Caixa
    # =========================================================================
    "BankAccountRepository",
    "BankTransactionRepository",
    "BankReconciliationRepository",
    "CashFlowEntryRepository",
    "CashFlowForecastRepository",
    # =========================================================================
    # REPOSITORIES - Compras
    # =========================================================================
    "ProductCategoryRepository",
    "ProductRepository",
    "PurchaseRequisitionRepository",
    "PurchaseQuotationRepository",
    "PurchaseOrderRepository",
    "GoodsReceiptRepository",
    "PurchaseApprovalRepository",
    # =========================================================================
    # REPOSITORIES - Estoque
    # =========================================================================
    "WarehouseRepository",
    "StockItemRepository",
    "StockMovementRepository",
    "StockInventoryRepository",
    "StockReservationRepository",
    # =========================================================================
    # REPOSITORIES - Contabilidade
    # =========================================================================
    "ChartOfAccountsRepository",
    "AccountingAccountRepository",
    "CostCenterRepository",
    "AccountingPeriodRepository",
    "JournalEntryRepository",
    "TrialBalanceRepository",
    # =========================================================================
    # REPOSITORIES - Fiscal
    # =========================================================================
    "FiscalRepository",
    # =========================================================================
    # REPOSITORIES - Custeio ABC
    # =========================================================================
    "CostDriverRepository",
    "CostActivityRepository",
    "CostPoolRepository",
    "CostObjectRepository",
    "CostAllocationRepository",
    "CostAnalysisRepository",
]

__version__ = "1.0.0"
