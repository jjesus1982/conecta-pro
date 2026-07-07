"""Controller para contas bancárias."""

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.models import (
    BankAccount,
    BankAccountStatus,
    BankAccountType,
    TransactionCategory,
    TransactionType,
)
from modules.financial.repositories import BankAccountRepository, BankTransactionRepository
from modules.financial.schemas import (
    BankAccountCreate,
    BankAccountFilter,
    BankAccountResponse,
    BankAccountStats,
    BankAccountUpdate,
    TransferRequest,
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


@router.post(
    "",
    response_model=BankAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar conta bancária",
)
@router.post(
    "/",
    response_model=BankAccountResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_bank_account(
    data: BankAccountCreate,
    repo: BankAccountRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BankAccountResponse:
    """Cria nova conta bancária."""
    try:
        account = await repo.create(data.model_dump())
        logger.info(f"Conta bancária criada: {account.id} por {_user_email(current_user)}")
        return BankAccountResponse.model_validate(account)
    except Exception as e:
        logger.error(f"Erro ao criar conta bancária: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar conta bancária",
        )


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


@router.get(
    "/main",
    response_model=BankAccountResponse,
    summary="Obter conta principal",
)
async def get_main_account(  # pylint: disable=unused-argument
    condominio_id: UUID,
    repo: BankAccountRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BankAccountResponse:
    """Retorna conta bancária principal do condomínio."""
    account = await repo.get_main_account(condominio_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta principal não encontrada",
        )
    return BankAccountResponse.model_validate(account)


@router.get(
    "/stats",
    response_model=BankAccountStats,
    summary="Estatísticas das contas",
)
async def get_stats(  # pylint: disable=unused-argument
    condominio_id: UUID,
    repo: BankAccountRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BankAccountStats:
    """Retorna estatísticas das contas bancárias."""
    total_balance = await repo.get_total_balance(condominio_id)
    accounts = await repo.list_with_filters(
        BankAccountFilter(condominio_id=condominio_id),
        skip=0,
        limit=1000,
    )

    def _ev(v):
        # status/account_type podem vir como str (Enum nativo no banco) ou Enum
        return v.value if hasattr(v, "value") else v

    active_count = len([a for a in accounts if _ev(a.status) == _ev(BankAccountStatus.ATIVA)])
    by_type = {}
    for account in accounts:
        type_name = _ev(account.account_type)
        if type_name not in by_type:
            by_type[type_name] = {"count": 0, "balance": Decimal("0")}
        by_type[type_name]["count"] += 1
        by_type[type_name]["balance"] += account.current_balance or Decimal("0")

    return BankAccountStats(
        total_accounts=len(accounts),
        active_accounts=active_count,
        total_balance=total_balance,
        by_type=by_type,
    )


@router.get(
    "/{account_id}",
    response_model=BankAccountResponse,
    summary="Obter conta bancária",
)
async def get_bank_account(  # pylint: disable=unused-argument
    account_id: UUID,
    repo: BankAccountRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BankAccountResponse:
    """Retorna conta bancária pelo ID."""
    account = await repo.get_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )
    return BankAccountResponse.model_validate(account)


@router.put(
    "/{account_id}",
    response_model=BankAccountResponse,
    summary="Atualizar conta bancária",
)
async def update_bank_account(
    account_id: UUID,
    data: BankAccountUpdate,
    repo: BankAccountRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BankAccountResponse:
    """Atualiza conta bancária."""
    account = await repo.get_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )

    update_data = data.model_dump(exclude_unset=True)
    updated = await repo.update(account_id, update_data)
    logger.info(f"Conta bancária atualizada: {account_id} por {_user_email(current_user)}")
    return BankAccountResponse.model_validate(updated)


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir conta bancária",
)
async def delete_bank_account(
    account_id: UUID,
    repo: BankAccountRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Exclui conta bancária (soft delete)."""
    account = await repo.get_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )

    if account.current_balance != Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir conta com saldo diferente de zero",
        )

    await repo.delete(account_id)
    logger.info(f"Conta bancária excluída: {account_id} por {_user_email(current_user)}")


# ==================== OPERAÇÕES ====================


@router.post(
    "/{account_id}/activate", response_model=BankAccountResponse, summary="Ativar conta bancária", status_code=201
)
async def activate_account(
    account_id: UUID,
    repo: BankAccountRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BankAccountResponse:
    """Ativa conta bancária."""
    account = await repo.get_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )

    updated = await repo.update(account_id, {"status": BankAccountStatus.ATIVA})
    logger.info(f"Conta bancária ativada: {account_id} por {_user_email(current_user)}")
    return BankAccountResponse.model_validate(updated)


@router.post(
    "/{account_id}/suspend", response_model=BankAccountResponse, summary="Suspender conta bancária", status_code=201
)
async def suspend_account(
    account_id: UUID,
    repo: BankAccountRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BankAccountResponse:
    """Suspende conta bancária."""
    account = await repo.get_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )

    updated = await repo.update(account_id, {"status": BankAccountStatus.SUSPENSA})
    logger.info(f"Conta bancária suspensa: {account_id} por {_user_email(current_user)}")
    return BankAccountResponse.model_validate(updated)


@router.post(
    "/{account_id}/set-main",
    response_model=BankAccountResponse,
    summary="Definir como conta principal",
    status_code=201,
)
async def set_as_main_account(
    account_id: UUID,
    repo: BankAccountRepository = Depends(get_repository),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> BankAccountResponse:
    """Define conta como principal do condomínio."""
    account = await repo.get_by_id(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )

    # Remove flag de outras contas
    await session.execute(
        sql_update(BankAccount)
        .where(BankAccount.condominio_id == account.condominio_id)
        .where(BankAccount.id != account_id)
        .values(is_main=False)
    )

    # Define esta como principal
    updated = await repo.update(account_id, {"is_main": True})
    await session.commit()

    logger.info(f"Conta principal definida: {account_id} por {_user_email(current_user)}")
    return BankAccountResponse.model_validate(updated)


@router.post(
    "/transfer",
    status_code=status.HTTP_200_OK,
    summary="Transferir entre contas",
)
async def transfer_between_accounts(
    data: TransferRequest,
    repo: BankAccountRepository = Depends(get_repository),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Realiza transferência entre contas bancárias."""
    from_account = await repo.get_by_id(data.from_account_id)
    to_account = await repo.get_by_id(data.to_account_id)

    if not from_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta de origem não encontrada",
        )

    if not to_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta de destino não encontrada",
        )

    if from_account.current_balance < data.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Saldo insuficiente na conta de origem",
        )

    # Cria transações
    tx_repo = BankTransactionRepository(session)

    # Débito na conta de origem
    await tx_repo.create(
        {
            "bank_account_id": data.from_account_id,
            "transaction_type": TransactionType.DEBITO,
            "category": TransactionCategory.TRANSFERENCIA,
            "amount": data.amount,
            "description": data.description or f"Transferência para conta {to_account.account_number}",
            "is_transfer": True,
            "transfer_to_account_id": data.to_account_id,
        }
    )

    # Crédito na conta de destino
    await tx_repo.create(
        {
            "bank_account_id": data.to_account_id,
            "transaction_type": TransactionType.CREDITO,
            "category": TransactionCategory.TRANSFERENCIA,
            "amount": data.amount,
            "description": data.description or f"Transferência de conta {from_account.account_number}",
            "is_transfer": True,
            "transfer_from_account_id": data.from_account_id,
        }
    )

    # Atualiza saldos
    from_account.update_balance(-data.amount)
    to_account.update_balance(data.amount)

    await session.commit()

    logger.info(
        f"Transferência realizada: {data.amount} de {data.from_account_id} "
        f"para {data.to_account_id} por {_user_email(current_user)}"
    )

    return {
        "success": True,
        "message": "Transferência realizada com sucesso",
        "from_balance": from_account.current_balance,
        "to_balance": to_account.current_balance,
    }


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
