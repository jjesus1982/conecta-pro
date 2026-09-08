"""Controller para TimeSheet (Folha de Ponto)."""
# pylint: disable=unused-argument

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_roles
from core.database import get_db
from modules.hr.time_tracking.models import TimeSheetStatus
from modules.hr.time_tracking.repositories import TimeSheetRepository
from modules.hr.time_tracking.schemas import (
    TimeSheetFilter,
    TimeSheetListResponse,
    TimeSheetResponse,
    TimeSheetStats,
)

router = APIRouter(
    prefix="/time-sheets",
    tags=["Ponto Eletrônico - Folha de Ponto"],
)


@router.get(
    "/",
    response_model=list[TimeSheetListResponse],
    summary="Listar folhas de ponto",
)
async def list_time_sheets(  # pylint: disable=too-many-locals
    employee_id: str | None = None,
    reference_month: int | None = Query(None, ge=1, le=12),
    reference_year: int | None = Query(None, ge=2000, le=2100),
    sheet_status: TimeSheetStatus | None = Query(None, alias="status"),
    condominium_id: str | None = None,
    department_id: str | None = None,
    has_pending_issues: bool | None = None,
    is_fully_approved: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lista folhas de ponto com filtros."""
    repo = TimeSheetRepository(db)

    filters = TimeSheetFilter(
        employee_id=employee_id,
        reference_month=reference_month,
        reference_year=reference_year,
        status=sheet_status,
        condominium_id=condominium_id,
        department_id=department_id,
        has_pending_issues=has_pending_issues,
        is_fully_approved=is_fully_approved,
    )

    sheets, _total = await repo.list(filters, skip, limit)

    return sheets


@router.get(
    "/stats",
    response_model=TimeSheetStats,
    summary="Estatísticas de folhas",
)
async def get_time_sheet_stats(
    condominium_id: str | None = None,
    reference_month: int | None = Query(None, ge=1, le=12),
    reference_year: int | None = Query(None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["admin", "rh"])),
):
    """Retorna estatísticas consolidadas das folhas de ponto."""
    repo = TimeSheetRepository(db)

    stats = await repo.get_stats(
        condominium_id=condominium_id,
        reference_month=reference_month,
        reference_year=reference_year,
    )

    return TimeSheetStats(**stats)


@router.get(
    "/{sheet_id}",
    response_model=TimeSheetResponse,
    summary="Buscar folha por ID",
)
async def get_time_sheet(
    sheet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retorna detalhes completos de uma folha de ponto."""
    repo = TimeSheetRepository(db)

    sheet = await repo.get_by_id(sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folha de ponto não encontrada",
        )

    return sheet

