"""Controller para clientes/devedores do contas a receber."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from modules.financial.repositories.receivable_repository import CustomerRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customers", tags=["Clientes (Contas a Receber)"])


def get_repository(
    session: AsyncSession = Depends(get_session),
) -> CustomerRepository:
    """Retorna instancia do repository."""
    return CustomerRepository(session)


