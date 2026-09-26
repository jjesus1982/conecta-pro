"""
Controller REST para SPED Contábil (ECD).

Endpoints para operações do SPED Contábil.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    summary="Gera a ECD (SPED Contábil) do período",
    description=(
        "Gera o arquivo da Escrituração Contábil Digital a partir do razão real "
        "(`accounting_entries`) do CNPJ escolhido. Devolve JSON com o resumo e o conteúdo; "
        "com `formato=txt`, devolve o arquivo puro para download.\n\n"
        "O bloco J100 (balanço) só é emitido se o balanço FECHAR e o ativo for positivo — "
        "a razão da recusa vem em `veracidade.demonstrativos_bloco_j.motivo`.\n\n"
        "O arquivo NÃO vem assinado: a ECD exige assinatura de contabilista com CRC ativo, "
        "e nenhum software substitui isso."
    ),
)
async def gerar_ecd(
    payload: GerarArquivoRequest,
    current_user: CurrentActiveUser,
    formato: str = Query("json", pattern="^(json|txt)$"),
):
    """Gera a ECD do período para um CNPJ."""
    try:
        # Instância por requisição: o service acumula plano de contas e lançamentos no
        # manager, e reaproveitar somaria o período de uma geração na seguinte.
        service = SPEDContabilService(empresa_slug=payload.empresa_slug)
        resultado = service.gerar_arquivo(
            ano_referencia=payload.ano_referencia,
            periodo_inicio=payload.periodo_inicio,
            periodo_fim=payload.periodo_fim,
            numero_ordem=payload.numero_ordem,
            contas=[c.model_dump() for c in payload.contas] if payload.contas else None,
            lancamentos=(
                [lanc.model_dump() for lanc in payload.lancamentos] if payload.lancamentos else None
            ),
            balanco=payload.balanco.model_dump() if payload.balanco else None,
            dre=payload.dre.model_dump() if payload.dre else None,
        )
    except Exception as e:
        logger.error(f"Erro ao gerar ECD: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar ECD: {e}"
        )

    if not resultado.get("total_lancamentos"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Nenhum lançamento no razão do CNPJ {resultado.get('veracidade', {}).get('cnpj')} "
                f"entre {payload.periodo_inicio} e {payload.periodo_fim}. "
                "Gerar ECD vazia seria pior que não gerar."
            ),
        )

    if formato == "txt":
        nome = (
            f"ECD_{resultado.get('veracidade', {}).get('cnpj', '')}_"
            f"{payload.ano_referencia}.txt"
        )
        return PlainTextResponse(
            resultado["conteudo"],
            media_type="text/plain; charset=latin-1",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )

    return StandardResponse(
        success=True,
        message=(
            f"ECD gerada: {resultado['total_registros']} registros, "
            f"{resultado['total_lancamentos']} lançamentos"
        ),
        data=resultado,
    )
