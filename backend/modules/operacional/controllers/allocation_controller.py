"""
Controller (endpoints) para Allocation (Alocação Funcionário-Posto).
"""

import asyncio
from datetime import date
from typing import Any

from fastapi import Response, APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger
from core.rate_limit import BULK_LIMIT, limiter
from modules.operacional.models.allocation import AllocationStatus
from modules.operacional.permissions import Permission, require_operacional_permission
from modules.operacional.publishers import publish_alocacao_criada
from modules.operacional.repositories.allocation_repository import AllocationRepository
from modules.operacional.schemas.allocation import (
    AllocationBulkDelete,
    AllocationBulkOperationResult,
    AllocationBulkUpdate,
    AllocationCreate,
    AllocationFilter,
    AllocationListResponse,
    AllocationResponse,
    AllocationTerminate,
    AllocationUpdate,
)

router = APIRouter(prefix="/allocations", tags=["Operations - Allocations"])


@router.post(
    "/",
    response_model=AllocationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_CREATE)],
)
async def create_allocation(
    data: AllocationCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AllocationResponse:
    """
    Cria uma nova alocação de funcionário em posto.

    Requer autenticação.
    """
    repo = AllocationRepository(db)
    allocation: Any = await repo.create(data)

    logger.info(
        "Allocation criada com sucesso",
        action="create_allocation",
        allocation_id=str(allocation.id),
        employee_id=str(data.employee_id),
        post_id=str(data.post_id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    asyncio.create_task(
        publish_alocacao_criada(
            allocation_id=str(allocation.id),
            employee_id=str(data.employee_id),
            post_id=str(data.post_id),
        )
    )
    return AllocationResponse.model_validate(allocation)


@router.get(
    "",
    response_model=AllocationListResponse,
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_VIEW)],
    include_in_schema=False,
)
@router.get(
    "/",
    response_model=AllocationListResponse,
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_VIEW)],
)
async def list_allocations(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    post_id: str | None = None,
    employee_id: str | None = None,
    status_filter: AllocationStatus | None = Query(None, alias="status"),
    is_primary: bool | None = None,
    is_temporary: bool | None = None,
    is_current: bool | None = None,
    start_date_from: date | None = None,
    start_date_to: date | None = None,
) -> AllocationListResponse:
    """
    Lista alocações com filtros e paginação.
    """
    repo = AllocationRepository(db)

    filters = AllocationFilter(
        post_id=post_id,
        employee_id=employee_id,
        status=status_filter,
        is_primary=is_primary,
        is_temporary=is_temporary,
        is_current=is_current,
        start_date_from=start_date_from,
        start_date_to=start_date_to,
    )

    allocations: list[Any]
    total: int
    allocations, total = await repo.list(filters=filters, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size

    return AllocationListResponse(
        items=[AllocationResponse.model_validate(a) for a in allocations],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/current",
    response_model=list[AllocationResponse],
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_VIEW)],
)
async def get_current_allocations(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    post_id: str | None = None,
) -> list[AllocationResponse]:
    """
    Lista alocações vigentes (ativas no momento).
    """
    repo = AllocationRepository(db)

    filters = AllocationFilter(
        post_id=post_id,
        is_current=True,
        status=AllocationStatus.ACTIVE,
    )

    allocations: list[Any]
    _: int
    allocations, _ = await repo.list(filters=filters, page=1, page_size=500)

    return [AllocationResponse.model_validate(a) for a in allocations]


@router.get(
    "/available-employees",
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_VIEW)],
)
async def get_available_employees(
    post_id: str,
    target_date: date,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Lista funcionários disponíveis para alocação em um posto na data.
    """
    repo = AllocationRepository(db)
    employees: list[dict[str, Any]] = await repo.get_available_employees(shift_date=target_date, post_id=post_id)

    return employees


@router.get(
    "/post/{post_id}",
    response_model=list[AllocationResponse],
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_VIEW)],
)
async def get_allocations_by_post(
    post_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = Query(False, description="Incluir inativos"),
) -> list[AllocationResponse]:
    """
    Lista todas as alocações de um posto.
    """
    repo = AllocationRepository(db)

    filters = AllocationFilter(
        post_id=post_id,
        is_current=None if include_inactive else True,
    )

    allocations: list[Any]
    _: int
    allocations, _ = await repo.list(filters=filters, page=1, page_size=500)

    return [AllocationResponse.model_validate(a) for a in allocations]


@router.get(
    "/employee/{employee_id}",
    response_model=list[AllocationResponse],
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_VIEW)],
)
async def get_allocations_by_employee(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = Query(False, description="Incluir inativos"),
) -> list[AllocationResponse]:
    """
    Lista todas as alocações de um funcionário.
    """
    repo = AllocationRepository(db)

    filters = AllocationFilter(
        employee_id=employee_id,
        is_current=None if include_inactive else True,
    )

    allocations: list[Any]
    _: int
    allocations, _ = await repo.list(filters=filters, page=1, page_size=500)

    return [AllocationResponse.model_validate(a) for a in allocations]


# IMPORTANTE: /stats DEVE vir antes de /{allocation_id}, senão "stats" é parseado
# como UUID e dá 500 (DataError). Era o que derrubava o card de alocações no analytics.
@router.get(
    "/stats",
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_VIEW)],
)
async def allocation_stats(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Estatísticas de alocações (contagem por status)."""
    rows = (await db.execute(text("SELECT status, COUNT(*) AS qtd FROM allocations GROUP BY status"))).mappings().all()
    by_status = {str(r["status"]): r["qtd"] for r in rows}
    return {
        "total": sum(by_status.values()),
        "active": by_status.get("active", 0),
        "on_hold": by_status.get("on_hold", 0),
        "terminated": by_status.get("terminated", 0),
        "by_status": by_status,
    }


@router.get(
    "/{allocation_id}",
    response_model=AllocationResponse,
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_VIEW)],
)
async def get_allocation(
    allocation_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AllocationResponse:
    """
    Busca alocação por ID.
    """
    repo = AllocationRepository(db)
    allocation: Any = await repo.get_by_id(allocation_id)

    if not allocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alocação não encontrada",
        )

    return AllocationResponse.model_validate(allocation)


