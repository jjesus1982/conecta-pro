"""Controller para JobPosition."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.recruitment.models.job_position import (
    Department,
    PositionLevel,
    PositionStatus,
    PositionType,
    WorkModel,
)
from modules.recruitment.schemas.job_position import (
    JobPositionFilter,
    JobPositionListResponse,
    JobPositionResponse,
)
from modules.recruitment.services.job_position_service import JobPositionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/job-positions", tags=["Recruitment - Vagas"])


@router.get("", include_in_schema=False)  # espelho sem barra final (front chama sem barra)
@router.get(
    "/",
    response_model=JobPositionListResponse,
    summary="Listar vagas",
)
async def list_positions(  # pylint: disable=too-many-locals
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: PositionStatus | None = Query(None, alias="status"),
    position_type: PositionType | None = None,
    position_level: PositionLevel | None = None,
    department: Department | None = None,
    work_model: WorkModel | None = None,
    city: str | None = None,
    state: str | None = None,
    is_urgent: bool | None = None,
    condominium_id: str | None = None,
    search: str | None = None,
    order_by: str = "created_at",
    order_desc: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> JobPositionListResponse:
    """Lista vagas com filtros e paginação."""
    service = JobPositionService(db)

    filters = JobPositionFilter(
        status=status_filter,
        position_type=position_type,
        position_level=position_level,
        department=department,
        work_model=work_model,
        city=city,
        state=state,
        is_urgent=is_urgent,
        condominium_id=condominium_id,
        search=search,
    )

    positions, total = await service.list_with_filters(filters, skip, limit, order_by, order_desc)

    return JobPositionListResponse(
        items=[JobPositionResponse.model_validate(p) for p in positions],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/open",
    response_model=JobPositionListResponse,
    summary="Listar vagas abertas",
)
async def list_open_positions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> JobPositionListResponse:
    """Lista vagas abertas para candidaturas."""
    service = JobPositionService(db)
    positions = await service.get_open_positions(condominium_id, skip, limit)

    return JobPositionListResponse(
        items=[JobPositionResponse.model_validate(p) for p in positions],
        total=len(positions),
        skip=skip,
        limit=limit,
    )


