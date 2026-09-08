"""
My Notifications Controller — Notificacoes do funcionario no portal.

Endpoints:
- GET /portal/my-notifications
- PATCH /portal/my-notifications/{notification_id}/read
- POST /portal/my-notifications/test-trigger  (apenas em development)
"""

import logging
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Notificacoes"])


class NotificationResponse(BaseModel):
    """Notificacao do portal do funcionario."""

    id: int | None = None
    title: str | None = None
    message: str | None = None
    is_read: bool = False
    notification_type: str | None = None
    created_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class NotificationReadResponse(BaseModel):
    """Resposta ao marcar notificacao como lida."""

    id: int
    is_read: bool = True
    read_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TestTriggerRequest(BaseModel):
    """Payload para disparar auto-notificacao de teste."""

    evento: Literal[
        "payslip_published",
        "schedule_published",
        "document_pending",
        "vacation_approved",
        "overtime_alert",
    ] = Field(..., description="Tipo de evento a simular")
    mes: int = Field(default=3, ge=1, le=12, description="Mes (usado em payslip/schedule)")
    ano: int = Field(default=2026, ge=2020, le=2030, description="Ano")

    model_config = ConfigDict(from_attributes=True)


class TestTriggerResponse(BaseModel):
    """Resposta do test-trigger."""

    success: bool
    notification_id: int | None = None
    message: str

    model_config = ConfigDict(from_attributes=True)


