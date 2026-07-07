"""
Controller para Avaliacao de Desempenho.

Define endpoints REST para gestao de avaliacoes de desempenho,
ciclos de avaliacao e calibracao.

Prefixo: /human-resources/performance
"""

import asyncio
import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.people_management.human_resources.models.performance import (
    ReviewStatus,
    ReviewType,
)
from modules.people_management.human_resources.publishers import (
    publish_avaliacao_concluida,
    publish_avaliacao_criada,
)
from modules.people_management.human_resources.schemas.performance import (
    PerformanceReviewCreate,
    PerformanceReviewListResponse,
    PerformanceReviewResponse,
    PerformanceReviewUpdate,
)
from modules.people_management.human_resources.services.integrated_performance_service import (
    IntegratedPerformanceService,
)
from modules.people_management.human_resources.services.performance_service import (
    PerformanceService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["RH - Desempenho"])


@router.get(
    "/visao-integrada",
    summary="Visao integrada de desempenho (RH x ponto x campo x SST x treinamento)",
)
async def visao_integrada(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Visao integrada por funcionario ativo, com score composto transparente.

    Cruza performance_reviews, avaliacao 360, avaliacoes do lider,
    ponto (30d), ocorrencias de campo (90d), treinamentos, tempo de casa
    e afastamentos. Fontes ausentes viram blocos "indisponivel" — nunca
    numeros fabricados.
    """
    service = IntegratedPerformanceService(db)
    try:
        return await service.visao_integrada()
    except Exception as e:
        logger.error(f"Erro na visao integrada de desempenho: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao montar visao integrada de desempenho.",
        )


@router.get(
    "/visao-integrada/{employee_id}",
    summary="Visao integrada de desempenho de um funcionario",
)
async def visao_integrada_funcionario(
    employee_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Visao integrada de desempenho para um funcionario ativo especifico."""
    service = IntegratedPerformanceService(db)
    try:
        result = await service.visao_integrada(employee_id=str(employee_id))
    except Exception as e:
        logger.error(f"Erro na visao integrada de desempenho ({employee_id}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao montar visao integrada de desempenho.",
        )
    if result.get("erro"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["erro"])
    return result


@router.post(
    "/reviews",
    response_model=PerformanceReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar avaliacao de desempenho",
)
async def create_review(
    data: PerformanceReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> PerformanceReviewResponse:
    """Cria uma nova avaliacao de desempenho."""
    service = PerformanceService(db)
    try:
        review = await service.create_review(data)
        asyncio.create_task(
            publish_avaliacao_criada(
                employee_id=str(getattr(data, "employee_id", "") or ""),
                review_id=str(getattr(review, "id", "")),
            )
        )
        return PerformanceReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar avaliacao: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar avaliacao de desempenho.",
        )


@router.get(
    "/reviews",
    response_model=PerformanceReviewListResponse,
    summary="Listar avaliacoes de desempenho",
)
async def list_reviews(
    employee_id: UUID | None = None,
    reviewer_id: UUID | None = None,
    review_type: ReviewType | None = Query(None, alias="type"),
    review_status: ReviewStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> PerformanceReviewListResponse:
    """Lista avaliacoes com filtros e paginacao."""
    service = PerformanceService(db)
    result = await service.list_reviews(
        employee_id=employee_id,
        reviewer_id=reviewer_id,
        review_type=review_type.value if review_type else None,
        status=review_status.value if review_status else None,
        page=page,
        page_size=page_size,
    )
    return PerformanceReviewListResponse(
        items=[PerformanceReviewResponse.model_validate(r) for r in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get(
    "/reviews/{review_id}",
    response_model=PerformanceReviewResponse,
    summary="Buscar avaliacao por ID",
)
async def get_review(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> PerformanceReviewResponse:
    """Busca uma avaliacao pelo identificador."""
    service = PerformanceService(db)
    review = await service.get_review(review_id)
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Avaliacao nao encontrada.",
        )
    return PerformanceReviewResponse.model_validate(review)


@router.put(
    "/reviews/{review_id}",
    response_model=PerformanceReviewResponse,
    summary="Atualizar avaliacao",
)
async def update_review(
    review_id: UUID,
    data: PerformanceReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> PerformanceReviewResponse:
    """Atualiza os dados de uma avaliacao."""
    service = PerformanceService(db)
    try:
        review = await service.update_review(review_id, data)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Avaliacao nao encontrada.",
            )
        return PerformanceReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remover avaliacao (somente rascunho)",
)
async def delete_review(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Remove uma avaliacao em rascunho."""
    service = PerformanceService(db)
    try:
        deleted = await service.delete_review(review_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Avaliacao nao encontrada.",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/reviews/{review_id}/complete",
    response_model=PerformanceReviewResponse,
    summary="Concluir avaliacao",
    status_code=201,
)
async def complete_review(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> PerformanceReviewResponse:
    """Conclui uma avaliacao de desempenho."""
    service = PerformanceService(db)
    try:
        review = await service.complete_review(review_id)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Avaliacao nao encontrada.",
            )
        asyncio.create_task(
            publish_avaliacao_concluida(
                employee_id=str(getattr(review, "employee_id", "") or ""),
                review_id=str(getattr(review, "id", "")),
            )
        )
        return PerformanceReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/review-cycle",
    response_model=list[PerformanceReviewResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Iniciar ciclo de avaliacao",
)
async def start_review_cycle(
    employee_ids: list[UUID],
    reviewer_id: UUID,
    review_type: ReviewType = ReviewType.QUARTERLY,
    period_start: date = Query(...),
    period_end: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[PerformanceReviewResponse]:
    """Inicia um ciclo de avaliacao para multiplos funcionarios."""
    service = PerformanceService(db)
    reviews = await service.start_review_cycle(
        employee_ids=employee_ids,
        reviewer_id=reviewer_id,
        review_type=review_type,
        period_start=period_start,
        period_end=period_end,
    )
    return [PerformanceReviewResponse.model_validate(r) for r in reviews]
