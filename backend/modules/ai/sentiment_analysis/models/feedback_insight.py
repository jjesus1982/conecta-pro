"""
Feedback Insight Model - Sprint 46

Model para insights e recomendacoes baseados em feedback.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class InsightType(StrEnum):
    """Tipos de insight."""

    # Sentimento
    SENTIMENT_DROP = "sentiment_drop"
    SENTIMENT_SPIKE = "sentiment_spike"
    SENTIMENT_ANOMALY = "sentiment_anomaly"

    # Topicos
    EMERGING_TOPIC = "emerging_topic"
    TRENDING_TOPIC = "trending_topic"
    RECURRING_ISSUE = "recurring_issue"

    # Clientes
    CHURN_RISK = "churn_risk"
    CUSTOMER_CHAMPION = "customer_champion"
    CUSTOMER_RECOVERY = "customer_recovery"

    # Operacional
    SERVICE_ISSUE = "service_issue"
    PRODUCT_ISSUE = "product_issue"
    PROCESS_BOTTLENECK = "process_bottleneck"

    # Oportunidades
    UPSELL_OPPORTUNITY = "upsell_opportunity"
    IMPROVEMENT_SUGGESTION = "improvement_suggestion"
    FEATURE_REQUEST = "feature_request"

    # Comparativo
    BENCHMARK_DEVIATION = "benchmark_deviation"
    COMPETITOR_MENTION = "competitor_mention"

    # Alertas
    URGENT_ATTENTION = "urgent_attention"
    COMPLIANCE_RISK = "compliance_risk"

    # Positivos
    SUCCESS_STORY = "success_story"
    TEAM_RECOGNITION = "team_recognition"


class InsightPriority(StrEnum):
    """Prioridade do insight."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class InsightStatus(StrEnum):
    """Status do insight."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class FeedbackInsight(Base):
    """Model para insights de feedback."""

    __tablename__ = "feedback_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificacao
    insight_number = Column(String(20), unique=True)
    title = Column(String(300), nullable=False)
    description = Column(Text)

    # Tipo e prioridade
    insight_type = Column(Enum(InsightType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    priority = Column(
        Enum(InsightPriority, values_callable=lambda x: [e.value for e in x]), default=InsightPriority.MEDIUM
    )
    status = Column(Enum(InsightStatus, values_callable=lambda x: [e.value for e in x]), default=InsightStatus.NEW)

    # Categoria
    category = Column(String(100))
    subcategory = Column(String(100))
    tags = Column(JSONB, default=[])

    # Escopo
    scope = Column(String(50))  # global, segment, customer, product
    scope_value = Column(String(255))

    # Entidade relacionada
    entity_type = Column(String(50))
    entity_id = Column(UUID(as_uuid=True))
    entity_name = Column(String(255))

    # Metricas do insight
    impact_score = Column(Float, default=0)  # 0-100
    confidence_score = Column(Float, default=0)  # 0-100
    urgency_score = Column(Float, default=0)  # 0-100
    actionability_score = Column(Float, default=0)  # 0-100

    # Dados de suporte
    supporting_data = Column(JSONB, default={})
    # Exemplo: {
    #   "sentiment_scores": [...],
    #   "sample_feedback": [...],
    #   "metrics": {...}
    # }

    # Analises relacionadas
    analysis_ids = Column(JSONB, default=[])
    analysis_count = Column(Integer, default=0)

    # Periodo de referencia
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    detection_window_days = Column(Integer)

    # Metricas agregadas
    avg_sentiment = Column(Float)
    sentiment_change = Column(Float)
    volume = Column(Integer)
    affected_customers = Column(Integer)

    # Topicos/Keywords
    related_keywords = Column(JSONB, default=[])
    related_topics = Column(JSONB, default=[])
    related_aspects = Column(JSONB, default=[])

    # Recomendacoes
    recommendations = Column(JSONB, default=[])
    # Exemplo: [
    #   {"action": "...", "expected_impact": "...", "effort": "..."},
    # ]

    # Acoes tomadas
    actions_taken = Column(JSONB, default=[])
    action_results = Column(Text)

    # Benchmark
    benchmark_value = Column(Float)
    deviation_from_benchmark = Column(Float)

    # Previsao
    predicted_impact = Column(Text)
    predicted_revenue_impact = Column(Float)
    predicted_churn_impact = Column(Float)

    # Validade
    valid_until = Column(DateTime)
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String(100))

    # Notificacoes
    notifications_sent = Column(Integer, default=0)
    last_notified_at = Column(DateTime)
    notify_recipients = Column(JSONB, default=[])

    # Atribuicao
    assigned_to = Column(UUID(as_uuid=True))
    assigned_at = Column(DateTime)
    assigned_team = Column(String(100))

    # Resolucao
    resolved_by = Column(UUID(as_uuid=True))
    resolved_at = Column(DateTime)
    resolution_notes = Column(Text)
    resolution_outcome = Column(String(50))

    # Feedback
    was_useful = Column(Boolean)
    usefulness_rating = Column(Integer)  # 1-5
    feedback_notes = Column(Text)

    # Geracao
    generated_by = Column(String(50))  # system, ml_model, rule, manual
    model_version = Column(String(50))
    generation_context = Column(JSONB, default={})

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.insight_number:
            self.insight_number = self._generate_number()

    def _generate_number(self) -> str:
        """Gera numero unico do insight."""
        now = datetime.utcnow()
        return f"INS{now.strftime('%Y%m%d%H%M%S')}{str(uuid4())[:4].upper()}"

    def __repr__(self) -> str:
        return f"<FeedbackInsight {self.insight_number} - {self.insight_type.value}>"

    @property
    def is_actionable(self) -> bool:
        """Verifica se insight e acionavel."""
        return (
            self.actionability_score >= 60
            and self.status in [InsightStatus.NEW, InsightStatus.ACKNOWLEDGED]
            and bool(self.recommendations)
        )

    @property
    def is_critical(self) -> bool:
        """Verifica se e critico."""
        return self.priority == InsightPriority.CRITICAL or self.urgency_score >= 80

    @property
    def is_expired(self) -> bool:
        """Verifica se expirou."""
        if self.valid_until:
            return datetime.utcnow() > self.valid_until
        return False

    @property
    def overall_score(self) -> float:
        """Calcula score geral do insight."""
        weights = {
            "impact": 0.35,
            "confidence": 0.25,
            "urgency": 0.25,
            "actionability": 0.15,
        }

        score = (
            (self.impact_score or 0) * weights["impact"]
            + (self.confidence_score or 0) * weights["confidence"]
            + (self.urgency_score or 0) * weights["urgency"]
            + (self.actionability_score or 0) * weights["actionability"]
        )

        return round(score, 2)

    @property
    def priority_label(self) -> str:
        """Retorna label da prioridade."""
        labels = {
            InsightPriority.CRITICAL: "Critico",
            InsightPriority.HIGH: "Alta",
            InsightPriority.MEDIUM: "Media",
            InsightPriority.LOW: "Baixa",
            InsightPriority.INFO: "Informativo",
        }
        return labels.get(self.priority, "Desconhecida")

    def calculate_priority(self) -> InsightPriority:
        """Calcula prioridade baseada nos scores."""
        score = self.overall_score

        if score >= 80 or self.urgency_score >= 90:
            return InsightPriority.CRITICAL
        elif score >= 60 or self.urgency_score >= 70:
            return InsightPriority.HIGH
        elif score >= 40:
            return InsightPriority.MEDIUM
        elif score >= 20:
            return InsightPriority.LOW
        else:
            return InsightPriority.INFO

    def add_recommendation(
        self,
        action: str,
        expected_impact: str,
        effort: str = "medium",
        priority: int = 1,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Adiciona recomendacao."""
        if self.recommendations is None:
            self.recommendations = []

        self.recommendations.append(
            {
                "action": action,
                "expected_impact": expected_impact,
                "effort": effort,  # low, medium, high
                "priority": priority,
                "details": details or {},
                "added_at": datetime.utcnow().isoformat(),
            }
        )

        # Ordenar por prioridade
        self.recommendations.sort(key=lambda x: x.get("priority", 99))

    def add_supporting_sample(
        self,
        text: str,
        sentiment: str,
        source: str,
        analysis_id: str | None = None,
    ) -> None:
        """Adiciona exemplo de suporte."""
        if self.supporting_data is None:
            self.supporting_data = {}

        if "sample_feedback" not in self.supporting_data:
            self.supporting_data["sample_feedback"] = []

        self.supporting_data["sample_feedback"].append(
            {
                "text": text[:500],  # Limitar tamanho
                "sentiment": sentiment,
                "source": source,
                "analysis_id": analysis_id,
            }
        )

    def acknowledge(self, user_id: UUID) -> None:
        """Marca como reconhecido."""
        self.status = InsightStatus.ACKNOWLEDGED
        self.actions_taken = self.actions_taken or []
        self.actions_taken.append(
            {
                "action": "acknowledged",
                "by": str(user_id),
                "at": datetime.utcnow().isoformat(),
            }
        )

    def assign(self, user_id: UUID, team: str | None = None) -> None:
        """Atribui insight."""
        self.assigned_to = user_id
        self.assigned_at = datetime.utcnow()
        if team:
            self.assigned_team = team
        self.status = InsightStatus.IN_PROGRESS

    def resolve(
        self,
        user_id: UUID,
        outcome: str,
        notes: str | None = None,
    ) -> None:
        """Resolve insight."""
        self.resolved_by = user_id
        self.resolved_at = datetime.utcnow()
        self.resolution_outcome = outcome
        if notes:
            self.resolution_notes = notes
        self.status = InsightStatus.IMPLEMENTED

    def dismiss(self, user_id: UUID, reason: str | None = None) -> None:
        """Descarta insight."""
        self.status = InsightStatus.DISMISSED
        self.actions_taken = self.actions_taken or []
        self.actions_taken.append(
            {
                "action": "dismissed",
                "by": str(user_id),
                "reason": reason,
                "at": datetime.utcnow().isoformat(),
            }
        )

    def add_feedback(
        self,
        was_useful: bool,
        rating: int | None = None,
        notes: str | None = None,
    ) -> None:
        """Adiciona feedback sobre o insight."""
        self.was_useful = was_useful
        if rating:
            self.usefulness_rating = min(5, max(1, rating))
        if notes:
            self.feedback_notes = notes

    def to_summary(self) -> dict[str, Any]:
        """Retorna resumo do insight."""
        return {
            "id": str(self.id),
            "number": self.insight_number,
            "type": self.insight_type.value,
            "title": self.title,
            "priority": self.priority.value,
            "priority_label": self.priority_label,
            "status": self.status.value,
            "overall_score": self.overall_score,
            "is_actionable": self.is_actionable,
            "is_critical": self.is_critical,
            "affected_customers": self.affected_customers,
            "recommendations_count": len(self.recommendations or []),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
