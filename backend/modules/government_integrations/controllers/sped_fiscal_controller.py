"""
Controller REST para SPED Fiscal (EFD ICMS/IPI).

Endpoints para operações do SPED Fiscal.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.auth.dependencies import CurrentActiveUser

from ..schemas.common import StandardResponse
from ..services.sped_fiscal_service import (
    SPEDFiscalService,
    get_sped_fiscal_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sped-fiscal", tags=["SPED Fiscal"])


def get_service() -> SPEDFiscalService:
    """Dependency para obter o service."""
    return get_sped_fiscal_service()


@router.get(
    "/status",
    response_model=StandardResponse,
    summary="Status do SPED Fiscal",
    description="Retorna o status da configuração do SPED Fiscal",
)
async def get_status(
    current_user: CurrentActiveUser, service: SPEDFiscalService = Depends(get_service)
) -> StandardResponse:
    """Retorna status da configuração."""
    try:
        status_data = service.validar_status()

        return StandardResponse(success=True, message="Status SPED Fiscal obtido", data=status_data)

    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {str(e)}")


