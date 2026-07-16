"""Service para projeção de fluxo de caixa."""

import logging
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.financial.models.bank_account import BankAccount
from modules.financial.models.payable_account import PayableAccount
from modules.financial.models.payable_category import PayableCategory
from modules.financial.models.payable_installment import InstallmentStatus, PayableInstallment
from modules.financial.models.receivable_installment import (
    InstallmentStatus as ReceivableInstallmentStatus,
)
from modules.financial.models.receivable_account import ReceivableAccount
from modules.financial.models.receivable_installment import ReceivableInstallment
from modules.financial.models.supplier import Supplier

logger = logging.getLogger(__name__)


class CashFlowProjection:  # pylint: disable=too-few-public-methods
    """Representa uma projeção de fluxo de caixa."""

    def __init__(
        self,
        date: date,  # pylint: disable=redefined-outer-name
        payables: Decimal = Decimal("0"),
        receivables: Decimal = Decimal("0"),
        balance: Decimal = Decimal("0"),
    ):
        """Inicializa a projeção."""
        self.date = date
        self.payables = payables
        self.receivables = receivables
        self.balance = balance
        self.cumulative_balance = Decimal("0")
        self.details: list[dict] = []

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "date": self.date.isoformat(),
            "payables": float(self.payables),
            "receivables": float(self.receivables),
            "balance": float(self.balance),
            "cumulative_balance": float(self.cumulative_balance),
            "details": self.details,
        }


