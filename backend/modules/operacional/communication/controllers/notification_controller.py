"""
Controller (endpoints) para Notificacoes e Alertas.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score Target: 99+/100
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.communication.models.alert import AlertSeverity, AlertType
from modules.operacional.communication.models.notification import NotificationType
from modules.operacional.communication.schemas.communication_schemas import (
    AlertCreate,
    AlertFilter,
    AlertListResponse,
    AlertResponse,
    MarkNotificationReadRequest,
    NotificationFilter,
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCount,
)
from modules.operacional.communication.services.alert_service import (
    AlertNotFoundError,
    AlertService,
)
from modules.operacional.communication.services.notification_service import (
    NotificationNotFoundError,
    NotificationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Operacional - Notificacoes"])


def _get_tenant_id(user: CurrentActiveUser) -> str:
    """Extrai tenant_id do usuario."""
    return getattr(user, "tenant_id", str(user.id))


def _get_user_roles(user: CurrentActiveUser) -> list[str]:
    """Extrai roles do usuario."""
    role = getattr(user, "role", None)
    return [role] if role else []


# =============================================================================
# ENDPOINTS DE NOTIFICACOES
# =============================================================================


@router.get(
    "/notificacoes",
    response_model=NotificationListResponse,
    summary="Listar notificacoes",
    description="Lista notificacoes do usuario com filtros e paginacao",
)
async def list_notifications(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Pagina atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por pagina"),
    type_filter: NotificationType | None = Query(None, alias="type"),
    is_read: bool | None = None,
    reference_type: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> NotificationListResponse:
    """
    Lista notificacoes do usuario.

    Args:
        current_user: Usuario autenticado
        db: Sessao do banco de dados
        page: Pagina atual
        page_size: Itens por pagina
        type_filter: Filtro por tipo
        is_read: Filtro por lidas/nao lidas
        reference_type: Filtro por tipo de referencia
        created_after: Criadas apos
        created_before: Criadas antes

    Returns:
        Lista paginada de notificacoes
    """
    service = NotificationService(db)
    tenant_id = _get_tenant_id(current_user)

    filters = NotificationFilter(
        type=type_filter,
        is_read=is_read,
        reference_type=reference_type,
        created_after=created_after,
        created_before=created_before,
    )

    notifications, total = await service.list_for_user(
        tenant_id=tenant_id,
        user_id=str(current_user.id),
        filters=filters,
        page=page,
        page_size=page_size,
    )

    total_pages = (total + page_size - 1) // page_size

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/notificacoes/nao-lidas/count",
    response_model=NotificationUnreadCount,
    summary="Contagem de nao lidas",
    description="Retorna contagem de notificacoes nao lidas",
)
async def get_unread_count(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> NotificationUnreadCount:
    """
    Obtem contagem de notificacoes nao lidas.

    Args:
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Contagem total e por tipo
    """
    service = NotificationService(db)
    tenant_id = _get_tenant_id(current_user)

    return await service.get_unread_count(
        tenant_id=tenant_id,
        user_id=str(current_user.id),
    )


@router.post(
    "/notificacoes/{notification_id}/lida",
    response_model=NotificationResponse,
    summary="Marcar como lida",
    description="Marca uma notificacao como lida",
    status_code=201,
)
async def mark_notification_read(
    notification_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """
    Marca notificacao como lida.

    Args:
        notification_id: ID da notificacao
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Notificacao atualizada

    Raises:
        HTTPException 404: Se nao encontrada
    """
    service = NotificationService(db)

    try:
        notification = await service.mark_as_read(
            notification_id=notification_id,
            user_id=str(current_user.id),
        )
        return NotificationResponse.model_validate(notification)

    except NotificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificacao nao encontrada",
        )


@router.post(
    "/notificacoes/marcar-todas",
    response_model=dict,
    summary="Marcar todas como lidas",
    description="Marca todas notificacoes como lidas",
    status_code=201,
)
async def mark_all_notifications_read(
    request_data: MarkNotificationReadRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Marca todas notificacoes como lidas.

    Args:
        request_data: IDs especificos (opcional)
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Quantidade de notificacoes atualizadas
    """
    service = NotificationService(db)
    tenant_id = _get_tenant_id(current_user)

    count = await service.mark_all_as_read(
        tenant_id=tenant_id,
        user_id=str(current_user.id),
        notification_ids=request_data.notification_ids,
    )

    logger.info(f"Notificacoes marcadas como lidas por {current_user.email}: {count}")

    return {
        "success": True,
        "count": count,
    }


@router.delete(
    "/notificacoes/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover notificacao",
    description="Remove uma notificacao",
)
async def delete_notification(
    notification_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove uma notificacao.

    Args:
        notification_id: ID da notificacao
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Raises:
        HTTPException 404: Se nao encontrada
    """
    service = NotificationService(db)

    try:
        await service.delete(
            notification_id=notification_id,
            user_id=str(current_user.id),
        )
        logger.info(f"Notificacao removida por {current_user.email}: {notification_id}")

    except NotificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificacao nao encontrada",
        )


# =============================================================================
# ENDPOINTS DE ALERTAS
# =============================================================================


@router.get(
    "/alertas/ativos",
    response_model=AlertListResponse,
    summary="Alertas ativos do usuario",
    description="Lista apenas alertas ativos destinados ao usuario",
)
async def list_user_active_alerts(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """
    Lista alertas ativos do usuario.

    Args:
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Lista de alertas ativos
    """
    service = AlertService(db)
    tenant_id = _get_tenant_id(current_user)
    user_roles = _get_user_roles(current_user)

    alerts = await service.get_active_alerts(
        tenant_id=tenant_id,
        user_id=str(current_user.id),
        user_roles=user_roles,
    )

    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=len(alerts),
    )


@router.post(
    "/alertas/{alert_id}/acknowledge",
    response_model=AlertResponse,
    summary="Confirmar alerta",
    description="Confirma recebimento de um alerta",
    status_code=201,
)
async def acknowledge_alert(
    alert_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Confirma recebimento de alerta.

    Args:
        alert_id: ID do alerta
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Alerta atualizado

    Raises:
        HTTPException 404: Se nao encontrado
    """
    service = AlertService(db)
    tenant_id = _get_tenant_id(current_user)

    try:
        alert = await service.acknowledge(
            alert_id=alert_id,
            user_id=str(current_user.id),
            tenant_id=tenant_id,
        )

        logger.info(f"Alerta confirmado por {current_user.email}: {alert_id}")

        return AlertResponse.model_validate(alert)

    except AlertNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta nao encontrado",
        )


@router.post(
    "/alertas",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar alerta",
    description="Cria e dispara um novo alerta",
)
async def create_alert(
    data: AlertCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Cria e dispara um novo alerta.

    O alerta e automaticamente transmitido via WebSocket para os destinatarios.

    Args:
        data: Dados do alerta
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Alerta criado
    """
    service = AlertService(db)
    tenant_id = _get_tenant_id(current_user)

    alert = await service.create_and_broadcast(
        data=data,
        tenant_id=tenant_id,
    )

    logger.info(f"Alerta criado por {current_user.email}: {alert.id} [{alert.severity}]")

    return AlertResponse.model_validate(alert)
