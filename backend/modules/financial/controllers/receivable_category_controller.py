"""Controller para categorias de contas a receber."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from modules.financial.repositories.receivable_repository import ReceivableCategoryRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/receivable-categories", tags=["Categorias (Contas a Receber)"])


def get_repository(
    session: AsyncSession = Depends(get_session),
) -> ReceivableCategoryRepository:
    """Retorna instancia do repository."""
    return ReceivableCategoryRepository(session)


