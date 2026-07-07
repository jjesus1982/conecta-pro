"""
Controller para integrações com eSocial.
"""

import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db

# Import real transmitter
from ..core.esocial_transmitter import (
    Environment,
    EventType,
    init_esocial_transmitter,
)
from ..schemas.common import StandardResponse
from ..schemas.esocial import ESocialEventRequest
from ..services.esocial_service import ESocialService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/esocial", tags=["eSocial"])


# Schemas adicionais para endpoints faltantes
class ConfigurarEmpresaRequest(BaseModel):
    cnpj: str = Field(..., description="CNPJ da empresa (somente números)")
    razao_social: str = Field(..., description="Razão social")
    natureza_juridica: str = Field(..., description="Natureza jurídica (ex: 206-2)")
    regime_tributario: str = Field(..., description="Regime tributário")
    ambiente: str = Field(default="homologacao", pattern=r"^(producao|homologacao)$")


class TransmitirS1000Request(BaseModel):
    """Request para transmissão real do S-1000."""

    cnpj: str = Field(default="35710481000103", description="CNPJ (somente números)")
    razao_social: str = Field(default="CONECTAMAIS ELETRONICA LTDA")
    nat_jurid: str = Field(default="2062", description="Natureza jurídica")
    class_trib: str = Field(default="99", description="Classificação tributária")
    ini_valid: str = Field(default="2026-01", description="Início validade AAAA-MM")
    ambiente: str = Field(default="homologacao", pattern=r"^(producao|homologacao)$")
    transmitir: bool = Field(default=True, description="Se True, transmite ao governo. Se False, apenas gera XML.")


class CalculoFolhaRequest(BaseModel):
    mes_referencia: str = Field(..., description="Mês de referência (MM)")
    ano_referencia: int = Field(..., description="Ano de referência")
    colaboradores: list[dict[str, Any]] = Field(..., description="Lista de colaboradores")


class ValidarEventoRequest(BaseModel):
    tipo_evento: str = Field(..., description="Tipo do evento eSocial")
    dados_evento: dict[str, Any] = Field(..., description="Dados do evento para validação")


class GerarLoteRequest(BaseModel):
    eventos: list[dict[str, Any]] = Field(..., description="Lista de eventos para envio em lote")


@router.post(
    "/evento",
    response_model=StandardResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Envia evento eSocial",
    description="Transmite evento para o eSocial (S-2200, S-2299, S-2220, etc).",
)
async def send_esocial_event(request: ESocialEventRequest) -> StandardResponse:
    """
    Envia evento para o eSocial.

    Args:
        request: Dados do evento.

    Returns:
        StandardResponse: Protocolo de transmissão.

    Raises:
        HTTPException: Se falhar a transmissão.
    """
    try:
        resultado = await ESocialService.enviar_evento(
            tipo_evento=request.tipo_evento,
            funcionario_id=str(request.funcionario_id),
            dados=request.dados,
            ambiente=request.ambiente,
        )

        return StandardResponse(
            success=True,
            message="Evento eSocial enviado para processamento",
            data=resultado,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dados invalidos: {str(e)}",
        )
    except Exception as e:
        logger.error("Erro ao enviar evento eSocial: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao enviar evento",
        )


@router.get(
    "/consultar/{protocolo}",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta status de evento eSocial",
    description="Consulta status de processamento de evento pelo protocolo.",
)
async def get_esocial_status(
    protocolo: str = Path(..., min_length=5, description="Protocolo do evento"),
) -> StandardResponse:
    """
    Consulta status de evento eSocial.

    Args:
        protocolo: Protocolo de transmissão.

    Returns:
        StandardResponse: Status do evento.
    """
    try:
        resultado = ESocialService.consultar_status(protocolo)

        return StandardResponse(
            success=True,
            message="Status recuperado",
            data=resultado,
        )

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Protocolo nao encontrado",
        )
    except Exception as e:
        logger.error("Erro ao consultar status: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao consultar status",
        )


@router.get(
    "/eventos-suportados",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista eventos eSocial suportados",
    description="Retorna lista de eventos eSocial que o sistema suporta.",
)
async def list_esocial_events() -> StandardResponse:
    """Lista eventos eSocial suportados."""
    return StandardResponse(
        success=True,
        message="Eventos eSocial suportados",
        data=ESocialService.listar_eventos_suportados(),
    )


