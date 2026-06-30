"""
Controller (endpoints) para Comunicados.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score Target: 99+/100
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.communication.models.announcement import (
    AnnouncementCategory,
    AnnouncementPriority,
    AnnouncementStatus,
    AnnouncementTargetType,
)
from modules.operacional.communication.schemas.communication_schemas import (
    AnnouncementAcknowledgeRequest,
    AnnouncementCreate,
    AnnouncementFilter,
    AnnouncementListResponse,
    AnnouncementPublishRequest,
    AnnouncementReadStats,
    AnnouncementResponse,
    AnnouncementUpdate,
)
from modules.operacional.communication.services.announcement_service import (
    AnnouncementNotFoundError,
    AnnouncementPublishError,
    AnnouncementService,
)
from modules.operacional.publishers import publish_comunicado_publicado

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Operacional - Comunicados"])


def _get_tenant_id(user: CurrentActiveUser) -> str:
    """Extrai tenant_id do usuario."""
    return getattr(user, "tenant_id", str(user.id))


def _get_user_roles(user: CurrentActiveUser) -> list[str]:
    """Extrai roles do usuario."""
    role = getattr(user, "role", None)
    return [role] if role else []


@router.post(
    "/comunicados",
    response_model=AnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar comunicado",
    description="Cria um novo comunicado (rascunho ou agendado)",
)
async def create_announcement(
    data: AnnouncementCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AnnouncementResponse:
    """
    Cria um novo comunicado.

    O comunicado e criado como rascunho ou agendado se publish_at for fornecido.

    Args:
        data: Dados do comunicado
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Comunicado criado
    """
    service = AnnouncementService(db)
    tenant_id = _get_tenant_id(current_user)

    announcement = await service.create(
        data=data,
        tenant_id=tenant_id,
        created_by=str(current_user.id),
    )

    logger.info(
        "Comunicado criado com sucesso - id=%s user=%s",
        str(announcement.id),
        str(current_user.id),
    )
    return AnnouncementResponse.model_validate(announcement)


@router.get(
    "/comunicados",
    response_model=AnnouncementListResponse,
    summary="Listar comunicados",
    description="Lista comunicados com filtros e paginacao",
)
async def list_announcements(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Pagina atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por pagina"),
    status_filter: AnnouncementStatus | None = Query(None, alias="status"),
    priority: AnnouncementPriority | None = None,
    category: AnnouncementCategory | None = None,
    target_type: AnnouncementTargetType | None = None,
    requires_acknowledgment: bool | None = None,
    search: str | None = Query(None, max_length=100),
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> AnnouncementListResponse:
    """
    Lista comunicados com filtros.

    Args:
        current_user: Usuario autenticado
        db: Sessao do banco de dados
        page: Pagina atual
        page_size: Itens por pagina
        status_filter: Filtro por status
        priority: Filtro por prioridade
        category: Filtro por categoria
        target_type: Filtro por tipo de destinatario
        requires_acknowledgment: Filtro por confirmacao requerida
        search: Busca textual
        created_after: Criados apos
        created_before: Criados antes

    Returns:
        Lista paginada de comunicados
    """
    service = AnnouncementService(db)
    tenant_id = _get_tenant_id(current_user)

    filters = AnnouncementFilter(
        status=status_filter,
        priority=priority,
        category=category,
        target_type=target_type,
        requires_acknowledgment=requires_acknowledgment,
        search=search,
        created_after=created_after,
        created_before=created_before,
    )

    announcements, total = await service.list(
        tenant_id=tenant_id,
        filters=filters,
        page=page,
        page_size=page_size,
    )

    total_pages = (total + page_size - 1) // page_size

    return AnnouncementListResponse(
        items=[AnnouncementResponse.model_validate(a) for a in announcements],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/comunicados/nao-lidos",
    response_model=AnnouncementListResponse,
    summary="Comunicados nao lidos",
    description="Lista comunicados nao lidos pelo usuario atual",
)
async def list_unread_announcements(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AnnouncementListResponse:
    """
    Lista comunicados nao lidos pelo usuario.

    Args:
        current_user: Usuario autenticado
        db: Sessao do banco de dados
        page: Pagina atual
        page_size: Itens por pagina

    Returns:
        Lista de comunicados nao lidos
    """
    service = AnnouncementService(db)
    tenant_id = _get_tenant_id(current_user)
    user_roles = _get_user_roles(current_user)

    announcements, total = await service.get_for_user(
        tenant_id=tenant_id,
        user_id=str(current_user.id),
        user_roles=user_roles,
        only_unread=True,
        page=page,
        page_size=page_size,
    )

    total_pages = (total + page_size - 1) // page_size

    return AnnouncementListResponse(
        items=[AnnouncementResponse.model_validate(a) for a in announcements],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/comunicados/{announcement_id}",
    response_model=AnnouncementResponse,
    summary="Buscar comunicado",
    description="Busca comunicado por ID",
)
async def get_announcement(
    announcement_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AnnouncementResponse:
    """
    Busca comunicado por ID.

    Args:
        announcement_id: ID do comunicado
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Comunicado encontrado

    Raises:
        HTTPException 404: Se nao encontrado
    """
    service = AnnouncementService(db)
    tenant_id = _get_tenant_id(current_user)

    try:
        announcement = await service.get_by_id(announcement_id, tenant_id)

        # Marca como lido automaticamente
        await service.mark_as_read(
            announcement_id=announcement_id,
            user_id=str(current_user.id),
        )

        return AnnouncementResponse.model_validate(announcement)

    except AnnouncementNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comunicado nao encontrado",
        )


@router.patch(
    "/comunicados/{announcement_id}",
    response_model=AnnouncementResponse,
    summary="Atualizar comunicado",
    description="Atualiza um comunicado (apenas rascunhos)",
)
async def update_announcement(
    announcement_id: str,
    data: AnnouncementUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AnnouncementResponse:
    """
    Atualiza um comunicado.

    Apenas comunicados em rascunho ou agendados podem ser editados.

    Args:
        announcement_id: ID do comunicado
        data: Dados para atualizacao
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Comunicado atualizado

    Raises:
        HTTPException 404: Se nao encontrado
        HTTPException 400: Se nao puder ser editado
    """
    service = AnnouncementService(db)
    tenant_id = _get_tenant_id(current_user)

    try:
        announcement = await service.update(announcement_id, data, tenant_id)
        logger.info(f"Comunicado atualizado por {current_user.email}: {announcement_id}")
        return AnnouncementResponse.model_validate(announcement)

    except AnnouncementNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comunicado nao encontrado ou nao pode ser editado",
        )


@router.delete(
    "/comunicados/{announcement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover comunicado",
    description="Remove um comunicado (soft delete)",
)
async def delete_announcement(
    announcement_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove um comunicado.

    Args:
        announcement_id: ID do comunicado
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Raises:
        HTTPException 404: Se nao encontrado
    """
    service = AnnouncementService(db)
    tenant_id = _get_tenant_id(current_user)

    try:
        await service.delete(announcement_id, tenant_id)
        logger.info(f"Comunicado removido por {current_user.email}: {announcement_id}")

    except AnnouncementNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comunicado nao encontrado",
        )


