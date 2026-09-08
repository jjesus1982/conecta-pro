"""
Controller (endpoints) para Commission.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.crm.models.commission import CommissionStatus, CommissionTrigger
from modules.crm.repositories.commission_repository import CommissionRepository
from modules.crm.schemas.commission import (
    CommissionFilter,
    CommissionListResponse,
    CommissionResponse,
)

router = APIRouter(prefix="/commissions", tags=["CRM - Commissions"])


# ============== Commission Rules Endpoints ==============


# ============== Commission Endpoints ==============


@router.get("", response_model=CommissionListResponse)
async def list_commissions(  # pylint: disable=too-many-locals
    current_user: CurrentActiveUser,  # pylint: disable=unused-argument
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    seller_id: str | None = None,
    proposal_id: str | None = None,
    status_filter: CommissionStatus | None = Query(None, alias="status"),
    trigger: CommissionTrigger | None = None,
    is_overdue: bool | None = None,
    min_value: float | None = Query(None, ge=0),
    max_value: float | None = Query(None, ge=0),
    date_from: date | None = None,
    date_to: date | None = None,
    due_date_from: date | None = None,
    due_date_to: date | None = None,
) -> CommissionListResponse:
    """Lista comissões com filtros."""
    repo = CommissionRepository(db)

    filters = CommissionFilter(
        seller_id=seller_id,
        proposal_id=proposal_id,
        status=status_filter,
        trigger=trigger,
        is_overdue=is_overdue,
        min_value=min_value,
        max_value=max_value,
        date_from=date_from,
        date_to=date_to,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
    )

    skip = (page - 1) * page_size
    commissions, total = await repo.list(filters=filters, skip=skip, limit=page_size)

    return CommissionListResponse(
        items=[CommissionResponse.model_validate(c) for c in commissions],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


# ============== Summary Endpoints (devem vir antes de /{commission_id}) ==============


# ============== Commission by ID (deve vir DEPOIS de rotas estáticas) ==============


# ============== Payment Endpoints ==============


