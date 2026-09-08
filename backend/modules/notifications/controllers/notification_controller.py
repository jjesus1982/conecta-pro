"""NotificationController - Endpoints REST para Notificações.

Sprint 36 - Notification Hub.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser
from core.database.session import get_sync_db_dependency
from modules.notifications.models import (
    NotificationQueue,
)
from modules.notifications.schemas import (
    QueueItemResponse,
    QueueStatsResponse,
)
from modules.notifications.services import NotificationService
from modules.notifications.services.push_service import PushNotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# =============================================================================
# Helpers
# =============================================================================


def get_tenant_id(current_user) -> UUID:
    """Extrai tenant_id do usuário atual."""
    if current_user is None:
        # Fallback para tenant padrão
        return UUID("00000000-0000-0000-0000-000000000001")
    tid = getattr(current_user, "tenant_id", None)
    if tid is None:
        return UUID("00000000-0000-0000-0000-000000000001")
    return tid


# =============================================================================
# Send Notifications
# =============================================================================


# =============================================================================
# Channels
# =============================================================================


# =============================================================================
# Templates
# =============================================================================


# =============================================================================
# Preferences
# =============================================================================


# =============================================================================
# Queue
# =============================================================================


@router.get("/queue", response_model=list[QueueItemResponse])
async def list_queue(
    current_user: CurrentActiveUser,
    queue_status: str | None = None,
    channel_type: str | None = None,
    user_id: UUID | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_sync_db_dependency),
) -> list[QueueItemResponse]:
    """Lista itens da fila de notificações."""
    tenant_id = get_tenant_id(current_user)

    query = db.query(NotificationQueue).filter(
        NotificationQueue.tenant_id == tenant_id,
    )

    if queue_status:
        query = query.filter(NotificationQueue.status == queue_status)
    if channel_type:
        query = query.filter(NotificationQueue.channel_type == channel_type)
    if user_id:
        query = query.filter(NotificationQueue.user_id == user_id)

    items = query.order_by(NotificationQueue.created_at.desc()).offset(skip).limit(limit).all()

    return items


@router.get("/queue/stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    current_user: CurrentActiveUser,
    db: Session = Depends(get_sync_db_dependency),
) -> QueueStatsResponse:
    """Obtém estatísticas da fila."""
    tenant_id = get_tenant_id(current_user)

    service = NotificationService(db, tenant_id)
    stats = service.get_queue_stats()

    return QueueStatsResponse(
        total_pending=stats["by_status"].get("pending", 0),
        total_scheduled=stats["by_status"].get("scheduled", 0),
        total_processing=stats["by_status"].get("processing", 0),
        total_sent=stats["by_status"].get("sent", 0),
        total_delivered=stats["by_status"].get("delivered", 0),
        total_failed=stats["by_status"].get("failed", 0),
        total_retry=stats["by_status"].get("retry", 0),
        by_channel=stats["by_channel"],
        oldest_pending_at=stats["oldest_pending_at"],
    )


# =============================================================================
# Logs & History
# =============================================================================


# =============================================================================
# Tracking (Webhooks)
# =============================================================================


# =============================================================================
# Push Notifications
# =============================================================================


@router.get("/push", status_code=status.HTTP_200_OK)
async def list_push_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    current_user: CurrentActiveUser = None,
    db: Session = Depends(get_sync_db_dependency),
) -> dict:
    """Lista notificações push do usuário."""
    try:
        if current_user is None:
            return {"notifications": [], "unread_count": 0, "total": 0}

        tenant_id = get_tenant_id(current_user)
        user_id = getattr(current_user, "id", None)
        if user_id is None:
            return {"notifications": [], "unread_count": 0, "total": 0}

        service = PushNotificationService(db, tenant_id)
        notifications = service.get_user_notifications(
            user_id=user_id,
            unread_only=unread_only,
            limit=limit,
            offset=offset,
        )

        unread_count = service.get_unread_count(user_id)

        return {
            "notifications": notifications,
            "unread_count": unread_count,
            "total": len(notifications),
        }
    except Exception:
        # Nunca retornar 500 — notificações são best-effort
        return {"notifications": [], "unread_count": 0, "total": 0}


@router.patch("/push/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_push_as_read(
    notification_id: UUID,
    current_user: CurrentActiveUser = None,
    db: Session = Depends(get_sync_db_dependency),
) -> dict:
    """Marca notificação como lida."""
    tenant_id = get_tenant_id(current_user)

    service = PushNotificationService(db, tenant_id)
    result = service.mark_as_read(
        notification_id=notification_id,
        user_id=current_user.id,
    )

    return result


@router.get("/push/unread-count", status_code=status.HTTP_200_OK)
async def get_push_unread_count(
    current_user: CurrentActiveUser = None,
    db: Session = Depends(get_sync_db_dependency),
) -> dict:
    """Retorna quantidade de notificações não lidas."""
    tenant_id = get_tenant_id(current_user)

    service = PushNotificationService(db, tenant_id)
    count = service.get_unread_count(user_id=current_user.id)

    return {"unread_count": count}


