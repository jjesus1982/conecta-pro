"""Schemas para aprovações de compra."""

from datetime import datetime
from decimal import Decimal

from modules.financial.schemas._money import Money, MoneyOpt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from modules.financial.models.purchase_approval import (
    ApprovalAction,
    ApprovalLevel,
    ApprovalStatus,
    ApprovalType,
)


class PurchaseApprovalBase(BaseModel):
    """Schema base para aprovação de compra."""

    approval_type: ApprovalType
    document_id: UUID
    document_number: str | None = Field(None, max_length=50)
    approval_level: ApprovalLevel
    document_total: MoneyOpt = Field(None, ge=0)
    deadline: datetime | None = None


class PurchaseApprovalCreate(PurchaseApprovalBase):
    """Schema para criar aprovação."""

    condominio_id: UUID
    approver_id: UUID
    approver_role: str | None = Field(None, max_length=50)
    sequence: int = 1


class PurchaseApprovalUpdate(BaseModel):
    """Schema para atualizar aprovação."""

    deadline: datetime | None = None
    approver_id: UUID | None = None


class PurchaseApprovalResponse(PurchaseApprovalBase):
    """Schema de resposta para aprovação."""

    id: UUID
    condominio_id: UUID
    sequence: int = 1
    status: ApprovalStatus
    approver_id: UUID
    approver_role: str | None = None
    original_approver_id: UUID | None = None
    delegated_by: UUID | None = None
    delegation_reason: str | None = None
    delegated_at: datetime | None = None
    requested_at: datetime
    responded_at: datetime | None = None
    response_time_hours: MoneyOpt = None
    action: ApprovalAction | None = None
    comments: str | None = None
    rejection_reason: str | None = None
    info_requested: str | None = None
    info_provided: str | None = None
    notification_sent: bool = False
    reminder_count: int = 0
    action_history: list[dict[str, Any]] = []
    created_at: datetime
    updated_at: datetime | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Configuracao do schema."""

        from_attributes = True


class PurchaseApprovalListResponse(BaseModel):
    """Schema de resposta para lista de aprovações."""

    items: list[PurchaseApprovalResponse]
    total: int
    page: int = 1
    page_size: int = 50


class ApprovalApproveRequest(BaseModel):
    """Request para aprovar."""

    comments: str | None = Field(None, max_length=500)


class ApprovalRejectRequest(BaseModel):
    """Request para rejeitar."""

    reason: str = Field(..., min_length=5, max_length=500)
    comments: str | None = Field(None, max_length=500)


class ApprovalDelegateRequest(BaseModel):
    """Request para delegar."""

    new_approver_id: UUID
    reason: str = Field(..., min_length=5, max_length=500)


class ApprovalInfoRequest(BaseModel):
    """Request para solicitar informações."""

    info_request: str = Field(..., min_length=5, max_length=1000)


class ApprovalInfoProvideRequest(BaseModel):
    """Request para fornecer informações."""

    info: str = Field(..., min_length=5, max_length=1000)


class ApprovalStats(BaseModel):
    """Estatísticas de aprovações."""

    total: int = 0
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_level: dict[str, int] = {}
    pending: int = 0
    overdue: int = 0
    average_response_hours: float | None = None
    approval_rate: float | None = None


class ApprovalFilter(BaseModel):
    """Filtros para busca de aprovações."""

    status: list[ApprovalStatus] | None = None
    approval_type: list[ApprovalType] | None = None
    approval_level: list[ApprovalLevel] | None = None
    approver_id: UUID | None = None
    document_id: UUID | None = None
    is_overdue: bool | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class MyApprovalsResponse(BaseModel):
    """Minhas aprovações pendentes."""

    pending: list[PurchaseApprovalResponse] = []
    recent: list[PurchaseApprovalResponse] = []
    overdue: list[PurchaseApprovalResponse] = []
    total_pending: int = 0
    total_overdue: int = 0


class ApprovalWorkflowConfig(BaseModel):
    """Configuração de workflow de aprovação."""

    approval_type: ApprovalType
    levels: list[dict[str, Any]] = []
    # [{level: "operacional", min_value: 0, max_value: 1000, approvers: [uuid1, uuid2]}]
    sequential: bool = True  # Aprovação sequencial ou paralela
    require_all: bool = False  # Requer todos aprovarem (paralelo)
    auto_approve_below: MoneyOpt = None  # Auto-aprovar abaixo deste valor
    deadline_hours: int = 48  # Prazo padrão em horas
