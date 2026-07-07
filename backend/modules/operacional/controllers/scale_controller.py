"""
Controller (endpoints) para Scale.
"""

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.cache import cache_response
from core.cache.utils import invalidate_on_create, invalidate_on_delete, invalidate_on_update
from core.database import get_db
from core.logging import logger
from core.rate_limit import CRITICAL_LIMIT, limiter
from modules.operacional.models.scale import ScaleStatus, ScaleType
from modules.operacional.permissions import Permission, require_operacional_permission
from modules.operacional.publishers import publish_escala_publicada
from modules.operacional.repositories.scale_repository import ScaleRepository
from modules.operacional.repositories.shift_repository import ShiftRepository
from modules.operacional.schemas.scale import (
    ScaleApproveRequest,
    ScaleCreate,
    ScaleFilter,
    ScaleGenerateRequest,
    ScaleListResponse,
    ScalePublishRequest,
    ScaleRejectRequest,
    ScaleResponse,
    ScaleStats,
    ScaleUpdate,
)
from modules.operacional.services.auto_scale_service import AutoScaleService
from modules.operacional.services.scale_generator import scale_generator

router = APIRouter(prefix="/scales", tags=["Operations - Scales"])


@router.post(
    "/",
    response_model=ScaleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
async def create_scale(
    data: ScaleCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleResponse:
    """
    Cria uma nova escala.

    Cria apenas a escala, sem turnos. Use /generate para gerar turnos.
    """
    repo = ScaleRepository(db)

    # Verificar se já existe escala para o período
    existing: Any = await repo.get_by_post_and_period(data.post_id, data.month, data.year)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe escala para este posto/período",
        )

    scale: Any = await repo.create(data, created_by=current_user.id)

    # Invalidar cache
    await invalidate_on_create("scale", [("post", data.post_id)])

    logger.info(
        "Scale criada com sucesso",
        action="create_scale",
        scale_id=str(scale.id),
        post_id=str(data.post_id),
        month=data.month,
        year=data.year,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return ScaleResponse.model_validate(scale)


@router.post(
    "/generate",
    response_model=ScaleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
@limiter.limit(CRITICAL_LIMIT)
async def generate_scale(
    request: Request,
    data: ScaleGenerateRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleResponse:
    """
    Gera escala automaticamente com IA.

    Cria a escala e todos os turnos baseado no tipo de escala
    e lista de funcionários.
    """
    scale_repo = ScaleRepository(db)
    shift_repo = ShiftRepository(db)

    # Verificar se já existe escala para o período
    existing: Any = await scale_repo.get_by_post_and_period(data.post_id, data.month, data.year)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe escala para este posto/período",
        )

    # Criar escala
    scale_data = ScaleCreate(
        post_id=data.post_id,
        scale_type=data.scale_type,
        month=data.month,
        year=data.year,
        config=data.config,
    )
    scale: Any = await scale_repo.create(scale_data, created_by=current_user.id)

    # Gerar turnos com IA
    shifts_data: list[dict[str, Any]] = scale_generator.generate(
        scale_id=scale.id,
        post_id=data.post_id,
        scale_type=data.scale_type,
        month=data.month,
        year=data.year,
        employee_ids=data.employee_ids,
        config=data.config,
    )

    # Criar turnos em lote
    await shift_repo.create_bulk(shifts_data)

    # Atualizar métricas da escala
    scale = await scale_repo.update_metrics(scale.id)

    logger.info(f"Scale gerada por {current_user.email}: {scale.id} ({len(shifts_data)} turnos)")

    return ScaleResponse.model_validate(scale)


@router.get(
    "/",
    response_model=ScaleListResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_VIEW_ALL, Permission.SCALES_VIEW_OWN)],
)
async def list_scales(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    post_id: str | None = None,
    scale_type: ScaleType | None = None,
    status_filter: ScaleStatus | None = Query(None, alias="status"),
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020, le=2100),
    is_current_month: bool | None = None,
    created_by: str | None = Query(None, description="Filtrar por criador"),
) -> ScaleListResponse:
    """
    Lista escalas com filtros e paginação.
    """
    repo = ScaleRepository(db)

    filters = ScaleFilter(
        post_id=post_id,
        scale_type=scale_type,
        status=status_filter,
        month=month,
        year=year,
        is_current_month=is_current_month,
        created_by=created_by,
    )

    scales: list[Any]
    total: int
    scales, total = await repo.list(filters=filters, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size

    # Enriquecer com post_name (buscar todos os postos incluindo inativos)
    from sqlalchemy import text

    post_ids = list({str(s.post_id) for s in scales if s.post_id})
    post_names: dict[str, str] = {}
    if post_ids:
        result = await db.execute(
            text("SELECT id::text, name FROM posts WHERE id::text = ANY(:ids)"),
            {"ids": post_ids},
        )
        post_names = {row[0]: row[1] for row in result.fetchall()}

    items = []
    for scale in scales:
        resp = ScaleResponse.model_validate(scale)
        resp.post_name = post_names.get(str(scale.post_id), "Posto removido")
        items.append(resp)

    return ScaleListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/stats",
    response_model=ScaleStats,
    dependencies=[require_operacional_permission(Permission.SCALES_VIEW_ALL, Permission.SCALES_VIEW_OWN)],
)
@cache_response(ttl=180, prefix="api:scale")  # 3 minutos
async def get_scale_stats(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleStats:
    """
    Obtém estatísticas de escalas.

    Cache: 3 minutos
    """
    repo = ScaleRepository(db)
    return await repo.get_stats()


@router.get(
    "/{scale_id}",
    response_model=ScaleResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_VIEW_ALL, Permission.SCALES_VIEW_OWN)],
)
async def get_scale(
    scale_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleResponse:
    """
    Busca escala por ID.
    """
    repo = ScaleRepository(db)
    scale: Any = await repo.get_by_id(str(scale_id))

    if not scale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada",
        )

    return ScaleResponse.model_validate(scale)


