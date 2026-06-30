"""
Sentiment Trend Model - Sprint 46

Model para rastrear tendencias de sentimento ao longo do tempo.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class TrendPeriod(StrEnum):
    """Periodo de agregacao da tendencia."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class TrendDirection(StrEnum):
    """Direcao da tendencia."""

    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    VOLATILE = "volatile"


class TrendCategory(StrEnum):
    """Categoria da tendencia."""

    OVERALL = "overall"
    BY_SOURCE = "by_source"
    BY_CUSTOMER = "by_customer"
    BY_SEGMENT = "by_segment"
    BY_PRODUCT = "by_product"
    BY_SERVICE = "by_service"
    BY_TOPIC = "by_topic"
    BY_ASPECT = "by_aspect"


class SentimentTrend(Base):
    """Model para tendencias de sentimento."""

    __tablename__ = "sentiment_trends"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Periodo
    period_type = Column(Enum(TrendPeriod, values_callable=lambda x: [e.value for e in x]), nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_label = Column(String(50))  # "2025-W01", "2025-01", etc

    # Categoria
    category = Column(
        Enum(TrendCategory, values_callable=lambda x: [e.value for e in x]), default=TrendCategory.OVERALL
    )
    category_value = Column(String(255))  # Valor especifico (ex: "email", "vip")

    # Entidade (opcional)
    entity_type = Column(String(50))
    entity_id = Column(UUID(as_uuid=True))
    entity_name = Column(String(255))

    # Metricas de sentimento
    avg_sentiment_score = Column(Float, default=0)
    min_sentiment_score = Column(Float)
    max_sentiment_score = Column(Float)
    std_sentiment_score = Column(Float)  # Desvio padrao

    # Distribuicao
    very_positive_count = Column(Integer, default=0)
    positive_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)
    negative_count = Column(Integer, default=0)
    very_negative_count = Column(Integer, default=0)
    mixed_count = Column(Integer, default=0)

    # Percentuais
    very_positive_pct = Column(Float, default=0)
    positive_pct = Column(Float, default=0)
    neutral_pct = Column(Float, default=0)
    negative_pct = Column(Float, default=0)
    very_negative_pct = Column(Float, default=0)

    # Total
    total_analyses = Column(Integer, default=0)
    total_with_action = Column(Integer, default=0)

    # Emocoes agregadas
    emotion_distribution = Column(JSONB, default={})  # {emotion: count}
    primary_emotion = Column(String(50))

    # Aspectos agregados
    aspect_sentiments = Column(JSONB, default={})  # {aspect: avg_score}
    top_positive_aspects = Column(JSONB, default=[])
    top_negative_aspects = Column(JSONB, default=[])

    # Keywords
    top_keywords = Column(JSONB, default=[])  # [{word, count}]
    trending_keywords = Column(JSONB, default=[])  # Novos ou crescentes

    # Topicos
    top_topics = Column(JSONB, default=[])

    # NPS (se aplicavel)
    nps_score = Column(Float)
    promoters_count = Column(Integer, default=0)
    passives_count = Column(Integer, default=0)
    detractors_count = Column(Integer, default=0)

    # Indicadores especiais
    complaints_count = Column(Integer, default=0)
    complaints_rate = Column(Float, default=0)
    urgency_count = Column(Integer, default=0)
    churn_risk_count = Column(Integer, default=0)

    # Comparacao com periodo anterior
    prev_avg_score = Column(Float)
    score_change = Column(Float, default=0)
    score_change_pct = Column(Float, default=0)
    volume_change = Column(Integer, default=0)
    volume_change_pct = Column(Float, default=0)

    # Tendencia
    trend_direction = Column(
        Enum(TrendDirection, values_callable=lambda x: [e.value for e in x]), default=TrendDirection.STABLE
    )
    trend_strength = Column(Float, default=0)  # 0-100
    trend_confidence = Column(Float, default=0)  # 0-100

    # Previsao
    predicted_next_score = Column(Float)
    prediction_confidence = Column(Float)

    # Alertas gerados
    alerts_generated = Column(Integer, default=0)
    alert_ids = Column(JSONB, default=[])

    # Insights
    insights = Column(JSONB, default=[])  # Insights automaticos

    # Timestamps
    calculated_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SentimentTrend {self.period_label} - {self.category.value}>"

    @property
    def satisfaction_rate(self) -> float:
        """Taxa de satisfacao (positivos / total)."""
        if self.total_analyses == 0:
            return 0
        positive = (self.very_positive_count or 0) + (self.positive_count or 0)
        return (positive / self.total_analyses) * 100

    @property
    def dissatisfaction_rate(self) -> float:
        """Taxa de insatisfacao (negativos / total)."""
        if self.total_analyses == 0:
            return 0
        negative = (self.very_negative_count or 0) + (self.negative_count or 0)
        return (negative / self.total_analyses) * 100

    @property
    def is_improving(self) -> bool:
        """Verifica se sentimento esta melhorando."""
        return self.trend_direction == TrendDirection.IMPROVING

    @property
    def is_declining(self) -> bool:
        """Verifica se sentimento esta piorando."""
        return self.trend_direction == TrendDirection.DECLINING

    @property
    def needs_attention(self) -> bool:
        """Verifica se precisa de atencao."""
        return (
            self.trend_direction == TrendDirection.DECLINING
            or self.dissatisfaction_rate > 30
            or self.complaints_rate > 10
            or self.churn_risk_count > 5
        )

    def calculate_percentages(self) -> None:
        """Calcula percentuais de distribuicao."""
        total = self.total_analyses or 1

        self.very_positive_pct = ((self.very_positive_count or 0) / total) * 100
        self.positive_pct = ((self.positive_count or 0) / total) * 100
        self.neutral_pct = ((self.neutral_count or 0) / total) * 100
        self.negative_pct = ((self.negative_count or 0) / total) * 100
        self.very_negative_pct = ((self.very_negative_count or 0) / total) * 100

    def calculate_trend(
        self,
        previous_score: float | None = None,
        previous_volume: int | None = None,
    ) -> None:
        """Calcula tendencia baseada em periodo anterior."""
        if previous_score is not None:
            self.prev_avg_score = previous_score
            self.score_change = self.avg_sentiment_score - previous_score

            if previous_score != 0:
                self.score_change_pct = (self.score_change / abs(previous_score)) * 100

            # Determinar direcao
            if self.score_change > 5:
                self.trend_direction = TrendDirection.IMPROVING
                self.trend_strength = min(100, abs(self.score_change) * 2)
            elif self.score_change < -5:
                self.trend_direction = TrendDirection.DECLINING
                self.trend_strength = min(100, abs(self.score_change) * 2)
            else:
                self.trend_direction = TrendDirection.STABLE
                self.trend_strength = 0

        if previous_volume is not None:
            self.volume_change = (self.total_analyses or 0) - previous_volume
            if previous_volume > 0:
                self.volume_change_pct = (self.volume_change / previous_volume) * 100

    def add_insight(
        self,
        insight_type: str,
        message: str,
        importance: str = "medium",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Adiciona insight automatico."""
        if self.insights is None:
            self.insights = []

        self.insights.append(
            {
                "type": insight_type,
                "message": message,
                "importance": importance,
                "data": data or {},
                "generated_at": datetime.utcnow().isoformat(),
            }
        )

    def generate_automatic_insights(self) -> None:
        """Gera insights automaticos baseados nos dados."""
        insights_to_add = []

        # Insight de tendencia
        if self.is_declining and self.score_change_pct < -10:
            insights_to_add.append(
                {
                    "type": "trend_alert",
                    "message": f"Sentimento em queda de {abs(self.score_change_pct):.1f}% no periodo",
                    "importance": "high",
                }
            )

        # Insight de satisfacao
        if self.satisfaction_rate > 80:
            insights_to_add.append(
                {
                    "type": "satisfaction",
                    "message": f"Alta taxa de satisfacao: {self.satisfaction_rate:.1f}%",
                    "importance": "low",
                }
            )
        elif self.dissatisfaction_rate > 30:
            insights_to_add.append(
                {
                    "type": "dissatisfaction_alert",
                    "message": f"Taxa de insatisfacao elevada: {self.dissatisfaction_rate:.1f}%",
                    "importance": "high",
                }
            )

        # Insight de reclamacoes
        if self.complaints_rate > 10:
            insights_to_add.append(
                {
                    "type": "complaints_alert",
                    "message": f"Taxa de reclamacoes acima do normal: {self.complaints_rate:.1f}%",
                    "importance": "high",
                }
            )

        # Insight de volume
        if self.volume_change_pct > 50:
            insights_to_add.append(
                {
                    "type": "volume_spike",
                    "message": f"Aumento de {self.volume_change_pct:.1f}% no volume de feedback",
                    "importance": "medium",
                }
            )

        # Insight de NPS
        if self.nps_score is not None:
            if self.nps_score >= 50:
                insights_to_add.append(
                    {
                        "type": "nps_excellent",
                        "message": f"NPS excelente: {self.nps_score:.0f}",
                        "importance": "low",
                    }
                )
            elif self.nps_score < 0:
                insights_to_add.append(
                    {
                        "type": "nps_critical",
                        "message": f"NPS critico: {self.nps_score:.0f} (negativo)",
                        "importance": "high",
                    }
                )

        # Insight de risco de churn
        if self.churn_risk_count > 0:
            insights_to_add.append(
                {
                    "type": "churn_risk",
                    "message": f"{self.churn_risk_count} clientes com risco de churn identificados",
                    "importance": "high",
                }
            )

        for insight in insights_to_add:
            self.add_insight(**insight)

    def to_summary(self) -> dict[str, Any]:
        """Retorna resumo da tendencia."""
        return {
            "period": self.period_label,
            "period_type": self.period_type.value,
            "category": self.category.value,
            "avg_score": round(self.avg_sentiment_score, 2),
            "total_analyses": self.total_analyses,
            "satisfaction_rate": round(self.satisfaction_rate, 1),
            "dissatisfaction_rate": round(self.dissatisfaction_rate, 1),
            "trend": self.trend_direction.value,
            "score_change": round(self.score_change, 2),
            "nps_score": round(self.nps_score, 1) if self.nps_score else None,
            "needs_attention": self.needs_attention,
        }
