"""Controller para Interview."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.recruitment.models.interview import InterviewStatus, InterviewType
from modules.recruitment.schemas.interview import (
    InterviewCalendar,
    InterviewCancel,
    InterviewComplete,
    InterviewCreate,
    InterviewEvaluation,
    InterviewFilter,
    InterviewListResponse,
    InterviewReschedule,
    InterviewResponse,
    InterviewSlot,
    InterviewStats,
    InterviewUpdate,
)
from modules.recruitment.services.interview_service import InterviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interviews", tags=["Recruitment - Entrevistas"])


@router.post(
    "/",
    response_model=InterviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agendar entrevista",
)
async def create_interview(
    data: InterviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Agenda uma nova entrevista."""
    service = InterviewService(db)

    try:
        interview = await service.create(data)
        return InterviewResponse.model_validate(interview)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao agendar entrevista: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao agendar entrevista",
        )


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


@router.get(
    "/today",
    response_model=InterviewListResponse,
    summary="Entrevistas de hoje",
)
async def list_today(
    interviewer_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewListResponse:
    """Lista entrevistas agendadas para hoje."""
    service = InterviewService(db)
    interviews = await service.get_today(interviewer_id)

    return InterviewListResponse(
        items=[InterviewResponse.model_validate(i) for i in interviews],
        total=len(interviews),
        skip=0,
        limit=len(interviews),
    )


@router.get(
    "/upcoming",
    response_model=InterviewListResponse,
    summary="Próximas entrevistas",
)
async def list_upcoming(
    days: int = Query(7, ge=1, le=30),
    interviewer_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewListResponse:
    """Lista próximas entrevistas."""
    service = InterviewService(db)
    interviews = await service.get_upcoming(days, interviewer_id)

    return InterviewListResponse(
        items=[InterviewResponse.model_validate(i) for i in interviews],
        total=len(interviews),
        skip=0,
        limit=len(interviews),
    )


@router.get(
    "/pending-confirmation",
    response_model=InterviewListResponse,
    summary="Pendentes de confirmação",
)
async def list_pending_confirmation(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewListResponse:
    """Lista entrevistas pendentes de confirmação."""
    service = InterviewService(db)
    interviews = await service.get_pending_confirmation()

    return InterviewListResponse(
        items=[InterviewResponse.model_validate(i) for i in interviews],
        total=len(interviews),
        skip=0,
        limit=len(interviews),
    )


@router.get(
    "/pending-result",
    response_model=InterviewListResponse,
    summary="Pendentes de resultado",
)
async def list_pending_result(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewListResponse:
    """Lista entrevistas pendentes de resultado."""
    service = InterviewService(db)
    interviews = await service.get_pending_result()

    return InterviewListResponse(
        items=[InterviewResponse.model_validate(i) for i in interviews],
        total=len(interviews),
        skip=0,
        limit=len(interviews),
    )


@router.get(
    "/by-date-range",
    response_model=InterviewListResponse,
    summary="Por período",
)
async def list_by_date_range(
    start_date: date,
    end_date: date,
    interviewer_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewListResponse:
    """Lista entrevistas em um período."""
    service = InterviewService(db)
    interviews = await service.get_by_date_range(start_date, end_date, interviewer_id)

    return InterviewListResponse(
        items=[InterviewResponse.model_validate(i) for i in interviews],
        total=len(interviews),
        skip=0,
        limit=len(interviews),
    )


@router.get(
    "/available-slots",
    response_model=list[InterviewSlot],
    summary="Horários disponíveis",
)
async def get_available_slots(
    interviewer_ids: list[str] = Query(..., min_length=1),
    start_date: date = Query(...),
    end_date: date = Query(...),
    duration_minutes: int = Query(60, ge=15, le=180),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[InterviewSlot]:
    """Retorna horários disponíveis para agendamento."""
    service = InterviewService(db)
    slots = await service.get_available_slots(interviewer_ids, start_date, end_date, duration_minutes)
    return slots


@router.get(
    "/calendar/{interviewer_id}",
    response_model=InterviewCalendar,
    summary="Calendário de entrevistas",
)
async def get_calendar(
    interviewer_id: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewCalendar:
    """Retorna calendário de entrevistas de um mês."""
    service = InterviewService(db)
    return await service.get_calendar(interviewer_id, month, year)


@router.get(
    "/stats",
    response_model=InterviewStats,
    summary="Estatísticas de entrevistas",
)
async def get_interview_stats(
    application_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewStats:
    """Retorna estatísticas das entrevistas."""
    service = InterviewService(db)
    stats = await service.get_stats(application_id)
    return InterviewStats(**stats)


@router.get(
    "/{interview_id}",
    response_model=InterviewResponse,
    summary="Buscar entrevista",
)
async def get_interview(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Busca entrevista por ID."""
    service = InterviewService(db)
    interview = await service.get_by_id_with_relations(interview_id)

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista não encontrada",
        )

    return InterviewResponse.model_validate(interview)


@router.put(
    "/{interview_id}",
    response_model=InterviewResponse,
    summary="Atualizar entrevista",
)
async def update_interview(
    interview_id: str,
    data: InterviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Atualiza uma entrevista."""
    service = InterviewService(db)

    try:
        interview = await service.update(interview_id, data)
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrevista não encontrada",
            )
        return InterviewResponse.model_validate(interview)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{interview_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover entrevista",
)
async def delete_interview(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> None:
    """Remove uma entrevista (soft delete)."""
    service = InterviewService(db)
    result = await service.delete(interview_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista não encontrada",
        )


@router.post(
    "/{interview_id}/confirm-candidate",
    response_model=InterviewResponse,
    summary="Confirmar presença candidato",
)
async def confirm_candidate(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Confirma presença do candidato."""
    service = InterviewService(db)

    interview = await service.confirm_candidate(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista não encontrada",
        )

    return InterviewResponse.model_validate(interview)


@router.post(
    "/{interview_id}/confirm-interviewer",
    response_model=InterviewResponse,
    summary="Confirmar presença entrevistador",
)
async def confirm_interviewer(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Confirma presença do entrevistador."""
    service = InterviewService(db)

    interview = await service.confirm_interviewer(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista não encontrada",
        )

    return InterviewResponse.model_validate(interview)


@router.post(
    "/{interview_id}/start",
    response_model=InterviewResponse,
    summary="Iniciar entrevista",
)
async def start_interview(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Inicia a entrevista."""
    service = InterviewService(db)

    try:
        interview = await service.start(interview_id)
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrevista não encontrada",
            )
        return InterviewResponse.model_validate(interview)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{interview_id}/complete",
    response_model=InterviewResponse,
    summary="Completar entrevista",
)
async def complete_interview(
    interview_id: str,
    data: InterviewComplete,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Completa a entrevista com resultado."""
    service = InterviewService(db)

    try:
        interview = await service.complete(interview_id, data)
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrevista não encontrada",
            )
        return InterviewResponse.model_validate(interview)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{interview_id}/cancel",
    response_model=InterviewResponse,
    summary="Cancelar entrevista",
)
async def cancel_interview(
    interview_id: str,
    data: InterviewCancel,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Cancela a entrevista."""
    service = InterviewService(db)

    interview = await service.cancel(interview_id, data)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista não encontrada",
        )

    return InterviewResponse.model_validate(interview)


@router.post(
    "/{interview_id}/reschedule",
    response_model=InterviewResponse,
    summary="Reagendar entrevista",
)
async def reschedule_interview(
    interview_id: str,
    data: InterviewReschedule,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Reagenda a entrevista."""
    service = InterviewService(db)

    try:
        interview = await service.reschedule(interview_id, data)
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrevista não encontrada",
            )
        return InterviewResponse.model_validate(interview)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{interview_id}/no-show",
    response_model=InterviewResponse,
    summary="Marcar não compareceu",
)
async def mark_no_show(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Marca que o candidato não compareceu."""
    service = InterviewService(db)

    interview = await service.mark_no_show(interview_id)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista não encontrada",
        )

    return InterviewResponse.model_validate(interview)


@router.post(
    "/{interview_id}/evaluation", response_model=InterviewResponse, summary="Adicionar avaliação", status_code=201
)
async def add_evaluation(
    interview_id: str,
    data: InterviewEvaluation,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewResponse:
    """Adiciona avaliação de competência."""
    service = InterviewService(db)

    interview = await service.add_evaluation(interview_id, data)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista não encontrada",
        )

    return InterviewResponse.model_validate(interview)


@router.get(
    "/{interview_id}/questions",
    summary="Sugestões de perguntas",
)
async def get_suggested_questions(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[dict]:
    """Retorna sugestões de perguntas para a entrevista."""
    service = InterviewService(db)

    questions = await service.generate_questions(interview_id)
    if questions is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrevista não encontrada",
        )

    return questions


@router.get(
    "/application/{application_id}",
    response_model=InterviewListResponse,
    summary="Entrevistas de uma candidatura",
)
async def list_by_application(
    application_id: str,
    status_filter: InterviewStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> InterviewListResponse:
    """Lista entrevistas de uma candidatura."""
    service = InterviewService(db)
    interviews = await service.get_by_application(application_id, status_filter)

    return InterviewListResponse(
        items=[InterviewResponse.model_validate(i) for i in interviews],
        total=len(interviews),
        skip=0,
        limit=len(interviews),
    )
