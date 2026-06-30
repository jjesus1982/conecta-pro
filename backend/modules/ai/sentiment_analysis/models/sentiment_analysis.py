"""
Sentiment Analysis Model - Sprint 46

Model para armazenar analises de sentimento de textos.
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


class SentimentType(StrEnum):
    """Tipos de sentimento."""

    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"
    MIXED = "mixed"


class EmotionType(StrEnum):
    """Tipos de emocao detectada."""

    JOY = "joy"
    SATISFACTION = "satisfaction"
    GRATITUDE = "gratitude"
    TRUST = "trust"
    ANTICIPATION = "anticipation"
    SURPRISE = "surprise"
    NEUTRAL = "neutral"
    CONCERN = "concern"
    FRUSTRATION = "frustration"
    DISAPPOINTMENT = "disappointment"
    ANGER = "anger"
    FEAR = "fear"
    SADNESS = "sadness"
    DISGUST = "disgust"
    URGENCY = "urgency"


class SourceType(StrEnum):
    """Tipo de fonte do texto."""

    TICKET = "ticket"
    EMAIL = "email"
    CHAT = "chat"
    REVIEW = "review"
    SURVEY = "survey"
    SOCIAL_MEDIA = "social_media"
    CALL_TRANSCRIPT = "call_transcript"
    FEEDBACK_FORM = "feedback_form"
    COMPLAINT = "complaint"
    SUGGESTION = "suggestion"
    COMMENT = "comment"
    NPS_RESPONSE = "nps_response"
    WHATSAPP = "whatsapp"
    OTHER = "other"


class AnalysisStatus(StrEnum):
    """Status da analise."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_REVIEW = "requires_review"


