"""
Controller para integrações com eSocial.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db

# Import real transmitter
from ..schemas.common import StandardResponse
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

    # 08/09/2026: eventos_esocial era órfã (0 linhas, sem INSERT); a verdade é o ESPELHO do
    # governo (esocial_eventos_espelho), que o beat sincroniza. Status = recebido pelo eSocial.
    if tipo_evento:
        conditions.append("tipo = :tipo_evento")
        params["tipo_evento"] = tipo_evento
    if status_filter and status_filter.lower() not in ("recebido", "sucesso", "processado"):
        conditions.append("false")  # o espelho só tem eventos recebidos
    if data_inicial:
        conditions.append("COALESCE(dt_recepcao, dt_evento) >= :data_inicial")
        params["data_inicial"] = data_inicial
    if data_final:
        conditions.append("COALESCE(dt_recepcao, dt_evento) <= :data_final")
        params["data_final"] = data_final

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    result = await db.execute(
        text(
            "SELECT id, tipo AS tipo_evento, 'recebido' AS status, to_char(dt_evento, 'YYYY-MM') AS competencia, "
            "dt_evento AS data_geracao, dt_recepcao AS data_envio, dt_recepcao AS data_retorno, "
            "id_evento AS protocolo, nr_recibo AS recibo, NULL AS erro_codigo, NULL AS erro_mensagem, 1 AS tentativas, "
            "cpf_trabalhador "
            f"FROM esocial_eventos_espelho{where} "
            "ORDER BY COALESCE(dt_recepcao, dt_evento) DESC NULLS LAST LIMIT 500"
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
            "cpf_trabalhador": r["cpf_trabalhador"],
        }
        for r in rows
    ]
    return StandardResponse(
        success=True,
        message=f"{len(itens)} evento(s) encontrado(s)",
        data={"items": itens, "total": len(itens)},
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
                COUNT(*) FILTER (WHERE status = 'ativo') as total_ativos,
                COUNT(*) FILTER (WHERE status = 'ativo' AND cpf IS NOT NULL AND cpf != '') as com_cpf,
                COUNT(*) FILTER (WHERE status = 'ativo' AND data_nascimento IS NOT NULL) as com_nascimento,
                COUNT(*) FILTER (WHERE status = 'ativo' AND data_admissao IS NOT NULL) as com_admissao,
                COUNT(*) FILTER (WHERE status = 'ativo' AND salario_base IS NOT NULL) as com_salario,
                COUNT(*) FILTER (WHERE status = 'ativo' AND sexo IS NOT NULL AND sexo != '') as com_sexo,
                COUNT(*) FILTER (WHERE status = 'ativo' AND rg IS NOT NULL AND rg != '') as com_rg,
                COUNT(*) FILTER (WHERE status = 'ativo' AND estado_civil IS NOT NULL AND estado_civil != '') as com_estado_civil,
                COUNT(*) FILTER (WHERE status = 'ativo' AND matricula IS NOT NULL AND matricula != '') as com_matricula,
                COUNT(*) FILTER (WHERE status = 'ativo' AND pis IS NOT NULL AND pis != '') as com_pis
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
