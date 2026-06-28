"""Service de IA para contas a pagar."""

import logging
from datetime import date, timedelta
from statistics import mean, stdev
from uuid import UUID

from sqlalchemy import and_, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.financial.models.payable_account import PayableAccount, PayableStatus
from modules.financial.models.payable_category import PayableCategory
from modules.financial.models.supplier import Supplier

logger = logging.getLogger(__name__)


class PayableAnomalyType:  # pylint: disable=too-few-public-methods
    """Tipos de anomalias detectadas."""

    VALUE_SPIKE = "value_spike"  # Valor muito acima do normal
    VALUE_DROP = "value_drop"  # Valor muito abaixo do normal
    FREQUENCY_CHANGE = "frequency_change"  # Mudança na frequência
    NEW_SUPPLIER = "new_supplier"  # Fornecedor novo
    DUPLICATE_SUSPECT = "duplicate_suspect"  # Possível duplicidade
    UNUSUAL_CATEGORY = "unusual_category"  # Categoria incomum


class PayableAIService:
    """Service de IA para análise preditiva de contas a pagar."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.anomaly_threshold = 2.0  # Desvios padrão para considerar anomalia

    async def detect_anomalies(
        self,
        condominio_id: UUID,
        account: PayableAccount | None = None,
        period_months: int = 6,
    ) -> list[dict]:
        """Detecta anomalias em contas a pagar."""
        anomalies = []

        if account:
            # Analisa uma conta específica
            anomalies.extend(await self._analyze_single_account(account, period_months))
        else:
            # Analisa todas as contas recentes
            today = date.today()
            start_date = today - timedelta(days=30)

            query = select(PayableAccount).where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.created_at >= start_date,
                )
            )

            result = await self.session.execute(query)
            accounts = list(result.scalars().all())

            for acc in accounts:
                anomalies.extend(await self._analyze_single_account(acc, period_months))

        return anomalies

    async def _analyze_single_account(
        self,
        account: PayableAccount,
        period_months: int,
    ) -> list[dict]:
        """Analisa uma conta específica."""
        anomalies = []

        # 1. Verifica valor vs histórico do fornecedor
        if account.supplier_id:
            value_anomaly = await self._check_value_anomaly(account, period_months)
            if value_anomaly:
                anomalies.append(value_anomaly)

        # 2. Verifica duplicidade
        duplicate = await self._check_duplicate(account)
        if duplicate:
            anomalies.append(duplicate)

        # 3. Verifica se fornecedor é novo
        if account.supplier_id:
            new_supplier = await self._check_new_supplier(account)
            if new_supplier:
                anomalies.append(new_supplier)

        # 4. Verifica categoria vs histórico
        if account.category_id:
            category_anomaly = await self._check_category_anomaly(account)
            if category_anomaly:
                anomalies.append(category_anomaly)

        return anomalies

    async def _check_value_anomaly(
        self,
        account: PayableAccount,
        period_months: int,
    ) -> dict | None:
        """Verifica anomalia de valor."""
        start_date = date.today() - timedelta(days=period_months * 30)

        # Busca histórico de valores para este fornecedor
        query = select(PayableAccount.net_value).where(
            and_(
                PayableAccount.condominio_id == account.condominio_id,
                PayableAccount.supplier_id == account.supplier_id,
                PayableAccount.ativo.is_(True),
                PayableAccount.id != account.id,
                PayableAccount.created_at >= start_date,
            )
        )

        result = await self.session.execute(query)
        values = [float(row[0]) for row in result if row[0]]

        if len(values) < 3:
            return None

        avg = mean(values)
        std = stdev(values) if len(values) > 1 else 0
        current_value = float(account.net_value)

        if std > 0:
            z_score = (current_value - avg) / std

            if z_score > self.anomaly_threshold:
                return {
                    "type": PayableAnomalyType.VALUE_SPIKE,
                    "account_id": str(account.id),
                    "description": (f"Valor {current_value:.2f} está {z_score:.1f} desvios acima da média ({avg:.2f})"),
                    "severity": "high" if z_score > 3 else "medium",
                    "data": {
                        "current_value": current_value,
                        "average": avg,
                        "std_dev": std,
                        "z_score": z_score,
                    },
                }
            elif z_score < -self.anomaly_threshold:
                return {
                    "type": PayableAnomalyType.VALUE_DROP,
                    "account_id": str(account.id),
                    "description": (
                        f"Valor {current_value:.2f} está {abs(z_score):.1f} desvios abaixo da média ({avg:.2f})"
                    ),
                    "severity": "low",
                    "data": {
                        "current_value": current_value,
                        "average": avg,
                        "std_dev": std,
                        "z_score": z_score,
                    },
                }

        return None

    async def _check_duplicate(self, account: PayableAccount) -> dict | None:
        """Verifica possível duplicidade."""
        # Busca contas similares no mesmo período
        date_range = timedelta(days=5)

        query = select(PayableAccount).where(
            and_(
                PayableAccount.condominio_id == account.condominio_id,
                PayableAccount.supplier_id == account.supplier_id,
                PayableAccount.ativo.is_(True),
                PayableAccount.id != account.id,
                PayableAccount.net_value == account.net_value,
                PayableAccount.due_date >= account.due_date - date_range,
                PayableAccount.due_date <= account.due_date + date_range,
            )
        )

        result = await self.session.execute(query)
        duplicates = list(result.scalars().all())

        if duplicates:
            return {
                "type": PayableAnomalyType.DUPLICATE_SUSPECT,
                "account_id": str(account.id),
                "description": f"Possível duplicidade com {len(duplicates)} conta(s) similar(es)",
                "severity": "high",
                "data": {
                    "similar_accounts": [str(d.id) for d in duplicates],
                    "value": float(account.net_value),
                    "due_date": account.due_date.isoformat(),
                },
            }

        return None

    async def _check_new_supplier(self, account: PayableAccount) -> dict | None:
        """Verifica se é um fornecedor novo."""
        # Verifica se há histórico com este fornecedor
        query = select(func.count(PayableAccount.id)).where(
            and_(
                PayableAccount.condominio_id == account.condominio_id,
                PayableAccount.supplier_id == account.supplier_id,
                PayableAccount.ativo.is_(True),
                PayableAccount.id != account.id,
            )
        )

        result = await self.session.execute(query)
        count = result.scalar_one()

        if count == 0:
            supplier_query = select(Supplier.name).where(Supplier.id == account.supplier_id)
            supplier_result = await self.session.execute(supplier_query)
            supplier_name = supplier_result.scalar_one_or_none() or "Desconhecido"

            return {
                "type": PayableAnomalyType.NEW_SUPPLIER,
                "account_id": str(account.id),
                "description": f"Primeira conta com fornecedor: {supplier_name}",
                "severity": "low",
                "data": {
                    "supplier_id": str(account.supplier_id),
                    "supplier_name": supplier_name,
                    "value": float(account.net_value),
                },
            }

        return None

    async def _check_category_anomaly(self, account: PayableAccount) -> dict | None:
        """Verifica se a categoria é incomum para o fornecedor."""
        # Busca categoria mais comum para este fornecedor
        query = (
            select(
                PayableAccount.category_id,
                func.count(PayableAccount.id).label("count"),
            )
            .where(
                and_(
                    PayableAccount.condominio_id == account.condominio_id,
                    PayableAccount.supplier_id == account.supplier_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.id != account.id,
                    PayableAccount.category_id.isnot(None),
                )
            )
            .group_by(PayableAccount.category_id)
            .order_by(func.count(PayableAccount.id).desc())
        )

        result = await self.session.execute(query)
        rows = list(result)

        if len(rows) >= 3:
            common_categories = {row[0] for row in rows[:2]}

            if account.category_id not in common_categories:
                cat_query = select(PayableCategory.name).where(PayableCategory.id == account.category_id)
                cat_result = await self.session.execute(cat_query)
                cat_name = cat_result.scalar_one_or_none() or "Desconhecida"

                return {
                    "type": PayableAnomalyType.UNUSUAL_CATEGORY,
                    "account_id": str(account.id),
                    "description": f"Categoria '{cat_name}' é incomum para este fornecedor",
                    "severity": "low",
                    "data": {
                        "category_id": str(account.category_id),
                        "category_name": cat_name,
                    },
                }

        return None

    async def predict_cashflow(  # pylint: disable=too-many-locals
        self,
        condominio_id: UUID,
        months_ahead: int = 3,
    ) -> list[dict]:
        """Prevê fluxo de caixa futuro baseado em histórico."""
        predictions = []
        today = date.today()

        # Busca dados históricos dos últimos 12 meses
        history_start = today - timedelta(days=365)

        # Unidade inline (literal_column) para que date_trunc renderize de forma
        # idêntica em SELECT/GROUP BY/ORDER BY. Se "month" virar bind param, o
        # Postgres trata cada ocorrência como expressão distinta e exige due_date
        # no GROUP BY (asyncpg GroupingError).
        month_expr = func.date_trunc(literal_column("'month'"), PayableAccount.due_date)
        query = (
            select(
                month_expr.label("month"),
                func.sum(PayableAccount.net_value).label("total"),
            )
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.due_date >= history_start,
                    PayableAccount.due_date <= today,
                )
            )
            .group_by(month_expr)
            .order_by(month_expr)
        )

        result = await self.session.execute(query)
        history = [(row.month, float(row.total or 0)) for row in result]

        if len(history) < 3:
            logger.warning("Histórico insuficiente para previsão")
            return predictions

        # Calcula média e tendência
        values = [h[1] for h in history]
        avg = mean(values)
        std = stdev(values) if len(values) > 1 else 0

        # Calcula tendência (regressão linear simples)
        n = len(values)
        if n > 1:
            x_mean = (n - 1) / 2
            y_mean = avg
            numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            slope = numerator / denominator if denominator != 0 else 0
        else:
            slope = 0

        # Gera previsões
        for i in range(1, months_ahead + 1):
            future_month = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
            predicted_value = avg + slope * (n + i - 1)
            predicted_value = max(0, predicted_value)  # Não pode ser negativo

            predictions.append(
                {
                    "month": future_month.isoformat(),
                    "predicted_value": predicted_value,
                    "confidence_low": max(0, predicted_value - std),
                    "confidence_high": predicted_value + std,
                    "trend": "up" if slope > 0 else "down" if slope < 0 else "stable",
                }
            )

        return predictions

    async def suggest_optimizations(
        self,
        condominio_id: UUID,
    ) -> list[dict]:
        """Sugere otimizações baseadas em análise de dados."""
        suggestions = []

        # 1. Fornecedores com pagamentos frequentes (candidatos a negociação)
        frequent_suppliers = await self._analyze_frequent_suppliers(condominio_id)
        if frequent_suppliers:
            suggestions.append(
                {
                    "type": "negotiation",
                    "title": "Fornecedores para Negociação",
                    "description": ("Fornecedores com alto volume de pagamentos podem oferecer melhores condições"),
                    "items": frequent_suppliers,
                    "potential_savings": sum(s.get("potential_savings", 0) for s in frequent_suppliers),
                }
            )

        # 2. Categorias com crescimento anormal
        growing_categories = await self._analyze_growing_categories(condominio_id)
        if growing_categories:
            suggestions.append(
                {
                    "type": "cost_control",
                    "title": "Categorias com Crescimento",
                    "description": "Estas categorias mostram crescimento acima da média",
                    "items": growing_categories,
                }
            )

        # 3. Oportunidades de consolidação de pagamentos
        consolidation = await self._analyze_consolidation_opportunities(condominio_id)
        if consolidation:
            suggestions.append(
                {
                    "type": "consolidation",
                    "title": "Oportunidades de Consolidação",
                    "description": "Pagamentos que podem ser consolidados para melhor gestão",
                    "items": consolidation,
                }
            )

        return suggestions

    async def _analyze_frequent_suppliers(
        self,
        condominio_id: UUID,
    ) -> list[dict]:
        """Analisa fornecedores frequentes."""
        last_year = date.today() - timedelta(days=365)

        query = (
            select(
                Supplier.id,
                Supplier.name,
                func.sum(PayableAccount.net_value).label("total"),
                func.count(PayableAccount.id).label("count"),
            )
            .join(PayableAccount, PayableAccount.supplier_id == Supplier.id)
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.due_date >= last_year,
                )
            )
            .group_by(Supplier.id, Supplier.name)
            .having(func.count(PayableAccount.id) >= 6)
            .order_by(func.sum(PayableAccount.net_value).desc())
            .limit(10)
        )

        result = await self.session.execute(query)

        return [
            {
                "supplier_id": str(row.id),
                "supplier_name": row.name,
                "total_paid": float(row.total or 0),
                "payment_count": row.count,
                "potential_savings": float(row.total or 0) * 0.05,  # Estimativa de 5%
            }
            for row in result
        ]

    async def _analyze_growing_categories(  # pylint: disable=too-many-locals
        self,
        condominio_id: UUID,
    ) -> list[dict]:
        """Analisa categorias com crescimento."""
        today = date.today()
        current_quarter_start = today.replace(day=1)
        if today.month <= 3:
            current_quarter_start = current_quarter_start.replace(month=1)
        elif today.month <= 6:
            current_quarter_start = current_quarter_start.replace(month=4)
        elif today.month <= 9:
            current_quarter_start = current_quarter_start.replace(month=7)
        else:
            current_quarter_start = current_quarter_start.replace(month=10)

        prev_quarter_start = current_quarter_start - timedelta(days=90)

        # Query para trimestre atual
        current_query = (
            select(
                PayableCategory.id,
                PayableCategory.name,
                func.sum(PayableAccount.net_value).label("total"),
            )
            .join(PayableAccount, PayableAccount.category_id == PayableCategory.id)
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.due_date >= current_quarter_start,
                )
            )
            .group_by(PayableCategory.id, PayableCategory.name)
        )

        # Query para trimestre anterior
        prev_query = (
            select(
                PayableCategory.id,
                func.sum(PayableAccount.net_value).label("total"),
            )
            .join(PayableAccount, PayableAccount.category_id == PayableCategory.id)
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.due_date >= prev_quarter_start,
                    PayableAccount.due_date < current_quarter_start,
                )
            )
            .group_by(PayableCategory.id)
        )

        current_result = await self.session.execute(current_query)
        current_data = {str(row.id): (row.name, float(row.total or 0)) for row in current_result}

        prev_result = await self.session.execute(prev_query)
        prev_data = {str(row.id): float(row.total or 0) for row in prev_result}

        growing = []
        for cat_id, (name, current_total) in current_data.items():
            prev_total = prev_data.get(cat_id, 0)

            if prev_total > 0:
                growth = ((current_total - prev_total) / prev_total) * 100

                if growth > 20:  # Crescimento > 20%
                    growing.append(
                        {
                            "category_id": cat_id,
                            "category_name": name,
                            "current_total": current_total,
                            "previous_total": prev_total,
                            "growth_percentage": growth,
                        }
                    )

        return sorted(growing, key=lambda x: x["growth_percentage"], reverse=True)[:5]

    async def _analyze_consolidation_opportunities(
        self,
        condominio_id: UUID,
    ) -> list[dict]:
        """Analisa oportunidades de consolidação."""
        # Busca fornecedores com múltiplos pagamentos no mesmo mês
        today = date.today()
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        query = (
            select(
                Supplier.id,
                Supplier.name,
                func.count(PayableAccount.id).label("count"),
                func.sum(PayableAccount.net_value).label("total"),
            )
            .join(PayableAccount, PayableAccount.supplier_id == Supplier.id)
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),
                    PayableAccount.status.in_([PayableStatus.PENDENTE.value, PayableStatus.APROVADA.value]),
                    PayableAccount.due_date >= month_start,
                    PayableAccount.due_date <= month_end,
                )
            )
            .group_by(Supplier.id, Supplier.name)
            .having(func.count(PayableAccount.id) >= 3)
            .order_by(func.count(PayableAccount.id).desc())
        )

        result = await self.session.execute(query)

        return [
            {
                "supplier_id": str(row.id),
                "supplier_name": row.name,
                "payment_count": row.count,
                "total_value": float(row.total or 0),
                "suggestion": f"Consolidar {row.count} pagamentos em uma única transação",
            }
            for row in result
        ]
