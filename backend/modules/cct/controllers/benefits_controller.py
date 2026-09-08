"""
Controller de Beneficios — CCT 2026.

Endpoints para beneficios obrigatorios, validacao e taxa negocial.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.cct.services.benefits_service import BenefitsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/beneficios", tags=["CCT — Beneficios"])


@router.get("")
async def get_beneficios_cct(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna lista completa de beneficios da CCT 2026."""
    service = BenefitsService(db)
    return service.get_beneficios_cct()


@router.get("/taxa-negocial")
async def get_taxa_negocial(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    mes: int | None = Query(None, ge=1, le=12),
) -> Any:
    """Retorna informacoes da taxa negocial sindical 2026."""
    service = BenefitsService(db)
    return service.get_taxa_negocial(mes)


