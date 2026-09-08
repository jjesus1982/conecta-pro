"""Controller para contas bancárias."""

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.models import (
    BankAccountStatus,
    BankAccountType,
    TransactionCategory,
    TransactionType,
)
from modules.financial.repositories import BankAccountRepository, BankTransactionRepository
from modules.financial.schemas import (
    BankAccountFilter,
    BankAccountResponse,
)

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


@router.get(
    "",
    response_model=list[BankAccountResponse],
    summary="Listar contas bancárias",
)
@router.get(
    "/",
    response_model=list[BankAccountResponse],
    include_in_schema=False,
)
async def list_bank_accounts(  # pylint: disable=unused-argument
    condominio_id: UUID | None = Query(None),
    account_type: BankAccountType | None = Query(None, description="Tipo de conta"),
    account_status: BankAccountStatus | None = Query(None, description="Status"),
    is_main: bool | None = Query(None, description="Conta principal"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    repo: BankAccountRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> list[BankAccountResponse]:
    """Lista contas bancárias com filtros."""
    filters = BankAccountFilter(
        condominio_id=condominio_id,
        account_type=account_type,
        status=account_status,
        is_main=is_main,
    )
    accounts = await repo.list_with_filters(filters, skip=skip, limit=limit)
    return [BankAccountResponse.model_validate(a) for a in accounts]


# ==================== OPERAÇÕES ====================


@router.post(
    "/{account_id}/adjust-balance", response_model=BankAccountResponse, summary="Ajustar saldo", status_code=201
)
async def adjust_balance(
    account_id: UUID,
    new_balance: Decimal = Query(..., description="Novo saldo"),
    reason: str = Query(..., min_length=5, max_length=500, description="Motivo do ajuste"),
    repo: BankAccountRepository = Depends(get_repository),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> BankAccountResponse:
    """Ajusta saldo da conta bancária (uso administrativo)."""
    account = await repo.get_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )

    difference = new_balance - account.current_balance

    # Cria transação de ajuste
    tx_repo = BankTransactionRepository(session)
    await tx_repo.create(
        {
            "bank_account_id": account_id,
            "transaction_type": (TransactionType.CREDITO if difference > 0 else TransactionType.DEBITO),
            "category": TransactionCategory.AJUSTE,
            "amount": abs(difference),
            "description": f"Ajuste de saldo: {reason}",
            "notes": f"Saldo anterior: {account.current_balance}, Novo saldo: {new_balance}",
        }
    )

    # Atualiza saldo
    account.current_balance = new_balance
    await session.commit()

    logger.info(
        f"Saldo ajustado: conta {account_id}, diferença {difference}, por {_user_email(current_user)}, motivo: {reason}"
    )

    return BankAccountResponse.model_validate(account)
