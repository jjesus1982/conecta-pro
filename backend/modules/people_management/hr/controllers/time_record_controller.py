"""
Controller de Ponto Eletronico (Time Records) — Departamento Pessoal.

Endpoints completos para gestao de registros de ponto:
- Listagem com filtros e paginacao
- Clock-in / Clock-out
- Lancamento manual (admin/DP)
- Atualizacao e justificativa
- Resumo mensal por funcionario
- Registros diarios
"""

import asyncio
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.publishers import publish_ponto_registrado
from modules.people_management.hr.schemas.time_record import (
    ClockOutRequest,
    DailyRecordsResponse,
    TimeRecordCreate,
    TimeRecordListResponse,
    TimeRecordResponse,
    TimeRecordUpdate,
)
from modules.people_management.hr.services.time_record_service import TimeRecordService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/time-records", tags=["DP - Ponto Eletrônico"])


@router.get(
    "",
    summary="Listar Registros de Ponto",
    response_model=TimeRecordListResponse,
    description="Retorna lista paginada de registros de ponto com filtros por funcionário, período e status.",
)
async def list_time_records(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = Query(None, description="Filtro por funcionário"),
    date_from: date | None = Query(None, description="Data inicial (YYYY-MM-DD)"),
    date_to: date | None = Query(None, description="Data final (YYYY-MM-DD)"),
    status: str | None = Query(None, description="regular|falta|atestado|feriado|compensacao|inconsistencia"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """Lista registros de ponto com filtros e paginação."""
    service = TimeRecordService(db)
    return await service.list_records(
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    summary="Lançamento Manual de Ponto",
    response_model=TimeRecordResponse,
    status_code=201,
    description="Retorna lista paginada de registros de ponto com filtros por funcionário, período e status.",
)
async def create_manual_record(
    data: TimeRecordCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria lançamento manual de ponto (uso por admin/DP)."""
    service = TimeRecordService(db)
    result = await service.create_manual(
        data=data.model_dump(),
        created_by=str(current_user.id),
    )
    await db.commit()
    asyncio.create_task(
        publish_ponto_registrado(
            employee_id=str(getattr(data, "employee_id", "")),
            tipo="manual",
            record_id=str(getattr(result, "id", "")),
        )
    )
    return result


@router.get(
    "/{record_id}",
    summary="Buscar Registro de Ponto",
    response_model=TimeRecordResponse,
    description="Retorna lista paginada de registros de ponto com filtros por funcionário, período e status.",
)
async def get_time_record(
    record_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um registro de ponto."""
    service = TimeRecordService(db)
    record = await service.get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Registro de ponto não encontrado")
    return record


@router.patch(
    "/{record_id}",
    summary="Atualizar/Justificar Registro",
    response_model=TimeRecordResponse,
    description="Retorna lista paginada de registros de ponto com filtros por funcionário, período e status.",
)
async def update_time_record(
    record_id: str,
    data: TimeRecordUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza/justifica um registro de ponto."""
    service = TimeRecordService(db)
    try:
        record = await service.update_record(
            record_id=record_id,
            data=data.model_dump(exclude_unset=True),
            updated_by=str(current_user.id),
        )
    except ValueError as e:  # tipo de batida inválido era 500
        raise HTTPException(status_code=400, detail=str(e))
    if not record:
        raise HTTPException(status_code=404, detail="Registro de ponto não encontrado")
    await db.commit()
    return record
