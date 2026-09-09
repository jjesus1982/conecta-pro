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


# =============================================================================
# Logs & History
# =============================================================================


# =============================================================================
# Tracking (Webhooks)
# =============================================================================


# =============================================================================
# Push Notifications
# =============================================================================


@router.post("/push/subscribe", status_code=status.HTTP_200_OK)
async def subscribe_push(
    device_token: str,
    platform: str,
    device_info: dict | None = None,
    current_user: CurrentActiveUser = None,
    db: Session = Depends(get_sync_db_dependency),
) -> dict:
    """Registra dispositivo para receber notificações push.

    09/09/2026: restaurado de ee5383812~1. Apagado como "só clássico" em 08/09, mas é chamado por
    features/notifications/hooks/useNotifications.ts → usePushNotifications → PushNotificationProvider, montado nos
    providers do layout RAIZ (toda página do redesign). A medição de 08/09 não viu porque `docker cp` não apaga
    arquivo: o container guardou o handler apagado até o bake de 09/09 00:54 — aí o 404 apareceu.
    """
    tenant_id = get_tenant_id(current_user)
    service = PushNotificationService(db, tenant_id)
    return service.subscribe_device(
        user_id=current_user.id,
        device_token=device_token,
        platform=platform,
        device_info=device_info,
    )


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


# 08/09/2026 (auditoria t6): restaurada — o centro de notificações (features/notifications, layout raiz) chama POST /push/read-all.
@router.post("/push/read-all", status_code=status.HTTP_200_OK)
async def mark_all_push_as_read(
    current_user: CurrentActiveUser = None,
    db: Session = Depends(get_sync_db_dependency),
) -> dict:
    """Marca todas as notificações como lidas."""
    tenant_id = get_tenant_id(current_user)

    service = PushNotificationService(db, tenant_id)
    result = service.mark_all_as_read(user_id=current_user.id)

    return result
