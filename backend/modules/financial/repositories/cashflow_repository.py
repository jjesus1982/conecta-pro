"""Repository para Fluxo de Caixa."""

import builtins
import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import String, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.financial.models.bank_account import BankAccount, BankAccountStatus
from modules.financial.models.bank_reconciliation import BankReconciliation, ReconciliationStatus
from modules.financial.models.bank_transaction import BankTransaction, TransactionStatus
from modules.financial.models.bank_transaction import (
    ReconciliationStatus as TransactionReconciliationStatus,
)
from modules.financial.models.cashflow_entry import (
    CashFlowEntry,
    CashFlowEntryStatus,
)
from modules.financial.models.cashflow_forecast import CashFlowForecast, ForecastStatus
from modules.financial.schemas.cashflow import (
    BankAccountFilter,
    BankTransactionFilter,
    CashFlowEntryFilter,
    CashFlowForecastFilter,
)

logger = logging.getLogger(__name__)


class BankAccountRepository:
    """Repository para contas bancarias."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, account: BankAccount) -> BankAccount:
        """Cria conta bancaria."""
        if isinstance(account, dict):
            account = BankAccount(**account)
        self.session.add(account)
        await self.session.flush()
        await self.session.refresh(account)
        return account

    async def get_by_id(
        self,
        account_id: UUID,
        with_relations: bool = False,
    ) -> BankAccount | None:
        """Busca conta por ID."""
        query = select(BankAccount).where(
            and_(
                BankAccount.id == account_id,
                BankAccount.ativo.is_(True),  # noqa: E712
            )
        )

        if with_relations:
            query = query.options(selectinload(BankAccount.transactions))

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID | None = None,
        filters: BankAccountFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BankAccount]:
        """Lista contas bancarias."""
        base_conditions = [BankAccount.ativo.is_(True)]  # noqa: E712
        if condominio_id is not None:
            base_conditions.append(BankAccount.condominio_id == condominio_id)
        query = select(BankAccount).where(and_(*base_conditions))

        if filters:
            if filters.status:
                query = query.where(BankAccount.status == filters.status)
            if filters.account_type:
                query = query.where(BankAccount.account_type == filters.account_type)
            if filters.bank_code:
                query = query.where(BankAccount.bank_code == filters.bank_code)
            is_main_val = filters.is_main_account if filters.is_main_account is not None else filters.is_main
            if is_main_val is not None:
                query = query.where(BankAccount.is_main_account == is_main_val)
            if filters.pix_enabled is not None:
                query = query.where(BankAccount.pix_enabled == filters.pix_enabled)
            if filters.boleto_enabled is not None:
                query = query.where(BankAccount.boleto_enabled == filters.boleto_enabled)

        query = query.order_by(BankAccount.is_main_account.desc(), BankAccount.name)
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        condominio_id: UUID,
        filters: BankAccountFilter | None = None,
    ) -> int:
        """Conta registros."""
        query = select(func.count(BankAccount.id)).where(
            and_(
                BankAccount.condominio_id == condominio_id,
                BankAccount.ativo.is_(True),  # noqa: E712
            )
        )

        if filters:
            if filters.status:
                query = query.where(BankAccount.status == filters.status)
            if filters.account_type:
                query = query.where(BankAccount.account_type == filters.account_type)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(self, account: BankAccount) -> BankAccount:
        """Atualiza conta."""
        await self.session.flush()
        await self.session.refresh(account)
        return account

    async def list_with_filters(
        self,
        filters: BankAccountFilter,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[BankAccount]:
        """Lista contas usando objeto de filtro (inclui condominio_id)."""
        return await self.list(
            condominio_id=filters.condominio_id,
            filters=filters,
            skip=skip,
            limit=limit,
        )

    async def delete(self, account_id: UUID) -> bool:
        """Deleta conta (soft delete)."""
        account = await self.get_by_id(account_id)
        if account:
            account.ativo = False
            account.status = BankAccountStatus.ENCERRADA.value
            await self.session.flush()
            return True
        return False

    async def get_main_account(self, condominio_id: UUID) -> BankAccount | None:
        """Busca conta principal do condominio."""
        query = select(BankAccount).where(
            and_(
                BankAccount.condominio_id == condominio_id,
                BankAccount.is_main_account.is_(True),  # noqa: E712
                BankAccount.ativo.is_(True),  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_total_balance(self, condominio_id: UUID) -> Decimal:
        """Retorna saldo total de todas as contas."""
        query = select(func.sum(BankAccount.current_balance)).where(
            and_(
                BankAccount.condominio_id == condominio_id,
                BankAccount.status == BankAccountStatus.ATIVA.value,
                BankAccount.ativo.is_(True),  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one() or Decimal("0")


class BankTransactionRepository:
    """Repository para movimentacoes bancarias."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, transaction: BankTransaction) -> BankTransaction:
        """Cria movimentacao."""
        if isinstance(transaction, dict):
            transaction = BankTransaction(**transaction)
        self.session.add(transaction)
        await self.session.flush()
        await self.session.refresh(transaction)
        return transaction

    async def get_by_id(self, transaction_id: UUID) -> BankTransaction | None:
        """Busca movimentacao por ID."""
        query = select(BankTransaction).where(
            and_(
                BankTransaction.id == transaction_id,
                BankTransaction.ativo.is_(True),  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        bank_account_id: UUID,
        filters: BankTransactionFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BankTransaction]:
        """Lista movimentacoes."""
        query = select(BankTransaction).where(
            and_(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.ativo.is_(True),  # noqa: E712
            )
        )

        if filters:
            if filters.transaction_type:
                query = query.where(BankTransaction.transaction_type == filters.transaction_type)
            if filters.category:
                query = query.where(BankTransaction.category == filters.category)
            if filters.status:
                query = query.where(BankTransaction.status == filters.status)
            if filters.reconciliation_status:
                query = query.where(BankTransaction.reconciliation_status == filters.reconciliation_status)
            if filters.origin:
                query = query.where(BankTransaction.origin == filters.origin)
            if filters.start_date:
                query = query.where(BankTransaction.transaction_date >= filters.start_date)
            if filters.end_date:
                query = query.where(BankTransaction.transaction_date <= filters.end_date)
            if filters.min_amount:
                query = query.where(BankTransaction.amount >= filters.min_amount)
            if filters.max_amount:
                query = query.where(BankTransaction.amount <= filters.max_amount)
            if filters.counterparty_name:
                query = query.where(BankTransaction.counterparty_name.ilike(f"%{filters.counterparty_name}%"))

        query = query.order_by(BankTransaction.transaction_date.desc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        bank_account_id: UUID,
        filters: BankTransactionFilter | None = None,
    ) -> int:
        """Conta movimentacoes."""
        query = select(func.count(BankTransaction.id)).where(
            and_(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.ativo.is_(True),  # noqa: E712
            )
        )

        if filters and filters.start_date:
            query = query.where(BankTransaction.transaction_date >= filters.start_date)
        if filters and filters.end_date:
            query = query.where(BankTransaction.transaction_date <= filters.end_date)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(self, transaction: BankTransaction) -> BankTransaction:
        """Atualiza movimentacao."""
        await self.session.flush()
        await self.session.refresh(transaction)
        return transaction

    async def delete(self, transaction_id: UUID) -> bool:
        """Deleta transacao (soft delete)."""
        transaction = await self.get_by_id(transaction_id)
        if transaction:
            transaction.ativo = False
            transaction.status = TransactionStatus.CANCELADA.value
            await self.session.flush()
            return True
        return False

    async def get_pending_reconciliation(
        self,
        bank_account_id: UUID,
        start_date: date,
        end_date: date,
    ) -> builtins.list[BankTransaction]:
        """Busca movimentacoes pendentes de conciliacao."""
        query = select(BankTransaction).where(
            and_(
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.reconciliation_status == TransactionReconciliationStatus.PENDENTE.value,
                BankTransaction.transaction_date >= start_date,
                BankTransaction.transaction_date <= end_date,
                BankTransaction.ativo.is_(True),  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_period(
        self,
        bank_account_id: UUID,
        start_date: date,
        end_date: date,
    ) -> builtins.list[BankTransaction]:
        """Busca movimentacoes por periodo."""
        query = (
            select(BankTransaction)
            .where(
                and_(
                    BankTransaction.bank_account_id == bank_account_id,
                    BankTransaction.transaction_date >= start_date,
                    BankTransaction.transaction_date <= end_date,
                    BankTransaction.status == TransactionStatus.CONFIRMADA.value,
                    BankTransaction.ativo.is_(True),  # noqa: E712
                )
            )
            .order_by(BankTransaction.transaction_date)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_with_filters(
        self,
        filters: dict | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """Lista transacoes com filtros dinamicos e paginacao."""
        filters = filters or {}
        query = select(BankTransaction).where(BankTransaction.ativo.is_(True))  # noqa: E712

        # Filtros dinamicos baseados nos campos reais do model
        if filters.get("bank_account_id"):
            query = query.where(BankTransaction.bank_account_id == filters["bank_account_id"])
        if filters.get("transaction_type"):
            query = query.where(BankTransaction.transaction_type == filters["transaction_type"])
        if filters.get("category"):
            query = query.where(BankTransaction.category == filters["category"])
        if filters.get("status"):
            query = query.where(BankTransaction.status == filters["status"])
        if filters.get("reconciliation_status"):
            query = query.where(BankTransaction.reconciliation_status == filters["reconciliation_status"])
        if filters.get("origin"):
            query = query.where(BankTransaction.origin == filters["origin"])
        if filters.get("source_type"):
            query = query.where(BankTransaction.source_type == filters["source_type"])
        if filters.get("start_date"):
            query = query.where(BankTransaction.transaction_date >= filters["start_date"])
        if filters.get("end_date"):
            query = query.where(BankTransaction.transaction_date <= filters["end_date"])
        if filters.get("min_amount"):
            query = query.where(BankTransaction.amount >= filters["min_amount"])
        if filters.get("max_amount"):
            query = query.where(BankTransaction.amount <= filters["max_amount"])
        if filters.get("counterparty_name"):
            query = query.where(BankTransaction.counterparty_name.ilike(f"%{filters['counterparty_name']}%"))
        if filters.get("is_transfer") is not None:
            query = query.where(BankTransaction.is_transfer == filters["is_transfer"])

        # Total (subquery para evitar re-execucao com ordenacao)
        count_q = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_q) or 0

        # Paginacao
        query = query.order_by(BankTransaction.transaction_date.desc())
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }


class BankReconciliationRepository:
    """Repository para conciliacoes bancarias."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, reconciliation: BankReconciliation) -> BankReconciliation:
        """Cria conciliacao."""
        self.session.add(reconciliation)
        await self.session.flush()
        await self.session.refresh(reconciliation)
        return reconciliation

    async def get_by_id(self, reconciliation_id: UUID) -> BankReconciliation | None:
        """Busca conciliacao por ID."""
        query = select(BankReconciliation).where(
            and_(
                BankReconciliation.id == reconciliation_id,
                BankReconciliation.ativo.is_(True),  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        bank_account_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BankReconciliation]:
        """Lista conciliacoes."""
        query = (
            select(BankReconciliation)
            .where(
                and_(
                    BankReconciliation.bank_account_id == bank_account_id,
                    BankReconciliation.ativo.is_(True),  # noqa: E712
                )
            )
            .order_by(BankReconciliation.period_end.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(self, reconciliation: BankReconciliation) -> BankReconciliation:
        """Atualiza conciliacao."""
        await self.session.flush()
        await self.session.refresh(reconciliation)
        return reconciliation

    async def get_in_progress(self, bank_account_id: UUID) -> BankReconciliation | None:
        """Busca conciliacao em andamento."""
        query = select(BankReconciliation).where(
            and_(
                BankReconciliation.bank_account_id == bank_account_id,
                BankReconciliation.status == ReconciliationStatus.EM_ANDAMENTO.value,
                BankReconciliation.ativo.is_(True),  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class CashFlowEntryRepository:
    """Repository para lancamentos de fluxo de caixa."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, entry: CashFlowEntry) -> CashFlowEntry:
        """Cria lancamento."""
        if isinstance(entry, dict):
            entry = CashFlowEntry(**entry)
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def get_by_id(self, entry_id: UUID) -> CashFlowEntry | None:
        """Busca lancamento por ID."""
        query = select(CashFlowEntry).where(
            and_(
                CashFlowEntry.id == entry_id,
                CashFlowEntry.ativo.is_(True),  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID,
        filters: CashFlowEntryFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CashFlowEntry]:
        """Lista lancamentos."""
        query = select(CashFlowEntry).where(
            and_(
                CashFlowEntry.condominio_id == condominio_id,
                CashFlowEntry.ativo.is_(True),  # noqa: E712
            )
        )

        if filters:
            if filters.entry_type:
                # colunas enum nativas: cast p/ texto evita "operator does not exist"
                query = query.where(cast(CashFlowEntry.entry_type, String) == str(filters.entry_type))
            if filters.source_type:
                query = query.where(cast(CashFlowEntry.source_type, String) == str(filters.source_type))
            if filters.status:
                query = query.where(cast(CashFlowEntry.status, String) == str(filters.status))
            if filters.bank_account_id:
                query = query.where(CashFlowEntry.bank_account_id == filters.bank_account_id)
            if filters.start_date:
                query = query.where(CashFlowEntry.entry_date >= filters.start_date)
            if filters.end_date:
                query = query.where(CashFlowEntry.entry_date <= filters.end_date)
            if filters.min_amount:
                query = query.where(CashFlowEntry.expected_amount >= filters.min_amount)
            if filters.max_amount:
                query = query.where(CashFlowEntry.expected_amount <= filters.max_amount)
            if filters.is_recurring is not None:
                query = query.where(CashFlowEntry.is_recurring == filters.is_recurring)
            if filters.is_overdue:
                today = date.today()
                query = query.where(
                    and_(
                        CashFlowEntry.due_date < today,
                        cast(CashFlowEntry.status, String).in_(
                            [
                                CashFlowEntryStatus.PREVISTO.value,
                                CashFlowEntryStatus.CONFIRMADO.value,
                            ]
                        ),
                    )
                )

        query = query.order_by(CashFlowEntry.entry_date.desc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        condominio_id: UUID,
        filters: CashFlowEntryFilter | None = None,
    ) -> int:
        """Conta lancamentos."""
        query = select(func.count(CashFlowEntry.id)).where(
            and_(
                CashFlowEntry.condominio_id == condominio_id,
                CashFlowEntry.ativo.is_(True),  # noqa: E712
            )
        )

        if filters:
            if filters.entry_type:
                query = query.where(CashFlowEntry.entry_type == filters.entry_type)
            if filters.status:
                query = query.where(CashFlowEntry.status == filters.status)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(self, entry: CashFlowEntry) -> CashFlowEntry:
        """Atualiza lancamento."""
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def list_with_filters(
        self,
        filters: CashFlowEntryFilter,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[CashFlowEntry]:
        """Lista lancamentos usando objeto de filtro (inclui condominio_id)."""
        return await self.list(
            condominio_id=filters.condominio_id,
            filters=filters,
            skip=skip,
            limit=limit,
        )

    async def delete(self, entry_id: UUID) -> bool:
        """Deleta lancamento (soft delete)."""
        entry = await self.get_by_id(entry_id)
        if entry:
            entry.ativo = False
            await self.session.flush()
            return True
        return False

    async def get_by_period(
        self,
        condominio_id: UUID,
        start_date: date,
        end_date: date,
        entry_type: str | None = None,
    ) -> builtins.list[CashFlowEntry]:
        """Busca lancamentos por periodo."""
        query = select(CashFlowEntry).where(
            and_(
                CashFlowEntry.condominio_id == condominio_id,
                CashFlowEntry.entry_date >= start_date,
                CashFlowEntry.entry_date <= end_date,
                CashFlowEntry.ativo.is_(True),  # noqa: E712
            )
        )

        if entry_type:
            query = query.where(CashFlowEntry.entry_type == entry_type)

        query = query.order_by(CashFlowEntry.entry_date)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_pending(
        self,
        condominio_id: UUID,
        entry_type: str | None = None,
    ) -> builtins.list[CashFlowEntry]:
        """Busca lancamentos pendentes."""
        query = select(CashFlowEntry).where(
            and_(
                CashFlowEntry.condominio_id == condominio_id,
                cast(CashFlowEntry.status, String).in_(
                    [
                        CashFlowEntryStatus.PREVISTO.value,
                        CashFlowEntryStatus.CONFIRMADO.value,
                    ]
                ),
                CashFlowEntry.ativo.is_(True),  # noqa: E712
            )
        )

        if entry_type:
            query = query.where(cast(CashFlowEntry.entry_type, String) == str(entry_type))

        query = query.order_by(CashFlowEntry.due_date)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_totals_by_type(
        self,
        condominio_id: UUID,
        start_date: date,
        end_date: date,
    ) -> dict[str, Decimal]:
        """Retorna totais por tipo de lancamento."""
        query = (
            select(
                CashFlowEntry.entry_type,
                func.sum(CashFlowEntry.expected_amount).label("total"),
            )
            .where(
                and_(
                    CashFlowEntry.condominio_id == condominio_id,
                    CashFlowEntry.entry_date >= start_date,
                    CashFlowEntry.entry_date <= end_date,
                    CashFlowEntry.ativo.is_(True),  # noqa: E712
                )
            )
            .group_by(CashFlowEntry.entry_type)
        )

        result = await self.session.execute(query)
        return {row.entry_type: row.total or Decimal("0") for row in result}


class CashFlowForecastRepository:
    """Repository para previsoes de fluxo de caixa."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, forecast: CashFlowForecast) -> CashFlowForecast:
        """Cria previsao."""
        if isinstance(forecast, dict):
            forecast = CashFlowForecast(**forecast)
        self.session.add(forecast)
        await self.session.flush()
        await self.session.refresh(forecast)
        return forecast

    async def get_by_id(self, forecast_id: UUID) -> CashFlowForecast | None:
        """Busca previsao por ID."""
        query = select(CashFlowForecast).where(
            and_(
                CashFlowForecast.id == forecast_id,
                CashFlowForecast.ativo.is_(True),  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID,
        filters: CashFlowForecastFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CashFlowForecast]:
        """Lista previsoes."""
        query = select(CashFlowForecast).where(
            and_(
                CashFlowForecast.condominio_id == condominio_id,
                CashFlowForecast.ativo.is_(True),  # noqa: E712
            )
        )

        if filters:
            if filters.status:
                query = query.where(cast(CashFlowForecast.status, String) == str(filters.status))
            if filters.period_type:
                query = query.where(cast(CashFlowForecast.period_type, String) == str(filters.period_type))
            if filters.start_date:
                query = query.where(CashFlowForecast.period_start >= filters.start_date)
            if filters.end_date:
                query = query.where(CashFlowForecast.period_end <= filters.end_date)
            if filters.ai_generated is not None:
                query = query.where(CashFlowForecast.is_ai_generated == filters.ai_generated)

        query = query.order_by(CashFlowForecast.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        condominio_id: UUID,
        filters: CashFlowForecastFilter | None = None,
    ) -> int:
        """Conta previsoes."""
        query = select(func.count(CashFlowForecast.id)).where(
            and_(
                CashFlowForecast.condominio_id == condominio_id,
                CashFlowForecast.ativo.is_(True),  # noqa: E712
            )
        )

        if filters and filters.status:
            query = query.where(cast(CashFlowForecast.status, String) == str(filters.status))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(self, forecast: CashFlowForecast) -> CashFlowForecast:
        """Atualiza previsao."""
        await self.session.flush()
        await self.session.refresh(forecast)
        return forecast

    async def list_with_filters(
        self,
        filters: CashFlowForecastFilter,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[CashFlowForecast]:
        """Lista previsoes usando objeto de filtro (inclui condominio_id)."""
        return await self.list(
            condominio_id=filters.condominio_id,
            filters=filters,
            skip=skip,
            limit=limit,
        )

    async def delete(self, forecast_id: UUID) -> bool:
        """Deleta previsao (soft delete)."""
        forecast = await self.get_by_id(forecast_id)
        if forecast:
            forecast.ativo = False
            await self.session.flush()
            return True
        return False

    async def get_active(self, condominio_id: UUID | None = None) -> builtins.list[CashFlowForecast]:
        """Lista previsoes ativas (status 'ativo') do condominio."""
        conditions = [
            cast(CashFlowForecast.status, String) == ForecastStatus.ATIVA.value,
            CashFlowForecast.ativo.is_(True),  # noqa: E712
        ]
        if condominio_id is not None:
            conditions.append(CashFlowForecast.condominio_id == condominio_id)
        query = (
            select(CashFlowForecast)
            .where(and_(*conditions))
            .order_by(CashFlowForecast.period_start.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_period(
        self,
        condominio_id: UUID,
        period_start: date,
        period_end: date,
    ) -> CashFlowForecast | None:
        """Busca previsao por periodo."""
        query = select(CashFlowForecast).where(
            and_(
                CashFlowForecast.condominio_id == condominio_id,
                CashFlowForecast.period_start == period_start,
                CashFlowForecast.period_end == period_end,
                CashFlowForecast.ativo.is_(True),  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
