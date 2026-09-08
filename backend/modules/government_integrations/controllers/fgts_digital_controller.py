"""
Controller REST para FGTS Digital.

Endpoints para operações do FGTS Digital.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.auth.dependencies import CurrentActiveUser

from ..schemas.common import StandardResponse
from ..services.fgts_digital_service import (
    FGTSDigitalService,
    get_fgts_digital_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fgts-digital", tags=["FGTS Digital"])


def get_service() -> FGTSDigitalService:
    """Dependency para obter o service."""
    return get_fgts_digital_service()


@router.get(
    "/status",
    response_model=StandardResponse,
    summary="Status do FGTS Digital",
    description="Retorna o status da configuração do FGTS Digital",
)
async def get_status(
    current_user: CurrentActiveUser, service: FGTSDigitalService = Depends(get_service)
) -> StandardResponse:
    """Retorna status da configuração."""
    try:
        status_data = service.validar_status()

        return StandardResponse(success=True, message="Status FGTS Digital obtido", data=status_data)

    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {str(e)}")


