"""
Controller REST para SPED Contábil (ECD).

Endpoints para operações do SPED Contábil.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from core.auth.dependencies import CurrentActiveUser

from ..schemas.common import StandardResponse
from ..schemas.sped_contabil import (
    GerarArquivoRequest,
)
from ..services.sped_contabil_service import (
    SPEDContabilService,
    get_sped_contabil_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sped-contabil", tags=["SPED Contabil"])


def get_service() -> SPEDContabilService:
    """Dependency para obter o service."""
    return get_sped_contabil_service()


@router.get(
    "/status",
    response_model=StandardResponse,
    summary="Status do SPED Contábil",
    description="Retorna o status da configuração do SPED Contábil",
)
async def get_status(
    current_user: CurrentActiveUser, service: SPEDContabilService = Depends(get_service)
) -> StandardResponse:
    """Retorna status da configuração."""
    try:
        status_data = service.validar_status()

        return StandardResponse(success=True, message="Status SPED Contábil obtido", data=status_data)

    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {str(e)}")


