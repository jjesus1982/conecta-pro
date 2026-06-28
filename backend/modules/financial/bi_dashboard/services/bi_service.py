"""Service de Business Intelligence Financeiro."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from modules.financial.bi_dashboard.models.dashboard_widget import DataSource
from modules.financial.bi_dashboard.models.kpi_definition import FinancialKPI


class BIService:
    """Servico de Business Intelligence Financeiro."""

    def __init__(self, db: Session):
        """Inicializa servico."""
        self.db = db

    def get_widget_data(
        self,
        data_source: DataSource,
        metric_field: str,
        dimension_field: str = None,
        aggregation: str = "sum",
        date_range_days: int = 30,
        group_by: list = None,
        sort_by: str = None,
        sort_order: str = "desc",
        limit: int = 10,
        condominio_id: UUID = None,
    ) -> dict:
        """Busca dados para widget baseado na fonte."""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=date_range_days)

        data = self._fetch_data_from_source(
            data_source=data_source,
            start_date=start_date,
            end_date=end_date,
            condominio_id=condominio_id,
        )

        result = self._aggregate_data(
            data=data,
            metric_field=metric_field,
            dimension_field=dimension_field,
            aggregation=aggregation,
            group_by=group_by or [],
        )

        if sort_by:
            result = sorted(
                result,
                key=lambda x: x.get(sort_by, 0),
                reverse=(sort_order == "desc"),
            )[:limit]

        return {
            "data": result,
            "total_rows": len(result),
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": date_range_days,
            },
            "aggregation": aggregation,
            "metric": metric_field,
            "dimension": dimension_field,
        }

    def _fetch_data_from_source(
        self,
        data_source: DataSource,
        start_date: datetime,
        end_date: datetime,
        condominio_id: UUID = None,
    ) -> list[dict]:
        """Busca dados da fonte especificada."""
        # Placeholder - implementacao real buscaria do banco
        # Parametros serao usados em queries reais
        _ = (start_date, end_date, condominio_id)

        source_handlers = {
            DataSource.CASH_FLOW: self._get_empty_data,
            DataSource.ACCOUNTS_PAYABLE: self._get_empty_data,
            DataSource.ACCOUNTS_RECEIVABLE: self._get_empty_data,
            DataSource.BANK_ACCOUNTS: self._get_empty_data,
            DataSource.PURCHASES: self._get_empty_data,
            DataSource.INVENTORY: self._get_empty_data,
            DataSource.ACCOUNTING: self._get_empty_data,
            DataSource.FISCAL: self._get_empty_data,
            DataSource.COSTING: self._get_empty_data,
            DataSource.BUDGET: self._get_empty_data,
        }

        handler = source_handlers.get(data_source, self._get_empty_data)
        return handler()

    def _get_empty_data(self) -> list[dict]:
        """Retorna dados vazios (placeholder)."""
        return []

    def _aggregate_data(
        self,
        data: list[dict],
        metric_field: str,
        dimension_field: str,
        aggregation: str,
        group_by: list,
    ) -> list[dict]:
        """Agrega dados conforme especificado."""
        if not data:
            return []

        if not group_by and not dimension_field:
            return self._simple_aggregation(data, metric_field, aggregation)

        return self._group_aggregation(data, metric_field, dimension_field, aggregation, group_by)

    def _simple_aggregation(
        self,
        data: list[dict],
        metric_field: str,
        aggregation: str,
    ) -> list[dict]:
        """Agregacao simples sem grupos."""
        values = [d.get(metric_field, 0) for d in data if metric_field in d]
        if not values:
            return [{"value": 0}]

        agg_funcs = {
            "sum": sum,
            "avg": lambda v: sum(v) / len(v),
            "count": len,
            "min": min,
            "max": max,
        }

        func = agg_funcs.get(aggregation, agg_funcs["sum"])
        return [{"value": func(values)}]

    def _group_aggregation(
        self,
        data: list[dict],
        metric_field: str,
        dimension_field: str,
        aggregation: str,
        group_by: list,
    ) -> list[dict]:
        """Agregacao por grupos."""
        groups = {}
        group_fields = group_by or ([dimension_field] if dimension_field else [])

        for item in data:
            key = tuple(item.get(f, "N/A") for f in group_fields)
            if key not in groups:
                groups[key] = []
            groups[key].append(item.get(metric_field, 0))

        result = []
        for key, values in groups.items():
            entry = dict(zip(group_fields, key, strict=False))
            entry["value"] = self._calc_aggregation(values, aggregation)
            result.append(entry)

        return result

    def _calc_aggregation(self, values: list, aggregation: str) -> float:
        """Calcula agregacao para valores."""
        if not values:
            return 0

        agg_funcs = {
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "count": len(values),
            "min": min(values),
            "max": max(values),
        }
        return agg_funcs.get(aggregation, sum(values))

    def calculate_kpi(
        self,
        kpi: FinancialKPI,
        condominio_id: UUID,
    ) -> Decimal:
        """Calcula valor de um KPI."""
        variables = {}
        for var_name, var_config in (kpi.variaveis or {}).items():
            source = var_config.get("source")
            metric = var_config.get("metric")
            period = var_config.get("period_days", 30)

            if source and metric:
                data = self.get_widget_data(
                    data_source=DataSource(source),
                    metric_field=metric,
                    aggregation="sum",
                    date_range_days=period,
                    condominio_id=condominio_id,
                )
                if data["data"]:
                    variables[var_name] = Decimal(str(data["data"][0].get("value", 0)))
                else:
                    variables[var_name] = Decimal("0")

        try:
            result = self._evaluate_formula(kpi.formula, variables)
            return Decimal(str(result))
        except (ValueError, ZeroDivisionError):
            return Decimal("0")

    def _evaluate_formula(
        self,
        formula: str,
        variables: dict,
    ) -> float:
        """Avalia formula matematica de forma segura."""
        expression = formula
        for var_name, var_value in variables.items():
            expression = expression.replace(f"{{{var_name}}}", str(var_value))

        allowed_names = {"abs": abs, "min": min, "max": max, "round": round}

        try:
            code = compile(expression, "<string>", "eval")
            for name in code.co_names:
                if name not in allowed_names and not name.isdigit():
                    raise ValueError(f"Nome nao permitido: {name}")
            # pylint: disable=eval-used
            return eval(expression, {"__builtins__": {}}, allowed_names)  # noqa: S307
        except (SyntaxError, NameError, TypeError):
            return 0.0

    def get_financial_summary(self, condominio_id=None, period_days: int = 30) -> dict:
        """Retorna resumo financeiro consolidado."""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period_days)

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": period_days,
            },
            "cash_flow": {
                "inflows": Decimal("0"),
                "outflows": Decimal("0"),
                "net": Decimal("0"),
                "balance": Decimal("0"),
            },
            "receivables": {
                "total": Decimal("0"),
                "overdue": Decimal("0"),
                "on_time": Decimal("0"),
            },
            "payables": {
                "total": Decimal("0"),
                "overdue": Decimal("0"),
                "due_soon": Decimal("0"),
            },
            "indicators": {
                "liquidity_ratio": Decimal("0"),
                "default_rate": Decimal("0"),
                "collection_efficiency": Decimal("0"),
            },
            "generated_at": datetime.utcnow().isoformat(),
        }

    def compare_periods(
        self,
        condominio_id: UUID,
        data_source: DataSource,
        metric_field: str,
        current_days: int = 30,
        previous_days: int = 30,
    ) -> dict:
        """Compara metricas entre periodos."""
        end_date = datetime.utcnow()
        current_start = end_date - timedelta(days=current_days)
        previous_end = current_start
        previous_start = previous_end - timedelta(days=previous_days)

        current_data = self.get_widget_data(
            data_source=data_source,
            metric_field=metric_field,
            aggregation="sum",
            date_range_days=current_days,
            condominio_id=condominio_id,
        )

        current_value = Decimal("0")
        if current_data["data"]:
            current_value = Decimal(str(current_data["data"][0].get("value", 0)))

        previous_value = Decimal("0")
        change = current_value - previous_value
        change_percent = Decimal("0")
        if previous_value != 0:
            change_percent = (change / previous_value) * 100

        return {
            "current": {
                "value": current_value,
                "period": {
                    "start": current_start.isoformat(),
                    "end": end_date.isoformat(),
                },
            },
            "previous": {
                "value": previous_value,
                "period": {
                    "start": previous_start.isoformat(),
                    "end": previous_end.isoformat(),
                },
            },
            "change": {
                "absolute": change,
                "percent": change_percent,
                "trend": "up" if change > 0 else "down" if change < 0 else "stable",
            },
        }
