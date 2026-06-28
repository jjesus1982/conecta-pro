"""Schemas para contas a receber."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.financial.models.billing_rule import (
    BillingFrequency,
    BillingRuleStatus,
    BillingType,
)
from modules.financial.models.customer import CustomerStatus, CustomerType
from modules.financial.models.receivable_account import (
    ReceivablePriority,
    ReceivableStatus,
    ReceivableType,
)
from modules.financial.models.receivable_category import CategoryType
from modules.financial.models.receivable_installment import InstallmentStatus
from modules.financial.models.receivable_payment import PaymentOrigin, PaymentStatus

# ============= Customer =============


class CustomerBase(BaseModel):
    """Base para cliente."""

    cpf_cnpj: str = Field(..., min_length=11, max_length=20)
    name: str = Field(..., min_length=2, max_length=200)
    trade_name: str | None = Field(None, max_length=200)
    customer_type: CustomerType = CustomerType.MORADOR

    # Vinculacao
    morador_id: UUID | None = None
    unidade_id: UUID | None = None

    # Contato
    email: str | None = Field(None, max_length=200)
    email_secondary: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=20)
    phone_secondary: str | None = Field(None, max_length=20)
    whatsapp: str | None = Field(None, max_length=20)

    # Endereco
    address_street: str | None = Field(None, max_length=200)
    address_number: str | None = Field(None, max_length=20)
    address_complement: str | None = Field(None, max_length=100)
    address_neighborhood: str | None = Field(None, max_length=100)
    address_city: str | None = Field(None, max_length=100)
    address_state: str | None = Field(None, max_length=2)
    address_zipcode: str | None = Field(None, max_length=10)

    # Financeiro
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0)

    # Cobranca
    billing_email: str | None = Field(None, max_length=200)
    billing_day: int | None = Field(None)
    auto_billing: bool = True

    # Notificacoes
    notify_email: bool = True
    notify_sms: bool = False
    notify_whatsapp: bool = True
    notify_push: bool = True

    notes: str | None = None


class CustomerCreate(CustomerBase):
    """Schema para criacao de cliente."""

    condominio_id: UUID


class CustomerUpdate(BaseModel):
    """Schema para atualizacao de cliente."""

    name: str | None = Field(None, min_length=2, max_length=200)
    trade_name: str | None = Field(None, max_length=200)
    customer_type: CustomerType | None = None

    morador_id: UUID | None = None
    unidade_id: UUID | None = None

    email: str | None = Field(None, max_length=200)
    email_secondary: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=20)
    phone_secondary: str | None = Field(None, max_length=20)
    whatsapp: str | None = Field(None, max_length=20)

    address_street: str | None = Field(None, max_length=200)
    address_number: str | None = Field(None, max_length=20)
    address_complement: str | None = Field(None, max_length=100)
    address_neighborhood: str | None = Field(None, max_length=100)
    address_city: str | None = Field(None, max_length=100)
    address_state: str | None = Field(None, max_length=2)
    address_zipcode: str | None = Field(None, max_length=10)

    credit_limit: Decimal | None = Field(None, ge=0)
    billing_email: str | None = Field(None, max_length=200)
    billing_day: int | None = Field(None)
    auto_billing: bool | None = None

    notify_email: bool | None = None
    notify_sms: bool | None = None
    notify_whatsapp: bool | None = None
    notify_push: bool | None = None

    notes: str | None = None


class CustomerResponse(CustomerBase):
    """Schema de resposta para cliente."""

    id: UUID
    condominio_id: UUID
    status: CustomerStatus

    total_debt: Decimal
    overdue_debt: Decimal
    available_credit: float
    is_inadimplente: bool

    is_blocked: bool
    blocked_reason: str | None = None
    blocked_at: datetime | None = None

    display_name: str
    formatted_cpf_cnpj: str

    created_at: datetime
    updated_at: datetime | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class CustomerFilter(BaseModel):
    """Filtros para busca de clientes."""

    search: str | None = None
    customer_type: CustomerType | None = None
    status: CustomerStatus | None = None
    is_inadimplente: bool | None = None
    is_blocked: bool | None = None
    unidade_id: UUID | None = None


# ============= ReceivableCategory =============


class ReceivableCategoryCreate(BaseModel):
    """Schema para criacao de categoria."""

    condominio_id: UUID
    code: str | None = Field(None, max_length=20)
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    category_type: CategoryType = CategoryType.OUTROS
    parent_id: UUID | None = None

    accounting_code: str | None = Field(None, max_length=30)
    cost_center: str | None = Field(None, max_length=30)

    apply_interest: bool = True
    interest_rate: str = "1.00"
    apply_penalty: bool = True
    penalty_rate: str = "2.00"
    grace_days: int = Field(default=0, ge=0)

    display_order: int = 0


class ReceivableCategoryUpdate(BaseModel):
    """Schema para atualizacao de categoria."""

    code: str | None = Field(None, max_length=20)
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = None
    category_type: CategoryType | None = None
    parent_id: UUID | None = None

    accounting_code: str | None = Field(None, max_length=30)
    cost_center: str | None = Field(None, max_length=30)

    apply_interest: bool | None = None
    interest_rate: str | None = None
    apply_penalty: bool | None = None
    penalty_rate: str | None = None
    grace_days: int | None = Field(None, ge=0)

    display_order: int | None = None


class ReceivableCategoryResponse(BaseModel):
    """Schema de resposta para categoria."""

    id: UUID
    condominio_id: UUID
    code: str | None = None
    name: str
    description: str | None = None
    category_type: str
    parent_id: UUID | None = None
    full_name: str

    accounting_code: str | None = None
    cost_center: str | None = None

    apply_interest: bool
    interest_rate: str
    apply_penalty: bool
    penalty_rate: str
    grace_days: int

    display_order: int
    has_children: bool
    ativo: bool

    created_at: datetime

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


# ============= ReceivableAccount =============


class ReceivableAccountBase(BaseModel):
    """Base para conta a receber."""

    description: str = Field(..., min_length=3, max_length=500)
    document_number: str | None = Field(None, max_length=50)
    receivable_type: ReceivableType = ReceivableType.AVULSA
    priority: ReceivablePriority = ReceivablePriority.MEDIA

    customer_id: UUID | None = None
    unidade_id: UUID | None = None
    morador_id: UUID | None = None
    category_id: UUID | None = None

    gross_value: Decimal = Field(..., gt=0)
    discount_value: Decimal = Field(default=Decimal("0"), ge=0)
    addition_value: Decimal = Field(default=Decimal("0"), ge=0)

    # Juros e multa
    interest_rate: Decimal = Field(default=Decimal("1"), ge=0)
    penalty_rate: Decimal = Field(default=Decimal("2"), ge=0)
    grace_days: int = Field(default=0, ge=0)

    # Datas
    issue_date: date | None = None
    due_date: date
    competence_date: date | None = None

    # Parcelamento
    total_installments: int = Field(default=1, ge=1, le=360)

    # Recorrencia
    is_recurring: bool = False
    recurrence_type: str | None = None
    recurrence_end_date: date | None = None

    # Centro de custo
    cost_center: str | None = Field(None, max_length=50)

    # Tags e notas
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class ReceivableAccountCreate(ReceivableAccountBase):
    """Schema para criacao de conta a receber."""

    condominio_id: UUID

    # Boleto/PIX automatico
    generate_boleto: bool = False
    generate_pix: bool = False


class ReceivableAccountUpdate(BaseModel):
    """Schema para atualizacao de conta a receber."""

    description: str | None = Field(None, min_length=3, max_length=500)
    document_number: str | None = Field(None, max_length=50)
    priority: ReceivablePriority | None = None

    customer_id: UUID | None = None
    category_id: UUID | None = None

    gross_value: Decimal | None = Field(None, gt=0)
    discount_value: Decimal | None = Field(None, ge=0)
    addition_value: Decimal | None = Field(None, ge=0)

    interest_rate: Decimal | None = Field(None, ge=0)
    penalty_rate: Decimal | None = Field(None, ge=0)
    grace_days: int | None = Field(None, ge=0)

    due_date: date | None = None
    competence_date: date | None = None

    cost_center: str | None = Field(None, max_length=50)
    tags: list[str] | None = None
    notes: str | None = None


class ReceivableAccountResponse(ReceivableAccountBase):
    """Schema de resposta para conta a receber."""

    id: UUID
    condominio_id: UUID
    code: str | None = None
    status: ReceivableStatus
    net_value: Decimal
    paid_value: Decimal
    remaining_value: Decimal | None = None
    interest_value: Decimal
    penalty_value: Decimal

    entry_date: date
    payment_date: date | None = None

    current_installment: int
    parent_id: UUID | None = None

    boleto_generated: bool
    boleto_number: str | None = None
    boleto_url: str | None = None
    pix_generated: bool
    pix_copy_paste: str | None = None

    collection_attempts: int
    last_collection_date: datetime | None = None

    is_protested: bool
    is_in_agreement: bool
    is_written_off: bool

    is_overdue: bool
    days_overdue: int
    days_until_due: int
    payment_percentage: float
    balance: Decimal
    current_total_value: Decimal

    attachments: list[dict] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class ReceivableAccountListResponse(BaseModel):
    """Schema de lista de contas a receber."""

    id: UUID
    code: str | None = None
    document_number: str | None = None
    description: str
    receivable_type: str
    status: str
    priority: str
    customer_name: str | None = None
    unidade_codigo: str | None = None
    category_name: str | None = None
    net_value: Decimal
    paid_value: Decimal
    balance: Decimal
    due_date: date
    payment_date: date | None = None
    is_overdue: bool
    days_overdue: int
    total_installments: int
    boleto_generated: bool
    pix_generated: bool

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class ReceivableAccountFilter(BaseModel):
    """Filtros para busca de contas a receber."""

    search: str | None = None
    customer_id: UUID | None = None
    unidade_id: UUID | None = None
    category_id: UUID | None = None
    status: ReceivableStatus | None = None
    receivable_type: ReceivableType | None = None
    priority: ReceivablePriority | None = None
    due_date_start: date | None = None
    due_date_end: date | None = None
    payment_date_start: date | None = None
    payment_date_end: date | None = None
    is_overdue: bool | None = None
    has_boleto: bool | None = None
    has_pix: bool | None = None
    cost_center: str | None = None
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    tags: list[str] | None = None


class ReceivableAccountStats(BaseModel):
    """Estatisticas de contas a receber."""

    total_count: int = 0
    total_value: Decimal = Decimal("0")
    total_received: Decimal = Decimal("0")
    total_pending: Decimal = Decimal("0")
    total_overdue: Decimal = Decimal("0")
    overdue_count: int = 0

    by_status: dict = Field(default_factory=dict)
    by_category: dict = Field(default_factory=dict)
    by_unit: dict = Field(default_factory=dict)
    by_priority: dict = Field(default_factory=dict)


# ============= ReceivableInstallment =============


class ReceivableInstallmentCreate(BaseModel):
    """Schema para criacao de parcela."""

    installment_number: int = Field(..., ge=1)
    total_installments: int = Field(..., ge=1)
    original_value: Decimal = Field(..., gt=0)
    due_date: date

    discount_value: Decimal = Field(default=Decimal("0"), ge=0)
    interest_rate: Decimal = Field(default=Decimal("1"), ge=0)
    penalty_rate: Decimal = Field(default=Decimal("2"), ge=0)
    grace_days: int = Field(default=0, ge=0)

    notes: str | None = None


class ReceivableInstallmentUpdate(BaseModel):
    """Schema para atualizacao de parcela."""

    due_date: date | None = None
    discount_value: Decimal | None = Field(None, ge=0)
    addition_value: Decimal | None = Field(None, ge=0)
    interest_rate: Decimal | None = Field(None, ge=0)
    penalty_rate: Decimal | None = Field(None, ge=0)
    grace_days: int | None = Field(None, ge=0)

    notes: str | None = None


class ReceivableInstallmentResponse(BaseModel):
    """Schema de resposta para parcela."""

    id: UUID
    receivable_account_id: UUID
    condominio_id: UUID
    installment_number: int
    total_installments: int
    display_number: str
    status: InstallmentStatus

    original_value: Decimal
    discount_value: Decimal
    interest_value: Decimal
    penalty_value: Decimal
    addition_value: Decimal
    current_value: Decimal
    paid_value: Decimal
    balance: Decimal

    due_date: date
    original_due_date: date | None = None
    payment_date: date | None = None

    interest_rate: Decimal
    penalty_rate: Decimal
    grace_days: int

    boleto_generated: bool
    boleto_number: str | None = None
    boleto_barcode: str | None = None
    boleto_digitable_line: str | None = None
    boleto_url: str | None = None
    boleto_expires_at: date | None = None

    pix_generated: bool
    pix_qrcode: str | None = None
    pix_copy_paste: str | None = None
    pix_expires_at: datetime | None = None

    collection_attempts: int
    last_collection_date: datetime | None = None

    is_overdue: bool
    days_overdue: int
    days_until_due: int
    is_paid: bool
    is_partially_paid: bool
    is_renegotiated: bool
    can_generate_boleto: bool

    notes: str | None = None
    created_at: datetime

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class ReceivableInstallmentRenegotiateRequest(BaseModel):
    """Request para renegociar parcela."""

    new_due_date: date
    new_value: Decimal | None = Field(None, gt=0)
    reason: str = Field(..., min_length=5, max_length=500)


class ReceivableInstallmentBoletoRequest(BaseModel):
    """Request para gerar boleto."""

    expiration_days: int = Field(default=30, ge=1, le=365)


class ReceivableInstallmentPixRequest(BaseModel):
    """Request para gerar PIX."""

    expiration_hours: int = Field(default=24, ge=1, le=168)


# ============= ReceivablePayment =============


class ReceivablePaymentCreate(BaseModel):
    """Schema para criacao de recebimento."""

    installment_id: UUID
    paid_value: Decimal = Field(..., gt=0)
    payment_date: date
    origin: PaymentOrigin = PaymentOrigin.MANUAL

    discount_value: Decimal = Field(default=Decimal("0"), ge=0)
    interest_value: Decimal = Field(default=Decimal("0"), ge=0)
    penalty_value: Decimal = Field(default=Decimal("0"), ge=0)
    fee_value: Decimal = Field(default=Decimal("0"), ge=0)

    payment_method_id: UUID | None = None
    bank_account_id: UUID | None = None

    receipt_number: str | None = Field(None, max_length=50)
    receipt_url: str | None = Field(None, max_length=500)
    authentication_code: str | None = Field(None, max_length=100)

    notes: str | None = None


class ReceivablePaymentUpdate(BaseModel):
    """Schema para atualizacao de recebimento."""

    payment_date: date | None = None
    discount_value: Decimal | None = Field(None, ge=0)
    interest_value: Decimal | None = Field(None, ge=0)
    penalty_value: Decimal | None = Field(None, ge=0)
    fee_value: Decimal | None = Field(None, ge=0)

    receipt_number: str | None = Field(None, max_length=50)
    receipt_url: str | None = Field(None, max_length=500)
    authentication_code: str | None = Field(None, max_length=100)

    notes: str | None = None


class ReceivablePaymentResponse(BaseModel):
    """Schema de resposta para recebimento."""

    id: UUID
    installment_id: UUID
    condominio_id: UUID
    code: str | None = None
    status: PaymentStatus
    origin: PaymentOrigin

    paid_value: Decimal
    discount_value: Decimal
    interest_value: Decimal
    penalty_value: Decimal
    fee_value: Decimal
    net_value: Decimal
    total_additions: Decimal
    total_deductions: Decimal

    payment_date: date
    processing_date: date | None = None
    confirmation_date: date | None = None
    credit_date: date | None = None

    payment_method_name: str | None = None
    bank_account_name: str | None = None

    receipt_number: str | None = None
    receipt_url: str | None = None
    authentication_code: str | None = None

    bank_transaction_id: str | None = None
    bank_return_code: str | None = None
    bank_return_message: str | None = None

    boleto_nosso_numero: str | None = None
    pix_txid: str | None = None
    pix_end_to_end_id: str | None = None

    is_confirmed: bool
    is_reversed: bool
    is_reconciled: bool

    reversed_at: datetime | None = None
    reversal_reason: str | None = None

    notes: str | None = None
    created_at: datetime

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class ReceivablePaymentReverseRequest(BaseModel):
    """Request para estornar recebimento."""

    reason: str = Field(..., min_length=5, max_length=500)
    receipt: str | None = Field(None, max_length=500)


class ReceivablePaymentReconcileRequest(BaseModel):
    """Request para conciliar recebimento."""

    notes: str | None = Field(None, max_length=500)


# ============= BillingRule =============


class BillingRuleBase(BaseModel):
    """Base para regra de cobranca."""

    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = None
    billing_type: BillingType = BillingType.TAXA_CONDOMINIAL
    category_id: UUID | None = None

    base_value: Decimal = Field(..., gt=0)
    value_type: str = Field(default="fixo")  # fixo, percentual, por_m2
    reference_field: str | None = Field(None, max_length=50)

    frequency: BillingFrequency = BillingFrequency.MENSAL
    due_day: int = Field(default=10, ge=1, le=28)
    generation_day: int = Field(default=1, ge=1, le=28)

    start_date: date
    end_date: date | None = None

    apply_interest: bool = True
    interest_rate: Decimal = Field(default=Decimal("1"), ge=0)
    apply_penalty: bool = True
    penalty_rate: Decimal = Field(default=Decimal("2"), ge=0)
    grace_days: int = Field(default=0, ge=0)

    apply_discount: bool = False
    discount_rate: Decimal = Field(default=Decimal("0"), ge=0)
    discount_days: int = Field(default=0, ge=0)

    auto_generate_boleto: bool = True
    boleto_days_before: int = Field(default=5, ge=1, le=30)
    boleto_expiration_days: int = Field(default=30, ge=1, le=365)

    auto_generate_pix: bool = True
    pix_expiration_hours: int = Field(default=24, ge=1, le=168)

    notifications_enabled: bool = True
    notification_channels: list[str] = Field(default_factory=lambda: ["email", "push"])
    notify_before_days: list[int] = Field(default_factory=lambda: [7, 3, 1])
    notify_after_days: list[int] = Field(default_factory=lambda: [1, 3, 7, 15, 30])
    notification_time: time = Field(default=time(9, 0))

    apply_to_all: bool = True
    unit_filter: dict = Field(default_factory=dict)

    notes: str | None = None


class BillingRuleCreate(BillingRuleBase):
    """Schema para criacao de regra."""

    condominio_id: UUID

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, v: date) -> date:
        """Valida data de inicio."""
        return v


class BillingRuleUpdate(BaseModel):
    """Schema para atualizacao de regra."""

    name: str | None = Field(None, min_length=3, max_length=100)
    description: str | None = None
    category_id: UUID | None = None

    base_value: Decimal | None = Field(None, gt=0)
    value_type: str | None = None
    reference_field: str | None = Field(None, max_length=50)

    due_day: int | None = Field(None, ge=1, le=28)
    generation_day: int | None = Field(None, ge=1, le=28)

    end_date: date | None = None

    apply_interest: bool | None = None
    interest_rate: Decimal | None = Field(None, ge=0)
    apply_penalty: bool | None = None
    penalty_rate: Decimal | None = Field(None, ge=0)
    grace_days: int | None = Field(None, ge=0)

    apply_discount: bool | None = None
    discount_rate: Decimal | None = Field(None, ge=0)
    discount_days: int | None = Field(None, ge=0)

    auto_generate_boleto: bool | None = None
    boleto_days_before: int | None = Field(None, ge=1, le=30)
    boleto_expiration_days: int | None = Field(None, ge=1, le=365)

    auto_generate_pix: bool | None = None
    pix_expiration_hours: int | None = Field(None, ge=1, le=168)

    notifications_enabled: bool | None = None
    notification_channels: list[str] | None = None
    notify_before_days: list[int] | None = None
    notify_after_days: list[int] | None = None
    notification_time: time | None = None

    apply_to_all: bool | None = None
    unit_filter: dict | None = None

    notes: str | None = None


class BillingRuleResponse(BaseModel):
    """Schema de resposta para regra de cobranca."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condominio_id: UUID
    name: str = ""
    description: str | None = None
    billing_type: str | None = None
    base_value: Decimal = Decimal("0")
    frequency: str = "mensal"
    due_day: int = 10
    start_date: date | None = None
    end_date: date | None = None
    status: str = "ativa"
    is_active: bool = True
    should_run_today: bool = False
    total_generated: int = 0
    total_collected: Decimal = Decimal("0")
    collection_rate: Decimal = Decimal("0")
    last_run_at: datetime | None = None
    last_run_result: dict | None = None
    next_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BillingRuleFilter(BaseModel):
    """Filtros para busca de regras."""

    search: str | None = None
    billing_type: BillingType | None = None
    status: BillingRuleStatus | None = None
    frequency: BillingFrequency | None = None
    is_active: bool | None = None


