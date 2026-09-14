"""
Controller para NFS-e Padrao Nacional.

Endpoints REST para emissao, consulta e cancelamento de NFS-e.
Preparacao para migracao do padrao ABRASF para o Padrao Nacional de NFS-e.

Portal: https://www.gov.br/nfse
Documentacao: https://www.gov.br/nfse/pt-br/acesso-a-informacao/manuais
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from core.auth.dependencies import CurrentActiveUser

from ..schemas.common import StandardResponse
from ..schemas.nfse_nacional import (
    DPSStatusEnum,
    EmitirDPSRequest,
    EmitirDPSResponse,
    StatusConexaoNacionalResponse,
)
from ..services.nfse_nacional_service import get_nfse_nacional_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfse-nacional", tags=["NFS-e Padrao Nacional"])


@router.post(
    "/emitir",
    response_model=StandardResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Emite DPS (Padrao Nacional)",
    description="""
    Emite Declaracao de Prestacao de Servicos (DPS) no Padrao Nacional.

    **IMPORTANTE**: O Padrao Nacional ainda nao esta disponivel em Manaus.
    Este endpoint prepara o payload para quando a migracao estiver disponivel.
    Para emissoes atuais, use /nfse-manaus/emitir.
    """,
)
async def emitir_dps(current_user: CurrentActiveUser, request: EmitirDPSRequest) -> StandardResponse:
    """
    Emite DPS (Declaracao de Prestacao de Servicos).

    No Padrao Nacional, o RPS foi substituido pela DPS.
    Este endpoint esta em preparacao para a migracao prevista para 2026.

    Args:
        request: Dados para emissao (tomador, servico, competencia).

    Returns:
        StandardResponse com payload preparado.
    """
    try:
        service = get_nfse_nacional_service()

        prestador_data = request.prestador.model_dump() if request.prestador else None

        resultado = service.emitir_dps(
            tomador_data=request.tomador.model_dump(),
            servico_data=request.servico.model_dump(),
            prestador_data=prestador_data,
            competencia=request.competencia,
            tipo_tributacao=request.tipo_tributacao.value,
            dry_run=getattr(request, "dry_run", False),
        )

        # Resultado real do manager (pode conter xml_gerado, http_status, response, etc.)
        status_dps = resultado.get("status", "preparacao")
        sucesso = status_dps in ("aceita", "dry_run", "preparacao")
        if not sucesso:  # 08/09/2026: rejeição voltava 202 e o front dizia "emitida com sucesso"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"NFS-e Nacional {status_dps}: {resultado.get('erro') or resultado.get('mensagem') or resultado.get('response') or 'sem detalhe'}"
                       + (f" (HTTP {resultado.get('http_status')})" if resultado.get("http_status") else ""),
            )

        response_data = EmitirDPSResponse(
            id_dps=resultado.get("id_dps"),
            numero_dps=resultado.get("numero_dps"),
            status=DPSStatusEnum.AUTORIZADA if status_dps == "aceita" else DPSStatusEnum.PREPARACAO,
            mensagem=resultado.get("mensagem") or resultado.get("erro"),
            data_emissao=datetime.now(),
            valor_servico=request.servico.valor_servico,
            valor_iss=request.servico.valor_servico * request.servico.aliquota_iss,
            valor_liquido=resultado.get("valor_liquido"),
            tomador_cpf_cnpj=request.tomador.cpf_cnpj,
            previsao_migracao=None,
            payload_json=None,  # Dados extras vão no dict separado
        )

        # Incluir dados da transmissão real
        extra = {}
        for k in ("http_status", "response", "xml_gerado", "xml_assinado", "xml_tamanho", "fonte", "erro"):
            if k in resultado:
                extra[k] = resultado[k]

        resp_dict = response_data.model_dump()
        resp_dict.update(extra)

        return StandardResponse(
            success=sucesso,
            message=f"NFS-e Nacional: {status_dps}"
            + (f" — HTTP {resultado.get('http_status')}" if resultado.get("http_status") else ""),
            data=resp_dict,
        )

    except HTTPException:
        # O bloco acima levanta 422 com a rejeição EXATA do governo (código e descrição).
        # Sem este re-raise, o `except Exception` abaixo capturava a própria HTTPException e
        # devolvia 500 "Erro interno ao preparar DPS" — jogando fora a única informação útil.
        # Medido em 14/09/2026: o governo respondeu «E0310 — O código de tributação nacional
        # informado não existe conforme a lista de serviços nacional» e o usuário leu
        # "erro interno". A causa estava escrita no log e não chegava a quem podia corrigir.
        raise
    except ValueError as e:
        logger.warning(f"Dados invalidos para emissao DPS: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dados invalidos: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Erro ao preparar DPS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao preparar DPS",
        )


@router.get(
    "/status",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Valida conexao e status",
    description="Verifica status da API e configuracao do Padrao Nacional.",
)
async def validar_conexao(current_user: CurrentActiveUser) -> StandardResponse:
    """
    Valida conexao e status do Padrao Nacional.

    Verifica:
    - Status da API Nacional
    - Configuracao do certificado digital
    - Disponibilidade da migracao

    Returns:
        StandardResponse com status da conexao.
    """
    try:
        service = get_nfse_nacional_service()
        resultado = service.validar_conexao()

        response_data = StatusConexaoNacionalResponse(
            ambiente=resultado.get("ambiente", ""),
            cnpj=resultado.get("cnpj", ""),
            url_base=resultado.get("url_base", ""),
            status_api=resultado.get("status_api", "preparacao"),
            certificado_configurado=resultado.get("certificado_configurado", False),
            certificado_valido=resultado.get("certificado_valido"),
            certificado_expira=resultado.get("certificado_expira"),
            migracao_disponivel=resultado.get("migracao_disponivel", False),
            mensagem=resultado.get("mensagem"),
        )

        return StandardResponse(
            success=True,
            message="Validacao de status concluida",
            data=response_data.model_dump(),
        )

    except Exception as e:
        logger.error(f"Erro ao validar conexao: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao validar conexao",
        )


