"""Controller para transações bancárias."""

import logging
import re
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from modules.financial.models import (
    TransactionType,
)
from modules.financial.repositories import BankAccountRepository, BankTransactionRepository

logger = logging.getLogger(__name__)


def _user_email(current_user) -> str | None:
    """Extrai o e-mail do usuario seja ele dict ou objeto User (evita AttributeError)."""
    if isinstance(current_user, dict):
        return current_user.get("email")
    return getattr(current_user, "email", None)


router = APIRouter(prefix="/bank-transactions", tags=["Transações Bancárias"])


def get_repository(session: AsyncSession = Depends(get_session)) -> BankTransactionRepository:
    """Retorna instância do BankTransactionRepository."""
    return BankTransactionRepository(session)


def get_account_repository(session: AsyncSession = Depends(get_session)) -> BankAccountRepository:
    """Retorna instância do BankAccountRepository."""
    return BankAccountRepository(session)


# ==================== CRUD ====================


# ==================== OPERAÇÕES ====================


# ==================== IMPORTAÇÃO ====================


def _parse_ofx(content: str) -> list[dict]:
    """Parse simplificado de arquivo OFX."""
    transactions = []

    # Busca transações
    stmttrn_pattern = r"<STMTTRN>(.*?)</STMTTRN>"
    matches = re.findall(stmttrn_pattern, content, re.DOTALL)

    for match in matches:
        tx = {}

        # Tipo
        trntype = re.search(r"<TRNTYPE>(.*?)[\n<]", match)
        if trntype:
            tx["type"] = (
                TransactionType.CREDITO if trntype.group(1).strip() in ["CREDIT", "DEP"] else TransactionType.DEBITO
            )

        # Data
        dtposted = re.search(r"<DTPOSTED>(\d{8})", match)
        if dtposted:
            tx["date"] = datetime.strptime(dtposted.group(1), "%Y%m%d").date()

        # Valor
        trnamt = re.search(r"<TRNAMT>([-\d.]+)", match)
        if trnamt:
            tx["amount"] = abs(Decimal(trnamt.group(1)))

        # FITID
        fitid = re.search(r"<FITID>(.*?)[\n<]", match)
        if fitid:
            tx["fitid"] = fitid.group(1).strip()

        # Descrição
        memo = re.search(r"<MEMO>(.*?)[\n<]", match)
        name = re.search(r"<NAME>(.*?)[\n<]", match)
        tx["description"] = (memo or name or type("", (), {"group": lambda s, x: "Transação OFX"})()).group(1).strip()

        if all(k in tx for k in ["type", "date", "amount", "fitid"]):
            transactions.append(tx)

    return transactions
