"""Controller para contas bancárias."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from modules.financial.repositories import BankAccountRepository

logger = logging.getLogger(__name__)


def _user_email(current_user) -> str | None:
    """Extrai o e-mail do usuario seja ele dict ou objeto User (evita AttributeError)."""
    if isinstance(current_user, dict):
        return current_user.get("email")
    return getattr(current_user, "email", None)


router = APIRouter(prefix="/bank-accounts", tags=["Contas Bancárias"])


def get_repository(session: AsyncSession = Depends(get_session)) -> BankAccountRepository:
    """Retorna instância do BankAccountRepository."""
    return BankAccountRepository(session)


# ==================== CRUD ====================


# ==================== OPERAÇÕES ====================


