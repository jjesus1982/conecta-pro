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


@router.post(
    "/gerar",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gerar arquivo SPED",
    description="Gera o arquivo SPED Contábil",
)
async def gerar_arquivo(
    current_user: CurrentActiveUser, request: GerarArquivoRequest, service: SPEDContabilService = Depends(get_service)
) -> StandardResponse:
    """Gera arquivo SPED."""
    try:
        contas = [c.model_dump() for c in request.contas] if request.contas else None
        lancamentos = [lanc.model_dump() for lanc in request.lancamentos] if request.lancamentos else None
        balanco = request.balanco.model_dump() if request.balanco else None
        dre = request.dre.model_dump() if request.dre else None

        resultado = service.gerar_arquivo(
            ano_referencia=request.ano_referencia,
            periodo_inicio=request.periodo_inicio,
            periodo_fim=request.periodo_fim,
            numero_ordem=request.numero_ordem,
            contas=contas,
            lancamentos=lancamentos,
            balanco=balanco,
            dre=dre,
        )

        return StandardResponse(
            success=True, message=f"Arquivo gerado: {resultado['total_registros']} registros", data=resultado
        )

    except ValueError as e:
        logger.warning(f"Erro de validação: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro na geração: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {str(e)}")


@router.post(
    "/gerar/download",
    response_class=PlainTextResponse,
    summary="Download arquivo SPED",
    description="Gera e retorna o arquivo SPED para download",
    status_code=201,
)
async def gerar_arquivo_download(
    current_user: CurrentActiveUser, request: GerarArquivoRequest, service: SPEDContabilService = Depends(get_service)
) -> PlainTextResponse:
    """Gera arquivo SPED para download."""
    try:
        contas = [c.model_dump() for c in request.contas] if request.contas else None
        lancamentos = [lanc.model_dump() for lanc in request.lancamentos] if request.lancamentos else None
        balanco = request.balanco.model_dump() if request.balanco else None
        dre = request.dre.model_dump() if request.dre else None

        resultado = service.gerar_arquivo(
            ano_referencia=request.ano_referencia,
            periodo_inicio=request.periodo_inicio,
            periodo_fim=request.periodo_fim,
            numero_ordem=request.numero_ordem,
            contas=contas,
            lancamentos=lancamentos,
            balanco=balanco,
            dre=dre,
        )

        filename = f"ECD_{request.ano_referencia}.txt"

        return PlainTextResponse(
            content=resultado["conteudo"],
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error(f"Erro no download: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {str(e)}")


