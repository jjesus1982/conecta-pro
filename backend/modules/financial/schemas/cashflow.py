"""Schemas Pydantic para Fluxo de Caixa."""

from datetime import date, datetime
from decimal import Decimal

from modules.financial.schemas._money import Money, MoneyOpt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ===================== BANK ACCOUNT =====================


class BankAccountBase(BaseModel):
    """Schema base para conta bancaria."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    bank_code: str = Field(..., min_length=1, max_length=10)
    bank_name: str = Field(..., min_length=1, max_length=100)
    agency: str = Field(..., min_length=1, max_length=10)
    agency_digit: str | None = Field(None, max_length=2)
    account_number: str = Field(..., min_length=1, max_length=20)
    account_digit: str = Field(..., min_length=1, max_length=2)
    account_type: str = Field(default="corrente")
    holder_name: str | None = Field(None, max_length=150)
    holder_document: str | None = Field(None, max_length=20)


class BankAccountCreate(BankAccountBase):
    """Schema para criacao de conta bancaria."""

    condominio_id: UUID
    opening_balance: Money = Field(default=Decimal("0"))
    opening_date: date | None = None
    pix_enabled: bool = False
    pix_key: str | None = None
    pix_key_type: str | None = None
    boleto_enabled: bool = False
    boleto_wallet: str | None = None
    boleto_agreement: str | None = None
    is_main_account: bool = False


class BankAccountUpdate(BaseModel):
    """Schema para atualizacao de conta bancaria."""

    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=500)
    holder_name: str | None = Field(None, max_length=150)
    holder_document: str | None = Field(None, max_length=20)
    pix_enabled: bool | None = None
    pix_key: str | None = None
    pix_key_type: str | None = None
    boleto_enabled: bool | None = None
    boleto_wallet: str | None = None
    boleto_agreement: str | None = None
    is_main_account: bool | None = None
    allow_negative_balance: bool | None = None
    overdraft_limit: MoneyOpt = None
    minimum_balance: MoneyOpt = None
    bank_manager_name: str | None = None
    bank_manager_phone: str | None = None
    bank_manager_email: str | None = None
    notes: str | None = None


class BankAccountResponse(BankAccountBase):
    """Schema de resposta para conta bancaria."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condominio_id: UUID
    status: str
    opening_balance: Money
    current_balance: Money
    available_balance: Money
    blocked_balance: Money
    pix_enabled: bool
    pix_key: str | None
    boleto_enabled: bool
    is_main_account: bool
    opening_date: date | None
    last_balance_update: datetime | None
    created_at: datetime
    ativo: bool


class BankAccountFilter(BaseModel):
    """Filtros para busca de contas bancarias."""

    condominio_id: UUID | None = None
    status: str | None = None
    account_type: str | None = None
    bank_code: str | None = None
    is_main_account: bool | None = None
    is_main: bool | None = None  # alias usado pelo controller
    pix_enabled: bool | None = None
    boleto_enabled: bool | None = None


class BankAccountStats(BaseModel):
    """Estatisticas de contas bancarias."""

    total_accounts: int = 0
    active_accounts: int = 0
    total_balance: Money = Decimal("0")
    total_available: Money = Decimal("0")
    total_blocked: Money = Decimal("0")
    accounts_with_pix: int = 0
    accounts_with_boleto: int = 0


# ===================== BANK TRANSACTION =====================


class BankTransactionBase(BaseModel):
    """Schema base para movimentacao bancaria."""

    transaction_type: str
    category: str = "nao_identificado"
    amount: Money
    description: str = Field(..., min_length=1, max_length=500)
    memo: str | None = None
    transaction_date: date
    competence_date: date | None = None


class BankTransactionCreate(BankTransactionBase):
    """Schema para criacao de movimentacao."""

    bank_account_id: UUID
    document_number: str | None = None
    reference: str | None = None
    counterparty_name: str | None = None
    counterparty_document: str | None = None
    pix_key: str | None = None
    barcode: str | None = None


