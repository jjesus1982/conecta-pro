"""Schemas para contas a pagar."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from modules.financial.models.payable_account import (
    PayablePriority,
    PayableStatus,
    PayableType,
    RecurrenceType,
)
from modules.financial.models.payable_installment import InstallmentStatus
from modules.financial.models.payable_payment import PaymentOrigin, PaymentStatus

# ============= PayableAccount =============


class PayableAccountBase(BaseModel):
    """Base para conta a pagar."""

    description: str = Field(..., min_length=3, max_length=500)
    document_number: str | None = Field(None, max_length=50)
    payable_type: PayableType = PayableType.AVULSA
    priority: PayablePriority = PayablePriority.MEDIA

    supplier_id: UUID | None = None
    category_id: UUID | None = None

    gross_value: Decimal = Field(..., gt=0)
    discount_value: Decimal = Field(default=Decimal("0"), ge=0)
    addition_value: Decimal = Field(default=Decimal("0"), ge=0)

    # Retenções
    withhold_iss: Decimal = Field(default=Decimal("0"), ge=0)
    withhold_ir: Decimal = Field(default=Decimal("0"), ge=0)
    withhold_pis: Decimal = Field(default=Decimal("0"), ge=0)
    withhold_cofins: Decimal = Field(default=Decimal("0"), ge=0)
    withhold_csll: Decimal = Field(default=Decimal("0"), ge=0)
    withhold_inss: Decimal = Field(default=Decimal("0"), ge=0)

    # Datas
    issue_date: date | None = None
    due_date: date
    competence_date: date | None = None

    # Parcelamento
    total_installments: int = Field(default=1, ge=1, le=360)

    # Recorrência
    is_recurring: bool = False
    recurrence_type: RecurrenceType | None = None
    recurrence_end_date: date | None = None

    # Centro de custo
    cost_center: str | None = Field(None, max_length=50)
    project: str | None = Field(None, max_length=50)

    # Documento fiscal
    fiscal_document_type: str | None = Field(None, max_length=30)
    fiscal_document_key: str | None = Field(None, max_length=50)
    fiscal_document_url: str | None = Field(None, max_length=500)

    # Contrato
    contract_id: UUID | None = None

    # Forma de pagamento
    payment_method_id: UUID | None = None
    bank_account_id: UUID | None = None

    # Aprovação
    requires_approval: bool = False

    # Tags e notas
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class PayableAccountCreate(PayableAccountBase):
    """Schema para criação de conta a pagar."""

    condominio_id: UUID

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v: date) -> date:
        """Valida data de vencimento."""
        # Permite datas no passado (para lançamentos retroativos)
        return v


class PayableAccountUpdate(BaseModel):
    """Schema para atualização de conta a pagar."""

    description: str | None = Field(None, min_length=3, max_length=500)
    document_number: str | None = Field(None, max_length=50)
    priority: PayablePriority | None = None

    supplier_id: UUID | None = None
    category_id: UUID | None = None

    gross_value: Decimal | None = Field(None, gt=0)
    discount_value: Decimal | None = Field(None, ge=0)
    addition_value: Decimal | None = Field(None, ge=0)

    # Retenções
    withhold_iss: Decimal | None = Field(None, ge=0)
    withhold_ir: Decimal | None = Field(None, ge=0)
    withhold_pis: Decimal | None = Field(None, ge=0)
    withhold_cofins: Decimal | None = Field(None, ge=0)
    withhold_csll: Decimal | None = Field(None, ge=0)
    withhold_inss: Decimal | None = Field(None, ge=0)

    # Datas
    due_date: date | None = None
    competence_date: date | None = None

    # Centro de custo
    cost_center: str | None = Field(None, max_length=50)
    project: str | None = Field(None, max_length=50)

    # Forma de pagamento
    payment_method_id: UUID | None = None
    bank_account_id: UUID | None = None

    # Tags e notas
    tags: list[str] | None = None
    notes: str | None = None


class PayableAccountResponse(PayableAccountBase):
    """Schema de resposta para conta a pagar."""

    id: UUID
    condominio_id: UUID
    code: str | None = None
    status: PayableStatus
    net_value: Decimal
    paid_value: Decimal
    remaining_value: Decimal | None = None
    total_withholdings: Decimal

    entry_date: date
    payment_date: date | None = None

    current_installment: int
    parent_id: UUID | None = None

    approval_status: str | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None

    scheduled_payment_date: date | None = None

    is_overdue: bool
    days_overdue: int
    days_until_due: int
    payment_percentage: float
    balance: Decimal

    attachments: list[dict] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class PayableAccountListResponse(BaseModel):
    """Schema de lista de contas a pagar."""

    id: UUID
    code: str | None = None
    document_number: str | None = None
    description: str
    payable_type: str
    status: str
    priority: str
    supplier_name: str | None = None
    category_name: str | None = None
    net_value: Decimal
    paid_value: Decimal
    balance: Decimal
    due_date: date
    payment_date: date | None = None
    is_overdue: bool
    days_overdue: int
    total_installments: int

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class PayableAccountFilter(BaseModel):
    """Filtros para busca de contas a pagar."""

    search: str | None = None
    supplier_id: UUID | None = None
    category_id: UUID | None = None
    status: PayableStatus | None = None
    payable_type: PayableType | None = None
    priority: PayablePriority | None = None
    due_date_start: date | None = None
    due_date_end: date | None = None
    payment_date_start: date | None = None
    payment_date_end: date | None = None
    is_overdue: bool | None = None
    cost_center: str | None = None
    project: str | None = None
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    tags: list[str] | None = None


class PayableAccountStats(BaseModel):
    """Estatísticas de contas a pagar."""

    total_count: int = 0
    total_value: Decimal = Decimal("0")
    total_paid: Decimal = Decimal("0")
    total_pending: Decimal = Decimal("0")
    total_overdue: Decimal = Decimal("0")
    overdue_count: int = 0

    by_status: dict = Field(default_factory=dict)
    by_category: dict = Field(default_factory=dict)
    by_supplier: dict = Field(default_factory=dict)
    by_priority: dict = Field(default_factory=dict)


# ============= PayableInstallment =============


class PayableInstallmentCreate(BaseModel):
    """Schema para criação de parcela."""

    installment_number: int = Field(..., ge=1)
    total_installments: int = Field(..., ge=1)
    original_value: Decimal = Field(..., gt=0)
    due_date: date

    discount_value: Decimal = Field(default=Decimal("0"), ge=0)
    interest_rate: Decimal = Field(default=Decimal("0"), ge=0)
    penalty_rate: Decimal = Field(default=Decimal("0"), ge=0)

    payment_method_id: UUID | None = None
    barcode: str | None = Field(None, max_length=100)
    pix_copy_paste: str | None = Field(None, max_length=500)

    notes: str | None = None


class PayableInstallmentUpdate(BaseModel):
    """Schema para atualização de parcela."""

    due_date: date | None = None
    discount_value: Decimal | None = Field(None, ge=0)
    addition_value: Decimal | None = Field(None, ge=0)
    interest_rate: Decimal | None = Field(None, ge=0)
    penalty_rate: Decimal | None = Field(None, ge=0)

    payment_method_id: UUID | None = None
    barcode: str | None = Field(None, max_length=100)
    digitable_line: str | None = Field(None, max_length=100)
    pix_qrcode: str | None = None
    pix_copy_paste: str | None = Field(None, max_length=500)
    boleto_url: str | None = Field(None, max_length=500)

    scheduled_payment_date: date | None = None
    notes: str | None = None


class PayableInstallmentResponse(BaseModel):
    """Schema de resposta para parcela."""

    id: UUID
    payable_account_id: UUID
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

    interest_rate: Decimal | None = None
    penalty_rate: Decimal | None = None

    barcode: str | None = None
    digitable_line: str | None = None
    pix_copy_paste: str | None = None
    boleto_url: str | None = None

    scheduled_payment_date: date | None = None

    is_overdue: bool
    days_overdue: int
    days_until_due: int
    is_paid: bool
    is_partially_paid: bool
    is_renegotiated: bool

    notes: str | None = None
    created_at: datetime

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class PayableInstallmentRenegotiateRequest(BaseModel):
    """Request para renegociar parcela."""

    new_due_date: date
    new_value: Decimal | None = Field(None, gt=0)
    reason: str = Field(..., min_length=5, max_length=500)


# ============= PayablePayment =============


class PayablePaymentCreate(BaseModel):
    """Schema para criação de pagamento."""

    installment_id: UUID
    paid_value: Decimal = Field(..., gt=0)
    payment_date: date

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


class PayablePaymentUpdate(BaseModel):
    """Schema para atualização de pagamento."""

    payment_date: date | None = None
    discount_value: Decimal | None = Field(None, ge=0)
    interest_value: Decimal | None = Field(None, ge=0)
    penalty_value: Decimal | None = Field(None, ge=0)
    fee_value: Decimal | None = Field(None, ge=0)

    receipt_number: str | None = Field(None, max_length=50)
    receipt_url: str | None = Field(None, max_length=500)
    authentication_code: str | None = Field(None, max_length=100)

    notes: str | None = None


class PayablePaymentResponse(BaseModel):
    """Schema de resposta para pagamento."""

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

    payment_date: date
    processing_date: date | None = None
    confirmation_date: date | None = None

    payment_method_name: str | None = None
    bank_account_name: str | None = None

    receipt_number: str | None = None
    receipt_url: str | None = None
    authentication_code: str | None = None

    bank_transaction_id: str | None = None
    bank_return_code: str | None = None
    bank_return_message: str | None = None

    is_confirmed: bool
    is_reversed: bool
    is_reconciled: bool

    reversed_at: datetime | None = None
    reversal_reason: str | None = None

    notes: str | None = None
    created_at: datetime

    class Config:  # pylint: disable=too-few-public-methods
        """Configuração do schema."""

        from_attributes = True


class PayablePaymentReverseRequest(BaseModel):
    """Request para estornar pagamento."""

    reason: str = Field(..., min_length=5, max_length=500)
    receipt: str | None = Field(None, max_length=500)


class PayablePaymentReconcileRequest(BaseModel):
    """Request para conciliar pagamento."""

    notes: str | None = Field(None, max_length=500)


# ============= Bulk Operations =============


class PayableBulkPaymentRequest(BaseModel):
    """Request para pagamento em lote."""

    installment_ids: list[UUID] = Field(..., min_length=1)
    payment_date: date
    payment_method_id: UUID | None = None
    bank_account_id: UUID | None = None


class PayableBulkApproveRequest(BaseModel):
    """Request para aprovação em lote."""

    payable_ids: list[UUID] = Field(..., min_length=1)
    notes: str | None = Field(None, max_length=500)


class PayableScheduleRequest(BaseModel):
    """Request para agendar pagamento."""

    scheduled_date: date

    @field_validator("scheduled_date")
    @classmethod
    def validate_scheduled_date(cls, v: date) -> date:
        """Valida data de agendamento."""
        if v < date.today():
            raise ValueError("Data de agendamento não pode ser no passado")
        return v
