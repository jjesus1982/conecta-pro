"""
Controller para Ordem de Servico.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.campo.models.ordem_servico import OrigemOS, PrioridadeOS, StatusOS, TipoOS
from modules.campo.schemas.ordem_servico import (
    OrdemServicoListItem,
    OSDashboardStats,
    OSFiltro,
    OSPaginatedResponse,
)
from modules.campo.services.ordem_servico_service import OrdemServicoService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> OrdemServicoService:
    """Dependency para obter service."""
    return OrdemServicoService(db)


# =============================================================================
# CRUD
# =============================================================================


@router.get("/", response_model=OSPaginatedResponse)
async def listar_os(
    current_user: CurrentActiveUser,
    tipo: TipoOS | None = None,
    status_os: StatusOS | None = Query(None, alias="status"),
    prioridade: PrioridadeOS | None = None,
    origem: OrigemOS | None = None,
    cliente_id: UUID | None = None,
    tecnico_id: UUID | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cidade: str | None = None,
    estado: str | None = None,
    sla_vencido: bool | None = None,
    busca: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    service: OrdemServicoService = Depends(get_service),
):
    """Lista Ordens de Servico com filtros e paginacao."""
    filtro = OSFiltro(
        tipo=tipo,
        status=status_os,
        prioridade=prioridade,
        origem=origem,
        cliente_id=cliente_id,
        tecnico_id=tecnico_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        cidade=cidade,
        estado=estado,
        sla_vencido=sla_vencido,
        busca=busca,
    )
    return await service.listar_os(filtro, page, page_size)


@router.get("/atrasadas", response_model=list[OrdemServicoListItem])
async def listar_os_atrasadas(
    current_user: CurrentActiveUser,
    service: OrdemServicoService = Depends(get_service),
):
    """Lista OS com SLA vencido."""
    os_list = await service.listar_os_atrasadas()
    return [OrdemServicoListItem.model_validate(os) for os in os_list]


@router.get("/dashboard", response_model=OSDashboardStats)
async def obter_dashboard(
    current_user: CurrentActiveUser,
    cliente_id: UUID | None = None,
    tecnico_id: UUID | None = None,
    periodo_dias: int = Query(30, ge=1, le=365),
    service: OrdemServicoService = Depends(get_service),
):
    """Obtem estatisticas para dashboard."""
    return await service.obter_estatisticas(cliente_id, tecnico_id, periodo_dias)


# =============================================================================
# ACOES DO FLUXO
# =============================================================================


# =============================================================================
# AVALIACAO E ASSINATURA
# =============================================================================


