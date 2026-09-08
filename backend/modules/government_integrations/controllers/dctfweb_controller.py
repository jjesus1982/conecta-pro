"""
Controller REST para DCTFWeb.

Endpoints para geração e transmissão de DCTFWeb.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query

from core.auth.dependencies import CurrentActiveUser

from ..schemas.common import StandardResponse
from ..schemas.dctfweb import (
    ConsolidarDeclaracaoRequest,
    GerarDarfsRequest,
)
from ..services.dctfweb_service import DCTFWebService, get_dctfweb_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dctfweb", tags=["DCTFWeb"])


def get_service(
    empresa: str | None = Query(None, description="Slug da empresa: conecta_eletronica | conecta_patrimonial (vazio = principal)"),
) -> DCTFWebService:
    """Dependency para obter o service. 08/09/2026: sem `empresa` era sempre a Eletrônica."""
    return DCTFWebService(empresa) if empresa else get_dctfweb_service()


@router.get(
    "/status",
    response_model=StandardResponse,
    summary="Status do DCTFWeb",
    description="Retorna o status da configuração DCTFWeb",
)
async def get_status(
    current_user: CurrentActiveUser, service: DCTFWebService = Depends(get_service)
) -> StandardResponse:
    """Retorna status da configuração."""
    try:
        status_data = service.validar_status()

        return StandardResponse(success=True, message="Status DCTFWeb obtido com sucesso", data=status_data)

    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao obter status: {str(e)}")