class BankTransactionUpdate(BaseModel):
    """Schema para atualizacao de movimentacao."""

    category: str | None = None
    description: str | None = Field(None, max_length=500)
    memo: str | None = None
    competence_date: date | None = None
    counterparty_name: str | None = None
    counterparty_document: str | None = None


class BankTransactionResponse(BankTransactionBase):
    """Schema de resposta para movimentacao."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bank_account_id: UUID
    status: str
    balance_before: MoneyOpt
    balance_after: MoneyOpt
    origin: str
    source_type: str | None
    reconciliation_status: str
    external_id: str | None
    document_number: str | None
    counterparty_name: str | None
    is_transfer: bool
    is_reversal: bool
    created_at: datetime


class BankTransactionFilter(BaseModel):
    """Filtros para busca de movimentacoes."""

    transaction_type: str | None = None
    category: str | None = None
    status: str | None = None
    reconciliation_status: str | None = None
    origin: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    min_amount: MoneyOpt = None
    max_amount: MoneyOpt = None
    counterparty_name: str | None = None


class BankTransactionImport(BaseModel):
    """Schema para importacao de extrato."""

    bank_account_id: UUID
    file_format: str = Field(..., pattern="^(ofx|cnab|csv)$")
    transactions: list[dict[str, Any]]


class TransferRequest(BaseModel):
    """Schema para transferencia entre contas."""

    source_account_id: UUID
    destination_account_id: UUID
    amount: Money = Field(..., gt=0)
    description: str = Field(..., min_length=1, max_length=500)
    transaction_date: date
    competence_date: date | None = None


# ===================== BANK RECONCILIATION =====================


class BankReconciliationBase(BaseModel):
    """Schema base para conciliacao."""

    reference: str | None = Field(None, max_length=50)
    description: str | None = None
    period_type: str = "mensal"
    period_start: date
    period_end: date


class BankReconciliationCreate(BankReconciliationBase):
    """Schema para criacao de conciliacao."""

    bank_account_id: UUID
    condominio_id: UUID
    system_opening_balance: Money


class BankReconciliationUpdate(BaseModel):
    """Schema para atualizacao de conciliacao."""

    bank_opening_balance: MoneyOpt = None
    bank_closing_balance: MoneyOpt = None
    notes: str | None = None


class BankReconciliationResponse(BankReconciliationBase):
    """Schema de resposta para conciliacao."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bank_account_id: UUID
    condominio_id: UUID | None = None
    status: str
    system_opening_balance: Money
    system_closing_balance: MoneyOpt
    bank_opening_balance: MoneyOpt
    bank_closing_balance: MoneyOpt
    closing_difference: Money
    reconciliation_progress: Money
    reconciled_count: int
    pending_system_count: int
    pending_bank_count: int
    divergent_count: int
    statement_imported: bool
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class BankReconciliationFilter(BaseModel):
    """Schema para filtros de listagem de conciliacoes."""

    bank_account_id: UUID | None = None
    condominio_id: UUID | None = None
    status: str | None = None
    period_type: str | None = None
    period_start_from: date | None = None
    period_start_to: date | None = None


class ReconciliationItemMatch(BaseModel):
    """Schema para conciliar item."""

    system_transaction_id: UUID
    bank_transaction_id: UUID | None = None
    note: str | None = None


class ReconciliationAdjustment(BaseModel):
    """Schema para ajuste de conciliacao."""

    adjustment_type: str = Field(..., pattern="^(credito|debito)$")
    amount: Money = Field(..., gt=0)
    description: str = Field(..., min_length=1, max_length=500)


class StatementImport(BaseModel):
    """Schema para importacao de extrato."""

    reconciliation_id: UUID
    file_name: str
    file_format: str = Field(..., pattern="^(ofx|cnab|csv|pdf)$")
    transactions: list[dict[str, Any]]


# ===================== CASHFLOW ENTRY =====================