# ============= Bulk Operations =============


class ReceivableBulkPaymentRequest(BaseModel):
    """Request para recebimento em lote."""

    installment_ids: list[UUID] = Field(..., min_length=1)
    payment_date: date
    payment_method_id: UUID | None = None
    bank_account_id: UUID | None = None


class ReceivableBulkBoletoRequest(BaseModel):
    """Request para geracao de boletos em lote."""

    installment_ids: list[UUID] = Field(..., min_length=1)
    expiration_days: int = Field(default=30, ge=1, le=365)


class ReceivableBulkNotifyRequest(BaseModel):
    """Request para envio de notificacoes em lote."""

    installment_ids: list[UUID] = Field(..., min_length=1)
    channels: list[str] = Field(default_factory=lambda: ["email"])
    template: str = Field(default="cobranca")


class ReceivableWriteOffRequest(BaseModel):
    """Request para baixa de conta."""

    reason: str = Field(..., min_length=5, max_length=500)


class ReceivableProtestRequest(BaseModel):
    """Request para protesto de conta."""

    protest_number: str = Field(..., min_length=1, max_length=50)


class ReceivableAgreementRequest(BaseModel):
    """Request para acordo de conta."""

    agreement_id: UUID
    new_due_date: date
    new_value: Decimal | None = Field(None, gt=0)
    installments: int = Field(default=1, ge=1, le=60)