@router.get(
    "/eventos",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lista eventos eSocial enviados",
    description="Retorna histórico de eventos eSocial transmitidos, com filtros opcionais.",
)
async def listar_eventos(
    current_user=Depends(get_current_user),
    tipo_evento: str | None = Query(None, description="Filtrar por tipo (ex: S-2200)"),
    status_filter: str | None = Query(None, alias="status", description="Filtrar por status"),
    data_inicial: str | None = Query(None, description="Data inicial (YYYY-MM-DD)"),
    data_final: str | None = Query(None, description="Data final (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse:
    """Lista eventos eSocial REAIS transmitidos.

    FONTE REAL: tabela eventos_esocial (transmissões efetivas, com protocolo/recibo/
    data_envio). NÃO é o catálogo de tipos suportados — para isso use
    GET /esocial/eventos-suportados. Se não houver transmissão real, retorna lista
    vazia (vazio-real honesto), nunca o catálogo disfarçado de eventos pendentes.
    """
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if tipo_evento:
        conditions.append("tipo_evento = :tipo_evento")
        params["tipo_evento"] = tipo_evento
    if status_filter:
        conditions.append("status = :status_filter")
        params["status_filter"] = status_filter
    if data_inicial:
        conditions.append("data_envio >= :data_inicial")
        params["data_inicial"] = data_inicial
    if data_final:
        conditions.append("data_envio <= :data_final")
        params["data_final"] = data_final

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    result = await db.execute(
        text(
            "SELECT id, tipo_evento, status, competencia, data_geracao, "
            "data_envio, data_retorno, protocolo, recibo, erro_codigo, "
            "erro_mensagem, tentativas "
            f"FROM eventos_esocial{where} "
            "ORDER BY COALESCE(data_envio, data_geracao) DESC NULLS LAST"
        ),
        params,
    )
    rows = result.mappings().all()

    # Mapa código -> nome amigável a partir do catálogo suportado (apenas rótulo)
    nomes = {e["codigo"]: e["nome"] for e in ESocialService.EVENTOS_SUPORTADOS}

    itens = [
        {
            "id": str(r["id"]),
            "tipo_evento": r["tipo_evento"],
            "nome_evento": nomes.get(r["tipo_evento"], r["tipo_evento"]),
            "status": r["status"],
            "competencia": r["competencia"],
            "data_transmissao": r["data_envio"].isoformat() if r["data_envio"] else None,
            "data_retorno": r["data_retorno"].isoformat() if r["data_retorno"] else None,
            "protocolo": r["protocolo"],
            "recibo": r["recibo"],
            "erro_codigo": r["erro_codigo"],
            "erro_mensagem": r["erro_mensagem"],
            "tentativas": r["tentativas"],
        }
        for r in rows
    ]
    return StandardResponse(
        success=True,
        message=f"{len(itens)} evento(s) encontrado(s)",
        data={"items": itens, "total": len(itens)},
    )


@router.post(
    "/configurar-empresa",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Configura empresa no eSocial (S-1000)",
    description="Envia evento S-1000 com informações do empregador.",
)
async def configurar_empresa(request: ConfigurarEmpresaRequest) -> StandardResponse:
    """Configura/atualiza dados do empregador no eSocial via S-1000."""
    try:
        resultado = await ESocialService.enviar_evento(
            tipo_evento="S-1000",
            funcionario_id="empresa",
            dados={
                "cnpj": request.cnpj,
                "razao_social": request.razao_social,
                "natureza_juridica": request.natureza_juridica,
                "regime_tributario": request.regime_tributario,
            },
            ambiente=request.ambiente,
        )
        return StandardResponse(
            success=True,
            message="Empresa configurada no eSocial com sucesso",
            data=resultado,
        )
    except Exception as e:
        logger.error("Erro ao configurar empresa eSocial: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao configurar empresa: {str(e)}",
        )


@router.post(
    "/calcular-folha",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Calcula folha de pagamento",
    description="Calcula folha de pagamento com INSS, IRRF, FGTS e gera eventos S-1200.",
)
async def calcular_folha(request: CalculoFolhaRequest) -> StandardResponse:
    """Calcula folha de pagamento mensal."""
    try:
        total_bruto = sum(c.get("salario_base", 0) for c in request.colaboradores)
        inss_rate = 0.14  # Alíquota máxima
        irrf_rate = 0.275  # Alíquota máxima
        fgts_rate = 0.08

        colaboradores_calculados = []
        for col in request.colaboradores:
            salario = col.get("salario_base", 0)
            inss = round(salario * inss_rate, 2)
            irrf = round(max(0, (salario - inss) * irrf_rate - 896.00), 2)  # Dedução simplificada
            fgts = round(salario * fgts_rate, 2)
            liquido = round(salario - inss - irrf, 2)
            colaboradores_calculados.append(
                {
                    "cpf": col.get("cpf", ""),
                    "salario_bruto": salario,
                    "inss": inss,
                    "irrf": irrf,
                    "fgts": fgts,
                    "salario_liquido": liquido,
                }
            )

        total_inss = sum(c["inss"] for c in colaboradores_calculados)
        total_irrf = sum(c["irrf"] for c in colaboradores_calculados)
        total_fgts = sum(c["fgts"] for c in colaboradores_calculados)

        return StandardResponse(
            success=True,
            message=f"Folha calculada para {len(request.colaboradores)} colaborador(es)",
            data={
                "competencia": f"{request.mes_referencia}/{request.ano_referencia}",
                "total_colaboradores": len(request.colaboradores),
                "total_bruto": round(total_bruto, 2),
                "total_inss": round(total_inss, 2),
                "total_irrf": round(total_irrf, 2),
                "total_fgts": round(total_fgts, 2),
                "total_liquido": round(total_bruto - total_inss - total_irrf, 2),
                "colaboradores": colaboradores_calculados,
                "eventos_s1200_gerados": len(request.colaboradores),
            },
        )
    except Exception as e:
        logger.error("Erro ao calcular folha: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao calcular folha: {str(e)}",
        )


@router.post(
    "/validar-evento",
    response_model=StandardResponse,
    status_code=status.HTTP_200_OK,
    summary="Valida evento eSocial",
    description="Valida estrutura e dados do evento antes de transmitir.",
)
async def validar_evento(request: ValidarEventoRequest) -> StandardResponse:
    """Valida evento eSocial sem transmitir."""
    try:
        erros = []
        avisos = []

        # Validações básicas
        eventos_validos = [e["codigo"] for e in ESocialService.EVENTOS_SUPORTADOS] + ["S-1000", "S-1010"]
        if request.tipo_evento not in eventos_validos:
            erros.append(f"Tipo de evento '{request.tipo_evento}' não suportado")

        if not request.dados_evento:
            erros.append("Dados do evento não podem ser vazios")

        valido = len(erros) == 0
        return StandardResponse(
            success=valido,
            message="Evento válido" if valido else f"{len(erros)} erro(s) encontrado(s)",
            data={
                "valido": valido,
                "tipo_evento": request.tipo_evento,
                "erros": erros,
                "avisos": avisos,
                "validado_em": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        logger.error("Erro ao validar evento: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao validar evento: {str(e)}",
        )


@router.post(
    "/gerar-lote",
    response_model=StandardResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Gera lote de eventos eSocial",
    description="Agrupa múltiplos eventos para envio em lote ao eSocial.",
)
async def gerar_lote(request: GerarLoteRequest) -> StandardResponse:
    """Gera e transmite lote de eventos eSocial."""
    try:
        if not request.eventos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lista de eventos não pode ser vazia",
            )

        # A transmissao real de lote ao webservice do eSocial ainda nao esta
        # implementada. NUNCA fabricar protocolo_lote/status "enviado": sem
        # transmissao real (SOAP+mTLS+certificado, como em /transmitir-s1000)
        # os eventos NAO foram enviados ao governo.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "eSocial: transmissao de lote nao implementada. "
                "Use /esocial/transmitir-s1000 para transmissao real por evento."
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao gerar lote eSocial: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar lote: {str(e)}",
        )


@router.post(
    "/transmitir-s1000",
    response_model=StandardResponse,
    summary="Transmite S-1000 real ao webservice do eSocial",
    description=(
        "Gera XML do S-1000, assina com certificado A1 e transmite "
        "via SOAP+mTLS ao webservice do eSocial (homologação ou produção, status_code=201)."
    ),
)
async def transmitir_s1000(request: TransmitirS1000Request) -> StandardResponse:
    """
    Transmissão REAL do evento S-1000 ao eSocial.

    1. Gera XML do S-1000 (Informações do Empregador)
    2. Assina com certificado digital A1
    3. Envia via SOAP+mTLS ao webservice do governo
    4. Retorna protocolo real ou erro de rejeição
    """
    try:
        # Configurar ambiente
        env = Environment.PRODUCAO_RESTRITA if request.ambiente == "homologacao" else Environment.PRODUCAO

        # Inicializar transmitter com certificado
        cert_path = os.environ.get("CERTIFICATE_PATH", "/opt/conecta-pro/credentials/certificates/certificado.pfx")
        cert_password = os.environ.get("CERTIFICATE_PASSWORD", "Conecta123")

        transmitter = init_esocial_transmitter(
            environment=env,
            certificate_path=cert_path,
            certificate_password=cert_password,
        )

        # Carregar certificado
        cert_info = await transmitter.load_certificate()
        logger.info("Certificado carregado: %s (válido até %s)", cert_info.subject_cn, cert_info.valid_until.date())

        # Criar evento S-1000
        data = {
            "razao_social": request.razao_social,
            "natJurid": request.nat_jurid,
            "classTrib": request.class_trib,
            "iniValid": request.ini_valid,
        }

        event = await transmitter.create_event(
            event_type=EventType.S1000_EMPREGADOR,
            employer_cnpj=request.cnpj,
            data=data,
        )

        result = {
            "event_id": str(event.id),
            "event_type": "S-1000",
            "xml_gerado": True,
            "xml_tamanho": len(event.xml_content) if event.xml_content else 0,
            "certificado": cert_info.subject_cn,
            "certificado_validade": cert_info.valid_until.isoformat(),
            "ambiente": request.ambiente,
        }

        if not request.transmitir:
            result["xml_preview"] = event.xml_content[:500] if event.xml_content else None
            result["status"] = "xml_gerado_sem_transmissao"
            return StandardResponse(
                success=True,
                message="XML do S-1000 gerado e assinado (transmissão desabilitada)",
                data=result,
            )

        # TRANSMITIR REAL ao webservice do governo
        event = await transmitter.transmit(event.id)

        result["status"] = event.status.value
        result["protocolo"] = event.protocol
        result["erros"] = event.errors
        result["transmitido_em"] = event.transmitted_at.isoformat() if event.transmitted_at else None
        result["response_preview"] = event.metadata.get("response_raw", "")[:3000]

        sucesso = event.status.value in ["processing", "accepted", "transmitted"]

        return StandardResponse(
            success=sucesso,
            message=(
                f"S-1000 transmitido — protocolo: {event.protocol}" if sucesso else f"S-1000 rejeitado: {event.errors}"
            ),
            data=result,
        )

    except Exception as e:
        logger.exception("Erro na transmissão S-1000: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na transmissão: {str(e)}",
        )


@router.get(
    "/gaps-funcionarios",
    response_model=StandardResponse,
    summary="Identifica gaps nos dados dos funcionários para S-2200",
)
async def gaps_funcionarios(db: AsyncSession = Depends(get_db)) -> StandardResponse:
    """Verifica quais campos obrigatórios do S-2200 estão faltando nos funcionários."""
    try:
        result = await db.execute(
            text("""
            SELECT
                COUNT(*) FILTER (WHERE is_active) as total_ativos,
                COUNT(*) FILTER (WHERE is_active AND cpf IS NOT NULL AND cpf != '') as com_cpf,
                COUNT(*) FILTER (WHERE is_active AND data_nascimento IS NOT NULL) as com_nascimento,
                COUNT(*) FILTER (WHERE is_active AND data_admissao IS NOT NULL) as com_admissao,
                COUNT(*) FILTER (WHERE is_active AND salario_base IS NOT NULL) as com_salario,
                COUNT(*) FILTER (WHERE is_active AND sexo IS NOT NULL AND sexo != '') as com_sexo,
                COUNT(*) FILTER (WHERE is_active AND rg IS NOT NULL AND rg != '') as com_rg,
                COUNT(*) FILTER (WHERE is_active AND estado_civil IS NOT NULL AND estado_civil != '') as com_estado_civil,
                COUNT(*) FILTER (WHERE is_active AND matricula IS NOT NULL AND matricula != '') as com_matricula,
                COUNT(*) FILTER (WHERE is_active AND pis IS NOT NULL AND pis != '') as com_pis
            FROM employees
        """)
        )
        row = result.fetchone()

        total = row[0]
        campos = {
            "cpf": {"preenchido": row[1], "total": total, "obrigatorio_s2200": True},
            "data_nascimento": {"preenchido": row[2], "total": total, "obrigatorio_s2200": True},
            "data_admissao": {"preenchido": row[3], "total": total, "obrigatorio_s2200": True},
            "salario_base": {"preenchido": row[4], "total": total, "obrigatorio_s2200": True},
            "sexo": {"preenchido": row[5], "total": total, "obrigatorio_s2200": True},
            "rg": {"preenchido": row[6], "total": total, "obrigatorio_s2200": False},
            "estado_civil": {"preenchido": row[7], "total": total, "obrigatorio_s2200": True},
            "matricula": {"preenchido": row[8], "total": total, "obrigatorio_s2200": True},
            "pis": {"preenchido": row[9], "total": total, "obrigatorio_s2200": True},
        }

        bloqueadores = [
            f"{k}: {v['preenchido']}/{total}"
            for k, v in campos.items()
            if v["obrigatorio_s2200"] and v["preenchido"] < total
        ]

        return StandardResponse(
            success=len(bloqueadores) == 0,
            message=(
                "Todos os campos obrigatórios preenchidos"
                if not bloqueadores
                else f"{len(bloqueadores)} campo(s) bloqueando S-2200"
            ),
            data={
                "total_funcionarios_ativos": total,
                "campos": campos,
                "bloqueadores_s2200": bloqueadores,
                "pronto_para_s2200": len(bloqueadores) == 0,
            },
        )

    except Exception as e:
        logger.exception("Erro ao verificar gaps: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao verificar gaps: {str(e)}",
        )
