"""
Controller REST para EFD-Reinf.

Endpoints para geração e envio de eventos EFD-Reinf.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.auth.dependencies import CurrentActiveUser

from ..schemas.common import StandardResponse
from ..schemas.efd_reinf import (
    GerarR1000Request,
    GerarR2010Request,
    GerarR2099Request,
    GerarR4010Request,
    GerarR4020Request,
)
from ..services.efd_reinf_service import EFDReinfService, get_efd_reinf_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/efd-reinf", tags=["EFD-Reinf"])


def get_service() -> EFDReinfService:
    """Dependency para obter o service."""
    return get_efd_reinf_service()


@router.get(
    "/status",
    response_model=StandardResponse,
    summary="Status do EFD-Reinf",
    description="Retorna o status da configuração e conexão do EFD-Reinf",
)
async def get_status(
    current_user: CurrentActiveUser, service: EFDReinfService = Depends(get_service)
) -> StandardResponse:
    """Retorna status da configuração EFD-Reinf."""
    try:
        status_data = service.validar_status()

        return StandardResponse(success=True, message="Status EFD-Reinf obtido com sucesso", data=status_data)

    except Exception as e:
        logger.error(f"Erro ao obter status EFD-Reinf: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao obter status: {str(e)}")


@router.get(
    "/classificacoes-tributarias",
    response_model=StandardResponse,
    summary="Lista classificações tributárias",
    description="Retorna a lista de classificações tributárias disponíveis",
)
async def listar_classificacoes(
    current_user: CurrentActiveUser, service: EFDReinfService = Depends(get_service)
) -> StandardResponse:
    """Lista classificações tributárias disponíveis."""
    try:
        classificacoes = service.listar_classificacoes_tributarias()

        return StandardResponse(success=True, message="Classificações tributárias listadas", data=classificacoes)

    except Exception as e:
        logger.error(f"Erro ao listar classificações: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao listar classificações: {str(e)}"
        )


