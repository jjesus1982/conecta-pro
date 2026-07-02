"""Analytics avançado para notificações."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TimeGranularity(Enum):
    """Granularidade temporal."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TrendDirection(Enum):
    """Direção da tendência."""

    UP = "up"
    DOWN = "down"
    STABLE = "stable"


@dataclass
class MetricPoint:
    """Ponto de métrica no tempo."""

    timestamp: datetime
    value: float
    count: int = 0


@dataclass
class ChannelPerformance:
    """Performance de um canal."""

    channel: str
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_converted: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    conversion_rate: float
    avg_delivery_time_seconds: float
    cost_total: float
    cost_per_conversion: float
    trend: TrendDirection


@dataclass
class CampaignMetrics:
    """Métricas de uma campanha."""

    campaign_id: str
    name: str
    start_date: datetime
    end_date: datetime | None
    total_recipients: int
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_converted: int
    total_unsubscribed: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    conversion_rate: float
    unsubscribe_rate: float
    revenue_attributed: float
    roi: float


@dataclass
class TrendAnalysis:
    """Análise de tendência."""

    metric_name: str
    direction: TrendDirection
    change_percentage: float
    current_value: float
    previous_value: float
    period: str
    data_points: list[MetricPoint]
    forecast: list[MetricPoint]
    confidence: float


@dataclass
class MetricReport:
    """Relatório de métricas."""

    period_start: datetime
    period_end: datetime
    total_notifications: int
    total_unique_users: int
    channels_performance: list[ChannelPerformance]
    top_campaigns: list[CampaignMetrics]
    trends: list[TrendAnalysis]
    insights: list[str]
    recommendations: list[str]


@dataclass
class AnalyticsDashboard:
    """Dashboard de analytics."""

    generated_at: datetime
    summary: dict[str, Any]
    realtime_metrics: dict[str, float]
    channel_breakdown: list[ChannelPerformance]
    recent_campaigns: list[CampaignMetrics]
    alerts: list[str]
    health_score: float


