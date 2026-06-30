"""
My Schedules Controller — Consulta de escalas do funcionario.

Endpoints:
- GET /portal/my-schedules
- GET /portal/my-schedules/current-month
- GET /portal/my-schedules/next-shift
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId
from modules.people_management.employee_portal.schemas.schedule import (
    MyScheduleResponse,
    MyShiftResponse,
)
from modules.people_management.employee_portal.services.document_view_service import (
    DocumentViewService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Escalas"])


@router.get(
    "/my-schedules",
    response_model=MyScheduleResponse,
    summary="Minha escala",
    description="Retorna a escala do funcionario para o mes/ano especificado.",
)
async def get_my_schedules(
    employee_id: CurrentEmployeeId,
    month: int = Query(default=None, ge=1, le=12, description="Mes (1-12)"),
    year: int = Query(default=None, ge=2020, le=2030, description="Ano"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna escala do funcionario autenticado."""
    service = DocumentViewService(db)
    schedule = await service.get_my_schedules(
        employee_id=employee_id,
        month=month,
        year=year,
    )
    return MyScheduleResponse(**schedule)


@router.get(
    "/my-schedules/current-month",
    response_model=MyScheduleResponse,
    summary="Escala do mes atual",
    description="Atalho para retornar a escala do mes corrente.",
)
async def get_current_month_schedule(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna escala do mes atual do funcionario autenticado."""
    now = datetime.utcnow()
    service = DocumentViewService(db)
    schedule = await service.get_my_schedules(
        employee_id=employee_id,
        month=now.month,
        year=now.year,
    )
    return MyScheduleResponse(**schedule)


@router.get(
    "/my-schedules/next-shift",
    response_model=MyShiftResponse,
    summary="Proximo turno",
    description="Retorna dados do proximo turno agendado do funcionario.",
)
async def get_next_shift(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna o proximo turno agendado do funcionario autenticado."""
    try:
        service = DocumentViewService(db)
        shift = await service.get_next_shift(employee_id=employee_id)
        if shift:
            return MyShiftResponse(**shift)
    except Exception as e:
        logger.warning(f"Erro ao buscar proximo turno: {e}")

    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Nenhum turno futuro encontrado.",
    )
