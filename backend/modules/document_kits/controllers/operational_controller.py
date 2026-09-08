"""Controller de Integração Operacional - Document Kits."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.document_kits.services.kit_monthly_generator_service import KitMonthlyGeneratorService
from modules.document_kits.services.kit_operational_service import KitOperationalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document-kits-operational", tags=["Document Kits - Operational"])


async def get_operational_service(db: AsyncSession = Depends(get_db)) -> KitOperationalService:
    """Retorna instancia do Operational service."""
    return KitOperationalService(db)


async def get_generator_service(db: AsyncSession = Depends(get_db)) -> KitMonthlyGeneratorService:
    """Retorna instancia do Monthly Generator service."""
    return KitMonthlyGeneratorService(db)


# === Operational Integration Endpoints ===


# === Monthly Kit Generation Endpoints ===


# === Scheduler Management Endpoints ===