@router.post(
    "/comunicados/{announcement_id}/publicar",
    response_model=AnnouncementResponse,
    summary="Publicar comunicado",
    description="Publica ou agenda um comunicado",
    status_code=201,
)
async def publish_announcement(
    announcement_id: str,
    request_data: AnnouncementPublishRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AnnouncementResponse:
    """
    Publica ou agenda um comunicado.

    Args:
        announcement_id: ID do comunicado
        request_data: Dados de publicacao
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Comunicado publicado/agendado

    Raises:
        HTTPException 404: Se nao encontrado
        HTTPException 400: Se nao puder ser publicado
    """
    service = AnnouncementService(db)
    tenant_id = _get_tenant_id(current_user)

    try:
        announcement = await service.publish(
            announcement_id=announcement_id,
            tenant_id=tenant_id,
            published_by=str(current_user.id),
            schedule_at=request_data.schedule_at,
        )

        action = "agendado" if request_data.schedule_at else "publicado"
        logger.info(f"Comunicado {action} por {current_user.email}: {announcement_id}")
        asyncio.create_task(
            publish_comunicado_publicado(
                announcement_id=str(announcement.id),
                titulo=str(getattr(announcement, "title", "") or getattr(announcement, "titulo", "")),
                tenant_id=str(getattr(announcement, "tenant_id", "") or ""),
            )
        )
        return AnnouncementResponse.model_validate(announcement)

    except AnnouncementNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comunicado nao encontrado",
        )
    except AnnouncementPublishError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/comunicados/{announcement_id}/confirmar",
    response_model=dict,
    summary="Confirmar leitura",
    description="Confirma leitura de comunicado que requer confirmacao",
    status_code=201,
)
async def acknowledge_announcement(
    announcement_id: str,
    request_data: AnnouncementAcknowledgeRequest,
    request: Request,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Confirma leitura de comunicado.

    Args:
        announcement_id: ID do comunicado
        request_data: Dados de confirmacao
        request: Request HTTP
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Status da confirmacao

    Raises:
        HTTPException 404: Se nao encontrado
    """
    service = AnnouncementService(db)
    tenant_id = _get_tenant_id(current_user)

    # Obtem IP e User-Agent
    ip_address = request_data.ip_address or request.client.host
    user_agent = request_data.user_agent or request.headers.get("user-agent")

    try:
        # Primeiro marca como lido
        await service.mark_as_read(
            announcement_id=announcement_id,
            user_id=str(current_user.id),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Depois confirma
        read = await service.acknowledge(
            announcement_id=announcement_id,
            user_id=str(current_user.id),
            tenant_id=tenant_id,
        )

        logger.info(f"Comunicado confirmado por {current_user.email}: {announcement_id}")

        return {
            "success": True,
            "acknowledged_at": read.acknowledged_at.isoformat(),
        }

    except AnnouncementNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comunicado nao encontrado",
        )


@router.get(
    "/comunicados/{announcement_id}/leituras",
    response_model=AnnouncementReadStats,
    summary="Estatisticas de leitura",
    description="Obtem estatisticas de leitura de um comunicado",
)
async def get_announcement_read_stats(
    announcement_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AnnouncementReadStats:
    """
    Obtem estatisticas de leitura de um comunicado.

    Args:
        announcement_id: ID do comunicado
        current_user: Usuario autenticado
        db: Sessao do banco de dados

    Returns:
        Estatisticas de leitura

    Raises:
        HTTPException 404: Se nao encontrado
    """
    service = AnnouncementService(db)
    tenant_id = _get_tenant_id(current_user)

    try:
        stats = await service.get_read_stats(announcement_id, tenant_id)
        return stats

    except AnnouncementNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comunicado nao encontrado",
        )
