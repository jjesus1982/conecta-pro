"""Schemas Pydantic para o módulo de Contabilidade."""

from datetime import date, datetime
from decimal import Decimal

from modules.financial.schemas._money import Money, MoneyOpt
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from modules.financial.models import (
    AccountClassification,
    AccountNature,
    AccountStatus,
    AccountType,
    AllocationMethod,
    BalancePeriod,
    BalanceStatus,
    BalanceType,
    ChartStandard,
    ChartStatus,
    ChartType,
    ClosingType,
    CostCenterStatus,
    CostCenterType,
    EntryOrigin,
    EntryStatus,
    EntryType,
    PeriodStatus,
    PeriodType,
    SpedAccountNature,
)

# ============================================================================
# Chart of Accounts Schemas
# ============================================================================


class ChartOfAccountsBase(BaseModel):
    """Schema base para ChartOfAccounts."""

    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    chart_type: ChartType = ChartType.STANDARD
    standard: ChartStandard = ChartStandard.CUSTOM
    version: str | None = Field(None, max_length=20)
    max_levels: int = Field(default=5, ge=1, le=10)
    account_mask: str | None = Field(None, max_length=50)
    separator: str | None = Field(".", max_length=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    sped_layout_code: str | None = Field(None, max_length=10)
    sped_version: str | None = Field(None, max_length=20)
    is_default: bool = False
    allow_modifications: bool = True
    notes: str | None = None


class ChartOfAccountsCreate(ChartOfAccountsBase):
    """Schema para criar ChartOfAccounts."""


class ChartOfAccountsUpdate(BaseModel):
    """Schema para atualizar ChartOfAccounts."""

    name: str | None = Field(None, max_length=100)
    description: str | None = None
    status: ChartStatus | None = None
    version: str | None = Field(None, max_length=20)
    valid_until: datetime | None = None
    is_default: bool | None = None
    allow_modifications: bool | None = None
    notes: str | None = None


class ChartOfAccountsResponse(ChartOfAccountsBase):
    """Schema de resposta para ChartOfAccounts."""

    id: UUID
    condominio_id: UUID
    status: ChartStatus
    version_date: datetime | None = None
    total_accounts: int = 0
    total_analytical: int = 0
    total_synthetic: int = 0
    active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class ChartOfAccountsListResponse(BaseModel):
    """Schema de lista de ChartOfAccounts."""

    items: list[ChartOfAccountsResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ============================================================================
# Accounting Account Schemas
# ============================================================================


class AccountingAccountBase(BaseModel):
    """Schema base para AccountingAccount."""

    chart_id: UUID
    parent_id: UUID | None = None
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=150)
    short_name: str | None = Field(None, max_length=50)
    description: str | None = None
    account_type: AccountType
    nature: AccountNature
    classification: AccountClassification
    level: int = Field(default=1, ge=1, le=10)
    order_index: int | None = None
    sped_nature: SpedAccountNature | None = None
    sped_referential_code: str | None = Field(None, max_length=30)
    default_cost_center_id: UUID | None = None
    requires_cost_center: bool = False
    requires_project: bool = False
    requires_history: bool = True
    allows_manual_entry: bool = True
    dre_group: str | None = Field(None, max_length=50)
    dre_order: int | None = None
    balance_sheet_group: str | None = Field(None, max_length=50)
    balance_sheet_order: int | None = None
    is_tax_related: bool = False
    is_bank_account: bool = False
    bank_account_id: UUID | None = None
    notes: str | None = None


class AccountingAccountCreate(AccountingAccountBase):
    """Schema para criar AccountingAccount."""

    opening_balance: Money = Field(default=Decimal("0"))


class AccountingAccountUpdate(BaseModel):
    """Schema para atualizar AccountingAccount."""

    name: str | None = Field(None, max_length=150)
    short_name: str | None = Field(None, max_length=50)
    description: str | None = None
    status: AccountStatus | None = None
    sped_nature: SpedAccountNature | None = None
    sped_referential_code: str | None = Field(None, max_length=30)
    default_cost_center_id: UUID | None = None
    requires_cost_center: bool | None = None
    requires_project: bool | None = None
    allows_manual_entry: bool | None = None
    dre_group: str | None = Field(None, max_length=50)
    dre_order: int | None = None
    notes: str | None = None


class AccountingAccountResponse(AccountingAccountBase):
    """Schema de resposta para AccountingAccount."""

    id: UUID
    condominio_id: UUID
    status: AccountStatus
    path: str | None = None
    opening_balance: Money = Decimal("0")
    current_balance: Money = Decimal("0")
    debit_total: Money = Decimal("0")
    credit_total: Money = Decimal("0")
    period_debit: Money = Decimal("0")
    period_credit: Money = Decimal("0")
    period_balance: Money = Decimal("0")
    last_movement_date: datetime | None = None
    is_system: bool = False
    active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class AccountingAccountListResponse(BaseModel):
    """Schema de lista de AccountingAccount."""

    items: list[AccountingAccountResponse]
    total: int
    page: int
    per_page: int
    pages: int


class AccountTreeResponse(BaseModel):
    """Schema para árvore de contas."""

    id: UUID
    code: str
    name: str
    account_type: AccountType
    nature: AccountNature
    classification: AccountClassification
    level: int
    current_balance: Money = Decimal("0")
    children: list["AccountTreeResponse"] = []

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


# ============================================================================
# Cost Center Schemas
# ============================================================================


class CostCenterBase(BaseModel):
    """Schema base para CostCenter."""

    parent_id: UUID | None = None
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    short_name: str | None = Field(None, max_length=30)
    description: str | None = None
    cost_center_type: CostCenterType = CostCenterType.ADMINISTRATIVE
    level: int = Field(default=1, ge=1, le=10)
    manager_id: UUID | None = None
    manager_name: str | None = Field(None, max_length=100)
    department: str | None = Field(None, max_length=100)
    budget_annual: Money = Field(default=Decimal("0"))
    budget_monthly: Money = Field(default=Decimal("0"))
    allocation_method: AllocationMethod = AllocationMethod.DIRECT
    allocation_percentage: Money = Field(default=Decimal("100"), ge=0, le=100)
    headcount: int = Field(default=0, ge=0)
    area_m2: Money = Field(default=Decimal("0"), ge=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_default: bool = False
    requires_approval: bool = False
    approval_limit: MoneyOpt = None
    allows_over_budget: bool = False
    notes: str | None = None


class CostCenterCreate(CostCenterBase):
    """Schema para criar CostCenter."""


class CostCenterUpdate(BaseModel):
    """Schema para atualizar CostCenter."""

    name: str | None = Field(None, max_length=100)
    short_name: str | None = Field(None, max_length=30)
    description: str | None = None
    status: CostCenterStatus | None = None
    manager_id: UUID | None = None
    manager_name: str | None = Field(None, max_length=100)
    department: str | None = Field(None, max_length=100)
    budget_annual: MoneyOpt = None
    budget_monthly: MoneyOpt = None
    allocation_percentage: MoneyOpt = Field(None, ge=0, le=100)
    headcount: int | None = Field(None, ge=0)
    area_m2: MoneyOpt = Field(None, ge=0)
    valid_until: datetime | None = None
    requires_approval: bool | None = None
    approval_limit: MoneyOpt = None
    notes: str | None = None


class CostCenterResponse(CostCenterBase):
    """Schema de resposta para CostCenter."""

    id: UUID
    condominio_id: UUID
    status: CostCenterStatus
    path: str | None = None
    order_index: int | None = None
    budget_used: Money = Decimal("0")
    budget_available: Money = Decimal("0")
    total_debit: Money = Decimal("0")
    total_credit: Money = Decimal("0")
    current_balance: Money = Decimal("0")
    period_debit: Money = Decimal("0")
    period_credit: Money = Decimal("0")
    last_movement_date: datetime | None = None
    active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class CostCenterListResponse(BaseModel):
    """Schema de lista de CostCenter."""

    items: list[CostCenterResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ============================================================================
# Accounting Period Schemas
# ============================================================================


class AccountingPeriodBase(BaseModel):
    """Schema base para AccountingPeriod."""

    chart_id: UUID | None = None
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    period_type: PeriodType = PeriodType.MONTHLY
    year: int = Field(..., ge=2000, le=2100)
    month: int | None = Field(None, ge=1, le=12)
    quarter: int | None = Field(None, ge=1, le=4)
    start_date: date
    end_date: date
    requires_approval: bool = True
    is_initial: bool = False
    is_adjustment: bool = False
    notes: str | None = None

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: date, info) -> date:
        """Valida que end_date é posterior a start_date."""
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date deve ser posterior a start_date")
        return v


class AccountingPeriodCreate(AccountingPeriodBase):
    """Schema para criar AccountingPeriod."""


class AccountingPeriodUpdate(BaseModel):
    """Schema para atualizar AccountingPeriod."""

    name: str | None = Field(None, max_length=100)
    description: str | None = None
    requires_approval: bool | None = None
    notes: str | None = None


class AccountingPeriodResponse(AccountingPeriodBase):
    """Schema de resposta para AccountingPeriod."""

    id: UUID
    condominio_id: UUID
    status: PeriodStatus
    opening_date: datetime | None = None
    closing_date: datetime | None = None
    closing_type: ClosingType | None = None
    total_entries: int = 0
    total_debit: Money = Decimal("0")
    total_credit: Money = Decimal("0")
    total_documents: int = 0
    opening_balance_total: Money = Decimal("0")
    closing_balance_total: Money = Decimal("0")
    period_revenue: Money = Decimal("0")
    period_expenses: Money = Decimal("0")
    period_result: Money = Decimal("0")
    closed_by: UUID | None = None
    sped_transmitted: bool = False
    allows_entries: bool = True
    active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class AccountingPeriodListResponse(BaseModel):
    """Schema de lista de AccountingPeriod."""

    items: list[AccountingPeriodResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PeriodCloseRequest(BaseModel):
    """Schema para fechar período."""

    closing_type: ClosingType = ClosingType.PROVISIONAL
    closing_notes: str | None = None


class PeriodReopenRequest(BaseModel):
    """Schema para reabrir período."""

    reopen_reason: str = Field(..., min_length=10, max_length=500)


# ============================================================================
# Journal Entry Schemas
# ============================================================================


class JournalEntryLineBase(BaseModel):
    """Schema base para JournalEntryLine."""

    account_id: UUID
    cost_center_id: UUID | None = None
    line_number: int = Field(..., ge=1)
    debit_amount: Money = Field(default=Decimal("0"), ge=0)
    credit_amount: Money = Field(default=Decimal("0"), ge=0)
    description: str | None = Field(None, max_length=500)
    history_code: str | None = Field(None, max_length=10)
    document_type: str | None = Field(None, max_length=30)
    document_number: str | None = Field(None, max_length=50)
    document_date: date | None = None
    project_id: UUID | None = None
    project_code: str | None = Field(None, max_length=30)

    @field_validator("credit_amount")
    @classmethod
    def validate_amounts(cls, v: Money, info) -> Decimal:
        """Valida que apenas um dos valores (débito ou crédito) é preenchido."""
        if "debit_amount" in info.data:
            if info.data["debit_amount"] > 0 and v > 0:
                raise ValueError("Apenas débito ou crédito pode ser preenchido, não ambos")
            if info.data["debit_amount"] == 0 and v == 0:
                raise ValueError("Débito ou crédito deve ser maior que zero")
        return v


class JournalEntryLineCreate(JournalEntryLineBase):
    """Schema para criar JournalEntryLine."""


class JournalEntryLineResponse(JournalEntryLineBase):
    """Schema de resposta para JournalEntryLine."""

    id: UUID
    journal_entry_id: UUID
    counterpart_account_id: UUID | None = None
    counterpart_account_code: str | None = None
    is_reconciled: bool = False
    reconciliation_date: datetime | None = None
    created_at: datetime

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class JournalEntryBase(BaseModel):
    """Schema base para JournalEntry."""

    period_id: UUID
    description: str = Field(..., min_length=1, max_length=500)
    complement: str | None = None
    entry_type: EntryType = EntryType.MANUAL
    origin: EntryOrigin = EntryOrigin.MANUAL
    entry_date: date
    competence_date: date
    source_type: str | None = Field(None, max_length=50)
    source_id: UUID | None = None
    source_number: str | None = Field(None, max_length=50)
    requires_approval: bool = False
    notes: str | None = None


class JournalEntryCreate(JournalEntryBase):
    """Schema para criar JournalEntry."""

    lines: list[JournalEntryLineCreate] = Field(..., min_length=2)

    @field_validator("lines")
    @classmethod
    def validate_balanced(cls, v: list[JournalEntryLineCreate]) -> list[JournalEntryLineCreate]:
        """Valida que o lançamento está balanceado."""
        total_debit = sum(line.debit_amount for line in v)
        total_credit = sum(line.credit_amount for line in v)
        if total_debit != total_credit:
            raise ValueError(f"Lançamento desbalanceado: Débito={total_debit}, Crédito={total_credit}")
        return v


class JournalEntryUpdate(BaseModel):
    """Schema para atualizar JournalEntry."""

    description: str | None = Field(None, max_length=500)
    complement: str | None = None
    competence_date: date | None = None
    notes: str | None = None


class JournalEntryResponse(JournalEntryBase):
    """Schema de resposta para JournalEntry."""

    id: UUID
    condominio_id: UUID
    entry_number: str
    batch_number: str | None = None
    status: EntryStatus
    total_debit: Money = Decimal("0")
    total_credit: Money = Decimal("0")
    line_count: int = 0
    posting_date: datetime | None = None
    is_reversal: bool = False
    reversed_entry_id: UUID | None = None
    reversal_entry_id: UUID | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    posted_by: UUID | None = None
    sped_included: bool = False
    is_balanced: bool = True
    active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None
    lines: list[JournalEntryLineResponse] = []

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class JournalEntryListResponse(BaseModel):
    """Schema de lista de JournalEntry."""

    items: list[JournalEntryResponse]
    total: int
    page: int
    per_page: int
    pages: int


class JournalEntryReversalRequest(BaseModel):
    """Schema para estornar lançamento."""

    reversal_reason: str = Field(..., min_length=10, max_length=200)
    reversal_date: date | None = None


class JournalEntryApprovalRequest(BaseModel):
    """Schema para aprovar/rejeitar lançamento."""

    approved: bool
    notes: str | None = Field(None, max_length=500)


# ============================================================================
# Trial Balance Schemas
# ============================================================================


class TrialBalanceBase(BaseModel):
    """Schema base para TrialBalance."""

    chart_id: UUID
    period_id: UUID | None = None
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None
    balance_type: BalanceType = BalanceType.VERIFICATION
    balance_period: BalancePeriod = BalancePeriod.MONTHLY
    reference_date: date
    start_date: date
    end_date: date
    year: int = Field(..., ge=2000, le=2100)
    month: int | None = Field(None, ge=1, le=12)
    include_zero_balance: bool = False
    include_inactive: bool = False
    show_cost_centers: bool = False
    notes: str | None = None


class TrialBalanceCreate(TrialBalanceBase):
    """Schema para criar TrialBalance."""

    filter_account_types: list[AccountType] | None = None
    filter_levels: list[int] | None = None
    filter_cost_centers: list[UUID] | None = None


class TrialBalanceResponse(TrialBalanceBase):
    """Schema de resposta para TrialBalance."""

    id: UUID
    condominio_id: UUID
    code: str
    status: BalanceStatus
    total_accounts: int = 0
    total_analytical: int = 0
    previous_debit_total: Money = Decimal("0")
    previous_credit_total: Money = Decimal("0")
    previous_balance_debit: Money = Decimal("0")
    previous_balance_credit: Money = Decimal("0")
    period_debit_total: Money = Decimal("0")
    period_credit_total: Money = Decimal("0")
    current_debit_total: Money = Decimal("0")
    current_credit_total: Money = Decimal("0")
    current_balance_debit: Money = Decimal("0")
    current_balance_credit: Money = Decimal("0")
    is_balanced: bool = True
    difference_amount: Money = Decimal("0")
    total_revenue: Money = Decimal("0")
    total_expenses: Money = Decimal("0")
    period_result: Money = Decimal("0")
    total_assets: Money = Decimal("0")
    total_liabilities: Money = Decimal("0")
    total_equity: Money = Decimal("0")
    generated_at: datetime | None = None
    generated_by: UUID | None = None
    generation_time_ms: int | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    exported_pdf: bool = False
    exported_excel: bool = False
    active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class TrialBalanceItemResponse(BaseModel):
    """Schema de resposta para TrialBalanceItem."""

    id: UUID
    trial_balance_id: UUID
    account_id: UUID
    account_code: str
    account_name: str
    account_type: str
    account_nature: str
    account_level: int
    is_analytical: bool
    cost_center_id: UUID | None = None
    cost_center_code: str | None = None
    cost_center_name: str | None = None
    previous_debit: Money = Decimal("0")
    previous_credit: Money = Decimal("0")
    previous_balance: Money = Decimal("0")
    period_debit: Money = Decimal("0")
    period_credit: Money = Decimal("0")
    current_debit: Money = Decimal("0")
    current_credit: Money = Decimal("0")
    current_balance: Money = Decimal("0")
    variation_absolute: MoneyOpt = None
    variation_percentage: MoneyOpt = None
    display_order: int | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class TrialBalanceListResponse(BaseModel):
    """Schema de lista de TrialBalance."""

    items: list[TrialBalanceResponse]
    total: int
    page: int
    per_page: int
    pages: int


class TrialBalanceDetailResponse(TrialBalanceResponse):
    """Schema detalhado de TrialBalance com itens."""

    items: list[TrialBalanceItemResponse] = []


# ============================================================================
# Statistics Schemas
# ============================================================================


class ChartStats(BaseModel):
    """Estatísticas do plano de contas."""

    total_charts: int = 0
    active_charts: int = 0
    total_accounts: int = 0
    analytical_accounts: int = 0
    synthetic_accounts: int = 0
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}


class AccountStats(BaseModel):
    """Estatísticas de contas contábeis."""

    total_accounts: int = 0
    active_accounts: int = 0
    by_type: dict[str, int] = {}
    by_nature: dict[str, int] = {}
    by_classification: dict[str, int] = {}
    total_balance: Money = Decimal("0")
    total_debit: Money = Decimal("0")
    total_credit: Money = Decimal("0")


class CostCenterStats(BaseModel):
    """Estatísticas de centros de custo."""

    total_cost_centers: int = 0
    active_cost_centers: int = 0
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    total_budget: Money = Decimal("0")
    total_used: Money = Decimal("0")
    budget_usage_percent: Money = Decimal("0")
    over_budget_count: int = 0


class PeriodStats(BaseModel):
    """Estatísticas de períodos contábeis."""

    total_periods: int = 0
    open_periods: int = 0
    closed_periods: int = 0
    by_status: dict[str, int] = {}
    total_entries: int = 0
    total_debit: Money = Decimal("0")
    total_credit: Money = Decimal("0")


class JournalStats(BaseModel):
    """Estatísticas de lançamentos contábeis."""

    total_entries: int = 0
    posted_entries: int = 0
    pending_entries: int = 0
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    total_debit: Money = Decimal("0")
    total_credit: Money = Decimal("0")
    entries_today: int = 0
    entries_this_month: int = 0


class BalanceStats(BaseModel):
    """Estatísticas de balancetes."""

    total_balances: int = 0
    generated: int = 0
    approved: int = 0
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    last_generated: datetime | None = None


# ============================================================================
# Filter Schemas
# ============================================================================


class AccountFilter(BaseModel):
    """Filtros para contas contábeis."""

    chart_id: UUID | None = None
    parent_id: UUID | None = None
    account_type: AccountType | None = None
    nature: AccountNature | None = None
    classification: AccountClassification | None = None
    status: AccountStatus | None = None
    level: int | None = None
    has_balance: bool | None = None
    search: str | None = None


class JournalFilter(BaseModel):
    """Filtros para lançamentos contábeis."""

    period_id: UUID | None = None
    entry_type: EntryType | None = None
    status: EntryStatus | None = None
    origin: EntryOrigin | None = None
    account_id: UUID | None = None
    cost_center_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_amount: MoneyOpt = None
    max_amount: MoneyOpt = None
    search: str | None = None


class BalanceFilter(BaseModel):
    """Filtros para balancetes."""

    balance_type: BalanceType | None = None
    status: BalanceStatus | None = None
    year: int | None = None
    month: int | None = None
    date_from: date | None = None
    date_to: date | None = None