class SentimentAnalysis(Base):
    """Model para analise de sentimento."""

    __tablename__ = "sentiment_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Texto analisado
    original_text = Column(Text, nullable=False)
    normalized_text = Column(Text)
    language = Column(String(10), default="pt")
    word_count = Column(Integer)
    char_count = Column(Integer)

    # Fonte
    source_type = Column(Enum(SourceType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    source_id = Column(UUID(as_uuid=True))
    source_reference = Column(String(255))

    # Entidade relacionada
    entity_type = Column(String(50))
    entity_id = Column(UUID(as_uuid=True))
    entity_name = Column(String(255))

    # Cliente/Usuario
    customer_id = Column(UUID(as_uuid=True))
    customer_name = Column(String(255))
    customer_segment = Column(String(100))

    # Resultado do sentimento
    sentiment_type = Column(
        Enum(SentimentType, values_callable=lambda x: [e.value for e in x]), default=SentimentType.NEUTRAL
    )
    sentiment_score = Column(Float, default=0)  # -100 a +100
    confidence_score = Column(Float, default=0)  # 0 a 100

    # Polaridade detalhada
    positive_score = Column(Float, default=0)  # 0 a 100
    negative_score = Column(Float, default=0)  # 0 a 100
    neutral_score = Column(Float, default=0)  # 0 a 100

    # Emocoes detectadas
    primary_emotion = Column(
        Enum(EmotionType, values_callable=lambda x: [e.value for e in x]), default=EmotionType.NEUTRAL
    )
    secondary_emotion = Column(Enum(EmotionType, values_callable=lambda x: [e.value for e in x]))
    emotion_scores = Column(JSONB, default={})  # {emotion: score}

    # Aspectos identificados
    aspects = Column(JSONB, default=[])  # [{aspect, sentiment, score}]
    topics = Column(JSONB, default=[])  # Topicos mencionados
    keywords = Column(JSONB, default=[])  # Palavras-chave

    # Entidades extraidas
    entities_mentioned = Column(JSONB, default=[])  # Pessoas, produtos, etc
    products_mentioned = Column(JSONB, default=[])
    services_mentioned = Column(JSONB, default=[])

    # Indicadores especiais
    has_urgency = Column(Boolean, default=False)
    urgency_level = Column(Integer, default=0)  # 0-10
    has_complaint = Column(Boolean, default=False)
    has_praise = Column(Boolean, default=False)
    has_question = Column(Boolean, default=False)
    has_suggestion = Column(Boolean, default=False)
    has_intent_to_leave = Column(Boolean, default=False)  # Churn indicator
    requires_action = Column(Boolean, default=False)

    # Frases importantes
    key_phrases = Column(JSONB, default=[])
    negative_phrases = Column(JSONB, default=[])
    positive_phrases = Column(JSONB, default=[])

    # NPS relacionado
    nps_score = Column(Integer)  # 0-10
    nps_category = Column(String(20))  # promoter, passive, detractor

    # Comparacao com historico
    sentiment_change = Column(Float, default=0)  # Mudanca vs anterior
    is_sentiment_improving = Column(Boolean)

    # Status e processamento
    status = Column(
        Enum(AnalysisStatus, values_callable=lambda x: [e.value for e in x]), default=AnalysisStatus.PENDING
    )
    processing_time_ms = Column(Integer)
    model_version = Column(String(50))
    error_message = Column(Text)

    # Revisao humana
    is_reviewed = Column(Boolean, default=False)
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    corrected_sentiment = Column(Enum(SentimentType, values_callable=lambda x: [e.value for e in x]))

    # Regras acionadas
    triggered_rules = Column(JSONB, default=[])
    alert_generated = Column(Boolean, default=False)
    alert_id = Column(UUID(as_uuid=True))

    # Metadados
    extra_metadata = Column(JSONB, default={})
    tags = Column(JSONB, default=[])

    # Timestamps
    analyzed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SentimentAnalysis {self.id} - {self.sentiment_type.value}>"

    @property
    def is_positive(self) -> bool:
        """Verifica se sentimento e positivo."""
        return self.sentiment_type in [
            SentimentType.POSITIVE,
            SentimentType.VERY_POSITIVE,
        ]

    @property
    def is_negative(self) -> bool:
        """Verifica se sentimento e negativo."""
        return self.sentiment_type in [
            SentimentType.NEGATIVE,
            SentimentType.VERY_NEGATIVE,
        ]

    @property
    def is_critical(self) -> bool:
        """Verifica se requer atencao critica."""
        return (
            self.sentiment_type == SentimentType.VERY_NEGATIVE
            or self.has_intent_to_leave
            or self.urgency_level >= 8
            or (self.has_complaint and self.sentiment_score < -50)
        )

    @property
    def sentiment_label(self) -> str:
        """Retorna label legivel do sentimento."""
        labels = {
            SentimentType.VERY_POSITIVE: "Muito Positivo",
            SentimentType.POSITIVE: "Positivo",
            SentimentType.NEUTRAL: "Neutro",
            SentimentType.NEGATIVE: "Negativo",
            SentimentType.VERY_NEGATIVE: "Muito Negativo",
            SentimentType.MIXED: "Misto",
        }
        return labels.get(self.sentiment_type, "Desconhecido")

    def determine_sentiment_type(self) -> SentimentType:
        """Determina tipo de sentimento baseado no score."""
        if self.sentiment_score >= 60:
            return SentimentType.VERY_POSITIVE
        elif self.sentiment_score >= 20:
            return SentimentType.POSITIVE
        elif self.sentiment_score >= -20:
            return SentimentType.NEUTRAL
        elif self.sentiment_score >= -60:
            return SentimentType.NEGATIVE
        else:
            return SentimentType.VERY_NEGATIVE

    def add_aspect(
        self,
        aspect: str,
        sentiment: str,
        score: float,
        mentions: int = 1,
    ) -> None:
        """Adiciona aspecto identificado."""
        if self.aspects is None:
            self.aspects = []

        self.aspects.append(
            {
                "aspect": aspect,
                "sentiment": sentiment,
                "score": score,
                "mentions": mentions,
                "detected_at": datetime.utcnow().isoformat(),
            }
        )

    def add_keyword(self, keyword: str, frequency: int = 1) -> None:
        """Adiciona palavra-chave."""
        if self.keywords is None:
            self.keywords = []

        existing = next((k for k in self.keywords if k.get("word") == keyword), None)
        if existing:
            existing["frequency"] = existing.get("frequency", 0) + frequency
        else:
            self.keywords.append(
                {
                    "word": keyword,
                    "frequency": frequency,
                }
            )

    def set_emotion_score(self, emotion: EmotionType, score: float) -> None:
        """Define score de emocao."""
        if self.emotion_scores is None:
            self.emotion_scores = {}
        self.emotion_scores[emotion.value] = score

    def mark_reviewed(
        self,
        reviewer_id: UUID,
        corrected_sentiment: SentimentType | None = None,
        notes: str | None = None,
    ) -> None:
        """Marca como revisado."""
        self.is_reviewed = True
        self.reviewed_by = reviewer_id
        self.reviewed_at = datetime.utcnow()
        if corrected_sentiment:
            self.corrected_sentiment = corrected_sentiment
        if notes:
            self.review_notes = notes

    def calculate_action_priority(self) -> int:
        """Calcula prioridade de acao (1-10)."""
        priority = 5  # Base

        if self.sentiment_type == SentimentType.VERY_NEGATIVE:
            priority += 3
        elif self.sentiment_type == SentimentType.NEGATIVE:
            priority += 2

        if self.has_intent_to_leave:
            priority += 2

        if self.has_urgency:
            priority += self.urgency_level // 3

        if self.has_complaint:
            priority += 1

        if self.nps_category == "detractor":
            priority += 1

        return min(10, max(1, priority))

    def to_summary(self) -> dict[str, Any]:
        """Retorna resumo da analise."""
        return {
            "id": str(self.id),
            "sentiment": self.sentiment_type.value,
            "sentiment_label": self.sentiment_label,
            "score": self.sentiment_score,
            "confidence": self.confidence_score,
            "primary_emotion": self.primary_emotion.value if self.primary_emotion else None,
            "is_critical": self.is_critical,
            "requires_action": self.requires_action,
            "key_aspects": self.aspects[:3] if self.aspects else [],
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
        }
