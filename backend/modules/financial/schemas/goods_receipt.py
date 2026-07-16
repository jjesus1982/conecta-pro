"""Schemas para recebimento de mercadorias."""

from datetime import date, datetime
from decimal import Decimal

from modules.financial.schemas._money import Money, MoneyOpt
from uuid import UUID

from pydantic import BaseModel, Field

from modules.financial.models.goods_receipt import InspectionResult, ReceiptStatus, ReceiptType


class ReceiptItemBase(BaseModel):
    """Schema base para item de recebimento."""

    description: str = Field(..., min_length=1, max_length=500)
    unit_of_measure: str = Field(default="un", max_length=10)
    quantity_expected: Money = Field(..., gt=0)
    quantity_received: Money = Field(default=Decimal("0"), ge=0)
    quantity_accepted: Money = Field(default=Decimal("0"), ge=0)
    quantity_rejected: Money = Field(default=Decimal("0"), ge=0)
    unit_price: MoneyOpt = Field(None, ge=0)
    batch_number: str | None = Field(None, max_length=50)
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    serial_numbers: list[str] = []
    storage_location: str | None = Field(None, max_length=100)
    storage_position: str | None = Field(None, max_length=50)
    notes: str | None = None
    order_item_id: UUID | None = None
    product_id: UUID | None = None


class ReceiptItemCreate(ReceiptItemBase):
    """Schema para criar item de recebimento."""


class ReceiptItemUpdate(BaseModel):
    """Schema para atualizar item de recebimento."""

    quantity_received: MoneyOpt = Field(None, ge=0)
    quantity_accepted: MoneyOpt = Field(None, ge=0)
    quantity_rejected: MoneyOpt = Field(None, ge=0)
    batch_number: str | None = None
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    serial_numbers: list[str] | None = None
    storage_location: str | None = None
    storage_position: str | None = None
    inspection_result: InspectionResult | None = None
    inspection_notes: str | None = None
    rejection_reason: str | None = None
    notes: str | None = None


class ReceiptItemResponse(ReceiptItemBase):
    """Schema de resposta para item de recebimento."""

    id: UUID
    receipt_id: UUID
    item_number: int
    quantity_difference: Money = Decimal("0")
    expected_total: MoneyOpt = None
    received_total: MoneyOpt = None
    accepted_total: MoneyOpt = None
    rejected_total: MoneyOpt = None
    inspection_result: InspectionResult | None = None
    inspection_notes: str | None = None
    rejection_reason: str | None = None
    created_at: datetime

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class GoodsReceiptBase(BaseModel):
    """Schema base para recebimento de mercadorias."""

    receipt_type: ReceiptType = ReceiptType.NORMAL
    expected_date: date | None = None
    invoice_number: str | None = Field(None, max_length=50)
    invoice_series: str | None = Field(None, max_length=10)
    invoice_date: date | None = None
    invoice_key: str | None = Field(None, max_length=50)
    invoice_total: MoneyOpt = Field(None, ge=0)
    carrier: str | None = Field(None, max_length=200)
    carrier_cnpj: str | None = Field(None, max_length=18)
    vehicle_plate: str | None = Field(None, max_length=10)
    driver_name: str | None = Field(None, max_length=100)
    driver_document: str | None = Field(None, max_length=20)
    seal_number: str | None = Field(None, max_length=50)
    volumes: int | None = Field(None, ge=0)
    gross_weight: MoneyOpt = Field(None, ge=0)
    net_weight: MoneyOpt = Field(None, ge=0)
    storage_location: str | None = Field(None, max_length=100)
    storage_notes: str | None = None
    notes: str | None = None


class GoodsReceiptCreate(GoodsReceiptBase):
    """Schema para criar recebimento."""

    condominio_id: UUID
    order_id: UUID
    supplier_id: UUID
    items: list[ReceiptItemCreate] = Field(..., min_length=1)


class GoodsReceiptUpdate(BaseModel):
    """Schema para atualizar recebimento."""

    receipt_type: ReceiptType | None = None
    invoice_number: str | None = None
    invoice_series: str | None = None
    invoice_date: date | None = None
    invoice_key: str | None = None
    invoice_total: MoneyOpt = None
    carrier: str | None = None
    carrier_cnpj: str | None = None
    vehicle_plate: str | None = None
    driver_name: str | None = None
    driver_document: str | None = None
    seal_number: str | None = None
    volumes: int | None = None
    gross_weight: MoneyOpt = None
    net_weight: MoneyOpt = None
    storage_location: str | None = None
    storage_notes: str | None = None
    notes: str | None = None


class GoodsReceiptResponse(GoodsReceiptBase):
    """Schema de resposta para recebimento."""

    id: UUID
    condominio_id: UUID
    number: str
    order_id: UUID
    supplier_id: UUID
    status: ReceiptStatus
    receipt_date: date
    inspection_date: datetime | None = None
    approval_date: datetime | None = None
    total_expected: Money = Decimal("0")
    total_received: Money = Decimal("0")
    total_accepted: Money = Decimal("0")
    total_rejected: Money = Decimal("0")
    total_difference: Money = Decimal("0")
    inspection_result: InspectionResult | None = None
    inspection_notes: str | None = None
    inspected_by: UUID | None = None
    has_divergence: bool = False
    divergence_type: str | None = None
    divergence_description: str | None = None
    divergence_action: str | None = None
    approved_by: UUID | None = None
    rejection_reason: str | None = None
    receiver_name: str | None = None
    receiver_document: str | None = None
    received_at: datetime | None = None
    items: list[ReceiptItemResponse] = []
    created_at: datetime
    updated_at: datetime | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class GoodsReceiptListResponse(BaseModel):
    """Schema de resposta para lista de recebimentos."""

    items: list[GoodsReceiptResponse]
    total: int
    page: int = 1
    page_size: int = 50


class ReceiptInspectionRequest(BaseModel):
    """Request para iniciar/concluir inspeção."""

    result: InspectionResult
    notes: str | None = Field(None, max_length=1000)


class ReceiptApproveRequest(BaseModel):
    """Request para aprovar recebimento."""

    notes: str | None = Field(None, max_length=500)


class ReceiptRejectRequest(BaseModel):
    """Request para recusar recebimento."""

    reason: str = Field(..., min_length=5, max_length=500)


class ReceiptDivergenceRequest(BaseModel):
    """Request para registrar divergência."""

    divergence_type: str = Field(..., max_length=50)
    description: str = Field(..., min_length=5, max_length=1000)
    action: str | None = Field(None, max_length=50)


class ReceiptSignRequest(BaseModel):
    """Request para assinar recebimento."""

    receiver_name: str = Field(..., min_length=2, max_length=100)
    receiver_document: str = Field(..., min_length=5, max_length=20)
    signature: str | None = None


class ReceiptStats(BaseModel):
    """Estatísticas de recebimentos."""

    total: int = 0
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    pending_inspection: int = 0
    with_divergence: int = 0
    total_received_value: Money = Decimal("0")
    acceptance_rate: float | None = None
    average_inspection_hours: float | None = None


class ReceiptFilter(BaseModel):
    """Filtros para busca de recebimentos."""

    status: list[ReceiptStatus] | None = None
    receipt_type: list[ReceiptType] | None = None
    order_id: UUID | None = None
    supplier_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    has_divergence: bool | None = None
    search: str | None = None
