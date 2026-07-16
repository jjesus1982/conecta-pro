"""Schemas para requisições de compra."""

from datetime import date, datetime
from decimal import Decimal

from modules.financial.schemas._money import Money, MoneyOpt
from uuid import UUID

from pydantic import BaseModel, Field

from modules.financial.models.purchase_requisition import (
    RequisitionPriority,
    RequisitionStatus,
    RequisitionType,
)


class RequisitionItemBase(BaseModel):
    """Schema base para item de requisição."""

    description: str = Field(..., min_length=1, max_length=500)
    specifications: str | None = None
    unit_of_measure: str = Field(default="un", max_length=10)
    quantity_requested: Money = Field(..., gt=0)
    estimated_unit_price: MoneyOpt = Field(None, ge=0)
    product_id: UUID | None = None
    notes: str | None = None


class RequisitionItemCreate(RequisitionItemBase):
    """Schema para criar item de requisicao."""


class RequisitionItemUpdate(BaseModel):
    """Schema para atualizar item de requisição."""

    description: str | None = Field(None, min_length=1, max_length=500)
    specifications: str | None = None
    unit_of_measure: str | None = None
    quantity_requested: MoneyOpt = Field(None, gt=0)
    quantity_approved: MoneyOpt = Field(None, ge=0)
    estimated_unit_price: MoneyOpt = Field(None, ge=0)
    product_id: UUID | None = None
    notes: str | None = None


class RequisitionItemResponse(RequisitionItemBase):
    """Schema de resposta para item de requisição."""

    id: UUID
    requisition_id: UUID
    item_number: int
    quantity_approved: MoneyOpt = None
    quantity_ordered: Money = Decimal("0")
    quantity_received: Money = Decimal("0")
    estimated_total: MoneyOpt = None
    created_at: datetime

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class PurchaseRequisitionBase(BaseModel):
    """Schema base para requisição de compra."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    justification: str | None = None
    requisition_type: RequisitionType = RequisitionType.MATERIAL
    priority: RequisitionPriority = RequisitionPriority.MEDIA
    needed_by_date: date | None = None
    department: str | None = Field(None, max_length=100)
    cost_center: str | None = Field(None, max_length=50)
    min_quotations: int = Field(default=3, ge=1, le=10)
    quotation_deadline: date | None = None
    delivery_address: str | None = None
    delivery_contact: str | None = Field(None, max_length=100)
    delivery_phone: str | None = Field(None, max_length=20)
    delivery_instructions: str | None = None
    suggested_supplier_id: UUID | None = None
    supplier_justification: str | None = None
    notes: str | None = None


class PurchaseRequisitionCreate(PurchaseRequisitionBase):
    """Schema para criar requisição."""

    condominio_id: UUID
    requester_id: UUID
    items: list[RequisitionItemCreate] = Field(default=[], min_length=0)


class PurchaseRequisitionUpdate(BaseModel):
    """Schema para atualizar requisição."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    justification: str | None = None
    requisition_type: RequisitionType | None = None
    priority: RequisitionPriority | None = None
    needed_by_date: date | None = None
    department: str | None = None
    cost_center: str | None = None
    min_quotations: int | None = None
    quotation_deadline: date | None = None
    delivery_address: str | None = None
    delivery_contact: str | None = None
    delivery_phone: str | None = None
    delivery_instructions: str | None = None
    suggested_supplier_id: UUID | None = None
    supplier_justification: str | None = None
    notes: str | None = None


class PurchaseRequisitionResponse(PurchaseRequisitionBase):
    """Schema de resposta para requisição."""

    id: UUID
    condominio_id: UUID
    number: str
    revision: int = 1
    status: RequisitionStatus
    requester_id: UUID
    request_date: date
    estimated_total: Money = Decimal("0")
    approved_budget: MoneyOpt = None
    actual_total: Money = Decimal("0")
    approved_at: datetime | None = None
    approved_by: UUID | None = None
    rejection_reason: str | None = None
    cancellation_reason: str | None = None
    items: list[RequisitionItemResponse] = []
    created_at: datetime
    updated_at: datetime | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class PurchaseRequisitionListResponse(BaseModel):
    """Schema de resposta para lista de requisições."""

    items: list[PurchaseRequisitionResponse]
    total: int
    page: int = 1
    page_size: int = 50


class RequisitionApproveRequest(BaseModel):
    """Request para aprovar requisição."""

    comment: str | None = Field(None, max_length=500)
    approved_budget: MoneyOpt = Field(None, ge=0)


class RequisitionRejectRequest(BaseModel):
    """Request para rejeitar requisição."""

    reason: str = Field(..., min_length=5, max_length=500)
    comment: str | None = Field(None, max_length=500)


class RequisitionCancelRequest(BaseModel):
    """Request para cancelar requisição."""

    reason: str = Field(..., min_length=5, max_length=500)


class RequisitionStats(BaseModel):
    """Estatísticas de requisições."""

    total: int = 0
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_type: dict[str, int] = {}
    pending_approval: int = 0
    overdue: int = 0
    total_estimated: Money = Decimal("0")
    average_approval_time_hours: float | None = None


class RequisitionFilter(BaseModel):
    """Filtros para busca de requisições."""

    status: list[RequisitionStatus] | None = None
    priority: list[RequisitionPriority] | None = None
    requisition_type: list[RequisitionType] | None = None
    requester_id: UUID | None = None
    department: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    needed_by_from: date | None = None
    needed_by_to: date | None = None
    search: str | None = None