class CashFlowEntryBase(BaseModel):
    """Schema base para lancamento de fluxo de caixa."""

    entry_type: str
    description: str = Field(..., min_length=1, max_length=500)
    memo: str | None = None
    expected_amount: Money = Field(..., gt=0)
    entry_date: date
    competence_date: date | None = None
    due_date: date | None = None


class CashFlowEntryCreate(CashFlowEntryBase):
    """Schema para criacao de lancamento."""

    condominio_id: UUID
    bank_account_id: UUID | None = None
    payable_category_id: UUID | None = None
    receivable_category_id: UUID | None = None
    counterparty_name: str | None = None
    is_recurring: bool = False
    recurrence_frequency: str | None = None
    recurrence_start: date | None = None
    recurrence_end: date | None = None
    recurrence_count: int | None = None
    tags: list[str] = Field(default_factory=list)


class CashFlowEntryUpdate(BaseModel):
    """Schema para atualizacao de lancamento."""

    description: str | None = Field(None, max_length=500)
    memo: str | None = None
    expected_amount: MoneyOpt = Field(None, gt=0)
    entry_date: date | None = None
    due_date: date | None = None
    bank_account_id: UUID | None = None
    counterparty_name: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


class CashFlowEntryResponse(CashFlowEntryBase):
    """Schema de resposta para lancamento."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condominio_id: UUID
    bank_account_id: UUID | None
    source_type: str
    status: str
    realized_amount: MoneyOpt
    realized_date: date | None
    difference: MoneyOpt
    is_recurring: bool
    counterparty_name: str | None
    tags: list[str] | None = None
    is_approved: bool
    created_at: datetime


class CashFlowEntryFilter(BaseModel):
    """Filtros para busca de lancamentos."""

    condominio_id: UUID | None = None
    entry_type: str | None = None
    source_type: str | None = None
    status: str | None = None
    bank_account_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    min_amount: MoneyOpt = None
    max_amount: MoneyOpt = None
    is_recurring: bool | None = None
    is_overdue: bool | None = None


class CashFlowEntryRealize(BaseModel):
    """Schema para realizar lancamento."""

    realized_amount: Money = Field(..., gt=0)
    realized_date: date
    bank_transaction_id: UUID | None = None


# ===================== CASHFLOW FORECAST =====================


class CashFlowForecastBase(BaseModel):
    """Schema base para previsao."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    reference: str | None = Field(None, max_length=50)
    period_type: str = "mensal"
    period_start: date
    period_end: date
    forecast_date: date


class CashFlowForecastCreate(CashFlowForecastBase):
    """Schema para criacao de previsao."""

    condominio_id: UUID
    expected_opening_balance: Money = Decimal("0")
    expected_receivables: Money = Decimal("0")
    expected_other_income: Money = Decimal("0")
    expected_payables: Money = Decimal("0")
    expected_other_expenses: Money = Decimal("0")
    assumptions: list[str] = Field(default_factory=list)
    target_balance: MoneyOpt = None


class CashFlowForecastUpdate(BaseModel):
    """Schema para atualizacao de previsao."""

    name: str | None = Field(None, max_length=100)
    description: str | None = None
    expected_receivables: MoneyOpt = None
    expected_other_income: MoneyOpt = None
    expected_payables: MoneyOpt = None
    expected_other_expenses: MoneyOpt = None
    assumptions: list[str] | None = None
    target_balance: MoneyOpt = None
    notes: str | None = None


