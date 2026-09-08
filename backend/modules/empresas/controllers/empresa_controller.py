"""Controller para o módulo de Empresas (Multi-CNPJ)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import CurrentActiveUser, get_tenant_id
from core.database import get_db
from modules.empresas.schemas.empresa_schemas import (
    EmpresaListResponse,
    SimulacaoRegime,
)
from modules.empresas.services import empresa_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/empresas", tags=["Empresas - Multi-CNPJ"])


# ===================================================================
# REQUEST BODIES AUXILIARES
# ===================================================================


class SimularRegimeBody(BaseModel):
    novo_regime: str
    faturamento_anual: float


# ===================================================================
# EMPRESA ENDPOINTS
# ===================================================================


@router.get(
    "/",
    response_model=list[EmpresaListResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar empresas",
)
async def listar_empresas(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    status_filtro: str | None = Query(None, alias="status", description="Filtrar por status"),
) -> list[EmpresaListResponse]:
    """Lista todas as empresas do grupo empresarial."""
    try:
        condominio_id = UUID(get_tenant_id(current_user))
        return await empresa_service.listar_empresas(db, condominio_id, status_filtro=status_filtro)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Erro ao listar empresas: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar empresas",
        ) from exc


@router.post(
    "/{empresa_id}/simular-regime",
    response_model=SimulacaoRegime,
    status_code=status.HTTP_200_OK,
    summary="Simular mudança de regime tributário",
)
async def simular_mudanca_regime(
    empresa_id: UUID,
    body: SimularRegimeBody,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> SimulacaoRegime:
    """Simula a carga tributária em outro regime e calcula a economia potencial."""
    try:
        condominio_id = UUID(get_tenant_id(current_user))
        return await empresa_service.simular_mudanca_regime(
            db, empresa_id, body.novo_regime, body.faturamento_anual, condominio_id
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Erro ao simular regime: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao simular regime tributário",
        ) from exc


# ===================================================================
# LIMINARES ENDPOINTS
# ===================================================================


