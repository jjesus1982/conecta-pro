"""
Controller de Turnover para RH.

Fornece dashboard com dados reais de admissoes, desligamentos
e taxa de turnover baseados na tabela employees, incluindo o gap
honesto de motivos de desligamento nao informados.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.human_resources.services.turnover_service import (
    TurnoverService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/turnover", tags=["RH - Turnover"])


@router.get("/dashboard")
async def turnover_dashboard(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard de turnover com dados reais."""
    try:
        return await TurnoverService(db).dashboard()
    except Exception as exc:
        logger.warning("Erro no dashboard turnover: %s", exc)
        return {"total_colaboradores": 0, "taxa_turnover_trimestral": 0, "erro": str(exc)}


@router.get("/motivos")
async def turnover_motivos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Distribuicao por motivo de desligamento nos ultimos 12 meses."""
    try:
        return await TurnoverService(db).motivos()
    except Exception as exc:
        logger.warning("Erro ao buscar motivos: %s", exc)
        return {"motivos": [], "periodo": "12_meses", "erro": str(exc)}
