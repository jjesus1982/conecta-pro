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


@router.post(
    "/r1000",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar evento R-1000",
    description="Gera evento R-1000 - Informações do Contribuinte",
)
async def gerar_r1000(
    request: GerarR1000Request, current_user: CurrentActiveUser, service: EFDReinfService = Depends(get_service)
) -> StandardResponse:
    """Gera evento R-1000 - Informações do Contribuinte."""
    try:
        resultado = service.gerar_r1000(
            razao_social=request.razao_social,
            classificacao_tributaria=request.classificacao_tributaria.value,
            inicio_validade=request.inicio_validade,
            fim_validade=request.fim_validade,
            natureza_juridica=request.natureza_juridica,
            ind_coop=request.ind_coop,
            ind_constr=request.ind_constr,
            ind_desoneracao=request.ind_desoneracao,
            telefone=request.telefone,
            email=request.email,
            retificacao=request.retificacao,
        )

        return StandardResponse(success=True, message="Evento R-1000 gerado com sucesso", data=resultado)

    except ValueError as e:
        logger.warning(f"Erro de validação R-1000: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao gerar R-1000: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar evento: {str(e)}")


@router.post(
    "/r2010",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar evento R-2010",
    description="Gera evento R-2010 - Retenção Contribuição Previdenciária - Serviços Tomados",
)
async def gerar_r2010(
    request: GerarR2010Request, current_user: CurrentActiveUser, service: EFDReinfService = Depends(get_service)
) -> StandardResponse:
    """Gera evento R-2010 - Retenção CP Serviços Tomados."""
    try:
        retencoes = [ret.model_dump() for ret in request.retencoes]

        resultado = service.gerar_r2010(
            periodo_apuracao=request.periodo_apuracao,
            retencoes=retencoes,
            retificacao=request.retificacao,
        )

        return StandardResponse(
            success=True, message=f"Evento R-2010 gerado com {len(retencoes)} retenções", data=resultado
        )

    except ValueError as e:
        logger.warning(f"Erro de validação R-2010: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao gerar R-2010: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar evento: {str(e)}")


@router.post(
    "/r4010",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar evento R-4010",
    description="Gera evento R-4010 - Pagamentos/créditos a beneficiário pessoa física",
)
async def gerar_r4010(
    request: GerarR4010Request, current_user: CurrentActiveUser, service: EFDReinfService = Depends(get_service)
) -> StandardResponse:
    """Gera evento R-4010 - Pagamentos PF."""
    try:
        pagamentos = [pag.model_dump() for pag in request.pagamentos]

        resultado = service.gerar_r4010(
            periodo_apuracao=request.periodo_apuracao,
            pagamentos=pagamentos,
            retificacao=request.retificacao,
        )

        return StandardResponse(
            success=True, message=f"Evento R-4010 gerado com {len(pagamentos)} pagamentos", data=resultado
        )

    except ValueError as e:
        logger.warning(f"Erro de validação R-4010: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao gerar R-4010: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar evento: {str(e)}")


@router.post(
    "/r4020",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar evento R-4020",
    description="Gera evento R-4020 - Pagamentos/créditos a beneficiário pessoa jurídica",
)
async def gerar_r4020(
    request: GerarR4020Request, current_user: CurrentActiveUser, service: EFDReinfService = Depends(get_service)
) -> StandardResponse:
    """Gera evento R-4020 - Pagamentos PJ."""
    try:
        pagamentos = [pag.model_dump() for pag in request.pagamentos]

        resultado = service.gerar_r4020(
            periodo_apuracao=request.periodo_apuracao,
            pagamentos=pagamentos,
            retificacao=request.retificacao,
        )

        return StandardResponse(
            success=True, message=f"Evento R-4020 gerado com {len(pagamentos)} pagamentos", data=resultado
        )

    except ValueError as e:
        logger.warning(f"Erro de validação R-4020: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao gerar R-4020: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar evento: {str(e)}")


@router.post(
    "/r2099",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar evento R-2099",
    description="Gera evento R-2099 - Fechamento dos Eventos Periódicos",
)
async def gerar_r2099(
    request: GerarR2099Request, current_user: CurrentActiveUser, service: EFDReinfService = Depends(get_service)
) -> StandardResponse:
    """Gera evento R-2099 - Fechamento Periódico."""
    try:
        resultado = service.gerar_r2099(
            periodo_apuracao=request.periodo_apuracao,
            retificacao=request.retificacao,
        )

        return StandardResponse(
            success=True, message=f"Evento R-2099 gerado para período {request.periodo_apuracao}", data=resultado
        )

    except ValueError as e:
        logger.warning(f"Erro de validação R-2099: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao gerar R-2099: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar evento: {str(e)}")