@router.patch(
    "/{scale_id}",
    response_model=ScaleResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
async def update_scale(
    scale_id: UUID,
    data: ScaleUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleResponse:
    """
    Atualiza uma escala.

    Só é possível editar escalas em rascunho ou pendentes de aprovação.
    """
    repo = ScaleRepository(db)
    scale: Any = await repo.update(str(scale_id), data)

    if not scale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada ou não pode ser editada",
        )

    # Invalidar cache
    await invalidate_on_update("scale", str(scale_id), [("post", scale.post_id)])

    logger.info(
        "Scale atualizada com sucesso",
        action="update_scale",
        scale_id=str(scale.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return ScaleResponse.model_validate(scale)


@router.post(
    "/{scale_id}/submit",
    response_model=ScaleResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
async def submit_scale_for_approval(
    scale_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleResponse:
    """
    Envia escala para aprovação.
    """
    repo = ScaleRepository(db)
    scale: Any = await repo.get_by_id(str(scale_id))

    if not scale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada",
        )

    if scale.status != ScaleStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Escala não está em rascunho",
        )

    update = ScaleUpdate(status=ScaleStatus.PENDING_APPROVAL)
    scale = await repo.update(str(scale_id), update)

    logger.info(
        "Scale enviada para aprovação",
        action="submit_scale_for_approval",
        scale_id=str(scale.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return ScaleResponse.model_validate(scale)


@router.post(
    "/{scale_id}/approve",
    response_model=ScaleResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_APPROVE)],
)
async def approve_scale(
    scale_id: UUID,
    data: ScaleApproveRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleResponse:
    """
    Aprova uma escala.
    """
    repo = ScaleRepository(db)
    scale: Any = await repo.approve(str(scale_id), current_user.id, data.notes)

    if not scale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada ou não pode ser aprovada",
        )

    logger.info(
        "Scale aprovada com sucesso",
        action="approve_scale",
        scale_id=str(scale.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return ScaleResponse.model_validate(scale)


@router.post(
    "/{scale_id}/reject",
    response_model=ScaleResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_APPROVE)],
)
async def reject_scale(
    scale_id: UUID,
    data: ScaleRejectRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleResponse:
    """
    Rejeita uma escala em aprovação.

    A escala volta para status DRAFT para correções.
    """
    repo = ScaleRepository(db)
    scale: Any = await repo.reject(str(scale_id), current_user.id, data.reason, data.notes)

    if not scale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada ou não pode ser rejeitada",
        )

    logger.info(
        "Scale rejeitada",
        action="reject_scale",
        scale_id=scale_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
        reason=data.reason,
    )
    return ScaleResponse.model_validate(scale)


@router.post(
    "/{scale_id}/publish",
    response_model=ScaleResponse,
    dependencies=[require_operacional_permission(Permission.SCALES_PUBLISH)],
)
async def publish_scale(
    scale_id: UUID,
    data: ScalePublishRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ScaleResponse:
    """
    Publica uma escala.

    Após publicação, os funcionários são notificados.
    """
    repo = ScaleRepository(db)

    # Guard honesto: não publicar escala vazia (total_shifts=0 / sem turnos gerados)
    scale_check: Any = await repo.get_by_id(str(scale_id))
    if not scale_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada ou não pode ser publicada",
        )
    if len(scale_check.shifts) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="escala sem turnos — gere os turnos antes de publicar",
        )

    scale: Any = await repo.publish(str(scale_id), current_user.id)

    if not scale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada ou não pode ser publicada",
        )

    # PENDENTE: Enviar notificações aos funcionários
    if data.notify_employees:
        logger.info(
            "Notificação de funcionários solicitada",
            action="notify_employees",
            scale_id=str(scale.id),
            channels=data.notification_channels,
        )

    logger.info(
        "Scale publicada com sucesso",
        action="publish_scale",
        scale_id=str(scale.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    asyncio.create_task(
        publish_escala_publicada(
            escala_id=str(scale.id),
            cliente_id=str(scale.client_id) if hasattr(scale, "client_id") and scale.client_id else None,
            competencia=f"{scale.year}-{scale.month:02d}"
            if hasattr(scale, "month") and hasattr(scale, "year")
            else None,
            total_turnos=getattr(scale, "total_shifts", 0),
            funcionarios=[],
        )
    )
    return ScaleResponse.model_validate(scale)


@router.delete(
    "/{scale_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
async def delete_scale(
    scale_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove uma escala (soft delete).

    Só é possível deletar escalas em rascunho.
    """
    repo = ScaleRepository(db)

    # Buscar scale antes de deletar para invalidar cache do post
    scale: Any = await repo.get_by_id(str(scale_id))
    if not scale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não encontrada",
        )

    post_id: str = scale.post_id
    deleted: bool = await repo.delete(str(scale_id))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escala não pode ser deletada",
        )

    # Invalidar cache
    await invalidate_on_delete("scale", str(scale_id), [("post", post_id)])

    logger.info(
        "Scale deletada com sucesso",
        action="delete_scale",
        scale_id=scale_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )


@router.post(
    "/auto-generate",
    status_code=status.HTTP_200_OK,
    dependencies=[require_operacional_permission(Permission.SCALES_CREATE)],
)
@limiter.limit(CRITICAL_LIMIT)
async def auto_generate_scales(
    request: Request,
    response: Response,  # exigido pelo slowapi p/ endpoints que retornam dict
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    month: int | None = Query(None, ge=1, le=12, description="Mês (se não especificado, usa mês atual)"),
    year: int | None = Query(None, ge=2020, le=2100, description="Ano (se não especificado, usa ano atual)"),
) -> dict[str, Any]:
    """
    Gera escalas automaticamente para todos os postos com alocações ativas.

    Se mês/ano não especificados, gera para o mês atual.
    Útil para inicializar o sistema ou gerar escalas mensalmente.
    """
    service = AutoScaleService(db)

    result: dict[str, Any]
    if month and year:
        result = await service.generate_scales_for_month(month, year, created_by=current_user.id)
    else:
        result = await service.generate_scales_for_current_month(created_by=current_user.id)

    logger.info(
        "Geração automática de escalas executada",
        action="auto_generate_scales",
        user_id=str(current_user.id),
        user_email=current_user.email,
        result=result,
    )
    return result
