"""
Controller REST para e-CAC - Centro Virtual de Atendimento ao Contribuinte.

Endpoints para acesso aos servicos do e-CAC da Receita Federal.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.auth.dependencies import CurrentActiveUser

from ..schemas.common import StandardResponse
from ..schemas.ecac import (
    SituacaoDebitoEnum,
)
from ..services.ecac_service import EcacService, get_ecac_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ecac", tags=["e-CAC"])


def get_service() -> EcacService:
    """Dependency para obter o service."""
    return get_ecac_service()


@router.get(
    "/status",
    response_model=StandardResponse,
    summary="Status do e-CAC",
    description="Retorna o status da configuracao e conexao do e-CAC",
)
async def get_status(current_user: CurrentActiveUser, service: EcacService = Depends(get_service)) -> StandardResponse:
    """Retorna status da configuracao e-CAC."""
    try:
        status_data = service.validar_status()

        return StandardResponse(success=True, message="Status e-CAC obtido com sucesso", data=status_data)

    except Exception as e:
        logger.error(f"Erro ao obter status e-CAC: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao obter status: {str(e)}")


@router.get(
    "/situacao-fiscal",
    response_model=StandardResponse,
    summary="Consulta situacao fiscal",
    description="Consulta a situacao fiscal do contribuinte no e-CAC",
)
async def consultar_situacao_fiscal(
    current_user: CurrentActiveUser,
    cpf_cnpj: str | None = Query(None, description="CPF ou CNPJ (opcional, usa o configurado)"),
    service: EcacService = Depends(get_service),
) -> StandardResponse:
    """Consulta situacao fiscal do contribuinte."""
    try:
        # Limpa formatacao se fornecido
        if cpf_cnpj:
            cpf_cnpj = cpf_cnpj.replace(".", "").replace("/", "").replace("-", "")

        resultado = service.consultar_situacao_fiscal(cpf_cnpj=cpf_cnpj)

        return StandardResponse(success=True, message="Situacao fiscal consultada com sucesso", data=resultado)

    except ValueError as e:
        logger.warning(f"Erro de validacao situacao fiscal: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao consultar situacao fiscal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao consultar situacao fiscal: {str(e)}"
        )


@router.get(
    "/debitos",
    response_model=StandardResponse,
    summary="Consulta debitos",
    description="Consulta debitos fiscais do contribuinte",
)
async def consultar_debitos(
    current_user: CurrentActiveUser,
    situacao: SituacaoDebitoEnum | None = Query(None, description="Filtro por situacao do debito"),
    competencia_inicio: str | None = Query(None, pattern=r"^\d{4}-\d{2}$", description="Competencia inicial (YYYY-MM)"),
    competencia_fim: str | None = Query(None, pattern=r"^\d{4}-\d{2}$", description="Competencia final (YYYY-MM)"),
    service: EcacService = Depends(get_service),
) -> StandardResponse:
    """Consulta debitos fiscais."""
    try:
        resultado = service.consultar_debitos(
            situacao=situacao.value if situacao else None,
            competencia_inicio=competencia_inicio,
            competencia_fim=competencia_fim,
        )

        return StandardResponse(
            success=True, message=f"Debitos consultados: {resultado['quantidade']} encontrados", data=resultado
        )

    except ValueError as e:
        logger.warning(f"Erro de validacao consulta debitos: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao consultar debitos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao consultar debitos: {str(e)}"
        )


