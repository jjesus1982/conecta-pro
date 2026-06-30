"""Controller para Application."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.recruitment.models.application import ApplicationStatus
from modules.recruitment.schemas.application import (
    ApplicationAdvance,
    ApplicationBulkAction,
    ApplicationCreate,
    ApplicationFilter,
    ApplicationHire,
    ApplicationListResponse,
    ApplicationProposal,
    ApplicationReject,
    ApplicationResponse,
    ApplicationStats,
    ApplicationUpdate,
)
from modules.recruitment.services.application_service import ApplicationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applications", tags=["Recruitment - Candidaturas"])


@router.post(
    "/",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar candidatura",
)
async def create_application(
    data: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Cria uma nova candidatura."""
    service = ApplicationService(db)

    try:
        application = await service.create(data)
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar candidatura: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar candidatura",
        )


@router.get("", include_in_schema=False)  # espelho sem barra final (front chama sem barra)
@router.get(
    "/",
    response_model=ApplicationListResponse,
    summary="Listar candidaturas",
)
async def list_applications(  # pylint: disable=too-many-locals
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    job_position_id: str | None = None,
    candidate_id: str | None = None,
    status_filter: ApplicationStatus | None = Query(None, alias="status"),
    min_score: int | None = None,
    max_score: int | None = None,
    assigned_to_id: str | None = None,
    order_by: str = "applied_at",
    order_desc: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationListResponse:
    """Lista candidaturas com filtros e paginação."""
    service = ApplicationService(db)

    filters = ApplicationFilter(
        job_position_id=job_position_id,
        candidate_id=candidate_id,
        status=status_filter,
        min_score=min_score,
        max_score=max_score,
        assigned_to_id=assigned_to_id,
    )

    applications, total = await service.list_with_filters(filters, skip, limit, order_by, order_desc)

    return ApplicationListResponse(
        items=[ApplicationResponse.model_validate(a) for a in applications],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/position/{position_id}",
    response_model=ApplicationListResponse,
    summary="Candidaturas de uma vaga",
)
async def list_by_position(
    position_id: str,
    status_filter: ApplicationStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationListResponse:
    """Lista candidaturas de uma vaga específica."""
    service = ApplicationService(db)
    applications = await service.get_by_position(position_id, status_filter, skip, limit)

    return ApplicationListResponse(
        items=[ApplicationResponse.model_validate(a) for a in applications],
        total=len(applications),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/candidate/{candidate_id}",
    response_model=ApplicationListResponse,
    summary="Candidaturas de um candidato",
)
async def list_by_candidate(
    candidate_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationListResponse:
    """Lista candidaturas de um candidato específico."""
    service = ApplicationService(db)
    applications = await service.get_by_candidate(candidate_id, skip, limit)

    return ApplicationListResponse(
        items=[ApplicationResponse.model_validate(a) for a in applications],
        total=len(applications),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/active",
    response_model=ApplicationListResponse,
    summary="Candidaturas ativas",
)
async def list_active(
    position_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationListResponse:
    """Lista candidaturas ativas (em processo)."""
    service = ApplicationService(db)
    applications = await service.get_active(position_id, skip, limit)

    return ApplicationListResponse(
        items=[ApplicationResponse.model_validate(a) for a in applications],
        total=len(applications),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/shortlisted/{position_id}",
    response_model=ApplicationListResponse,
    summary="Lista restrita",
)
async def list_shortlisted(
    position_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationListResponse:
    """Lista candidaturas na lista restrita de uma vaga."""
    service = ApplicationService(db)
    applications = await service.get_shortlisted(position_id, skip, limit)

    return ApplicationListResponse(
        items=[ApplicationResponse.model_validate(a) for a in applications],
        total=len(applications),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/favorites",
    response_model=ApplicationListResponse,
    summary="Candidaturas favoritas",
)
async def list_favorites(
    position_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationListResponse:
    """Lista candidaturas marcadas como favoritas."""
    service = ApplicationService(db)
    applications = await service.get_favorites(position_id, skip, limit)

    return ApplicationListResponse(
        items=[ApplicationResponse.model_validate(a) for a in applications],
        total=len(applications),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/stats",
    response_model=ApplicationStats,
    summary="Estatísticas de candidaturas",
)
async def get_application_stats(
    position_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationStats:
    """Retorna estatísticas das candidaturas."""
    service = ApplicationService(db)
    stats = await service.get_stats(position_id)
    return ApplicationStats(**stats)


@router.get(
    "/{application_id}",
    response_model=ApplicationResponse,
    summary="Buscar candidatura",
)
async def get_application(
    application_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Busca candidatura por ID com relacionamentos."""
    service = ApplicationService(db)
    application = await service.get_by_id_with_relations(application_id)

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada",
        )

    return ApplicationResponse.model_validate(application)


@router.put(
    "/{application_id}",
    response_model=ApplicationResponse,
    summary="Atualizar candidatura",
)
async def update_application(
    application_id: str,
    data: ApplicationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Atualiza uma candidatura."""
    service = ApplicationService(db)

    try:
        application = await service.update(application_id, data)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada",
            )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover candidatura",
)
async def delete_application(
    application_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> None:
    """Remove uma candidatura (soft delete)."""
    service = ApplicationService(db)
    result = await service.delete(application_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada",
        )


@router.post(
    "/{application_id}/advance",
    response_model=ApplicationResponse,
    summary="Avançar etapa",
)
async def advance_stage(
    application_id: str,
    data: ApplicationAdvance,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Avança candidatura para próxima etapa."""
    service = ApplicationService(db)

    try:
        application = await service.advance_stage(application_id, data)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada",
            )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{application_id}/reject",
    response_model=ApplicationResponse,
    summary="Rejeitar candidatura",
)
async def reject_application(
    application_id: str,
    data: ApplicationReject,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Rejeita uma candidatura."""
    service = ApplicationService(db)

    application = await service.reject(application_id, data)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada",
        )

    return ApplicationResponse.model_validate(application)


@router.post(
    "/{application_id}/proposal",
    response_model=ApplicationResponse,
    summary="Enviar proposta",
)
async def send_proposal(
    application_id: str,
    data: ApplicationProposal,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Envia proposta ao candidato."""
    service = ApplicationService(db)

    try:
        application = await service.send_proposal(application_id, data)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada",
            )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{application_id}/accept-proposal",
    response_model=ApplicationResponse,
    summary="Aceitar proposta",
)
async def accept_proposal(
    application_id: str,
    start_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Aceita proposta de emprego."""
    service = ApplicationService(db)

    try:
        application = await service.accept_proposal(application_id, start_date)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada",
            )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{application_id}/reject-proposal",
    response_model=ApplicationResponse,
    summary="Recusar proposta",
)
async def reject_proposal(
    application_id: str,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Recusa proposta de emprego."""
    service = ApplicationService(db)

    application = await service.reject_proposal(application_id, reason)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada",
        )

    return ApplicationResponse.model_validate(application)


@router.post(
    "/{application_id}/hire",
    response_model=ApplicationResponse,
    summary="Contratar",
)
async def hire_candidate(
    application_id: str,
    data: ApplicationHire,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Contrata o candidato."""
    service = ApplicationService(db)

    try:
        application = await service.hire(application_id, data)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada",
            )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{application_id}/toggle-favorite",
    response_model=ApplicationResponse,
    summary="Alternar favorito",
)
async def toggle_favorite(
    application_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Alterna status de favorito."""
    service = ApplicationService(db)

    application = await service.toggle_favorite(application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada",
        )

    return ApplicationResponse.model_validate(application)


@router.post(
    "/{application_id}/toggle-shortlist",
    response_model=ApplicationResponse,
    summary="Alternar lista restrita",
)
async def toggle_shortlist(
    application_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Alterna status de lista restrita."""
    service = ApplicationService(db)

    application = await service.toggle_shortlist(application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada",
        )

    return ApplicationResponse.model_validate(application)


@router.put(
    "/{application_id}/score",
    response_model=ApplicationResponse,
    summary="Atualizar scores",
)
async def update_scores(
    application_id: str,
    interview_score: float | None = None,
    test_score: float | None = None,
    reference_score: float | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ApplicationResponse:
    """Atualiza scores da candidatura."""
    service = ApplicationService(db)

    application = await service.update_score(application_id, interview_score, test_score, reference_score)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada",
        )

    return ApplicationResponse.model_validate(application)


@router.post(
    "/{application_id}/matching",
    summary="Recalcular matching",
)
async def recalculate_matching(
    application_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Recalcula score de matching."""
    service = ApplicationService(db)

    result = await service.calculate_matching(application_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidatura não encontrada",
        )

    return result


@router.post(
    "/position/{position_id}/update-ranking",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Atualizar ranking",
)
async def update_ranking(
    position_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> None:
    """Atualiza ranking das candidaturas de uma vaga."""
    service = ApplicationService(db)
    await service.update_ranking(position_id)


@router.post(
    "/bulk-action",
    summary="Ação em lote",
)
async def bulk_action(
    data: ApplicationBulkAction,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Executa ação em lote em candidaturas."""
    service = ApplicationService(db)

    try:
        success, failed = await service.bulk_action(data)
        return {
            "success": success,
            "failed": failed,
            "total": len(data.application_ids),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
