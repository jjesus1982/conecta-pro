"""
Controller (endpoints) para TimeBank (Banco de Horas).
"""

import asyncio
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.cache import cache_response
from core.database import get_db
from core.logging import logger
from modules.operacional.models.time_bank import TimeBankEntryType, TimeBankStatus
from modules.operacional.permissions import Permission, require_operacional_permission
from modules.operacional.publishers import publish_banco_horas_criado
from modules.operacional.repositories.time_bank_repository import TimeBankRepository
from modules.operacional.schemas.time_bank import (
    TimeBankApprove,
    TimeBankCompensate,
    TimeBankCreate,
    TimeBankFilter,
    TimeBankListResponse,
    TimeBankReject,
    TimeBankResponse,
    TimeBankStats,
    TimeBankSummary,
    TimeBankUpdate,
)
from modules.operacional.services.time_bank_service import time_bank_service

router = APIRouter(prefix="/time-bank", tags=["Operations - Time Bank"])


@router.post(
    "/",
    response_model=TimeBankResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.TIMEBANK_CREATE)],
)
async def create_entry(
    data: TimeBankCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TimeBankResponse:
    """
    Cria uma nova entrada no banco de horas.

    Requer aprovação para ser efetivada.
    """
    repo = TimeBankRepository(db)

    # Calcular data de expiração se não fornecida
    if not data.expiration_date:
        data.expiration_date = time_bank_service.get_expiration_date(data.reference_date)

    entry = await repo.create(data)

    logger.info(
        f"Entrada no banco de horas criada por {current_user.email}: "
        f"funcionário {data.employee_id}, {data.hours}h ({data.entry_type.value})"
    )
    asyncio.create_task(
        publish_banco_horas_criado(
            entry_id=str(entry.id),
            employee_id=str(data.employee_id),
            hours=float(data.hours),
            entry_type=data.entry_type.value,
        )
    )
    return TimeBankResponse.model_validate(entry)


@router.get(
    "/",
    response_model=TimeBankListResponse,
    dependencies=[require_operacional_permission(Permission.TIMEBANK_VIEW_ALL, Permission.TIMEBANK_VIEW_OWN)],
)
async def list_entries(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    employee_id: str | None = None,
    entry_type: TimeBankEntryType | None = None,
    status_filter: TimeBankStatus | None = Query(None, alias="status"),
    shift_id: str | None = None,
    post_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    is_expired: bool | None = None,
    is_pending: bool | None = None,
) -> TimeBankListResponse:
    """
    Lista entradas do banco de horas com filtros e paginação.
    """
    repo = TimeBankRepository(db)

    filters = TimeBankFilter(
        employee_id=employee_id,
        entry_type=entry_type,
        status=status_filter,
        shift_id=shift_id,
        post_id=post_id,
        start_date=start_date,
        end_date=end_date,
        is_expired=is_expired,
        is_pending=is_pending,
    )

    entries, total = await repo.list(filters=filters, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size

    return TimeBankListResponse(
        items=[TimeBankResponse.model_validate(e) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/pending",
    response_model=list[TimeBankResponse],
    dependencies=[require_operacional_permission(Permission.TIMEBANK_APPROVE)],
)
async def get_pending_entries(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = None,
) -> list[TimeBankResponse]:
    """
    Lista entradas pendentes de aprovação.
    """
    repo = TimeBankRepository(db)

    filters = TimeBankFilter(
        employee_id=employee_id,
        status=TimeBankStatus.PENDING,
    )

    entries, _ = await repo.list(filters=filters, page=1, page_size=100)

    return [TimeBankResponse.model_validate(e) for e in entries]


@router.get(
    "/expiring",
    response_model=list[TimeBankResponse],
    dependencies=[require_operacional_permission(Permission.TIMEBANK_VIEW_ALL)],
)
async def get_expiring_entries(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=90, description="Dias até expiração"),
) -> list[TimeBankResponse]:
    """
    Lista entradas próximas da expiração.
    """
    repo = TimeBankRepository(db)

    # PENDENTE: Implementar filtro por data de expiração
    filters = TimeBankFilter(
        status=TimeBankStatus.APPROVED,
    )

    entries, _ = await repo.list(filters=filters, page=1, page_size=500)

    # Filtrar manualmente por enquanto
    limit_date = date.today() + timedelta(days=days)
    expiring = [e for e in entries if e.expiration_date and e.expiration_date <= limit_date]

    return [TimeBankResponse.model_validate(e) for e in expiring]


@router.get(
    "/stats",
    response_model=TimeBankStats,
    dependencies=[require_operacional_permission(Permission.TIMEBANK_VIEW_ALL)],
)
@cache_response(ttl=240, prefix="api:time_bank")  # 4 minutos
async def get_stats(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TimeBankStats:
    """
    Obtém estatísticas gerais do banco de horas.

    Cache: 4 minutos
    """
    repo = TimeBankRepository(db)
    return await repo.get_global_stats()


@router.get(
    "/alerts",
    dependencies=[require_operacional_permission(Permission.TIMEBANK_VIEW_ALL)],
)
async def get_expiration_alerts(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Obtém alertas de expiração de horas.
    """
    repo = TimeBankRepository(db)

    # Buscar todas as entradas aprovadas
    filters = TimeBankFilter(status=TimeBankStatus.APPROVED)
    entries, _ = await repo.list(filters=filters, page=1, page_size=1000)

    # Converter para dicionário e verificar alertas
    entries_dict: list[dict[str, Any]] = [
        {
            "id": str(e.id),
            "employee_id": str(e.employee_id),
            "hours": e.hours,
            "expiration_date": e.expiration_date,
        }
        for e in entries
        if e.expiration_date
    ]

    alerts = time_bank_service.check_expiration_alerts(entries_dict)

    return alerts


@router.post(
    "/compensate/{employee_id}",
    response_model=TimeBankResponse,
    dependencies=[require_operacional_permission(Permission.TIMEBANK_CREATE)],
)
async def compensate_hours(
    employee_id: str,
    data: TimeBankCompensate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TimeBankResponse:
    """
    Registra compensação de horas.

    Valida se o funcionário tem saldo suficiente.
    """
    repo = TimeBankRepository(db)

    # Obter saldo atual
    summary = await repo.get_summary(employee_id)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Funcionário não encontrado",
        )

    # Validar compensação
    validation: dict[str, Any] = time_bank_service.validate_compensation_request(
        summary.current_balance,
        data.hours,
        data.compensation_date,
    )

    if not validation["is_valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(validation["errors"][0] if validation["errors"] else "Validação falhou"),
        )

    # Criar entrada de compensação
    entry = await repo.compensate(
        employee_id,
        data.hours,
        data.compensation_date,
        data.shift_id,
        data.notes,
    )

    logger.info(
        f"Compensação registrada por {current_user.email}: "
        f"funcionário {employee_id}, {data.hours}h em {data.compensation_date}"
    )
    return TimeBankResponse.model_validate(entry)


@router.get(
    "/{entry_id}",
    response_model=TimeBankResponse,
    dependencies=[require_operacional_permission(Permission.TIMEBANK_VIEW_ALL, Permission.TIMEBANK_VIEW_OWN)],
)
async def get_entry(
    entry_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TimeBankResponse:
    """
    Busca entrada do banco por ID.
    """
    repo = TimeBankRepository(db)
    entry = await repo.get_by_id(entry_id)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada não encontrada",
        )

    return TimeBankResponse.model_validate(entry)


@router.patch(
    "/{entry_id}",
    response_model=TimeBankResponse,
    dependencies=[require_operacional_permission(Permission.TIMEBANK_CREATE)],
)
async def update_entry(
    entry_id: str,
    data: TimeBankUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TimeBankResponse:
    """
    Atualiza uma entrada do banco.

    Só é possível editar entradas pendentes.
    """
    repo = TimeBankRepository(db)
    entry = await repo.update(entry_id, data)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada não encontrada ou não pode ser editada",
        )

    logger.info(
        "Entrada do banco atualizada",
        action="update_time_bank_entry",
        entry_id=str(entry.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return TimeBankResponse.model_validate(entry)


@router.post(
    "/{entry_id}/approve",
    response_model=TimeBankResponse,
    dependencies=[require_operacional_permission(Permission.TIMEBANK_APPROVE)],
)
async def approve_entry(
    entry_id: str,
    data: TimeBankApprove,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TimeBankResponse:
    """
    Aprova uma entrada no banco de horas.
    """
    repo = TimeBankRepository(db)
    entry = await repo.approve(entry_id, current_user.id, data.notes)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada não encontrada ou já processada",
        )

    logger.info(
        "Entrada do banco aprovada",
        action="approve_time_bank_entry",
        entry_id=str(entry.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return TimeBankResponse.model_validate(entry)


@router.post(
    "/{entry_id}/reject",
    response_model=TimeBankResponse,
    dependencies=[require_operacional_permission(Permission.TIMEBANK_APPROVE)],
)
async def reject_entry(
    entry_id: str,
    data: TimeBankReject,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> TimeBankResponse:
    """
    Rejeita uma entrada no banco de horas.
    """
    repo = TimeBankRepository(db)
    entry = await repo.reject(entry_id, data.rejection_reason, str(current_user.id))

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada não encontrada ou já processada",
        )

    logger.info(
        "Entrada do banco rejeitada",
        action="reject_time_bank_entry",
        entry_id=str(entry.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return TimeBankResponse.model_validate(entry)


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_operacional_permission(Permission.TIMEBANK_CREATE)],
)
async def delete_entry(
    entry_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove uma entrada do banco (soft delete).

    Só é possível deletar entradas pendentes.
    """
    repo = TimeBankRepository(db)
    deleted = await repo.delete(entry_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada não encontrada ou não pode ser deletada",
        )

    logger.info(
        "Entrada do banco deletada",
        action="delete_time_bank_entry",
        entry_id=entry_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
