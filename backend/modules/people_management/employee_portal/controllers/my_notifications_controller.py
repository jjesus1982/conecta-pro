"""
My Notifications Controller — Notificacoes do funcionario no portal.

Endpoints:
- GET /portal/my-notifications
- PATCH /portal/my-notifications/{notification_id}/read
- POST /portal/my-notifications/test-trigger  (apenas em development)
"""

import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId

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


@router.get(
    "/my-notifications",
    response_model=list[NotificationResponse],
    summary="Minhas notificacoes",
    description="Retorna lista de notificacoes do funcionario logado.",
)
async def get_my_notifications(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna notificacoes do funcionario autenticado."""
    try:
        from sqlalchemy import select

        from modules.people_management.employee_portal.models.notification import (
            PortalNotification,
        )

        result = await db.execute(
            select(PortalNotification)
            .where(PortalNotification.employee_id == str(employee_id))
            .order_by(PortalNotification.created_at.desc())
        )
        notifications = result.scalars().all()

        return [
            NotificationResponse(
                id=n.id,
                title=n.title,
                message=n.message,
                is_read=n.is_read,
                notification_type=str(n.notification_type.value) if n.notification_type else None,
                created_at=str(n.created_at) if n.created_at else None,
            )
            for n in notifications
        ]

    except (ImportError, Exception) as e:
        logger.warning(f"Erro ao buscar notificacoes do funcionario {employee_id}: {e}")

    return []


@router.patch(
    "/my-notifications/{notification_id}/read",
    response_model=NotificationReadResponse,
    summary="Marcar notificacao como lida",
    description="Marca uma notificacao especifica como lida.",
)
async def mark_notification_as_read(
    notification_id: int,
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Marca uma notificacao como lida para o funcionario autenticado."""
    try:
        from sqlalchemy import select

        from modules.people_management.employee_portal.models.notification import (
            PortalNotification,
        )

        result = await db.execute(
            select(PortalNotification).where(
                PortalNotification.id == notification_id,
                PortalNotification.employee_id == str(employee_id),
            )
        )
        notification = result.scalar_one_or_none()

        if not notification:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Notificacao {notification_id} nao encontrada.",
            )

        notification.is_read = True
        notification.read_at = datetime.utcnow()
        await db.commit()
        await db.refresh(notification)

        logger.info(f"Notificacao {notification_id} marcada como lida pelo funcionario {employee_id}")

        return NotificationReadResponse(
            id=notification.id,
            is_read=True,
            read_at=str(notification.read_at),
        )

    except HTTPException:
        raise
    except (ImportError, Exception) as e:
        logger.warning(f"Erro ao marcar notificacao {notification_id} como lida: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar notificacao.",
        )


# ---------------------------------------------------------------------------
# Test-trigger (apenas desenvolvimento)
# ---------------------------------------------------------------------------


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


@router.post(
    "/my-notifications/test-trigger",
    response_model=TestTriggerResponse,
    summary="Disparar notificacao de teste (apenas development, status_code=201)",
    description=(
        "Simula um evento de negocio e dispara a auto-notificacao correspondente "
        "para o funcionario autenticado. **Disponivel apenas em modo development.**"
    ),
)
async def test_notification_trigger(
    payload: TestTriggerRequest,
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dispara uma auto-notificacao de teste para o funcionario autenticado.

    Retorna 403 em producao (environment != 'development').
    """
    if settings.environment != "development":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Endpoint disponivel apenas em modo development.",
        )

    from modules.people_management.employee_portal.services.auto_notification_service import (
        AutoNotificationService,
    )

    svc = AutoNotificationService(db)
    notif_id: int | None = None

    try:
        if payload.evento == "payslip_published":
            notif_id = await svc.notify_payslip_published(
                employee_id=employee_id,
                mes=payload.mes,
                ano=payload.ano,
            )
        elif payload.evento == "schedule_published":
            notif_id = await svc.notify_schedule_published(
                employee_id=employee_id,
                mes=payload.mes,
                ano=payload.ano,
            )
        elif payload.evento == "document_pending":
            notif_id = await svc.notify_document_pending_signature(
                employee_id=employee_id,
                doc_id="DOC-TESTE-001",
                doc_nome="Termo de Ciencia - Politica de Seguranca",
            )
        elif payload.evento == "vacation_approved":
            notif_id = await svc.notify_vacation_approved(
                employee_id=employee_id,
                data_inicio="01/07/2026",
                dias=30,
            )
        elif payload.evento == "overtime_alert":
            notif_id = await svc.notify_overtime_balance_alert(
                employee_id=employee_id,
                saldo_horas=-5.0,  # Forcado abaixo do limiar
            )

        if notif_id:
            return TestTriggerResponse(
                success=True,
                notification_id=notif_id,
                message=f"Notificacao de teste '{payload.evento}' criada com sucesso.",
            )

        return TestTriggerResponse(
            success=False,
            notification_id=None,
            message=f"Evento '{payload.evento}' nao gerou notificacao (verifique limiar/logs).",
        )

    except Exception as exc:
        logger.error("Erro no test-trigger: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao disparar notificacao de teste: {exc}",
        ) from exc
