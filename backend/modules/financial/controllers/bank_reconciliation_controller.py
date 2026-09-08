"""Controller para conciliação bancária."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from modules.financial.repositories import (
    BankAccountRepository,
    BankReconciliationRepository,
    BankTransactionRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bank-reconciliations", tags=["Conciliação Bancária"])


def get_repository(session: AsyncSession = Depends(get_session)) -> BankReconciliationRepository:
    """Retorna instância do BankReconciliationRepository."""
    return BankReconciliationRepository(session)


def get_account_repository(session: AsyncSession = Depends(get_session)) -> BankAccountRepository:
    """Retorna instância do BankAccountRepository."""
    return BankAccountRepository(session)


def get_transaction_repository(
    session: AsyncSession = Depends(get_session),
) -> BankTransactionRepository:
    """Retorna instância do BankTransactionRepository."""
    return BankTransactionRepository(session)


# ==================== CRUD ====================


# ==================== OPERAÇÕES ====================


# ==================== RELATÓRIOS ====================


