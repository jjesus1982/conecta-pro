"""
Controller (endpoints) para Shift.
"""

import asyncio
from datetime import date
from typing import Any
from uuid import UUID  # [Operacoes] tipar path id -> 500 (uuid cast) vira 422

from fastapi import Response, APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger
from core.rate_limit import BULK_LIMIT, limiter
from modules.operacional.models.shift import ShiftStatus
from modules.operacional.permissions import Permission, require_operacional_permission
from modules.operacional.publishers import publish_turno_encerrado, publish_turno_iniciado
from modules.operacional.repositories.shift_repository import ShiftRepository
from modules.operacional.schemas.shift import (
    ShiftBulkOperationResult,
    ShiftBulkUpdate,
    ShiftCheckIn,
    ShiftCheckOut,
    ShiftCreate,
    ShiftFilter,
    ShiftListResponse,
    ShiftResponse,
    ShiftUpdate,
)

router = APIRouter(prefix="/shifts", tags=["Operations - Shifts"])


@router.post(
    "/",
    response_model=ShiftResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.SHIFTS_CREATE)],
)
async def create_shift(
    data: ShiftCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ShiftResponse:
    """
    Cria um novo turno.
    """
    repo = ShiftRepository(db)
    shift: Any = await repo.create(data)

    logger.info(
        "Shift criado com sucesso",
        action="create_shift",
        shift_id=str(shift.id),
        scale_id=str(data.scale_id),
        post_id=str(data.post_id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return ShiftResponse.model_validate(shift)


@router.get(
    "/",
    response_model=ShiftListResponse,
    dependencies=[require_operacional_permission(Permission.SHIFTS_VIEW_ALL, Permission.SHIFTS_VIEW_OWN)],
)
async def list_shifts(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(50, ge=1, le=200, description="Itens por página"),
    scale_id: str | None = None,
    employee_id: str | None = None,
    post_id: str | None = None,
    status_filter: ShiftStatus | None = Query(None, alias="status"),
    start_date: date | None = None,
    end_date: date | None = None,
    is_holiday: bool | None = None,
    is_night_shift: bool | None = None,
    is_off_day: bool | None = None,
    is_filled: bool | None = None,
    needs_substitution: bool | None = None,
) -> ShiftListResponse:
    """
    Lista turnos com filtros e paginação.
    """
    repo = ShiftRepository(db)

    filters = ShiftFilter(
        scale_id=scale_id,
        employee_id=employee_id,
        post_id=post_id,
        status=status_filter,
        start_date=start_date,
        end_date=end_date,
        is_holiday=is_holiday,
        is_night_shift=is_night_shift,
        is_off_day=is_off_day,
        is_filled=is_filled,
        needs_substitution=needs_substitution,
    )

    shifts: list[Any]
    total: int
    shifts, total = await repo.list(filters=filters, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size

    return ShiftListResponse(
        items=[ShiftResponse.model_validate(shift) for shift in shifts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/today",
    dependencies=[require_operacional_permission(Permission.SHIFTS_VIEW_ALL, Permission.SHIFTS_VIEW_OWN)],
)
async def get_today_shifts(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    post_id: str | None = None,
) -> ShiftListResponse:
    """
    Lista turnos do dia atual.
    """
    repo = ShiftRepository(db)
    today = date.today()

    filters = ShiftFilter(
        start_date=today,
        end_date=today,
        post_id=post_id,
    )

    shifts: list[Any]
    total: int
    shifts, total = await repo.list(filters=filters, page=1, page_size=100)

    return ShiftListResponse(
        items=[ShiftResponse.model_validate(shift) for shift in shifts],
        total=total,
        page=1,
        page_size=100,
        total_pages=1,
    )


@router.get(
    "/scale/{scale_id}",
    response_model=list[ShiftResponse],
    dependencies=[require_operacional_permission(Permission.SHIFTS_VIEW_ALL, Permission.SHIFTS_VIEW_OWN)],
)
async def get_shifts_by_scale(
    scale_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> list[ShiftResponse]:
    """
    Lista todos os turnos de uma escala.
    """
    repo = ShiftRepository(db)
    shifts: list[Any] = await repo.get_by_scale(scale_id)

    return [ShiftResponse.model_validate(shift) for shift in shifts]


@router.get(
    "/{shift_id}",
    response_model=ShiftResponse,
    dependencies=[require_operacional_permission(Permission.SHIFTS_VIEW_ALL, Permission.SHIFTS_VIEW_OWN)],
)
async def get_shift(
    shift_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ShiftResponse:
    """
    Busca turno por ID.
    """
    repo = ShiftRepository(db)
    shift: Any = await repo.get_by_id(shift_id)

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turno não encontrado",
        )

    return ShiftResponse.model_validate(shift)


@router.patch(
    "/{shift_id}",
    response_model=ShiftResponse,
    dependencies=[require_operacional_permission(Permission.SHIFTS_CREATE)],
)
async def update_shift(
    shift_id: str,
    data: ShiftUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ShiftResponse:
    """
    Atualiza um turno.
    """
    repo = ShiftRepository(db)
    shift: Any = await repo.update(shift_id, data)

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turno não encontrado",
        )

    logger.info(
        "Shift atualizado com sucesso",
        action="update_shift",
        shift_id=str(shift.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return ShiftResponse.model_validate(shift)


@router.post(
    "/{shift_id}/check-in",
    response_model=ShiftResponse,
    dependencies=[require_operacional_permission(Permission.SHIFTS_CHECKIN)],
)
async def check_in(
    shift_id: str,
    data: ShiftCheckIn,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ShiftResponse:
    """
    Registra entrada no turno.
    """
    repo = ShiftRepository(db)
    shift: Any = await repo.check_in(shift_id, data.actual_start_time, data.notes)

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turno não encontrado",
        )

    logger.info(
        "Check-in registrado com sucesso",
        action="shift_check_in",
        shift_id=str(shift.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    asyncio.create_task(
        publish_turno_iniciado(
            shift_id=str(shift.id),
            employee_id=str(getattr(shift, "employee_id", "")),
            post_id=str(getattr(shift, "post_id", "")),
        )
    )
    return ShiftResponse.model_validate(shift)


@router.post(
    "/{shift_id}/check-out",
    response_model=ShiftResponse,
    dependencies=[require_operacional_permission(Permission.SHIFTS_CHECKIN)],
)
async def check_out(
    shift_id: str,
    data: ShiftCheckOut,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ShiftResponse:
    """
    Registra saída do turno.
    """
    repo = ShiftRepository(db)
    shift: Any = await repo.check_out(
        shift_id,
        data.actual_end_time,
        data.actual_break_minutes,
        data.notes,
    )

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turno não encontrado",
        )

    logger.info(
        "Check-out registrado com sucesso",
        action="shift_check_out",
        shift_id=str(shift.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    asyncio.create_task(
        publish_turno_encerrado(
            shift_id=str(shift.id),
            employee_id=str(getattr(shift, "employee_id", "")),
            post_id=str(getattr(shift, "post_id", "")),
        )
    )
    return ShiftResponse.model_validate(shift)


@router.post(
    "/{shift_id}/mark-missed",
    response_model=ShiftResponse,
    dependencies=[require_operacional_permission(Permission.SHIFTS_MARK_MISSED)],
)
async def mark_as_missed(
    shift_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    reason: str | None = Query(None, description="Motivo da falta"),
) -> ShiftResponse:
    """
    Marca turno como falta.
    """
    repo = ShiftRepository(db)
    shift: Any = await repo.mark_as_missed(shift_id, reason)

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turno não encontrado",
        )

    logger.info(
        "Turno marcado como falta",
        action="mark_shift_missed",
        shift_id=str(shift.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return ShiftResponse.model_validate(shift)


@router.delete(
    "/{shift_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_operacional_permission(Permission.SHIFTS_CREATE)],
)
async def delete_shift(
    shift_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove um turno (soft delete).
    """
    repo = ShiftRepository(db)
    deleted: bool = await repo.delete(shift_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turno não encontrado",
        )

    logger.info(
        "Shift deletado com sucesso",
        action="delete_shift",
        shift_id=shift_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )


@router.patch(
    "/bulk",
    response_model=ShiftBulkOperationResult,
    dependencies=[require_operacional_permission(Permission.SHIFTS_CREATE)],
)
@limiter.limit(BULK_LIMIT)
async def bulk_update_shifts(
    request: Request,
    response: Response,  # exigido pelo slowapi
    data: ShiftBulkUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> ShiftBulkOperationResult:
    """
    Atualiza múltiplos turnos em lote.

    Útil para atribuir funcionários a múltiplos turnos de uma vez,
    alterar status em massa, ou outras operações em lote.

    Retorna contagem de sucessos e erros.
    """
    repo = ShiftRepository(db)
    result: dict[str, int] = await repo.bulk_update(data.items)

    logger.info(
        "Bulk update de turnos",
        action="bulk_update_shifts",
        user_id=str(current_user.id),
        user_email=current_user.email,
        requested_count=len(data.items),
        success_count=result["success_count"],
        error_count=result["error_count"],
    )

    return ShiftBulkOperationResult(**result)
