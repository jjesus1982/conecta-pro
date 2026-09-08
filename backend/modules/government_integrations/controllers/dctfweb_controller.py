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


@router.post(
    "/consolidar",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Consolidar declaração",
    description="Consolida declaração com dados do eSocial e EFD-Reinf",
)
async def consolidar_declaracao(
    current_user: CurrentActiveUser,
    request: ConsolidarDeclaracaoRequest,
    service: DCTFWebService = Depends(get_service),
) -> StandardResponse:
    """Consolida declaração."""
    try:
        dados_esocial = request.dados_esocial.model_dump(exclude_none=True) if request.dados_esocial else None
        dados_reinf = request.dados_reinf.model_dump(exclude_none=True) if request.dados_reinf else None

        resultado = service.consolidar_declaracao(
            periodo_apuracao=request.periodo_apuracao,
            dados_esocial=dados_esocial,
            dados_reinf=dados_reinf,
        )

        return StandardResponse(success=True, message="DCTFWeb consolidada com sucesso", data=resultado)

    except ValueError as e:
        logger.warning(f"Erro de validação: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao consolidar: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {str(e)}")


@router.post(
    "/gerar-darfs",
    response_model=StandardResponse,
    summary="Gerar DARFs",
    description="Gera DARFs para a declaração",
    status_code=201,
)
async def gerar_darfs(
    request: GerarDarfsRequest, current_user: CurrentActiveUser, service: DCTFWebService = Depends(get_service)
) -> StandardResponse:
    """Gera DARFs."""
    try:
        dados_esocial = request.dados_esocial.model_dump(exclude_none=True) if request.dados_esocial else None
        dados_reinf = request.dados_reinf.model_dump(exclude_none=True) if request.dados_reinf else None

        resultado = service.gerar_darfs(
            periodo_apuracao=request.periodo_apuracao,
            dados_esocial=dados_esocial,
            dados_reinf=dados_reinf,
            data_vencimento=request.data_vencimento,
        )

        return StandardResponse(success=True, message=f"Gerados {resultado['quantidade_darfs']} DARFs", data=resultado)

    except ValueError as e:
        logger.warning(f"Erro de validação: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao gerar DARFs: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {str(e)}")


@router.get(
    "/consultar/{periodo_apuracao}",
    response_model=StandardResponse,
    summary="Consultar declaração",
    description="Consulta declaração DCTFWeb por período",
)
async def consultar_declaracao(
    current_user: CurrentActiveUser, periodo_apuracao: str, service: DCTFWebService = Depends(get_service)
) -> StandardResponse:
    """Consulta declaração por período."""
    try:
        resultado = service.consultar(periodo_apuracao)

        return StandardResponse(success=True, message=f"Consulta período {periodo_apuracao}", data=resultado)

    except Exception as e:
        logger.error(f"Erro ao consultar: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {str(e)}")
