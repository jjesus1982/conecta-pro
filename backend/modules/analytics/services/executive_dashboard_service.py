"""
Executive Dashboard Service - FASE 3 ONDA 1
===========================================

Dashboard executivo avançado com KPIs em tempo real,
analytics preditivos e insights de IA.

ROI Target: R$ 180K
Sprint: FASE 3 - Otimização Total
"""

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import text

from core.database.session import async_session_factory

logger = logging.getLogger(__name__)


# Mapeamento categoria (executive_kpis) -> DashboardMetricType
_CATEGORY_MAP: dict[str, str] = {
    "FINANCIAL": "financial",
    "OPERATIONAL": "operational",
    "HR": "hr",
    "COMMERCIAL": "client",
    "COMPLIANCE": "operational",
}


class DashboardMetricType(StrEnum):
    """Tipos de métricas do dashboard."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    HR = "hr"
    SAFETY = "safety"
    CLIENT = "client"
    PERFORMANCE = "performance"
    PREDICTION = "prediction"


class TrendDirection(StrEnum):
    """Direção da tendência."""

    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class AlertLevel(StrEnum):
    """Níveis de alerta."""

    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class KPIMetric:
    """Métrica de KPI."""

    name: str
    value: float
    previous_value: float
    target: float
    unit: str
    trend: TrendDirection
    change_percent: float
    category: DashboardMetricType
    updated_at: datetime


@dataclass
class DashboardAlert:
    """Alerta do dashboard."""

    title: str
    message: str
    level: AlertLevel
    metric: str
    value: float
    threshold: float
    created_at: datetime
    action_required: bool


@dataclass
class PredictiveInsight:
    """Insight preditivo."""

    title: str
    description: str
    confidence: float
    impact: str
    recommendation: str
    timeline: str
    category: DashboardMetricType


@dataclass
class ExecutiveDashboard:
    """Dashboard executivo completo."""

    timestamp: datetime
    kpis: list[KPIMetric]
    alerts: list[DashboardAlert]
    insights: list[PredictiveInsight]
    summary: dict[str, Any]
    trends: dict[str, list[float]]


class ExecutiveDashboardService:
    """Serviço de Dashboard Executivo Avançado."""

    def __init__(self):
        self.cache_duration = timedelta(minutes=5)
        self._cache: ExecutiveDashboard | None = None
        self._last_update: datetime | None = None

    async def get_executive_dashboard(self, refresh: bool = False) -> ExecutiveDashboard:
        """
        Gera dashboard executivo completo.

        Args:
            refresh: Forçar atualização dos dados

        Returns:
            Dashboard executivo com KPIs, alertas e insights
        """
        if not refresh and self._is_cache_valid():
            return self._cache

        # Coleta dados em paralelo
        kpis_task = self._collect_kpis()
        alerts_task = self._detect_alerts()
        insights_task = self._generate_insights()
        trends_task = self._calculate_trends()

        kpis, alerts, insights, trends = await asyncio.gather(kpis_task, alerts_task, insights_task, trends_task)

        # Gera resumo executivo
        summary = await self._generate_summary(kpis, alerts, insights)

        dashboard = ExecutiveDashboard(
            timestamp=datetime.now(), kpis=kpis, alerts=alerts, insights=insights, summary=summary, trends=trends
        )

        # Cache do resultado
        self._cache = dashboard
        self._last_update = datetime.now()

        return dashboard

    async def _load_kpi_rows(self) -> list[dict[str, Any]]:
        """Lê os KPIs reais da tabela executive_kpis (fonte da verdade).

        Retorna as linhas ativas (status ACTIVE) ordenadas por display_order.
        NÃO fabrica dados: se a tabela estiver vazia, retorna lista vazia.
        """
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT code, name, category, kpi_type, unit,
                               current_value, previous_value, target_value,
                               trend, alert_level, last_calculated_at
                        FROM executive_kpis
                        WHERE status = 'ACTIVE'
                        ORDER BY display_order
                        """
                    )
                )
                return [dict(row) for row in result.mappings().all()]
        except Exception as e:  # noqa: BLE001
            logger.error(f"Falha ao ler executive_kpis: {e}")
            return []

    async def _collect_kpis(self) -> list[KPIMetric]:
        """Coleta todos os KPIs reais a partir de executive_kpis."""
        rows = await self._load_kpi_rows()
        kpis: list[KPIMetric] = []

        for row in rows:
            current = float(row["current_value"]) if row["current_value"] is not None else None
            previous = float(row["previous_value"]) if row["previous_value"] is not None else None
            target = float(row["target_value"]) if row["target_value"] is not None else None

            # Trend: usa a coluna trend da tabela; deriva do delta se ausente.
            db_trend = (row.get("trend") or "").lower()
            if db_trend in ("up", "down", "stable"):
                trend = TrendDirection(db_trend)
            elif current is not None and previous is not None:
                if current > previous:
                    trend = TrendDirection.UP
                elif current < previous:
                    trend = TrendDirection.DOWN
                else:
                    trend = TrendDirection.STABLE
            else:
                trend = TrendDirection.STABLE

            # change_percent: derivado real (previous -> current). None se sem base.
            if current is not None and previous not in (None, 0):
                change_percent = round(((current - previous) / previous) * 100, 2)
            else:
                change_percent = 0.0

            category = DashboardMetricType(_CATEGORY_MAP.get(row["category"], "performance"))
            updated_at = row.get("last_calculated_at") or datetime.now()

            kpis.append(
                KPIMetric(
                    name=row["name"],
                    value=current if current is not None else 0.0,
                    previous_value=previous if previous is not None else 0.0,
                    target=target if target is not None else 0.0,
                    unit=row["unit"],
                    trend=trend,
                    change_percent=change_percent,
                    category=category,
                    updated_at=updated_at,
                )
            )

        return kpis

    async def _load_expiring_certidoes(self, days_ahead: int = 30) -> list[dict[str, Any]]:
        """Lê certidões (ged_certidoes) que vencem nos próximos N dias."""
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT name, document_type, expiry_date
                        FROM ged_certidoes
                        WHERE expiry_date IS NOT NULL
                          AND expiry_date <= (CURRENT_DATE + make_interval(days => :days))
                        ORDER BY expiry_date ASC
                        """
                    ),
                    {"days": days_ahead},
                )
                return [dict(row) for row in result.mappings().all()]
        except Exception as e:  # noqa: BLE001
            logger.error(f"Falha ao ler ged_certidoes: {e}")
            return []

    async def _detect_alerts(self) -> list[DashboardAlert]:
        """Detecta alertas a partir de fatos reais.

        Fontes: alert_level/status dos KPIs (executive_kpis) e certidões
        vencendo (ged_certidoes). Nenhum alerta é fabricado.
        """
        alerts: list[DashboardAlert] = []
        now = datetime.now()

        # Alertas derivados dos KPIs reais (WARNING/CRITICAL na tabela)
        for row in await self._load_kpi_rows():
            level_raw = (row.get("alert_level") or "NORMAL").upper()
            if level_raw not in ("WARNING", "CRITICAL"):
                continue
            level = AlertLevel.CRITICAL if level_raw == "CRITICAL" else AlertLevel.WARNING
            current = float(row["current_value"]) if row["current_value"] is not None else 0.0
            target = float(row["target_value"]) if row["target_value"] is not None else 0.0
            alerts.append(
                DashboardAlert(
                    title=f"KPI em atenção: {row['name']}",
                    message=(
                        f"{row['name']} está em nível {level_raw} "
                        f"(atual {current:g} {row['unit']}, meta {target:g} {row['unit']})."
                    ),
                    level=level,
                    metric=row["name"],
                    value=current,
                    threshold=target,
                    created_at=now,
                    action_required=level == AlertLevel.CRITICAL,
                )
            )

        # Alertas de certidões vencendo (fato real de ged_certidoes)
        today = date.today()
        for cert in await self._load_expiring_certidoes(30):
            expiry = cert["expiry_date"]
            days_left = (expiry - today).days if isinstance(expiry, date) else None
            expired = days_left is not None and days_left < 0
            msg = (
                f"Certidão '{cert['name']}' venceu em {expiry:%d/%m/%Y}."
                if expired
                else f"Certidão '{cert['name']}' vence em {expiry:%d/%m/%Y}"
                + (f" ({days_left} dias)." if days_left is not None else ".")
            )
            alerts.append(
                DashboardAlert(
                    title="Certidão vencida" if expired else "Certidão a vencer",
                    message=msg,
                    level=AlertLevel.CRITICAL if expired else AlertLevel.WARNING,
                    metric=cert.get("document_type") or "certidao",
                    value=float(days_left) if days_left is not None else 0.0,
                    threshold=0.0,
                    created_at=now,
                    action_required=True,
                )
            )

        return alerts

    async def _generate_insights(self) -> list[PredictiveInsight]:
        """Insights preditivos.

        Não há motor preditivo com fonte de dados histórica confiável, então
        não fabricamos insights. Retorna lista vazia (honesto: "aguardando dado").
        """
        return []

    async def _calculate_trends(self) -> dict[str, list[float]]:
        """Séries de tendência derivadas de dados reais.

        Só há dois pontos por KPI em executive_kpis (previous_value ->
        current_value); não existe série histórica. Emitimos apenas esses dois
        pontos reais por KPI que os possua. NÃO inventamos séries longas.
        """
        trends: dict[str, list[float]] = {}
        for row in await self._load_kpi_rows():
            current = row["current_value"]
            previous = row["previous_value"]
            if current is None or previous is None:
                continue
            trends[row["code"].lower()] = [float(previous), float(current)]
        return trends

    async def _generate_summary(
        self, kpis: list[KPIMetric], alerts: list[DashboardAlert], insights: list[PredictiveInsight]
    ) -> dict[str, Any]:
        """Gera resumo executivo inteligente."""

        total_kpis = len(kpis)
        positive_trends = sum(1 for kpi in kpis if kpi.trend == TrendDirection.UP)
        critical_alerts = sum(1 for alert in alerts if alert.level == AlertLevel.CRITICAL)

        performance_score = (positive_trends / total_kpis) * 100 if total_kpis > 0 else 0
        warning_alerts = sum(1 for alert in alerts if alert.level == AlertLevel.WARNING)

        # Destaque/concern derivados de fatos reais dos KPIs, não fabricados.
        highlight_kpi = max(
            (k for k in kpis if k.trend == TrendDirection.UP),
            key=lambda k: k.change_percent,
            default=None,
        )
        concern_kpi = max(
            (a for a in alerts if a.level in (AlertLevel.CRITICAL, AlertLevel.WARNING)),
            key=lambda a: 1 if a.level == AlertLevel.CRITICAL else 0,
            default=None,
        )

        return {
            "performance_score": round(performance_score, 1),
            "total_kpis": total_kpis,
            "positive_trends": positive_trends,
            "critical_alerts": critical_alerts,
            "warning_alerts": warning_alerts,
            "total_alerts": len(alerts),
            "total_insights": len(insights),
            "status": "excellent" if performance_score >= 80 else "good" if performance_score >= 60 else "attention",
            "main_highlight": (
                f"{highlight_kpi.name}: {highlight_kpi.change_percent:+.1f}% vs período anterior"
                if highlight_kpi
                else None
            ),
            "key_concern": (concern_kpi.title if concern_kpi else None),
        }

    def _is_cache_valid(self) -> bool:
        """Verifica se o cache ainda é válido."""
        if not self._cache or not self._last_update:
            return False

        return datetime.now() - self._last_update < self.cache_duration

    async def export_dashboard_data(self, format_type: str = "json") -> dict[str, Any]:
        """
        Exporta dados do dashboard para diferentes formatos.

        Args:
            format_type: Formato de exportação (json, csv, excel)

        Returns:
            Dados formatados para exportação
        """
        dashboard = await self.get_executive_dashboard()

        if format_type.lower() == "json":
            return self._export_to_json(dashboard)
        elif format_type.lower() == "csv":
            return self._export_to_csv(dashboard)
        else:
            raise ValueError(f"Formato {format_type} não suportado")

    def _export_to_json(self, dashboard: ExecutiveDashboard) -> dict[str, Any]:
        """Exporta dashboard para JSON."""
        return {
            "timestamp": dashboard.timestamp.isoformat(),
            "summary": dashboard.summary,
            "kpis": [asdict(kpi) for kpi in dashboard.kpis],
            "alerts": [asdict(alert) for alert in dashboard.alerts],
            "insights": [asdict(insight) for insight in dashboard.insights],
            "trends": dashboard.trends,
        }

    def _export_to_csv(self, dashboard: ExecutiveDashboard) -> dict[str, Any]:
        """Exporta KPIs para formato CSV."""
        csv_data = []
        for kpi in dashboard.kpis:
            csv_data.append(
                {
                    "Métrica": kpi.name,
                    "Valor Atual": kpi.value,
                    "Valor Anterior": kpi.previous_value,
                    "Meta": kpi.target,
                    "Unidade": kpi.unit,
                    "Tendência": kpi.trend.value,
                    "Mudança %": kpi.change_percent,
                    "Categoria": kpi.category.value,
                }
            )

        return {"kpis": csv_data}


# Instância singleton do serviço
executive_dashboard_service = ExecutiveDashboardService()
