"""
Controller para Checklist.
"""


from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.campo.services.checklist_service import ChecklistService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> ChecklistService:
    """Dependency para obter service."""
    return ChecklistService(db)


# =============================================================================
# TEMPLATE
# =============================================================================


# =============================================================================
# ITENS
# =============================================================================


# =============================================================================
# PREENCHIMENTO
# =============================================================================