class CashFlowService:
    """Service para projeção e análise de fluxo de caixa."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session

    async def get_projection(  # pylint: disable=too-many-locals
        self,
        condominio_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        include_pending: bool = True,  # pylint: disable=unused-argument
        include_scheduled: bool = True,
        group_by: str = "day",  # day, week, month
    ) -> list[CashFlowProjection]:
        """Gera projeção de fluxo de caixa."""
        if start_date is None:
            start_date = date.today()
        if end_date is None:
            end_date = start_date + timedelta(days=90)

        logger.info(f"Gerando projeção de {start_date} a {end_date} para {condominio_id}")

        # FIN-04: projeta a partir das CONTAS em aberto (onde está o saldo real),
        # não das parcelas. A maioria das contas não tem parcela desmembrada (só
        # ~18 de 71 pagáveis / ~21 de 9 recebíveis), então a projeção por parcela
        # ficava quase vazia → valor incoerente (ex.: −R$67). Projetamos as DUAS
        # pontas por data de vencimento: pagáveis (saída) e recebíveis (entrada).
        _CLOSED_PAY = ("paga", "cancelada")
        _CLOSED_REC = ("paga", "pago", "cancelada")

        projections_map: dict[date, CashFlowProjection] = {}

        pay_query = (
            select(PayableAccount)
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.due_date >= start_date,
                    PayableAccount.due_date <= end_date,
                    PayableAccount.status.notin_(_CLOSED_PAY),
                )
            )
            .order_by(PayableAccount.due_date)
        )
        for acct in (await self.session.execute(pay_query)).scalars().all():
            amount = (acct.net_value or Decimal("0")) - (acct.paid_value or Decimal("0"))
            if amount <= 0:
                continue
            proj_date = self._get_grouped_date(acct.due_date, group_by)
            if proj_date not in projections_map:
                projections_map[proj_date] = CashFlowProjection(date=proj_date)
            proj = projections_map[proj_date]
            proj.payables += amount
            proj.balance -= amount
            proj.details.append(
                {
                    "type": "payable",
                    "account_id": str(acct.id),
                    "description": acct.description or "Conta a pagar",
                    "due_date": acct.due_date.isoformat(),
                    "amount": float(amount),
                }
            )

        rec_query = (
            select(ReceivableAccount)
            .where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),
                    ReceivableAccount.due_date >= start_date,
                    ReceivableAccount.due_date <= end_date,
                    ReceivableAccount.status.notin_(_CLOSED_REC),
                )
            )
            .order_by(ReceivableAccount.due_date)
        )
        for acct in (await self.session.execute(rec_query)).scalars().all():
            amount = (acct.net_value or Decimal("0")) - (acct.paid_value or Decimal("0"))
            if amount <= 0:
                continue
            proj_date = self._get_grouped_date(acct.due_date, group_by)
            if proj_date not in projections_map:
                projections_map[proj_date] = CashFlowProjection(date=proj_date)
            proj = projections_map[proj_date]
            proj.receivables += amount
            proj.balance += amount
            proj.details.append(
                {
                    "type": "receivable",
                    "account_id": str(acct.id),
                    "description": acct.description or acct.customer_name or "Conta a receber",
                    "due_date": acct.due_date.isoformat(),
                    "amount": float(amount),
                }
            )

        # Ordena e calcula saldo acumulado
        projections = sorted(projections_map.values(), key=lambda p: p.date)

        # FIN-04: parte do SALDO ATUAL (não de zero) — assim o acumulado projetado
        # tem sentido físico (saldo de hoje ± fluxos futuros).
        opening_res = await self.session.execute(
            select(func.sum(BankAccount.current_balance)).where(
                and_(
                    BankAccount.condominio_id == condominio_id,
                    BankAccount.ativo.is_(True),
                )
            )
        )
        cumulative = opening_res.scalar() or Decimal("0")
        for proj in projections:
            cumulative += proj.balance
            proj.cumulative_balance = cumulative

        return projections

    def _get_grouped_date(self, d: date, group_by: str) -> date:
        """Agrupa data conforme período."""
        if group_by == "week":
            # Início da semana (segunda-feira)
            return d - timedelta(days=d.weekday())
        elif group_by == "month":
            # Primeiro dia do mês
            return d.replace(day=1)
        return d

    async def get_summary(  # pylint: disable=too-many-locals
        self,
        condominio_id,
        period_days: int = 30,
    ) -> dict:
        """Retorna resumo do fluxo de caixa usando cashflow_entries."""
        today = date.today()
        period_start = today - timedelta(days=period_days)
        period_end = today

        cid_clause = "AND condominio_id = :cid" if condominio_id else ""
        base_params_period = {"start": period_start, "end": period_end}
        base_params_today = {"today": today}
        base_params_start = {"start": period_start}
        if condominio_id:
            base_params_period["cid"] = str(condominio_id)
            base_params_today["cid"] = str(condominio_id)
            base_params_start["cid"] = str(condominio_id)

        # Totais de entrada e saída no período (cashflow_entries)
        inflow_q = await self.session.execute(
            text(f"""
                SELECT
                    COALESCE(SUM(expected_amount), 0) as total,
                    category
                FROM cashflow_entries
                WHERE entry_type = 'entrada'
                  {cid_clause}
                  AND entry_date BETWEEN :start AND :end
                  AND ativo = true
                GROUP BY category
            """),
            base_params_period,
        )
        inflows_by_cat: dict = {}
        total_inflows = Decimal("0")
        for row in inflow_q:
            val = Decimal(str(row.total))
            cat = row.category or "outros"
            inflows_by_cat[cat] = val
            total_inflows += val

        outflow_q = await self.session.execute(
            text(f"""
                SELECT
                    COALESCE(SUM(expected_amount), 0) as total,
                    category
                FROM cashflow_entries
                WHERE entry_type = 'saida'
                  {cid_clause}
                  AND entry_date BETWEEN :start AND :end
                  AND ativo = true
                GROUP BY category
            """),
            base_params_period,
        )
        outflows_by_cat: dict = {}
        total_outflows = Decimal("0")
        for row in outflow_q:
            val = Decimal(str(row.total))
            cat = row.category or "outros"
            outflows_by_cat[cat] = val
            total_outflows += val

        net_flow = total_inflows - total_outflows

        # Saldo (soma de realized_amount de todas as entradas - saídas confirmadas)
        bal_q = await self.session.execute(
            text(f"""
                SELECT
                    COALESCE(SUM(CASE WHEN entry_type='entrada' THEN realized_amount ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN entry_type='saida' THEN realized_amount ELSE 0 END), 0) as balance
                FROM cashflow_entries
                WHERE ativo = true
                  {cid_clause}
                  AND status IN ('realizado', 'confirmado')
                  AND entry_date < :start
            """),
            base_params_start,
        )
        bal_row = bal_q.one()
        opening_balance = Decimal(str(bal_row.balance or 0))
        closing_balance = opening_balance + net_flow

        # Contas a receber pendentes
        rec_q = await self.session.execute(
            text(f"""
                SELECT
                    COALESCE(SUM(CASE WHEN due_date >= :today THEN net_value ELSE 0 END), 0) as pending,
                    COALESCE(SUM(CASE WHEN due_date < :today THEN net_value ELSE 0 END), 0) as overdue
                FROM receivable_accounts
                WHERE ativo = true
                  {cid_clause}
                  AND status IN ('pendente', 'aprovada', 'aberta')
            """),
            base_params_today,
        )
        rec_row = rec_q.one()
        pending_receivables = Decimal(str(rec_row.pending or 0))
        overdue_receivables = Decimal(str(rec_row.overdue or 0))

        # Contas a pagar pendentes
        pay_q = await self.session.execute(
            text(f"""
                SELECT
                    COALESCE(SUM(CASE WHEN due_date >= :today THEN net_value ELSE 0 END), 0) as pending,
                    COALESCE(SUM(CASE WHEN due_date < :today THEN net_value ELSE 0 END), 0) as overdue
                FROM payable_accounts
                WHERE ativo = true
                  {cid_clause}
                  AND status IN ('pendente', 'aprovada')
            """),
            base_params_today,
        )
        pay_row = pay_q.one()
        pending_payables = Decimal(str(pay_row.pending or 0))
        overdue_payables = Decimal(str(pay_row.overdue or 0))

        return {
            "period_start": period_start,
            "period_end": period_end,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "total_inflows": total_inflows,
            "total_outflows": total_outflows,
            "net_flow": net_flow,
            "inflows_by_category": inflows_by_cat,
            "outflows_by_category": outflows_by_cat,
            "pending_receivables": pending_receivables,
            "pending_payables": pending_payables,
            "overdue_receivables": overdue_receivables,
            "overdue_payables": overdue_payables,
        }

    async def get_category_breakdown(
        self,
        condominio_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        """Retorna breakdown por categoria."""
        if start_date is None:
            start_date = date.today().replace(day=1)
        if end_date is None:
            end_date = date.today()

        query = (
            select(
                PayableCategory.id,
                PayableCategory.name,
                func.sum(PayableAccount.net_value).label("total"),
                func.count(PayableAccount.id).label("count"),
            )
            .join(PayableAccount, PayableAccount.category_id == PayableCategory.id)
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.due_date >= start_date,
                    PayableAccount.due_date <= end_date,
                )
            )
            .group_by(PayableCategory.id, PayableCategory.name)
            .order_by(func.sum(PayableAccount.net_value).desc())
        )

        result = await self.session.execute(query)

        return [
            {
                "category_id": str(row.id),
                "name": row.name,
                "full_name": row.name,
                "total": float(row.total or 0),
                "count": row.count,
            }
            for row in result
        ]

    async def get_supplier_breakdown(
        self,
        condominio_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Retorna breakdown por fornecedor."""
        if start_date is None:
            start_date = date.today().replace(day=1)
        if end_date is None:
            end_date = date.today()

        query = (
            select(
                Supplier.id,
                Supplier.name,
                Supplier.trade_name,
                func.sum(PayableAccount.net_value).label("total"),
                func.count(PayableAccount.id).label("count"),
            )
            .join(PayableAccount, PayableAccount.supplier_id == Supplier.id)
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.due_date >= start_date,
                    PayableAccount.due_date <= end_date,
                )
            )
            .group_by(Supplier.id, Supplier.name, Supplier.trade_name)
            .order_by(func.sum(PayableAccount.net_value).desc())
            .limit(limit)
        )

        result = await self.session.execute(query)

        return [
            {
                "supplier_id": str(row.id),
                "name": row.name,
                "trade_name": row.trade_name,
                "total": float(row.total or 0),
                "count": row.count,
            }
            for row in result
        ]

    async def get_monthly_trend(
        self,
        condominio_id: UUID,
        months: int = 12,
    ) -> list[dict]:
        """Retorna tendência mensal de pagamentos."""
        today = date.today()
        start_date = (today.replace(day=1) - timedelta(days=months * 30)).replace(day=1)

        query = (
            select(
                func.date_trunc(text("'month'"), PayableAccount.due_date).label("month"),
                func.sum(PayableAccount.net_value).label("total"),
                func.sum(PayableAccount.paid_value).label("paid"),
                func.count(PayableAccount.id).label("count"),
            )
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.due_date >= start_date,
                    PayableAccount.due_date <= today,
                )
            )
            .group_by(text("1"))
            .order_by(text("1"))
        )

        result = await self.session.execute(query)

        return [
            {
                "month": row.month.isoformat() if row.month else None,
                "total": float(row.total or 0),
                "paid": float(row.paid or 0),
                "count": row.count,
            }
            for row in result
        ]