class NotificationAnalytics:
    """
    Sistema de analytics para notificações.

    Features:
    - Métricas em tempo real
    - Análise de tendências
    - Performance por canal
    - ROI de campanhas
    - Forecasting simples
    - Alertas automáticos
    """

    # Thresholds para alertas
    ALERT_THRESHOLDS = {
        "delivery_rate": 0.90,  # Alerta se < 90%
        "open_rate_drop": 0.20,  # Alerta se cair > 20%
        "unsubscribe_spike": 0.05,  # Alerta se > 5%
        "cost_spike": 1.5,  # Alerta se custo > 150% da média
    }

    def __init__(
        self,
        default_lookback_days: int = 30,
        enable_forecasting: bool = True,
    ) -> None:
        """
        Inicializa o analytics.

        Args:
            default_lookback_days: Dias padrão para análise
            enable_forecasting: Habilitar previsões
        """
        self.lookback_days = default_lookback_days
        self.enable_forecasting = enable_forecasting

    async def get_dashboard(
        self,
        db: AsyncSession,
        tenant_id: str | None = None,
    ) -> AnalyticsDashboard:
        """
        Gera dashboard de analytics.

        Args:
            db: Sessão do banco
            tenant_id: ID do tenant (opcional)

        Returns:
            AnalyticsDashboard com visão geral
        """
        now = datetime.utcnow()

        # Métricas em tempo real
        realtime = await self._get_realtime_metrics(db, tenant_id)

        # Performance por canal
        channels = await self._get_channel_performance(db, tenant_id, days=7)

        # Campanhas recentes
        campaigns = await self._get_recent_campaigns(db, tenant_id, limit=5)

        # Gerar alertas
        alerts = await self._generate_alerts(db, tenant_id, realtime, channels)

        # Calcular health score
        health = self._calculate_health_score(realtime, channels, alerts)

        # Summary
        summary = {
            "total_sent_today": realtime.get("sent_today", 0),
            "total_delivered_today": realtime.get("delivered_today", 0),
            "avg_delivery_rate": realtime.get("delivery_rate", 0),
            "avg_open_rate": realtime.get("open_rate", 0),
            "active_campaigns": len([c for c in campaigns if not c.end_date]),
        }

        return AnalyticsDashboard(
            generated_at=now,
            summary=summary,
            realtime_metrics=realtime,
            channel_breakdown=channels,
            recent_campaigns=campaigns,
            alerts=alerts,
            health_score=health,
        )

    async def generate_report(
        self,
        db: AsyncSession,
        start_date: datetime,
        end_date: datetime,
        tenant_id: str | None = None,
        granularity: TimeGranularity = TimeGranularity.DAILY,
    ) -> MetricReport:
        """
        Gera relatório detalhado.

        Args:
            db: Sessão do banco
            start_date: Data inicial
            end_date: Data final
            tenant_id: ID do tenant
            granularity: Granularidade temporal

        Returns:
            MetricReport completo
        """
        # Obter dados agregados
        totals = await self._get_period_totals(db, start_date, end_date, tenant_id)

        # Performance por canal
        channels = await self._get_channel_performance(
            db,
            tenant_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Top campanhas
        campaigns = await self._get_top_campaigns(
            db,
            tenant_id,
            start_date=start_date,
            end_date=end_date,
            limit=10,
        )

        # Análise de tendências
        trends = await self._analyze_trends(
            db,
            tenant_id,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )

        # Gerar insights
        insights = self._generate_insights(channels, campaigns, trends)

        # Gerar recomendações
        recommendations = self._generate_recommendations(channels, campaigns, trends)

        return MetricReport(
            period_start=start_date,
            period_end=end_date,
            total_notifications=totals.get("total_sent", 0),
            total_unique_users=totals.get("unique_users", 0),
            channels_performance=channels,
            top_campaigns=campaigns,
            trends=trends,
            insights=insights,
            recommendations=recommendations,
        )

    async def get_channel_analytics(
        self,
        db: AsyncSession,
        channel: str,
        days: int = 30,
        tenant_id: str | None = None,
    ) -> ChannelPerformance:
        """
        Obtém analytics de um canal específico.

        Args:
            db: Sessão do banco
            channel: Nome do canal
            days: Dias para análise
            tenant_id: ID do tenant

        Returns:
            ChannelPerformance detalhado
        """
        return await self._get_channel_metrics(db, channel, days, tenant_id)

    async def get_campaign_analytics(
        self,
        db: AsyncSession,
        campaign_id: str,
    ) -> CampaignMetrics:
        """
        Obtém analytics de uma campanha.

        Args:
            db: Sessão do banco
            campaign_id: ID da campanha

        Returns:
            CampaignMetrics detalhado
        """
        return await self._get_campaign_metrics(db, campaign_id)

    async def get_user_analytics(
        self,
        db: AsyncSession,
        user_id: int,
        days: int = 30,
    ) -> dict[str, Any]:
        """
        Obtém analytics de um usuário.

        Args:
            db: Sessão do banco
            user_id: ID do usuário
            days: Dias para análise

        Returns:
            Dict com métricas do usuário. Computado de notification_logs;
            se não houver registros, retorna zeros honestos.
        """
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE event_type IN ('sent', 'delivered')) AS total_received,
                    COUNT(*) FILTER (WHERE event_type = 'opened') AS total_opened,
                    COUNT(*) FILTER (WHERE event_type = 'clicked') AS total_clicked,
                    MAX(created_at) FILTER (WHERE event_type IN ('opened', 'clicked')) AS last_engagement,
                    MODE() WITHIN GROUP (ORDER BY channel_type) AS preferred_channel
                FROM notification_logs
                WHERE user_id = CAST(:user_id AS uuid)
                  AND created_at >= :since
                """
            ),
            {"user_id": str(user_id), "since": since},
        )
        row = result.mappings().first()

        total_received = int(row["total_received"] or 0) if row else 0
        total_opened = int(row["total_opened"] or 0) if row else 0
        total_clicked = int(row["total_clicked"] or 0) if row else 0
        open_rate = (total_opened / total_received) if total_received else 0.0
        click_rate = (total_clicked / total_opened) if total_opened else 0.0
        # Engajamento simples: média entre taxa de abertura e taxa de clique
        engagement_score = round((open_rate + click_rate) / 2, 4)

        return {
            "user_id": user_id,
            "total_received": total_received,
            "total_opened": total_opened,
            "total_clicked": total_clicked,
            "open_rate": round(open_rate, 4),
            "click_rate": round(click_rate, 4),
            "preferred_channel": (row["preferred_channel"] if row else None),
            "preferred_time": None,
            "engagement_score": engagement_score,
            "last_engagement": (row["last_engagement"] if row else None),
        }

    async def forecast_metrics(
        self,
        db: AsyncSession,
        metric: str,
        days_ahead: int = 7,
        tenant_id: str | None = None,
    ) -> list[MetricPoint]:
        """
        Prevê métricas futuras.

        Args:
            db: Sessão do banco
            metric: Nome da métrica
            days_ahead: Dias para previsão
            tenant_id: ID do tenant

        Returns:
            Lista de MetricPoint previstos
        """
        if not self.enable_forecasting:
            return []

        # Obter dados históricos
        historical = await self._get_historical_data(db, metric, days=30, tenant_id=tenant_id)

        # Calcular tendência simples (média móvel)
        forecast = self._simple_forecast(historical, days_ahead)

        return forecast

    async def _get_realtime_metrics(
        self,
        db: AsyncSession,
        tenant_id: str | None,
    ) -> dict[str, float]:
        """Obtém métricas em tempo real de notification_logs (dia corrente)."""
        start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        filters = "created_at >= :start_of_day"
        params: dict[str, Any] = {"start_of_day": start_of_day}
        if tenant_id:
            filters += " AND tenant_id = CAST(:tenant_id AS uuid)"
            params["tenant_id"] = str(tenant_id)

        result = await db.execute(
            text(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE event_type = 'sent') AS sent_today,
                    COUNT(*) FILTER (WHERE event_type = 'delivered') AS delivered_today,
                    COUNT(*) FILTER (WHERE event_type = 'opened') AS opened_today,
                    COUNT(*) FILTER (WHERE event_type = 'clicked') AS clicked_today,
                    COUNT(DISTINCT user_id) AS active_users,
                    AVG(processing_time_ms) AS avg_delivery_time_ms
                FROM notification_logs
                WHERE {filters}
                """
            ),
            params,
        )
        row = result.mappings().first()

        sent = int(row["sent_today"] or 0) if row else 0
        delivered = int(row["delivered_today"] or 0) if row else 0
        opened = int(row["opened_today"] or 0) if row else 0
        clicked = int(row["clicked_today"] or 0) if row else 0

        # Fila pendente (notification_queue)
        queue_result = await db.execute(text("SELECT COUNT(*) FROM notification_queue"))
        queue_size = int(queue_result.scalar() or 0)

        return {
            "sent_today": sent,
            "delivered_today": delivered,
            "opened_today": opened,
            "clicked_today": clicked,
            "delivery_rate": (delivered / sent) if sent else 0.0,
            "open_rate": (opened / delivered) if delivered else 0.0,
            "click_rate": (clicked / opened) if opened else 0.0,
            "active_users": int(row["active_users"] or 0) if row else 0,
            "queue_size": queue_size,
            "avg_delivery_time_ms": float(row["avg_delivery_time_ms"] or 0) if row else 0.0,
        }

    async def _get_channel_performance(
        self,
        db: AsyncSession,
        tenant_id: str | None,
        days: int = 30,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[ChannelPerformance]:
        """Obtém performance por canal."""
        channels = ["push", "email", "sms", "whatsapp", "in_app"]
        results = []

        for channel in channels:
            perf = await self._get_channel_metrics(db, channel, days, tenant_id)
            results.append(perf)

        return results

    async def _get_channel_metrics(
        self,
        db: AsyncSession,
        channel: str,
        days: int,
        tenant_id: str | None,
    ) -> ChannelPerformance:
        """Obtém métricas de um canal a partir de notification_logs.

        Se não houver registros para o canal, retorna zeros honestos.
        """
        since = datetime.utcnow() - timedelta(days=days)

        filters = "channel_type = :channel AND created_at >= :since"
        params: dict[str, Any] = {"channel": channel, "since": since}
        if tenant_id:
            filters += " AND tenant_id = CAST(:tenant_id AS uuid)"
            params["tenant_id"] = str(tenant_id)

        result = await db.execute(
            text(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE event_type = 'sent') AS sent,
                    COUNT(*) FILTER (WHERE event_type = 'delivered') AS delivered,
                    COUNT(*) FILTER (WHERE event_type = 'opened') AS opened,
                    COUNT(*) FILTER (WHERE event_type = 'clicked') AS clicked,
                    COUNT(*) FILTER (WHERE event_type = 'converted') AS converted,
                    AVG(processing_time_ms) AS avg_delivery_ms,
                    COALESCE(SUM(cost), 0) AS cost_total
                FROM notification_logs
                WHERE {filters}
                """
            ),
            params,
        )
        row = result.mappings().first()

        sent = int(row["sent"] or 0) if row else 0
        delivered = int(row["delivered"] or 0) if row else 0
        opened = int(row["opened"] or 0) if row else 0
        clicked = int(row["clicked"] or 0) if row else 0
        converted = int(row["converted"] or 0) if row else 0
        cost_total = float(row["cost_total"] or 0.0) if row else 0.0
        avg_delivery_ms = float(row["avg_delivery_ms"] or 0.0) if row else 0.0

        return ChannelPerformance(
            channel=channel,
            total_sent=sent,
            total_delivered=delivered,
            total_opened=opened,
            total_clicked=clicked,
            total_converted=converted,
            delivery_rate=(delivered / sent) if sent else 0.0,
            open_rate=(opened / delivered) if delivered else 0.0,
            click_rate=(clicked / opened) if opened else 0.0,
            conversion_rate=(converted / clicked) if clicked else 0.0,
            avg_delivery_time_seconds=avg_delivery_ms / 1000.0,
            cost_total=cost_total,
            cost_per_conversion=(cost_total / converted) if converted else 0.0,
            trend=TrendDirection.STABLE,
        )

    async def _get_recent_campaigns(
        self,
        db: AsyncSession,
        tenant_id: str | None,
        limit: int = 5,
    ) -> list[CampaignMetrics]:
        """Obtém campanhas recentes de push_campaigns.

        Se não houver campanhas, retorna lista vazia (honesto).
        """
        filters = ""
        params: dict[str, Any] = {"limit": limit}
        if tenant_id:
            filters = "WHERE tenant_id = CAST(:tenant_id AS uuid)"
            params["tenant_id"] = str(tenant_id)

        result = await db.execute(
            text(
                f"""
                SELECT
                    id, name, created_at, started_at, completed_at,
                    total_target, total_sent, total_delivered, total_opened,
                    total_clicked, total_converted,
                    delivery_rate, open_rate, click_rate, conversion_rate
                FROM push_campaigns
                {filters}
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.mappings().all()

        campaigns: list[CampaignMetrics] = []
        for row in rows:
            sent = int(row["total_sent"] or 0)
            delivered = int(row["total_delivered"] or 0)
            opened = int(row["total_opened"] or 0)
            clicked = int(row["total_clicked"] or 0)
            converted = int(row["total_converted"] or 0)
            campaigns.append(
                CampaignMetrics(
                    campaign_id=str(row["id"]),
                    name=row["name"],
                    start_date=row["started_at"] or row["created_at"],
                    end_date=row["completed_at"],
                    total_recipients=int(row["total_target"] or 0),
                    total_sent=sent,
                    total_delivered=delivered,
                    total_opened=opened,
                    total_clicked=clicked,
                    total_converted=converted,
                    total_unsubscribed=0,
                    delivery_rate=(
                        float(row["delivery_rate"])
                        if row["delivery_rate"] is not None
                        else ((delivered / sent) if sent else 0.0)
                    ),
                    open_rate=(
                        float(row["open_rate"])
                        if row["open_rate"] is not None
                        else ((opened / delivered) if delivered else 0.0)
                    ),
                    click_rate=(
                        float(row["click_rate"])
                        if row["click_rate"] is not None
                        else ((clicked / opened) if opened else 0.0)
                    ),
                    conversion_rate=(
                        float(row["conversion_rate"])
                        if row["conversion_rate"] is not None
                        else ((converted / clicked) if clicked else 0.0)
                    ),
                    unsubscribe_rate=0.0,
                    revenue_attributed=0.0,
                    roi=0.0,
                )
            )

        return campaigns

    async def _get_top_campaigns(
        self,
        db: AsyncSession,
        tenant_id: str | None,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10,
    ) -> list[CampaignMetrics]:
        """Obtém top campanhas por performance."""
        campaigns = await self._get_recent_campaigns(db, tenant_id, limit=limit)
        # Ordenar por open_rate
        return sorted(campaigns, key=lambda c: c.open_rate, reverse=True)

    async def _get_period_totals(
        self,
        db: AsyncSession,
        start_date: datetime,
        end_date: datetime,
        tenant_id: str | None,
    ) -> dict[str, int]:
        """Obtém totais do período de notification_logs (honesto: 0 se vazio)."""
        filters = "created_at >= :start_date AND created_at <= :end_date"
        params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
        if tenant_id:
            filters += " AND tenant_id = CAST(:tenant_id AS uuid)"
            params["tenant_id"] = str(tenant_id)

        result = await db.execute(
            text(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE event_type = 'sent') AS total_sent,
                    COUNT(*) FILTER (WHERE event_type = 'delivered') AS total_delivered,
                    COUNT(*) FILTER (WHERE event_type = 'opened') AS total_opened,
                    COUNT(*) FILTER (WHERE event_type = 'clicked') AS total_clicked,
                    COUNT(*) FILTER (WHERE event_type = 'converted') AS total_converted,
                    COUNT(DISTINCT user_id) AS unique_users
                FROM notification_logs
                WHERE {filters}
                """
            ),
            params,
        )
        row = result.mappings().first()
        if not row:
            return {
                "total_sent": 0,
                "total_delivered": 0,
                "total_opened": 0,
                "total_clicked": 0,
                "total_converted": 0,
                "unique_users": 0,
            }
        return {
            "total_sent": int(row["total_sent"] or 0),
            "total_delivered": int(row["total_delivered"] or 0),
            "total_opened": int(row["total_opened"] or 0),
            "total_clicked": int(row["total_clicked"] or 0),
            "total_converted": int(row["total_converted"] or 0),
            "unique_users": int(row["unique_users"] or 0),
        }

    async def _analyze_trends(
        self,
        db: AsyncSession,
        tenant_id: str | None,
        start_date: datetime,
        end_date: datetime,
        granularity: TimeGranularity,
    ) -> list[TrendAnalysis]:
        """Analisa tendências de métricas."""
        metrics = ["open_rate", "click_rate", "delivery_rate"]
        trends = []

        for metric in metrics:
            historical = await self._get_historical_data(
                db,
                metric,
                days=(end_date - start_date).days,
                tenant_id=tenant_id,
            )

            if len(historical) < 2:
                continue

            # Calcular tendência
            current = historical[-1].value
            previous = historical[0].value

            if previous > 0:
                change = (current - previous) / previous
            else:
                change = 0

            direction = TrendDirection.STABLE
            if change > 0.05:
                direction = TrendDirection.UP
            elif change < -0.05:
                direction = TrendDirection.DOWN

            # Forecast
            forecast = []
            if self.enable_forecasting:
                forecast = self._simple_forecast(historical, days_ahead=7)

            trends.append(
                TrendAnalysis(
                    metric_name=metric,
                    direction=direction,
                    change_percentage=change * 100,
                    current_value=current,
                    previous_value=previous,
                    period=f"{start_date.date()} - {end_date.date()}",
                    data_points=historical,
                    forecast=forecast,
                    confidence=0.75 if len(historical) >= 14 else 0.5,
                )
            )

        return trends

    async def _get_historical_data(
        self,
        db: AsyncSession,
        metric: str,
        days: int,
        tenant_id: str | None,
    ) -> list[MetricPoint]:
        """Obtém séries diárias de uma métrica de notification_logs.

        Calcula a taxa (open/click/delivery) por dia a partir dos eventos reais.
        Se não houver eventos, retorna série vazia (honesto — sem forecast).
        """
        if days <= 0:
            return []

        since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)

        filters = "created_at >= :since"
        params: dict[str, Any] = {"since": since}
        if tenant_id:
            filters += " AND tenant_id = CAST(:tenant_id AS uuid)"
            params["tenant_id"] = str(tenant_id)

        result = await db.execute(
            text(
                f"""
                SELECT
                    date_trunc('day', created_at) AS day,
                    COUNT(*) FILTER (WHERE event_type = 'sent') AS sent,
                    COUNT(*) FILTER (WHERE event_type = 'delivered') AS delivered,
                    COUNT(*) FILTER (WHERE event_type = 'opened') AS opened,
                    COUNT(*) FILTER (WHERE event_type = 'clicked') AS clicked
                FROM notification_logs
                WHERE {filters}
                GROUP BY 1
                ORDER BY 1
                """
            ),
            params,
        )
        rows = result.mappings().all()

        data: list[MetricPoint] = []
        for row in rows:
            sent = int(row["sent"] or 0)
            delivered = int(row["delivered"] or 0)
            opened = int(row["opened"] or 0)
            clicked = int(row["clicked"] or 0)

            if metric == "open_rate":
                value = (opened / delivered) if delivered else 0.0
                count = delivered
            elif metric == "click_rate":
                value = (clicked / opened) if opened else 0.0
                count = opened
            elif metric == "delivery_rate":
                value = (delivered / sent) if sent else 0.0
                count = sent
            else:
                value = 0.0
                count = sent

            data.append(
                MetricPoint(
                    timestamp=row["day"],
                    value=max(0.0, min(1.0, value)),
                    count=count,
                )
            )

        return data

    def _simple_forecast(
        self,
        historical: list[MetricPoint],
        days_ahead: int,
    ) -> list[MetricPoint]:
        """Faz previsão simples usando média móvel."""
        if len(historical) < 7:
            return []

        # Média dos últimos 7 dias
        recent = [p.value for p in historical[-7:]]
        avg = sum(recent) / len(recent)

        # Calcular tendência
        if len(historical) >= 14:
            older = [p.value for p in historical[-14:-7]]
            older_avg = sum(older) / len(older)
            trend = (avg - older_avg) / 7
        else:
            trend = 0

        # Gerar previsões
        forecast = []
        last_timestamp = historical[-1].timestamp

        for i in range(days_ahead):
            timestamp = last_timestamp + timedelta(days=i + 1)
            predicted_value = avg + (trend * (i + 1))
            # Limitar entre 0 e 1 para taxas
            predicted_value = max(0, min(1, predicted_value))

            forecast.append(
                MetricPoint(
                    timestamp=timestamp,
                    value=predicted_value,
                    count=0,
                )
            )

        return forecast

    async def _generate_alerts(
        self,
        db: AsyncSession,
        tenant_id: str | None,
        realtime: dict[str, float],
        channels: list[ChannelPerformance],
    ) -> list[str]:
        """Gera alertas automáticos."""
        alerts = []

        # Alerta de delivery rate baixo
        delivery_rate = realtime.get("delivery_rate", 1.0)
        if delivery_rate < self.ALERT_THRESHOLDS["delivery_rate"]:
            alerts.append(f"⚠️ Taxa de entrega baixa: {delivery_rate:.1%}")

        # Alerta por canal
        for channel in channels:
            if channel.delivery_rate < self.ALERT_THRESHOLDS["delivery_rate"]:
                alerts.append(f"⚠️ {channel.channel}: delivery rate baixo ({channel.delivery_rate:.1%})")

            if channel.trend == TrendDirection.DOWN:
                alerts.append(f"📉 {channel.channel}: tendência de queda detectada")

        # Alerta de fila
        queue_size = realtime.get("queue_size", 0)
        if queue_size > 1000:
            alerts.append(f"⚠️ Fila de notificações alta: {queue_size}")

        return alerts

    def _calculate_health_score(
        self,
        realtime: dict[str, float],
        channels: list[ChannelPerformance],
        alerts: list[str],
    ) -> float:
        """Calcula score de saúde do sistema."""
        score = 1.0

        # Penalidade por alertas
        score -= len(alerts) * 0.1

        # Penalidade por delivery rate baixo
        delivery_rate = realtime.get("delivery_rate", 1.0)
        if delivery_rate < 0.95:
            score -= 0.95 - delivery_rate

        # Penalidade por canais com problemas
        for channel in channels:
            if channel.delivery_rate < 0.90:
                score -= 0.05

        return max(0, min(1, score))

    def _generate_insights(
        self,
        channels: list[ChannelPerformance],
        campaigns: list[CampaignMetrics],
        trends: list[TrendAnalysis],
    ) -> list[str]:
        """Gera insights dos dados."""
        insights = []

        # Insight de melhor canal
        best_channel = max(channels, key=lambda c: c.open_rate)
        insights.append(f"Melhor canal por open rate: {best_channel.channel} ({best_channel.open_rate:.1%})")

        # Insight de custo-benefício
        cost_channels = [c for c in channels if c.cost_total > 0]
        if cost_channels:
            best_roi = min(cost_channels, key=lambda c: c.cost_per_conversion)
            insights.append(
                f"Melhor custo-benefício: {best_roi.channel} (R${best_roi.cost_per_conversion:.2f}/conversão)"
            )

        # Insight de tendências
        for trend in trends:
            if trend.direction == TrendDirection.UP and trend.change_percentage > 10:
                insights.append(f"📈 {trend.metric_name} crescendo {trend.change_percentage:.1f}%")
            elif trend.direction == TrendDirection.DOWN and trend.change_percentage < -10:
                insights.append(f"📉 {trend.metric_name} caindo {abs(trend.change_percentage):.1f}%")

        # Insight de campanhas
        if campaigns:
            best_campaign = max(campaigns, key=lambda c: c.conversion_rate)
            insights.append(f"Melhor campanha: {best_campaign.name} ({best_campaign.conversion_rate:.1%} conversão)")

        return insights

    def _generate_recommendations(
        self,
        channels: list[ChannelPerformance],
        campaigns: list[CampaignMetrics],
        trends: list[TrendAnalysis],
    ) -> list[str]:
        """Gera recomendações baseadas nos dados."""
        recommendations = []

        # Recomendação de canal
        underperforming = [c for c in channels if c.open_rate < 0.20]
        if underperforming:
            channels_names = ", ".join(c.channel for c in underperforming)
            recommendations.append(f"Revisar estratégia de {channels_names} - baixo engajamento")

        # Recomendação de timing
        for trend in trends:
            if trend.metric_name == "open_rate" and trend.direction == TrendDirection.DOWN:
                recommendations.append("Considerar otimização de timing de envio")

        # Recomendação de custo
        high_cost = [c for c in channels if c.cost_per_conversion > 1.0]
        if high_cost:
            recommendations.append(f"Avaliar ROI de {', '.join(c.channel for c in high_cost)}")

        # Recomendação de A/B testing
        if len(campaigns) > 0:
            avg_conversion = sum(c.conversion_rate for c in campaigns) / len(campaigns)
            if avg_conversion < 0.30:
                recommendations.append("Implementar A/B testing para melhorar conversão")

        return recommendations

    async def export_report(
        self,
        db: AsyncSession,
        report: MetricReport,
        export_format: str = "json",
    ) -> str:
        """
        Exporta relatório em formato específico.

        Args:
            db: Sessão do banco
            report: Relatório a exportar
            export_format: Formato (json, csv)

        Returns:
            String com dados exportados
        """
        if export_format == "json":
            import json

            return json.dumps(
                {
                    "period": f"{report.period_start} - {report.period_end}",
                    "total_notifications": report.total_notifications,
                    "total_users": report.total_unique_users,
                    "insights": report.insights,
                    "recommendations": report.recommendations,
                },
                default=str,
                indent=2,
            )

        elif export_format == "csv":
            lines = ["metric,value"]
            lines.append(f"total_notifications,{report.total_notifications}")
            lines.append(f"total_users,{report.total_unique_users}")
            for channel in report.channels_performance:
                lines.append(f"{channel.channel}_open_rate,{channel.open_rate}")
            return "\n".join(lines)

        return ""
