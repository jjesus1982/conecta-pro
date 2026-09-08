"""
Controller REST para Simples Nacional.

Endpoints para cálculos e operações do Simples Nacional.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.auth.dependencies import CurrentActiveUser

from ..schemas.common import StandardResponse
from ..services.simples_nacional_service import (
    SimplesNacionalService,
    get_simples_nacional_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simples-nacional", tags=["Simples Nacional"])


def get_service() -> SimplesNacionalService:
    """Dependency para obter o service."""
    return get_simples_nacional_service()


@router.get(
    "/status",
    response_model=StandardResponse,
    summary="Status do Simples Nacional",
    description="Retorna o status da configuração",
)
async def get_status(
    current_user: CurrentActiveUser, service: SimplesNacionalService = Depends(get_service)
) -> StandardResponse:
    """Retorna status da configuração."""
    try:
        status_data = service.validar_status()

        return StandardResponse(success=True, message="Status Simples Nacional obtido", data=status_data)

    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {str(e)}")


