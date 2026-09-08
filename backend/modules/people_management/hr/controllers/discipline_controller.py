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


