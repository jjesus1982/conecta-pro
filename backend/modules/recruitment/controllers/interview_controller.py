"""Controller para Interview."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.recruitment.models.interview import InterviewStatus, InterviewType
from modules.recruitment.schemas.interview import (
    InterviewFilter,
    InterviewListResponse,
    InterviewResponse,
)
from modules.recruitment.services.interview_service import InterviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interviews", tags=["Recruitment - Entrevistas"])


@router.get("", include_in_schema=False)  # espelho sem barra final (front chama sem barra)
@router.get(
    "/",
    response_model=InterviewListResponse,
    summary="Listar entrevistas",
)
async def list_interviews(  # pylint: disable=too-many-locals
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    application_id: str | None = None,
    interview_type: InterviewType | None = None,
    status_filter: InterviewStatus | None = Query(None, alias="status"),
    interviewer_id: str | None = None,
    scheduled_after: date | None = None,
    scheduled_before: date | None = None,
    is_today: bool = False,
    is_upcoming: bool = False,
    order_by: str = "scheduled_date",
    order_desc: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewListResponse:
    """Lista entrevistas com filtros e paginação."""
    service = InterviewService(db)

    filters = InterviewFilter(
        application_id=application_id,
        interview_type=interview_type,
        status=status_filter,
        interviewer_id=interviewer_id,
        scheduled_after=scheduled_after,
        scheduled_before=scheduled_before,
        is_today=is_today,
        is_upcoming=is_upcoming,
    )

    interviews, total = await service.list_with_filters(filters, skip, limit, order_by, order_desc)

    return InterviewListResponse(
        items=[InterviewResponse.model_validate(i) for i in interviews],
        total=total,
        skip=skip,
        limit=limit,
    )


