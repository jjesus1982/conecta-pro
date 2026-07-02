"""
Controller de Avaliacao de Impacto de Privacidade (PIA/DPIA) LGPD.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser
from core.database.session import get_sync_db_dependency
from modules.security_lgpd.repositories.pia_repository import PIARepository
from modules.security_lgpd.schemas.common import StandardResponse
from modules.security_lgpd.schemas.pia import PIARequest
from modules.security_lgpd.services.pia_service import PIAService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pia", tags=["LGPD - Avaliacao de Impacto (PIA/DPIA)"])


def get_pia_service(db: Session = Depends(get_sync_db_dependency)) -> PIAService:
    """Injeta um PIAService com repository ligado a sessao de banco."""
    return PIAService(PIARepository(db))


@router.post(
    "/create",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cria avaliacao de impacto (PIA/DPIA)",
    description="Inicia avaliacao de impacto de privacidade para projeto.",
)
async def create_pia(
    current_user: CurrentActiveUser,
    request: PIARequest,
    service: PIAService = Depends(get_pia_service),
) -> StandardResponse:
    """
    Cria avaliacao de impacto de privacidade.

    Args:
        request: Dados do projeto para avaliacao.

    Returns:
        StandardResponse: Resultado da avaliacao inicial.
    """
    try:
        result = service.create_assessment(
            project_name=request.project_name,
            description=request.description,
            data_categories=request.data_categories,
            processing_purposes=request.processing_purposes,
            data_subjects=request.data_subjects,
            risk_factors=request.risk_factors,
        )

        logger.info(
            "PIA criado para projeto: %s, nivel de risco: %s",
            request.project_name,
            result.get("risk_level", "unknown"),
        )

        return StandardResponse(
            success=True,
            message="Avaliacao de impacto criada",
            data=result,
        )

    except Exception as e:
        logger.error("Erro ao criar PIA: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar avaliacao",
        )


@router.get(
    "/{assessment_id}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta avaliacao PIA/DPIA",
    description="Retorna detalhes de uma avaliacao de impacto.",
)
async def get_pia(
    current_user: CurrentActiveUser,
    assessment_id: str = Path(..., description="ID da avaliacao"),
    service: PIAService = Depends(get_pia_service),
) -> StandardResponse:
    """
    Consulta avaliacao de impacto.

    Args:
        assessment_id: ID da avaliacao.

    Returns:
        StandardResponse: Detalhes da avaliacao.
    """
    try:
        assessment = service.get_assessment(assessment_id)

        return StandardResponse(
            success=True,
            message="Avaliacao recuperada",
            data=assessment,
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Avaliacao nao encontrada",
        )
    except Exception as e:
        logger.error("Erro ao consultar PIA: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao consultar avaliacao",
        )


@router.get("/risk-categories", include_in_schema=False)
@router.get(
    "/risk-categories/list",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista categorias de risco",
    description="Retorna categorias de risco disponiveis.",
)
async def list_risk_categories(current_user: CurrentActiveUser) -> StandardResponse:
    """
    Lista categorias de risco disponiveis.

    Returns:
        StandardResponse: Lista de categorias de risco.
    """
    service = PIAService()
    categories = service.get_risk_categories()

    return StandardResponse(
        success=True,
        message="Categorias de risco disponiveis",
        data={"risk_categories": categories},
    )
