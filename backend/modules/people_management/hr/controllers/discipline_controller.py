"""
Controller de Medidas Disciplinares — Departamento Pessoal.

Re-exporta endpoints disciplinares do operacional e adiciona endpoints DP:
histórico por funcionário e criação a partir de ocorrência.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.services.discipline_service import DisciplineService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discipline", tags=["DP - Disciplinar"])

# Re-export do router existente de disciplinares
# IMPORTANTE: usar include_router (NÃO append) para preservar prefixos
try:
    from modules.operacional.disciplinary.controllers import disciplinary_router

    router.include_router(disciplinary_router)
except ImportError:
    logger.info("Router disciplinar operacional não disponível para re-export")


@router.get(
    "/employee/{employee_id}/history",
    summary="Histórico Disciplinar do Funcionário",
    description="Retorna histórico completo de medidas disciplinares de um funcionário com paginação.",
)
async def get_employee_discipline_history(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """Retorna histórico disciplinar completo de um funcionário."""
    service = DisciplineService(db)
    return await service.get_employee_history(employee_id, page=page, page_size=page_size)