class CashFlowForecastResponse(CashFlowForecastBase):
    """Schema de resposta para previsao."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condominio_id: UUID
    status: str
    expected_inflows: Money
    expected_outflows: Money
    expected_opening_balance: Money
    expected_closing_balance: Money
    expected_net_flow: Money
    actual_inflows: MoneyOpt
    actual_outflows: MoneyOpt
    actual_closing_balance: MoneyOpt
    balance_variance: MoneyOpt
    confidence_level: int
    confidence_category: str
    ai_generated: bool
    has_negative_balance_alert: bool
    risks: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    created_at: datetime


class CashFlowForecastFilter(BaseModel):
    """Filtros para busca de previsoes."""

    condominio_id: UUID | None = None
    status: str | None = None
    period_type: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    ai_generated: bool | None = None
    has_alerts: bool | None = None
    confidence: str | None = None  # campo passado pelo controller


class ForecastActualsUpdate(BaseModel):
    """Schema para atualizar valores realizados."""

    actual_inflows: Money
    actual_outflows: Money
    actual_opening_balance: Money
    actual_closing_balance: Money


class ForecastRisk(BaseModel):
    """Schema para adicionar risco."""

    risk_type: str = Field(..., max_length=50)
    probability: float = Field(..., ge=0, le=1)
    impact: Money = Field(..., gt=0)
    mitigation: str = Field(..., max_length=500)


class ForecastOpportunity(BaseModel):
    """Schema para adicionar oportunidade."""

    opportunity_type: str = Field(..., max_length=50)
    probability: float = Field(..., ge=0, le=1)
    value: Money = Field(..., gt=0)
    action: str = Field(..., max_length=500)


# ===================== PROJECTIONS & ANALYTICS =====================


class CashFlowProjection(BaseModel):
    """Projecao de fluxo de caixa."""

    date: date
    payables: Money = Decimal("0")
    receivables: Money = Decimal("0")
    balance: Money = Decimal("0")
    cumulative_balance: Money = Decimal("0")
    details: list[dict[str, Any]] = Field(default_factory=list)


class CashFlowSummary(BaseModel):
    """Resumo de fluxo de caixa."""

    period_start: date
    period_end: date
    opening_balance: Money
    closing_balance: Money
    total_inflows: Money
    total_outflows: Money
    net_flow: Money
    inflows_by_category: dict[str, Decimal]
    outflows_by_category: dict[str, Decimal]
    pending_receivables: Money
    pending_payables: Money
    overdue_receivables: Money
    overdue_payables: Money


class CashFlowTrend(BaseModel):
    """Tendencia de fluxo de caixa."""

    period: str
    inflows: Money
    outflows: Money
    net_flow: Money
    balance: Money
    variance_pct: float | None = None


class CashFlowDashboard(BaseModel):
    """Dashboard de fluxo de caixa."""

    summary: CashFlowSummary
    trends: list[CashFlowTrend]
    projections: list[CashFlowProjection]
    accounts: list[BankAccountResponse]
    alerts: list[dict[str, Any]]
    upcoming_payables: int
    upcoming_receivables: int
    overdue_payables: int
    overdue_receivables: int


# ===================== AI ANALYSIS =====================


class AIForecastRequest(BaseModel):
    """Request para previsao por IA."""

    condominio_id: UUID
    months_ahead: int = Field(default=3, ge=1, le=12)
    include_scenarios: bool = True
    confidence_threshold: int = Field(default=70, ge=0, le=100)


class AIForecastResponse(BaseModel):
    """Resposta de previsao por IA."""

    forecast: CashFlowForecastResponse
    scenarios: dict[str, dict[str, Decimal]]
    confidence_factors: dict[str, float]
    recommendations: list[str]
    risks: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]


class AnomalyDetectionRequest(BaseModel):
    """Request para deteccao de anomalias."""

    condominio_id: UUID
    period_months: int = Field(default=6, ge=3, le=12)
    sensitivity: str = Field(default="medium", pattern="^(low|medium|high)$")


class AnomalyDetectionResponse(BaseModel):
    """Resposta de deteccao de anomalias."""

    anomalies: list[dict[str, Any]]
    total: int
    by_severity: dict[str, int]
    by_category: dict[str, int]


class OptimizationSuggestion(BaseModel):
    """Sugestao de otimizacao."""

    id: str
    type: str
    title: str
    description: str
    potential_savings: Money
    implementation_effort: str
    priority: str
    action_items: list[str]
