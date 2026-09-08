"""Controller de Kits Documentais - Versão Async com Autenticação."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.document_kits.services.kit_ai_service import DocumentKitAIService
from modules.document_kits.services.kit_operational_service import KitOperationalService
from modules.document_kits.services.kit_service import DocumentKitService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document-kits", tags=["Document Kits"])


async def get_service(db: AsyncSession = Depends(get_db)) -> DocumentKitService:
    """Retorna instancia do service."""
    return DocumentKitService(db)


async def get_ai_service(db: AsyncSession = Depends(get_db)) -> DocumentKitAIService:
    """Retorna instancia do AI service."""
    return DocumentKitAIService(db)


async def get_operational_service(db: AsyncSession = Depends(get_db)) -> KitOperationalService:
    """Retorna instancia do Operational service."""
    return KitOperationalService(db)


# === Kit Endpoints ===


# === Kit Item Endpoints ===


# === Assignment Endpoints ===


# === Item Status Endpoints ===


# === AI Endpoints ===


# === Operational Integration Endpoints ===


