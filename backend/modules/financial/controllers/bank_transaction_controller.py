"""Controller para transações bancárias."""

import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.models import (
    ReconciliationStatus,
    TransactionCategory,
    TransactionStatus,
    TransactionType,
)
from modules.financial.publishers import publish_nota_emitida
from modules.financial.repositories import BankAccountRepository, BankTransactionRepository
from modules.financial.schemas import (
    BankTransactionCreate,
    BankTransactionFilter,
    BankTransactionImport,
    BankTransactionResponse,
    BankTransactionUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bank-transactions", tags=["Transações Bancárias"])


def get_repository(session: AsyncSession = Depends(get_session)) -> BankTransactionRepository:
    """Retorna instância do BankTransactionRepository."""
    return BankTransactionRepository(session)


def get_account_repository(session: AsyncSession = Depends(get_session)) -> BankAccountRepository:
    """Retorna instância do BankAccountRepository."""
    return BankAccountRepository(session)


# ==================== CRUD ====================


@router.post(
    "",
    response_model=BankTransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar transação",
)
async def create_transaction(
    data: BankTransactionCreate,
    repo: BankTransactionRepository = Depends(get_repository),
    account_repo: BankAccountRepository = Depends(get_account_repository),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> BankTransactionResponse:
    """Cria nova transação bancária."""
    # Verifica se conta existe
    account = await account_repo.get_by_id(data.bank_account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )

    try:
        transaction = await repo.create(data.model_dump())

        # Atualiza saldo da conta se transação efetivada
        if transaction.status == TransactionStatus.EFETIVADA:
            if transaction.transaction_type == TransactionType.CREDITO:
                account.update_balance(transaction.amount)
            else:
                account.update_balance(-transaction.amount)
            await session.commit()

        logger.info(f"Transação criada: {transaction.id} por {current_user.get('email')}")
        return BankTransactionResponse.model_validate(transaction)
    except Exception as e:
        logger.error(f"Erro ao criar transação: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar transação",
        )


@router.get(
    "",
    response_model=list[BankTransactionResponse],
    summary="Listar transações",
)
async def list_transactions(
    bank_account_id: UUID | None = Query(None),
    transaction_type: TransactionType | None = Query(None),
    category: TransactionCategory | None = Query(None),
    transaction_status: TransactionStatus | None = Query(None),
    reconciliation_status: ReconciliationStatus | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    min_amount: Decimal | None = Query(None),
    max_amount: Decimal | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    repo: BankTransactionRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[BankTransactionResponse]:
    """Lista transações bancárias com filtros."""
    filters = BankTransactionFilter(
        bank_account_id=bank_account_id,
        transaction_type=transaction_type,
        category=category,
        status=transaction_status,
        reconciliation_status=reconciliation_status,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
    )
    page = (skip // limit) + 1 if limit > 0 else 1
    result = await repo.list_with_filters(filters.model_dump(exclude_none=True), page=page, per_page=limit)
    return [BankTransactionResponse.model_validate(t) for t in result["items"]]


@router.get(
    "/pending-reconciliation",
    response_model=list[BankTransactionResponse],
    summary="Transações pendentes de conciliação",
)
async def get_pending_reconciliation(
    bank_account_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    repo: BankTransactionRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[BankTransactionResponse]:
    """Retorna transações pendentes de conciliação bancária."""
    # Default to last 30 days for pending reconciliation
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    transactions = await repo.get_pending_reconciliation(bank_account_id, start_date, end_date)
    return [BankTransactionResponse.model_validate(t) for t in transactions[:limit]]


@router.get(
    "/by-period",
    response_model=list[BankTransactionResponse],
    summary="Transações por período",
)
async def get_by_period(
    bank_account_id: UUID,
    start_date: date = Query(..., description="Data inicial"),
    end_date: date = Query(..., description="Data final"),
    repo: BankTransactionRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> list[BankTransactionResponse]:
    """Retorna transações em um período específico."""
    transactions = await repo.get_by_period(bank_account_id, start_date, end_date)
    return [BankTransactionResponse.model_validate(t) for t in transactions]


@router.get(
    "/summary",
    summary="Resumo de transações por período",
)
async def get_summary(
    bank_account_id: UUID | None = Query(None),
    period: str | None = Query("30d", description="7d|30d|90d|all"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """
    Totais de entradas, saídas e saldo por período.
    Usado pela Conciliação Bancária para exibir os cards de resumo.
    bank_account_id é opcional — sem ele retorna totais de todas as contas.
    """
    hoje = date.today()
    if start_date and end_date:
        dt_from = start_date
        dt_to = end_date
    elif period == "7d":
        dt_from = hoje - timedelta(days=7)
        dt_to = hoje
    elif period == "90d":
        dt_from = hoje - timedelta(days=90)
        dt_to = hoje
    elif period == "all":
        dt_from = date(2025, 1, 1)
        dt_to = hoje
    else:  # 30d default
        dt_from = hoje - timedelta(days=30)
        dt_to = hoje

    where_account = "AND bank_account_id = :account_id" if bank_account_id else ""
    result = await session.execute(
        text(
            f"SELECT "  # noqa: S608
            "  COUNT(*) as total_transacoes, "
            "  ROUND(COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0)::numeric, 2) as total_entradas, "
            "  ROUND(COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0)::numeric, 2) as total_saidas, "
            "  ROUND(COALESCE(SUM(amount), 0)::numeric, 2) as saldo_periodo, "
            "  MIN(transaction_date) as data_inicio, "
            "  MAX(transaction_date) as data_fim "
            f"FROM bank_transactions "
            f"WHERE transaction_date BETWEEN :dt_from AND :dt_to {where_account}"
        ),
        {"dt_from": dt_from, "dt_to": dt_to, "account_id": str(bank_account_id) if bank_account_id else None},
    )
    row = result.fetchone()

    return {
        "periodo": {"de": dt_from.isoformat(), "ate": dt_to.isoformat(), "filtro": period},
        "total_transacoes": int(row.total_transacoes or 0),
        "total_entradas": float(row.total_entradas or 0),
        "total_saidas": float(row.total_saidas or 0),
        "saldo_periodo": float(row.saldo_periodo or 0),
        "data_inicio": row.data_inicio.isoformat() if row.data_inicio else None,
        "data_fim": row.data_fim.isoformat() if row.data_fim else None,
    }


@router.get(
    "/{transaction_id}",
    response_model=BankTransactionResponse,
    summary="Obter transação",
)
async def get_transaction(
    transaction_id: UUID,
    repo: BankTransactionRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> BankTransactionResponse:
    """Retorna transação pelo ID."""
    transaction = await repo.get_by_id(transaction_id)
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transação não encontrada",
        )
    return BankTransactionResponse.model_validate(transaction)


@router.put(
    "/{transaction_id}",
    response_model=BankTransactionResponse,
    summary="Atualizar transação",
)
async def update_transaction(
    transaction_id: UUID,
    data: BankTransactionUpdate,
    repo: BankTransactionRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BankTransactionResponse:
    """Atualiza transação bancária."""
    transaction = await repo.get_by_id(transaction_id)
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transação não encontrada",
        )

    if transaction.reconciliation_status == ReconciliationStatus.CONCILIADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível alterar transação já conciliada",
        )

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(transaction, key, value)
    updated = await repo.update(transaction)
    logger.info(f"Transação atualizada: {transaction_id} por {current_user.get('email')}")
    return BankTransactionResponse.model_validate(updated)


@router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir transação",
)
async def delete_transaction(
    transaction_id: UUID,
    repo: BankTransactionRepository = Depends(get_repository),
    account_repo: BankAccountRepository = Depends(get_account_repository),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Exclui transação bancária."""
    transaction = await repo.get_by_id(transaction_id)
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transação não encontrada",
        )

    if transaction.reconciliation_status == ReconciliationStatus.CONCILIADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível excluir transação já conciliada",
        )

    # Reverte saldo se transação estava efetivada
    if transaction.status == TransactionStatus.EFETIVADA:
        account = await account_repo.get_by_id(transaction.bank_account_id)
        if account:
            if transaction.transaction_type == TransactionType.CREDITO:
                account.update_balance(-transaction.amount)
            else:
                account.update_balance(transaction.amount)

    await repo.delete(transaction_id)
    await session.commit()
    logger.info(f"Transação excluída: {transaction_id} por {current_user.get('email')}")


# ==================== OPERAÇÕES ====================


@router.post(
    "/{transaction_id}/confirm", response_model=BankTransactionResponse, summary="Confirmar transação", status_code=201
)
async def confirm_transaction(
    transaction_id: UUID,
    repo: BankTransactionRepository = Depends(get_repository),
    account_repo: BankAccountRepository = Depends(get_account_repository),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> BankTransactionResponse:
    """Confirma transação pendente."""
    transaction = await repo.get_by_id(transaction_id)
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transação não encontrada",
        )

    if transaction.status != TransactionStatus.PENDENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas transações pendentes podem ser confirmadas",
        )

    # Atualiza status
    transaction.status = TransactionStatus.EFETIVADA
    updated = await repo.update(transaction)

    # Atualiza saldo
    account = await account_repo.get_by_id(transaction.bank_account_id)
    if account:
        if transaction.transaction_type == TransactionType.CREDITO:
            account.update_balance(transaction.amount)
        else:
            account.update_balance(-transaction.amount)

    await session.commit()
    logger.info(f"Transação confirmada: {transaction_id} por {current_user.get('email')}")
    # Publisher GEDEON Event Bus — nota emitida (crédito confirmado)
    if transaction.transaction_type == TransactionType.CREDITO:
        try:
            import asyncio

            asyncio.create_task(
                publish_nota_emitida(
                    nota_id=str(transaction_id),
                    numero=str(getattr(transaction, "document_number", "") or str(transaction_id)[:8]),
                    valor=float(transaction.amount or 0),
                    cliente_id=str(getattr(transaction, "client_id", "") or ""),
                    extra={
                        "tipo": "transacao_bancaria",
                        "descricao": str(getattr(transaction, "description", "") or ""),
                        "conta_id": str(getattr(transaction, "bank_account_id", "") or ""),
                    },
                )
            )
        except Exception:
            pass
    return BankTransactionResponse.model_validate(updated)


@router.post(
    "/{transaction_id}/cancel", response_model=BankTransactionResponse, summary="Cancelar transação", status_code=201
)
async def cancel_transaction(
    transaction_id: UUID,
    reason: str = Query(..., min_length=5, max_length=500),
    repo: BankTransactionRepository = Depends(get_repository),
    account_repo: BankAccountRepository = Depends(get_account_repository),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> BankTransactionResponse:
    """Cancela transação."""
    transaction = await repo.get_by_id(transaction_id)
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transação não encontrada",
        )

    if transaction.reconciliation_status == ReconciliationStatus.CONCILIADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível cancelar transação conciliada",
        )

    # Reverte saldo se estava efetivada
    if transaction.status == TransactionStatus.EFETIVADA:
        account = await account_repo.get_by_id(transaction.bank_account_id)
        if account:
            if transaction.transaction_type == TransactionType.CREDITO:
                account.update_balance(-transaction.amount)
            else:
                account.update_balance(transaction.amount)

    # Atualiza status
    # Atualiza status
    transaction.status = TransactionStatus.CANCELADA
    transaction.notes = f"{transaction.notes or ''}\nCancelamento: {reason}".strip()
    updated = await repo.update(transaction)

    await session.commit()
    logger.info(f"Transação cancelada: {transaction_id} por {current_user.get('email')}, motivo: {reason}")
    return BankTransactionResponse.model_validate(updated)


@router.post(
    "/{transaction_id}/reconcile",
    response_model=BankTransactionResponse,
    summary="Conciliar transação",
    status_code=201,
)
async def reconcile_transaction(
    transaction_id: UUID,
    statement_reference: str | None = Query(None, max_length=100),
    repo: BankTransactionRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> BankTransactionResponse:
    """Marca transação como conciliada com extrato bancário."""
    transaction = await repo.get_by_id(transaction_id)
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transação não encontrada",
        )

    if transaction.status != TransactionStatus.EFETIVADA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas transações efetivadas podem ser conciliadas",
        )

    transaction.reconciliation_status = ReconciliationStatus.CONCILIADO
    transaction.reconciled_at = date.today()
    if statement_reference:
        transaction.statement_reference = statement_reference

    updated = await repo.update(transaction)
    logger.info(f"Transação conciliada: {transaction_id} por {current_user.get('email')}")
    return BankTransactionResponse.model_validate(updated)


# ==================== IMPORTAÇÃO ====================


@router.post("/import", summary="Importar transações de arquivo", status_code=201)
async def import_transactions(
    data: BankTransactionImport,
    repo: BankTransactionRepository = Depends(get_repository),
    account_repo: BankAccountRepository = Depends(get_account_repository),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Importa transações de extrato (OFX, CSV)."""
    # Verifica se conta existe
    account = await account_repo.get_by_id(data.bank_account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )

    created = 0
    duplicates = 0
    errors = []

    for i, tx_data in enumerate(data.transactions):
        try:
            # Verifica duplicidade por referência
            if tx_data.reference:
                existing = await repo.list_with_filters(
                    BankTransactionFilter(
                        bank_account_id=data.bank_account_id,
                    ),
                    skip=0,
                    limit=1,
                )
                if existing and any(t.statement_reference == tx_data.reference for t in existing):
                    duplicates += 1
                    continue

            # Cria transação
            await repo.create(
                {
                    "bank_account_id": data.bank_account_id,
                    "transaction_type": tx_data.transaction_type,
                    "category": tx_data.category or TransactionCategory.OUTROS,
                    "amount": tx_data.amount,
                    "description": tx_data.description,
                    "transaction_date": tx_data.transaction_date,
                    "statement_reference": tx_data.reference,
                    "status": TransactionStatus.EFETIVADA,
                    "reconciliation_status": ReconciliationStatus.PENDENTE,
                }
            )
            created += 1
        except (ValueError, TypeError, RuntimeError) as e:
            errors.append({"index": i, "error": str(e)})

    await session.commit()

    logger.info(
        f"Importação de transações: {created} criadas, {duplicates} duplicadas, "
        f"{len(errors)} erros, por {current_user.get('email')}"
    )

    return {
        "success": True,
        "created": created,
        "duplicates": duplicates,
        "errors": errors[:10],  # Limita erros retornados
        "total_processed": len(data.transactions),
    }


@router.post("/import/ofx", summary="Importar arquivo OFX", status_code=201)
async def import_ofx_file(
    bank_account_id: UUID = Query(...),
    file: UploadFile = File(..., description="Arquivo OFX"),
    repo: BankTransactionRepository = Depends(get_repository),
    account_repo: BankAccountRepository = Depends(get_account_repository),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Importa transações de arquivo OFX."""
    if not file.filename.lower().endswith(".ofx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo deve ser do tipo OFX",
        )

    # Verifica se conta existe
    account = await account_repo.get_by_id(bank_account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conta bancária não encontrada",
        )

    try:
        content = await file.read()
        # Parse OFX (simplificado - em produção usar biblioteca ofxparse)
        transactions = _parse_ofx(content.decode("latin-1"))

        created = 0
        for tx in transactions:
            await repo.create(
                {
                    "bank_account_id": bank_account_id,
                    "transaction_type": tx["type"],
                    "category": TransactionCategory.OUTROS,
                    "amount": tx["amount"],
                    "description": tx["description"],
                    "transaction_date": tx["date"],
                    "statement_reference": tx["fitid"],
                    "status": TransactionStatus.EFETIVADA,
                    "reconciliation_status": ReconciliationStatus.PENDENTE,
                }
            )
            created += 1

        await session.commit()

        logger.info(f"Arquivo OFX importado: {created} transações, por {current_user.get('email')}")

        return {
            "success": True,
            "created": created,
            "filename": file.filename,
        }

    except Exception as e:
        logger.error(f"Erro ao importar OFX: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao processar arquivo OFX: {str(e)}",
        )


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
