"""Schemas para cotações de compra."""

from datetime import date, datetime
from decimal import Decimal

from modules.financial.schemas._money import Money, MoneyOpt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from modules.financial.models.purchase_quotation import (
    DeliveryType,
    PaymentCondition,
    QuotationStatus,
)


class QuotationItemBase(BaseModel):
    """Schema base para item de cotação."""

    description: str = Field(..., min_length=1, max_length=500)
    unit_of_measure: str = Field(default="un", max_length=10)
    quantity_requested: Money = Field(..., gt=0)
    quantity_offered: MoneyOpt = Field(None, gt=0)
    unit_price: MoneyOpt = Field(None, ge=0)
    discount_percentage: Money = Decimal("0")
    ipi_percentage: Money = Decimal("0")
    icms_percentage: Money = Decimal("0")
    delivery_days: int | None = Field(None, ge=0)
    availability: str | None = Field(None, max_length=50)
    supplier_code: str | None = Field(None, max_length=50)
    supplier_description: str | None = Field(None, max_length=500)
    technical_specs: str | None = None
    notes: str | None = None
    requisition_item_id: UUID | None = None
    product_id: UUID | None = None


class QuotationItemCreate(QuotationItemBase):
    """Schema para criar item de cotacao."""


class QuotationItemUpdate(BaseModel):
    """Schema para atualizar item de cotação."""

    description: str | None = Field(None, min_length=1, max_length=500)
    quantity_offered: MoneyOpt = Field(None, gt=0)
    unit_price: MoneyOpt = Field(None, ge=0)
    discount_percentage: MoneyOpt = None
    ipi_percentage: MoneyOpt = None
    icms_percentage: MoneyOpt = None
    delivery_days: int | None = None
    availability: str | None = None
    supplier_code: str | None = None
    supplier_description: str | None = None
    technical_specs: str | None = None
    notes: str | None = None
    meets_specs: bool | None = None
    evaluation_notes: str | None = None


class QuotationItemResponse(QuotationItemBase):
    """Schema de resposta para item de cotação."""

    id: UUID
    quotation_id: UUID
    item_number: int
    discount_amount: Money = Decimal("0")
    total: MoneyOpt = None
    min_quantity: MoneyOpt = None
    meets_specs: bool | None = None
    evaluation_notes: str | None = None
    created_at: datetime

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class PurchaseQuotationBase(BaseModel):
    """Schema base para cotação de compra."""

    reference: str | None = Field(None, max_length=50)
    validity_date: date | None = None
    expected_delivery_date: date | None = None
    payment_condition: PaymentCondition = PaymentCondition.DIAS_30
    payment_installments: int | None = Field(None, ge=1)
    delivery_type: DeliveryType = DeliveryType.CIF
    delivery_days: int | None = Field(None, ge=0)
    discount_percentage: Money = Decimal("0")
    discount_amount: Money = Decimal("0")
    freight_amount: Money = Decimal("0")
    insurance_amount: Money = Decimal("0")
    other_costs: Money = Decimal("0")
    ipi_amount: Money = Decimal("0")
    icms_amount: Money = Decimal("0")
    notes: str | None = None
    supplier_notes: str | None = None


class PurchaseQuotationCreate(PurchaseQuotationBase):
    """Schema para criar cotação."""

    condominio_id: UUID
    requisition_id: UUID
    supplier_id: UUID
    items: list[QuotationItemCreate] = Field(default=[], min_length=0)


class PurchaseQuotationUpdate(BaseModel):
    """Schema para atualizar cotação."""

    reference: str | None = None
    validity_date: date | None = None
    expected_delivery_date: date | None = None
    payment_condition: PaymentCondition | None = None
    payment_installments: int | None = None
    delivery_type: DeliveryType | None = None
    delivery_days: int | None = None
    discount_percentage: MoneyOpt = None
    discount_amount: MoneyOpt = None
    freight_amount: MoneyOpt = None
    insurance_amount: MoneyOpt = None
    other_costs: MoneyOpt = None
    ipi_amount: MoneyOpt = None
    icms_amount: MoneyOpt = None
    notes: str | None = None
    supplier_notes: str | None = None
    technical_score: MoneyOpt = Field(None, ge=0, le=100)
    commercial_score: MoneyOpt = Field(None, ge=0, le=100)
    delivery_score: MoneyOpt = Field(None, ge=0, le=100)


class PurchaseQuotationResponse(PurchaseQuotationBase):
    """Schema de resposta para cotação."""

    id: UUID
    condominio_id: UUID
    number: str
    requisition_id: UUID
    supplier_id: UUID
    status: QuotationStatus
    request_date: date
    sent_date: datetime | None = None
    received_date: datetime | None = None
    subtotal: Money = Decimal("0")
    total: Money = Decimal("0")
    pis_amount: Money = Decimal("0")
    cofins_amount: Money = Decimal("0")
    technical_score: MoneyOpt = None
    commercial_score: MoneyOpt = None
    delivery_score: MoneyOpt = None
    overall_score: MoneyOpt = None
    is_best_price: bool = False
    is_best_delivery: bool = False
    is_best_overall: bool = False
    selected_at: datetime | None = None
    selected_by: UUID | None = None
    selection_justification: str | None = None
    rejection_reason: str | None = None
    items: list[QuotationItemResponse] = []
    created_at: datetime
    updated_at: datetime | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class PurchaseQuotationListResponse(BaseModel):
    """Schema de resposta para lista de cotações."""

    items: list[PurchaseQuotationResponse]
    total: int
    page: int = 1
    page_size: int = 50


class QuotationSelectRequest(BaseModel):
    """Request para selecionar cotação vencedora."""

    justification: str | None = Field(None, max_length=500)


class QuotationRejectRequest(BaseModel):
    """Request para rejeitar cotação."""

    reason: str = Field(..., min_length=5, max_length=500)


class QuotationScoreRequest(BaseModel):
    """Request para avaliar cotação."""

    technical_score: MoneyOpt = Field(None, ge=0, le=100)
    commercial_score: MoneyOpt = Field(None, ge=0, le=100)
    delivery_score: MoneyOpt = Field(None, ge=0, le=100)
    notes: str | None = None


class QuotationComparisonResponse(BaseModel):
    """Comparação entre cotações."""

    requisition_id: UUID
    requisition_number: str
    quotations: list[dict[str, Any]] = []
    best_price: UUID | None = None
    best_delivery: UUID | None = None
    best_overall: UUID | None = None
    recommendation: str | None = None


class QuotationStats(BaseModel):
    """Estatísticas de cotações."""

    total: int = 0
    by_status: dict[str, int] = {}
    pending_response: int = 0
    expired: int = 0
    average_response_days: float | None = None
    average_discount_percentage: float | None = None
