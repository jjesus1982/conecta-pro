"""Budget Service - Serviço de Orçamento.

Sprint 30 - Orçamento e Previsão.
Responsável por:
- Criação de orçamentos
- Acompanhamento orçamentário
- Relatórios de execução orçamentária
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.financial.models.accounting_account import AccountingAccount, AccountType
from modules.financial.models.cost_center import CostCenter
from modules.financial.models.journal_entry import EntryStatus, JournalEntry, JournalEntryLine


class BudgetPeriodType(StrEnum):
    """Tipo de período orçamentário."""

    MONTHLY = "MONTHLY"  # Mensal
    QUARTERLY = "QUARTERLY"  # Trimestral
    SEMIANNUAL = "SEMIANNUAL"  # Semestral
    ANNUAL = "ANNUAL"  # Anual


class BudgetStatus(StrEnum):
    """Status do orçamento."""

    DRAFT = "DRAFT"  # Rascunho
    APPROVED = "APPROVED"  # Aprovado
    ACTIVE = "ACTIVE"  # Em execução
    CLOSED = "CLOSED"  # Encerrado
    CANCELLED = "CANCELLED"  # Cancelado


class BudgetVarianceType(StrEnum):
    """Tipo de variação orçamentária."""

    FAVORABLE = "FAVORABLE"  # Favorável (gastou menos)
    UNFAVORABLE = "UNFAVORABLE"  # Desfavorável (gastou mais)
    ON_TARGET = "ON_TARGET"  # Dentro do esperado


@dataclass
class BudgetLineItem:
    """Item de linha do orçamento."""

    account_id: UUID | None = None
    account_code: str = ""
    account_name: str = ""
    cost_center_id: UUID | None = None
    cost_center_code: str = ""
    cost_center_name: str = ""

    # Valores orçados por mês
    jan: Decimal = Decimal("0")
    feb: Decimal = Decimal("0")
    mar: Decimal = Decimal("0")
    apr: Decimal = Decimal("0")
    may: Decimal = Decimal("0")
    jun: Decimal = Decimal("0")
    jul: Decimal = Decimal("0")
    aug: Decimal = Decimal("0")
    sep: Decimal = Decimal("0")
    oct: Decimal = Decimal("0")
    nov: Decimal = Decimal("0")
    dec: Decimal = Decimal("0")

    # Totais
    total_budgeted: Decimal = Decimal("0")
    total_realized: Decimal = Decimal("0")
    total_variance: Decimal = Decimal("0")
    variance_percentage: Decimal = Decimal("0")

    def calculate_total(self) -> None:
        """Calcula total orçado."""
        self.total_budgeted = (
            self.jan
            + self.feb
            + self.mar
            + self.apr
            + self.may
            + self.jun
            + self.jul
            + self.aug
            + self.sep
            + self.oct
            + self.nov
            + self.dec
        )

    def get_month_value(self, month: int) -> Decimal:
        """Obtém valor orçado de um mês."""
        months = [
            None,
            self.jan,
            self.feb,
            self.mar,
            self.apr,
            self.may,
            self.jun,
            self.jul,
            self.aug,
            self.sep,
            self.oct,
            self.nov,
            self.dec,
        ]
        return months[month] if 1 <= month <= 12 else Decimal("0")


@dataclass
class BudgetExecution:
    """Execução orçamentária de um item."""

    account_id: UUID | None = None
    account_code: str = ""
    account_name: str = ""
    cost_center_id: UUID | None = None
    cost_center_code: str = ""

    budgeted: Decimal = Decimal("0")
    realized: Decimal = Decimal("0")
    variance: Decimal = Decimal("0")
    variance_pct: Decimal = Decimal("0")
    variance_type: BudgetVarianceType = BudgetVarianceType.ON_TARGET

    # Detalhes por mês
    monthly_detail: list[dict] = field(default_factory=list)

    def calculate_variance(self) -> None:
        """Calcula variação."""
        self.variance = self.budgeted - self.realized
        if self.budgeted > Decimal("0"):
            self.variance_pct = (self.variance / self.budgeted) * Decimal("100")

        # Determina tipo de variação (threshold de 5%)
        if abs(self.variance_pct) <= Decimal("5"):
            self.variance_type = BudgetVarianceType.ON_TARGET
        elif self.variance > Decimal("0"):
            self.variance_type = BudgetVarianceType.FAVORABLE
        else:
            self.variance_type = BudgetVarianceType.UNFAVORABLE


@dataclass
class BudgetReport:
    """Relatório de orçamento."""

    condominio_id: UUID
    year: int
    period_type: BudgetPeriodType
    status: BudgetStatus = BudgetStatus.DRAFT
    generated_at: datetime = field(default_factory=datetime.utcnow)

    # Itens do orçamento
    items: list[BudgetLineItem] = field(default_factory=list)

    # Totais
    total_revenue_budget: Decimal = Decimal("0")
    total_expense_budget: Decimal = Decimal("0")
    total_revenue_realized: Decimal = Decimal("0")
    total_expense_realized: Decimal = Decimal("0")

    # Resultado
    budgeted_result: Decimal = Decimal("0")
    realized_result: Decimal = Decimal("0")
    result_variance: Decimal = Decimal("0")

    def calculate_totals(self) -> None:
        """Calcula totais do orçamento."""
        for item in self.items:
            item.calculate_total()

        self.budgeted_result = self.total_revenue_budget - self.total_expense_budget
        self.realized_result = self.total_revenue_realized - self.total_expense_realized
        self.result_variance = self.realized_result - self.budgeted_result


@dataclass
class BudgetExecutionReport:
    """Relatório de execução orçamentária."""

    condominio_id: UUID
    year: int
    month: int
    reference_date: date
    generated_at: datetime = field(default_factory=datetime.utcnow)

    # Execuções por conta/centro de custo
    executions: list[BudgetExecution] = field(default_factory=list)

    # Resumo
    total_budgeted: Decimal = Decimal("0")
    total_realized: Decimal = Decimal("0")
    total_variance: Decimal = Decimal("0")
    variance_pct: Decimal = Decimal("0")

    # Contadores
    items_on_target: int = 0
    items_favorable: int = 0
    items_unfavorable: int = 0

    def calculate_summary(self) -> None:
        """Calcula resumo da execução."""
        for execution in self.executions:
            execution.calculate_variance()

            self.total_budgeted += execution.budgeted
            self.total_realized += execution.realized

            if execution.variance_type == BudgetVarianceType.ON_TARGET:
                self.items_on_target += 1
            elif execution.variance_type == BudgetVarianceType.FAVORABLE:
                self.items_favorable += 1
            else:
                self.items_unfavorable += 1

        self.total_variance = self.total_budgeted - self.total_realized
        if self.total_budgeted > Decimal("0"):
            self.variance_pct = (self.total_variance / self.total_budgeted) * Decimal("100")


class BudgetService:
    """Serviço de Orçamento."""

    # Threshold para variação aceitável (5%)
    VARIANCE_THRESHOLD = Decimal("5")

    def __init__(self, session: AsyncSession):
        """Inicializa o serviço.

        Args:
            session: Sessão assíncrona do banco de dados.
        """
        self.session = session

    async def create_budget(
        self,
        condominio_id: UUID,
        year: int,
        period_type: BudgetPeriodType = BudgetPeriodType.ANNUAL,
        base_on_previous: bool = True,
        adjustment_pct: Decimal = Decimal("0"),
    ) -> BudgetReport:
        """Cria orçamento para um ano.

        Args:
            condominio_id: ID do condomínio.
            year: Ano do orçamento.
            period_type: Tipo de período.
            base_on_previous: Basear no ano anterior.
            adjustment_pct: Percentual de ajuste sobre o ano anterior.

        Returns:
            BudgetReport com o orçamento criado.
        """
        report = BudgetReport(
            condominio_id=condominio_id,
            year=year,
            period_type=period_type,
            status=BudgetStatus.DRAFT,
        )

        # Busca contas de despesa/receita
        accounts = await self._get_budget_accounts(condominio_id)

        for account in accounts:
            item = BudgetLineItem(
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
            )

            if base_on_previous:
                # Busca valores do ano anterior
                previous = await self._get_previous_year_values(account.id, year - 1)
                adjustment = Decimal("1") + (adjustment_pct / Decimal("100"))

                item.jan = previous.get(1, Decimal("0")) * adjustment
                item.feb = previous.get(2, Decimal("0")) * adjustment
                item.mar = previous.get(3, Decimal("0")) * adjustment
                item.apr = previous.get(4, Decimal("0")) * adjustment
                item.may = previous.get(5, Decimal("0")) * adjustment
                item.jun = previous.get(6, Decimal("0")) * adjustment
                item.jul = previous.get(7, Decimal("0")) * adjustment
                item.aug = previous.get(8, Decimal("0")) * adjustment
                item.sep = previous.get(9, Decimal("0")) * adjustment
                item.oct = previous.get(10, Decimal("0")) * adjustment
                item.nov = previous.get(11, Decimal("0")) * adjustment
                item.dec = previous.get(12, Decimal("0")) * adjustment

            item.calculate_total()
            report.items.append(item)

        report.calculate_totals()
        return report

    async def get_budget_execution(
        self,
        condominio_id: UUID,
        year: int,
        month: int,
        cost_center_id: UUID | None = None,
    ) -> BudgetExecutionReport:
        """Obtém relatório de execução orçamentária.

        Args:
            condominio_id: ID do condomínio.
            year: Ano.
            month: Mês.
            cost_center_id: Filtrar por centro de custo.

        Returns:
            BudgetExecutionReport com a execução.
        """
        reference_date = date(year, month, 1)
        report = BudgetExecutionReport(
            condominio_id=condominio_id,
            year=year,
            month=month,
            reference_date=reference_date,
        )

        # Busca centros de custo
        cost_centers = await self._get_cost_centers(condominio_id, cost_center_id)

        for cost_center in cost_centers:
            execution = BudgetExecution(
                cost_center_id=cost_center.id,
                cost_center_code=cost_center.code,
                budgeted=cost_center.budget_monthly,
            )

            # Busca realizado no mês
            realized = await self._get_realized_amount(cost_center.id, year, month)
            execution.realized = realized
            execution.calculate_variance()

            report.executions.append(execution)

        report.calculate_summary()
        # Orçado REAL do mês = financial_orcamentos (o que o usuário define), não valor fixo/por-centro.
        report.total_budgeted = await self._orcamento_meses(year, month, month)
        report.total_variance = report.total_budgeted - report.total_realized
        report.variance_pct = ((report.total_variance / report.total_budgeted) * Decimal("100")
                               if report.total_budgeted > 0 else Decimal("0"))
        return report

    async def get_ytd_execution(
        self,
        condominio_id: UUID,
        year: int,
        through_month: int,
    ) -> BudgetExecutionReport:
        """Obtém execução acumulada do ano (YTD - Year to Date).

        Args:
            condominio_id: ID do condomínio.
            year: Ano.
            through_month: Até qual mês.

        Returns:
            BudgetExecutionReport com execução acumulada.
        """
        reference_date = date(year, through_month, 1)
        report = BudgetExecutionReport(
            condominio_id=condominio_id,
            year=year,
            month=through_month,
            reference_date=reference_date,
        )

        # Busca contas de despesa
        accounts = await self._get_budget_accounts(condominio_id)

        for account in accounts:
            execution = BudgetExecution(
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
            )

            # Acumula orçado e realizado
            for month in range(1, through_month + 1):
                budgeted = await self._get_account_budget(account.id, year, month)
                realized = await self._get_account_realized(account.id, year, month)

                execution.budgeted += budgeted
                execution.realized += realized

                execution.monthly_detail.append(
                    {
                        "month": month,
                        "budgeted": budgeted,
                        "realized": realized,
                        "variance": budgeted - realized,
                    }
                )

            execution.calculate_variance()
            report.executions.append(execution)

        report.calculate_summary()
        # Orçado REAL YTD = soma de financial_orcamentos dos meses 1..through_month. Preenche também os
        # atributos *_ytd que o controller lê (antes inexistentes → o YTD retornava zeros por bug de nome).
        report.total_budgeted = await self._orcamento_meses(year, 1, through_month)
        report.total_variance = report.total_budgeted - report.total_realized
        report.total_budgeted_ytd = report.total_budgeted
        report.total_realized_ytd = report.total_realized
        report.total_variance_ytd = report.total_variance
        report.variance_pct = ((report.total_variance / report.total_budgeted) * Decimal("100")
                               if report.total_budgeted > 0 else Decimal("0"))
        return report

    async def get_cost_center_budget(
        self,
        condominio_id: UUID,
        cost_center_id: UUID,
        year: int,
    ) -> dict:
        """Obtém orçamento de um centro de custo.

        Args:
            condominio_id: ID do condomínio.
            cost_center_id: ID do centro de custo.
            year: Ano.

        Returns:
            Dict com dados do orçamento.
        """
        # Busca centro de custo
        cc_query = select(CostCenter).where(
            and_(
                CostCenter.condominio_id == condominio_id,
                CostCenter.id == cost_center_id,
            )
        )
        result = await self.session.execute(cc_query)
        cost_center = result.scalar_one_or_none()

        if not cost_center:
            return {"error": "Centro de custo não encontrado"}

        # Calcula realizado por mês
        monthly_data = []
        total_budgeted = Decimal("0")
        total_realized = Decimal("0")

        for month in range(1, 13):
            realized = await self._get_realized_amount(cost_center_id, year, month)
            budgeted = cost_center.budget_monthly

            monthly_data.append(
                {
                    "month": month,
                    "month_name": self._get_month_name(month),
                    "budgeted": budgeted,
                    "realized": realized,
                    "variance": budgeted - realized,
                    "variance_pct": (((budgeted - realized) / budgeted * 100) if budgeted > 0 else Decimal("0")),
                }
            )

            total_budgeted += budgeted
            total_realized += realized

        return {
            "cost_center_id": str(cost_center_id),
            "cost_center_code": cost_center.code,
            "cost_center_name": cost_center.name,
            "year": year,
            "budget_annual": cost_center.budget_annual,
            "budget_monthly": cost_center.budget_monthly,
            "total_budgeted": total_budgeted,
            "total_realized": total_realized,
            "total_variance": total_budgeted - total_realized,
            "monthly_data": monthly_data,
            "is_over_budget": total_realized > total_budgeted,
        }

    async def compare_budget_periods(
        self,
        condominio_id: UUID,
        year1: int,
        year2: int,
    ) -> dict:
        """Compara orçamentos de dois anos.

        Args:
            condominio_id: ID do condomínio.
            year1: Primeiro ano.
            year2: Segundo ano.

        Returns:
            Dict com comparação.
        """
        # Busca execuções dos dois anos
        exec1 = await self.get_ytd_execution(condominio_id, year1, 12)
        exec2 = await self.get_ytd_execution(condominio_id, year2, 12)

        comparison = {
            "year1": year1,
            "year2": year2,
            "year1_budgeted": exec1.total_budgeted,
            "year1_realized": exec1.total_realized,
            "year2_budgeted": exec2.total_budgeted,
            "year2_realized": exec2.total_realized,
            "budget_variation": exec2.total_budgeted - exec1.total_budgeted,
            "realized_variation": exec2.total_realized - exec1.total_realized,
        }

        # Percentuais
        if exec1.total_budgeted > Decimal("0"):
            comparison["budget_variation_pct"] = (comparison["budget_variation"] / exec1.total_budgeted) * 100
        else:
            comparison["budget_variation_pct"] = Decimal("0")

        if exec1.total_realized > Decimal("0"):
            comparison["realized_variation_pct"] = (comparison["realized_variation"] / exec1.total_realized) * 100
        else:
            comparison["realized_variation_pct"] = Decimal("0")

        return comparison

    async def update_cost_center_budget(
        self,
        cost_center_id: UUID,
        budget_annual: Decimal,
        budget_monthly: Decimal | None = None,
    ) -> dict:
        """Atualiza orçamento de um centro de custo.

        Args:
            cost_center_id: ID do centro de custo.
            budget_annual: Orçamento anual.
            budget_monthly: Orçamento mensal (se não informado, divide por 12).

        Returns:
            Dict com resultado.
        """
        cc_query = select(CostCenter).where(CostCenter.id == cost_center_id)
        result = await self.session.execute(cc_query)
        cost_center = result.scalar_one_or_none()

        if not cost_center:
            return {"success": False, "error": "Centro de custo não encontrado"}

        cost_center.budget_annual = budget_annual
        cost_center.budget_monthly = budget_monthly if budget_monthly else budget_annual / Decimal("12")
        cost_center.budget_available = cost_center.budget_annual - cost_center.budget_used

        await self.session.commit()

        return {
            "success": True,
            "cost_center_id": str(cost_center_id),
            "budget_annual": cost_center.budget_annual,
            "budget_monthly": cost_center.budget_monthly,
            "budget_available": cost_center.budget_available,
        }

    # --- Métodos privados ---

    async def _get_budget_accounts(
        self,
        condominio_id: UUID,
    ) -> list[AccountingAccount]:
        """Busca contas para orçamento (despesas e receitas)."""
        query = (
            select(AccountingAccount)
            .where(
                and_(
                    AccountingAccount.condominio_id == condominio_id,
                    AccountingAccount.account_type.in_(
                        [
                            AccountType.EXPENSE,
                            AccountType.REVENUE,
                            AccountType.COST,
                        ]
                    ),
                    AccountingAccount.active.is_(True),
                )
            )
            .order_by(AccountingAccount.code)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def _get_cost_centers(
        self,
        condominio_id: UUID,
        cost_center_id: UUID | None = None,
    ) -> list[CostCenter]:
        """Busca centros de custo."""
        query = select(CostCenter).where(
            and_(
                CostCenter.condominio_id == condominio_id,
                CostCenter.active.is_(True),
            )
        )

        if cost_center_id:
            query = query.where(CostCenter.id == cost_center_id)

        query = query.order_by(CostCenter.code)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def _get_previous_year_values(
        self,
        account_id: UUID,
        year: int,
    ) -> dict[int, Decimal]:
        """Obtém valores realizados do ano anterior por mês."""
        values = {}

        for month in range(1, 13):
            values[month] = await self._get_account_realized(account_id, year, month)

        return values

    async def _get_realized_amount(
        self,
        cost_center_id: UUID,
        year: int,
        month: int,
    ) -> Decimal:
        """Obtém valor realizado de um centro de custo no mês."""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        query = (
            select(func.coalesce(func.sum(JournalEntryLine.debit_amount), 0))
            .join(JournalEntry)
            .where(
                and_(
                    JournalEntryLine.cost_center_id == cost_center_id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date < end_date,
                    JournalEntry.status == EntryStatus.POSTED,
                )
            )
        )

        result = await self.session.execute(query)
        return Decimal(str(result.scalar() or 0))

    async def _get_account_realized(
        self,
        account_id: UUID,
        year: int,
        month: int,
    ) -> Decimal:
        """Obtém valor realizado de uma conta no mês."""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        query = (
            select(
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("credit"),
            )
            .join(JournalEntry)
            .where(
                and_(
                    JournalEntryLine.account_id == account_id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date < end_date,
                    JournalEntry.status == EntryStatus.POSTED,
                )
            )
        )

        result = await self.session.execute(query)
        row = result.one()

        # Despesas = débito, Receitas = crédito
        return Decimal(str(row.debit)) - Decimal(str(row.credit))

    async def _get_account_budget(
        self,
        account_id: UUID,  # pylint: disable=unused-argument
        year: int,  # pylint: disable=unused-argument
        month: int,  # pylint: disable=unused-argument
    ) -> Decimal:
        """Orçamento POR CONTA — não há orçamento por conta no dado (o usuário define orçamento
        MENSAL total em financial_orcamentos). Retorna 0 (honesto): NUNCA o valor fixo de demonstração.
        O total real do relatório vem de `_orcamento_meses` (financial_orcamentos)."""
        return Decimal("0")

    async def _orcamento_meses(self, year: int, m_from: int, m_to: int) -> Decimal:
        """Orçamento REAL definido pelo usuário em `financial_orcamentos` (chave 'month_AAAA_MM'),
        somado dos meses m_from..m_to. Sem orçamento definido → 0 (honesto, nunca fabrica)."""
        from sqlalchemy import text as _text

        rows = (await self.session.execute(_text(
            "SELECT chave, valor FROM financial_orcamentos WHERE chave LIKE :p"),
            {"p": f"month_{year}_%"})).fetchall()
        total = Decimal("0")
        for chave, valor in rows:
            try:
                mm = int(str(chave).rsplit("_", 1)[-1])
            except (ValueError, IndexError):
                continue
            if m_from <= mm <= m_to:
                total += Decimal(str(valor or 0))
        return total

    @staticmethod
    def _get_month_name(month: int) -> str:
        """Retorna nome do mês."""
        months = [
            "",
            "Janeiro",
            "Fevereiro",
            "Março",
            "Abril",
            "Maio",
            "Junho",
            "Julho",
            "Agosto",
            "Setembro",
            "Outubro",
            "Novembro",
            "Dezembro",
        ]
        return months[month] if 1 <= month <= 12 else ""
