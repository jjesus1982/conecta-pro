"""
Controller para NFS-e Padrao Nacional.

Endpoints REST para emissao, consulta e cancelamento de NFS-e.
Preparacao para migracao do padrao ABRASF para o Padrao Nacional de NFS-e.

Portal: https://www.gov.br/nfse
Documentacao: https://www.gov.br/nfse/pt-br/acesso-a-informacao/manuais
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Path, status

from core.auth.dependencies import CurrentActiveUser

from ..schemas.common import StandardResponse
from ..schemas.nfse_nacional import (
    CancelarNFSeNacionalRequest,
    CancelarNFSeNacionalResponse,
    DPSStatusEnum,
    EmitirDPSRequest,
    EmitirDPSResponse,
    StatusConexaoNacionalResponse,
    StatusMigracaoResponse,
    SubstituirNFSeNacionalRequest,
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
    "/consultar/dps/{id_dps}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta DPS por ID",
    description="Consulta DPS pelo ID. Em preparacao para migracao.",
)
async def consultar_dps(
    current_user: CurrentActiveUser,
    id_dps: str = Path(..., description="ID da DPS"),
) -> StandardResponse:
    """
    Consulta DPS pelo ID.

    NOTA: Em preparacao para quando a migracao estiver disponivel.

    Args:
        id_dps: ID da DPS.

    Returns:
        StandardResponse com dados da DPS.
    """
    try:
        service = get_nfse_nacional_service()
        resultado = service.consultar_dps(id_dps)

        return StandardResponse(
            success=True,
            message="Consulta em preparacao",
            data=resultado,
        )

    except Exception as e:
        logger.error(f"Erro ao consultar DPS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao consultar DPS",
        )


@router.get(
    "/consultar/nfse/{numero_nfse}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta NFS-e por numero nacional",
    description="Consulta NFS-e pelo numero nacional. Em preparacao para migracao.",
)
async def consultar_nfse(
    current_user: CurrentActiveUser,
    numero_nfse: str = Path(..., description="Numero nacional da NFS-e"),
) -> StandardResponse:
    """
    Consulta NFS-e pelo numero nacional.

    NOTA: Em preparacao para quando a migracao estiver disponivel.

    Args:
        numero_nfse: Numero nacional da NFS-e.

    Returns:
        StandardResponse com dados da NFS-e.
    """
    try:
        service = get_nfse_nacional_service()
        resultado = service.consultar_nfse(numero_nfse)

        return StandardResponse(
            success=True,
            message="Consulta em preparacao",
            data=resultado,
        )

    except Exception as e:
        logger.error(f"Erro ao consultar NFS-e: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao consultar NFS-e",
        )


@router.post(
    "/cancelar",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancela NFS-e (Padrao Nacional)",
    description="Cancela uma NFS-e no Padrao Nacional. Em preparacao para migracao.",
)
async def cancelar_nfse(current_user: CurrentActiveUser, request: CancelarNFSeNacionalRequest) -> StandardResponse:
    """
    Cancela uma NFS-e no Padrao Nacional.

    NOTA: Em preparacao. Use /nfse-manaus/cancelar para o padrao atual.

    Args:
        request: Dados do cancelamento.

    Returns:
        StandardResponse com resultado.
    """
    try:
        service = get_nfse_nacional_service()

        resultado = service.cancelar_nfse(
            numero_nfse=request.numero_nfse,
            motivo_cancelamento=request.motivo_cancelamento.value,
            justificativa=request.justificativa,
        )

        response_data = CancelarNFSeNacionalResponse(
            numero_nfse=request.numero_nfse,
            status=DPSStatusEnum.PREPARACAO,
            mensagem=resultado.get("mensagem"),
        )

        return StandardResponse(
            success=True,
            message="Cancelamento em preparacao",
            data=response_data.model_dump(),
        )

    except Exception as e:
        logger.error(f"Erro ao cancelar NFS-e: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao cancelar NFS-e",
        )


@router.post(
    "/substituir",
    response_model=StandardResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Substitui NFS-e (Padrao Nacional)",
    description="Substitui uma NFS-e no Padrao Nacional. Em preparacao para migracao.",
)
async def substituir_nfse(current_user: CurrentActiveUser, request: SubstituirNFSeNacionalRequest) -> StandardResponse:
    """
    Substitui uma NFS-e no Padrao Nacional.

    NOTA: Em preparacao. Use /nfse-manaus/substituir para o padrao atual.

    Args:
        request: Dados da substituicao.

    Returns:
        StandardResponse com resultado.
    """
    try:
        service = get_nfse_nacional_service()

        resultado = service.substituir_nfse(
            numero_nfse_substituida=request.numero_nfse_substituida,
            tomador_data=request.tomador.model_dump(),
            servico_data=request.servico.model_dump(),
        )

        return StandardResponse(
            success=True,
            message="Substituicao em preparacao",
            data=resultado,
        )

    except Exception as e:
        logger.error(f"Erro ao substituir NFS-e: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao substituir NFS-e",
        )


@router.get(
    "/eventos/{numero_nfse}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta eventos de NFS-e",
    description="Consulta eventos de uma NFS-e no Padrao Nacional.",
)
async def consultar_eventos(
    current_user: CurrentActiveUser,
    numero_nfse: str = Path(..., description="Numero nacional da NFS-e"),
) -> StandardResponse:
    """
    Consulta eventos de uma NFS-e.

    NOTA: Em preparacao para quando a migracao estiver disponivel.

    Args:
        numero_nfse: Numero nacional da NFS-e.

    Returns:
        StandardResponse com eventos da NFS-e.
    """
    try:
        service = get_nfse_nacional_service()
        resultado = service.consultar_eventos(numero_nfse)

        return StandardResponse(
            success=True,
            message="Consulta de eventos em preparacao",
            data=resultado,
        )

    except Exception as e:
        logger.error(f"Erro ao consultar eventos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao consultar eventos",
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


@router.get(
    "/migracao/status",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Status da migracao",
    description="Consulta o status da migracao para o Padrao Nacional.",
)
async def status_migracao(current_user: CurrentActiveUser) -> StandardResponse:
    """
    Consulta status da migracao para o Padrao Nacional.

    Retorna informacoes sobre:
    - Status atual da migracao
    - Previsao de disponibilidade
    - Padrao atualmente em uso
    - Links uteis

    Returns:
        StandardResponse com status da migracao.
    """
    try:
        service = get_nfse_nacional_service()
        resultado = service.consultar_status_migracao()

        response_data = StatusMigracaoResponse(
            municipio=resultado.get("municipio", ""),
            codigo_ibge=resultado.get("codigo_ibge", ""),
            padrao_atual=resultado.get("padrao_atual", ""),
            provedor_atual=resultado.get("provedor_atual", ""),
            migracao_prevista=resultado.get("migracao_prevista", ""),
            status=resultado.get("status", ""),
            notas=resultado.get("notas", []),
            links_uteis=resultado.get("links_uteis", {}),
        )

        return StandardResponse(
            success=True,
            message="Status da migracao consultado",
            data=response_data.model_dump(),
        )

    except Exception as e:
        logger.error(f"Erro ao consultar status migracao: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao consultar status da migracao",
        )


@router.get(
    "/migracao/comparar-padroes",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Compara padroes ABRASF x Nacional",
    description="Compara caracteristicas entre o padrao atual (ABRASF) e o Padrao Nacional.",
)
async def comparar_padroes(current_user: CurrentActiveUser) -> StandardResponse:
    """
    Compara caracteristicas entre padroes.

    Retorna comparacao detalhada entre:
    - ABRASF 2.04 (padrao atual em Manaus)
    - Padrao Nacional de NFS-e

    Returns:
        StandardResponse com comparacao.
    """
    try:
        service = get_nfse_nacional_service()
        resultado = service.comparar_padroes()

        return StandardResponse(
            success=True,
            message="Comparacao de padroes",
            data=resultado,
        )

    except Exception as e:
        logger.error(f"Erro ao comparar padroes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao comparar padroes",
        )


@router.get(
    "/migracao/mapeamento-servicos",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Mapeamento de codigos de servico",
    description="Lista mapeamento de codigos ABRASF para NBS (Padrao Nacional).",
)
async def mapeamento_servicos(current_user: CurrentActiveUser) -> StandardResponse:
    """
    Obtem mapeamento de codigos de servico.

    Retorna correspondencia entre:
    - Codigos ABRASF (LC 116)
    - Codigos NBS (Nomenclatura Brasileira de Servicos)

    Returns:
        StandardResponse com mapeamentos.
    """
    try:
        service = get_nfse_nacional_service()
        mapeamentos = service.obter_mapeamento_servicos()

        return StandardResponse(
            success=True,
            message="Mapeamento de codigos de servico",
            data={"mapeamentos": mapeamentos},
        )

    except Exception as e:
        logger.error(f"Erro ao obter mapeamento: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter mapeamento de servicos",
        )


@router.get(
    "/codigos-servico",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista codigos de servico NBS",
    description="Lista codigos de servico NBS disponiveis no Padrao Nacional.",
)
async def listar_codigos_servico(current_user: CurrentActiveUser) -> StandardResponse:
    """
    Lista codigos de servico NBS.

    Retorna codigos da Nomenclatura Brasileira de Servicos (NBS)
    mais usados para o setor de vigilancia e seguranca.

    Returns:
        StandardResponse com lista de codigos.
    """
    try:
        service = get_nfse_nacional_service()
        codigos = service.listar_codigos_servico_nacional()

        return StandardResponse(
            success=True,
            message="Codigos de servico NBS disponiveis",
            data={"codigos": codigos},
        )

    except Exception as e:
        logger.error(f"Erro ao listar codigos: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar codigos de servico",
        )


@router.get(
    "/info",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Informacoes do Padrao Nacional",
    description="Retorna informacoes gerais sobre o Padrao Nacional de NFS-e.",
)
async def info_padrao_nacional(current_user: CurrentActiveUser) -> StandardResponse:
    """
    Informacoes gerais do Padrao Nacional.

    Retorna informacoes sobre:
    - O que e o Padrao Nacional
    - Principais caracteristicas
    - Documentacao e links uteis

    Returns:
        StandardResponse com informacoes.
    """
    info = {
        "nome": "Padrao Nacional de NFS-e",
        "orgao_responsavel": "Receita Federal do Brasil / SPED",
        "portal": "https://www.gov.br/nfse",
        "documentacao": "https://www.gov.br/nfse/pt-br/acesso-a-informacao/manuais",
        "caracteristicas": {
            "protocolo": "REST/JSON (substitui SOAP/XML)",
            "autenticacao": "Certificado Digital + Gov.br",
            "documento": "DPS (Declaracao de Prestacao de Servicos)",
            "numeracao": "Nacional (unico em todo Brasil)",
            "ambiente_dados": "AUD (Ambiente Unico de Dados)",
        },
        "beneficios": [
            "Numero unico nacional da NFS-e",
            "Integracao automatica com eSocial e DCTFWeb",
            "API moderna e padronizada (REST/JSON)",
            "Simplificacao de obrigacoes acessorias",
            "Maior seguranca e rastreabilidade",
        ],
        "status_manaus": {
            "padrao_atual": "ABRASF 2.04",
            "provedor": "Abaco/GIF",
            "migracao_prevista": "2026",
            "status": "Aguardando migracao",
        },
    }

    return StandardResponse(
        success=True,
        message="Informacoes do Padrao Nacional",
        data=info,
    )


@router.get("/tomadores", response_model=StandardResponse)
async def listar_tomadores_endpoint(current_user: CurrentActiveUser) -> StandardResponse:
    """Lista os tomadores (condomínios) com endereço completo, p/ o seletor do emissor."""
    try:
        from modules.gedeon.services.nfse_nacional_adn import listar_tomadores

        tomadores = listar_tomadores()
        return StandardResponse(success=True, message=f"{len(tomadores)} tomadores", data={"tomadores": tomadores})
    except Exception as e:
        logger.error(f"Erro ao listar tomadores: {e}", exc_info=True)
        return StandardResponse(success=False, message=f"Erro: {str(e)[:120]}", data={"tomadores": []})
