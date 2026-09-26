"""
Controller REST para SPED Fiscal (EFD ICMS/IPI).

Endpoints para operações do SPED Fiscal.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.auth.dependencies import CurrentActiveUser

from fastapi.responses import PlainTextResponse

from ..schemas.common import StandardResponse
from ..schemas.sped_fiscal import GerarArquivoRequest
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


@router.post(
    "/gerar",
    summary="Gera a EFD ICMS/IPI (SPED Fiscal) do período",
    description=(
        "Gera a Escrituração Fiscal Digital a partir das NF-e modelo 55 REAIS e "
        "autorizadas em produção do CNPJ escolhido. Devolve JSON com o resumo e o "
        "conteúdo; com `formato=txt`, o arquivo puro para download.\n\n"
        "Mês sem NF-e gera arquivo SEM documento — que é a verdade. Até 25/09/2026 o "
        "carregador lia NOTAS DE SERVIÇO e as declarava como mercadoria «para não gerar "
        "arquivo oco»; arquivo oco é honesto, declaração falsa não.\n\n"
        "O arquivo NÃO vem assinado nem transmitido."
    ),
)
async def gerar_efd(
    payload: GerarArquivoRequest,
    current_user: CurrentActiveUser,
    formato: str = Query("json", pattern="^(json|txt)$"),
):
    """Gera a EFD ICMS/IPI do período para um CNPJ."""
    try:
        # Instância por requisição: o service acumula participantes, produtos e documentos
        # no manager, e reaproveitar somaria o período de uma geração na seguinte.
        service = SPEDFiscalService(empresa_slug=payload.empresa_slug)
        resultado = service.gerar_arquivo(
            periodo_inicio=payload.periodo_inicio,
            periodo_fim=payload.periodo_fim,
            finalidade=str(getattr(payload.finalidade, "value", payload.finalidade) or "0"),
            participantes=[x.model_dump() for x in payload.participantes] if payload.participantes else None,
            produtos=[x.model_dump() for x in payload.produtos] if payload.produtos else None,
            documentos=[x.model_dump() for x in payload.documentos] if payload.documentos else None,
            inventario=[x.model_dump() for x in payload.inventario] if payload.inventario else None,
        )
    except Exception as e:
        logger.error(f"Erro ao gerar EFD ICMS/IPI: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar EFD: {e}"
        )

    if not service.ie:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"O CNPJ {service.cnpj} não tem inscrição estadual cadastrada. EFD ICMS/IPI "
                "é obrigação de contribuinte do ICMS — sem IE não há o que escriturar."
            ),
        )

    if formato == "txt":
        nome = f"EFD_{service.cnpj}_{payload.periodo_inicio[:7].replace('-', '')}.txt"
        return PlainTextResponse(
            resultado["conteudo"],
            media_type="text/plain; charset=latin-1",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )

    return StandardResponse(
        success=True,
        message=(
            f"EFD ICMS/IPI gerada: {resultado.get('total_registros')} registros, "
            f"{resultado.get('total_documentos')} documento(s)"
        ),
        data=resultado,
    )