@router.patch(
    "/{allocation_id}",
    response_model=AllocationResponse,
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_EDIT)],
)
async def update_allocation(
    allocation_id: str,
    data: AllocationUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AllocationResponse:
    """
    Atualiza uma alocação.
    """
    repo = AllocationRepository(db)
    allocation: Any = await repo.update(allocation_id, data)

    if not allocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alocação não encontrada",
        )

    logger.info(
        "Allocation atualizada com sucesso",
        action="update_allocation",
        allocation_id=str(allocation.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return AllocationResponse.model_validate(allocation)


@router.post(
    "/{allocation_id}/terminate",
    response_model=AllocationResponse,
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_EDIT)],
)
async def terminate_allocation(
    allocation_id: str,
    data: AllocationTerminate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AllocationResponse:
    """
    Encerra uma alocação.
    """
    repo = AllocationRepository(db)
    allocation: Any = await repo.terminate(
        allocation_id,
        data.end_date,
        data.termination_reason,
        data.notes,
    )

    if not allocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alocação não encontrada ou já encerrada",
        )

    logger.info(
        "Allocation encerrada com sucesso",
        action="terminate_allocation",
        allocation_id=str(allocation.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
    )
    return AllocationResponse.model_validate(allocation)


@router.delete(
    "/{allocation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_EDIT)],
)
async def delete_allocation(
    allocation_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove uma alocação (soft delete).
    """
    repo = AllocationRepository(db)
    deleted: bool = await repo.delete(allocation_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alocação não encontrada",
        )

    logger.info(
        "Allocation deletada com sucesso",
        action="delete_allocation",
        allocation_id=allocation_id,
        user_id=str(current_user.id),
        user_email=current_user.email,
    )


@router.delete(
    "/bulk",
    response_model=AllocationBulkOperationResult,
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_EDIT)],
)
@limiter.limit(BULK_LIMIT)
async def bulk_delete_allocations(
    request: Request,
    response: Response,  # exigido pelo slowapi
    data: AllocationBulkDelete,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AllocationBulkOperationResult:
    """
    Deleta múltiplas alocações em lote (soft delete).

    Retorna contagem de sucessos e erros.
    """
    repo = AllocationRepository(db)
    result: dict[str, int] = await repo.bulk_delete(data.allocation_ids)

    logger.info(
        "Bulk delete de alocações",
        action="bulk_delete_allocations",
        user_id=str(current_user.id),
        user_email=current_user.email,
        requested_count=len(data.allocation_ids),
        success_count=result["success_count"],
        error_count=result["error_count"],
    )

    return AllocationBulkOperationResult(**result)


@router.patch(
    "/bulk",
    response_model=AllocationBulkOperationResult,
    dependencies=[require_operacional_permission(Permission.ALLOCATIONS_EDIT)],
)
@limiter.limit(BULK_LIMIT)
async def bulk_update_allocations(
    request: Request,
    response: Response,  # exigido pelo slowapi
    data: AllocationBulkUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> AllocationBulkOperationResult:
    """
    Atualiza múltiplas alocações em lote.

    Retorna contagem de sucessos e erros.
    """
    repo = AllocationRepository(db)
    result: dict[str, int] = await repo.bulk_update(data.items)

    logger.info(
        "Bulk update de alocações",
        action="bulk_update_allocations",
        user_id=str(current_user.id),
        user_email=current_user.email,
        requested_count=len(data.items),
        success_count=result["success_count"],
        error_count=result["error_count"],
    )

    return AllocationBulkOperationResult(**result)
