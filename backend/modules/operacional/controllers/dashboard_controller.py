"""
Controller de Dashboard Unificado do Operacional.

Fornece endpoints para:
- Dashboard consolidado (funcionários + diaristas)
- Métricas de ocupação
- Alocação de diaristas a postos
- Sugestões de alocação
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.services.integration_service import (
    get_integration_service,
)

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class AlocarDiaristaPostoRequest(BaseModel):
    """Request para alocar diarista a um condomínio.

    REWRITE (Ciclo 3, item 15): alinhado ao schema atual de diarist_assignments
    (condominio_id/unidade_id/data_inicio/data_fim). Campos antigos removidos
    sem equivalente no banco: post_id (→ condominio_id), shift_id, cliente_id,
    contrato_id.
    """

    diarista_id: UUID
    condominio_id: UUID
    data_inicio: date
    data_fim: date | None = None
    unidade_id: UUID | None = None
    valor_acordado: Decimal | None = Field(None, ge=0)
    observacoes: str | None = Field(None, max_length=500)


class DesalocarDiaristaRequest(BaseModel):
    """Request para desalocar diarista."""

    motivo: str | None = Field(None, max_length=500)


class DashboardResponse(BaseModel):
    """Response do dashboard unificado."""

    data_referencia: str
    postos: dict[str, Any]
    escalas: dict[str, Any]
    turnos: dict[str, Any]
    funcionarios: dict[str, Any]
    diaristas: dict[str, Any]
    ocupacao: dict[str, Any]
    alertas: list[dict[str, Any]]


class MetricasPeriodoResponse(BaseModel):
    """Response das métricas de período."""

    periodo: dict[str, Any]
    diaristas: dict[str, Any]
    funcionarios: dict[str, Any]
    consolidado: dict[str, Any]


class OcupacaoPostoResponse(BaseModel):
    """Response da ocupação de um posto."""

    posto_id: str
    posto_nome: str
    posto_tipo: str
    funcionarios_alocados: int
    diaristas_alocados: int
    total_alocados: int
    status: str
    detalhes: dict[str, Any]


class SugestaoDiaristaResponse(BaseModel):
    """Response de sugestão de diarista."""

    diarist_id: str
    nome: str
    score: int
    motivos: list[str]
    avaliacao: float | None = None
    total_servicos: int


# =============================================================================
# ENDPOINTS - DASHBOARD
# =============================================================================


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Dashboard unificado",
    description="Retorna métricas consolidadas de funcionários fixos e diaristas",
)
async def get_dashboard(
    current_user: CurrentActiveUser,
    data: date | None = Query(None, description="Data de referência (default: hoje)"),
    cliente_id: UUID | None = Query(None, description="Filtrar por cliente"),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """
    Retorna dashboard unificado do operacional.

    Inclui:
    - Status de postos
    - Escalas e turnos
    - Funcionários alocados
    - Diaristas em serviço
    - Taxa de ocupação
    - Alertas automáticos
    """
    service = get_integration_service(db)

    try:
        dashboard = await service.get_dashboard_unificado(
            data_referencia=data,
            cliente_id=cliente_id,
        )
        return dashboard
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar dashboard: {str(e)}"
        )


# =============================================================================
# ENDPOINTS - OCUPAÇÃO DE POSTOS
# =============================================================================


# =============================================================================
# ENDPOINTS - ALOCAÇÃO DE DIARISTAS
# =============================================================================


# =============================================================================
# ENDPOINTS - SUGESTÕES
# =============================================================================


# =============================================================================
# ENDPOINTS - RELATÓRIOS RÁPIDOS
# =============================================================================


