"""
Sentiment Rule Model - Sprint 46

Model para regras de classificacao e alerta de sentimento.
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


class RuleCategory(StrEnum):
    """Categorias de regras."""

    SENTIMENT = "sentiment"
    EMOTION = "emotion"
    KEYWORD = "keyword"
    ASPECT = "aspect"
    URGENCY = "urgency"
    CHURN = "churn"
    ESCALATION = "escalation"
    NOTIFICATION = "notification"
    CLASSIFICATION = "classification"
    CUSTOM = "custom"


class RuleAction(StrEnum):
    """Acoes da regra."""

    ALERT = "alert"
    ESCALATE = "escalate"
    NOTIFY_EMAIL = "notify_email"
    NOTIFY_SMS = "notify_sms"
    NOTIFY_SLACK = "notify_slack"
    CREATE_TICKET = "create_ticket"
    ASSIGN_AGENT = "assign_agent"
    TAG = "tag"
    PRIORITY_BOOST = "priority_boost"
    AUTO_RESPOND = "auto_respond"
    TRIGGER_WORKFLOW = "trigger_workflow"
    LOG = "log"


class SentimentRule(Base):
    """Model para regras de sentimento."""

    __tablename__ = "sentiment_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificacao
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Categoria
    category = Column(Enum(RuleCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    subcategory = Column(String(100))

    # Prioridade
    priority = Column(Integer, default=50)  # 1-100
    weight = Column(Float, default=1.0)

    # Condicoes
    conditions = Column(JSONB, default=[])
    # Exemplo: [
    #   {"field": "sentiment_score", "operator": "less_than", "value": -50},
    #   {"field": "has_complaint", "operator": "equals", "value": true}
    # ]

    # Condicoes de sentimento
    sentiment_threshold = Column(Float)  # Threshold de score
    sentiment_types = Column(JSONB, default=[])  # Tipos que acionam

    # Condicoes de emocao
    emotion_types = Column(JSONB, default=[])  # Emocoes que acionam
    emotion_threshold = Column(Float)

    # Palavras-chave
    keywords_include = Column(JSONB, default=[])  # Deve conter
    keywords_exclude = Column(JSONB, default=[])  # Nao deve conter
    keywords_match_all = Column(Boolean, default=False)  # AND vs OR

    # Aspectos
    aspects_include = Column(JSONB, default=[])
    aspects_sentiment = Column(String(20))  # positive, negative, neutral

    # Fontes
    source_types = Column(JSONB, default=[])  # Fontes aplicaveis
    exclude_sources = Column(JSONB, default=[])

    # Clientes
    customer_segments = Column(JSONB, default=[])  # Segmentos
    customer_tiers = Column(JSONB, default=[])  # VIP, regular, etc

    # Acoes
    primary_action = Column(Enum(RuleAction, values_callable=lambda x: [e.value for e in x]), default=RuleAction.ALERT)
    secondary_actions = Column(JSONB, default=[])
    action_config = Column(JSONB, default={})
    # Exemplo: {
    #   "notify_email": {"recipients": ["manager@company.com"]},
    #   "create_ticket": {"queue": "urgent", "priority": "high"}
    # }

    # Notificacoes
    notify_channels = Column(JSONB, default=[])
    notify_recipients = Column(JSONB, default=[])
    notify_template = Column(String(100))

    # Cooldown (evitar spam)
    cooldown_minutes = Column(Integer, default=60)
    cooldown_per_customer = Column(Boolean, default=True)
    max_triggers_per_day = Column(Integer)

    # Horarios de aplicacao
    active_hours_start = Column(Integer)  # 0-23
    active_hours_end = Column(Integer)
    active_days = Column(JSONB, default=[])  # [0-6] dom-sab

    # Estatisticas
    total_triggers = Column(Integer, default=0)
    total_actions = Column(Integer, default=0)
    true_positives = Column(Integer, default=0)
    false_positives = Column(Integer, default=0)
    last_triggered_at = Column(DateTime)

    # Status
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)
    is_test_mode = Column(Boolean, default=False)

    # Audit
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SentimentRule {self.code} - {self.name}>"

    @property
    def precision_rate(self) -> float | None:
        """Taxa de precisao da regra."""
        total = (self.true_positives or 0) + (self.false_positives or 0)
        if total == 0:
            return None
        return (self.true_positives / total) * 100

    def evaluate(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Avalia se a regra aplica a uma analise.

        Args:
            analysis: Dados da analise de sentimento

        Returns:
            Resultado da avaliacao
        """
        result = {
            "matched": False,
            "conditions_matched": 0,
            "conditions_total": 0,
            "reasons": [],
        }

        conditions_met = []

        # Verificar threshold de sentimento
        if self.sentiment_threshold is not None:
            result["conditions_total"] += 1
            score = analysis.get("sentiment_score", 0)
            if score <= self.sentiment_threshold:
                conditions_met.append("sentiment_threshold")
                result["reasons"].append(f"Score {score} <= threshold {self.sentiment_threshold}")

        # Verificar tipos de sentimento
        if self.sentiment_types:
            result["conditions_total"] += 1
            sentiment = analysis.get("sentiment_type")
            if sentiment in self.sentiment_types:
                conditions_met.append("sentiment_type")
                result["reasons"].append(f"Sentimento {sentiment} na lista")

        # Verificar emocoes
        if self.emotion_types:
            result["conditions_total"] += 1
            primary = analysis.get("primary_emotion")
            secondary = analysis.get("secondary_emotion")
            if primary in self.emotion_types or secondary in self.emotion_types:
                conditions_met.append("emotion")
                result["reasons"].append(f"Emocao detectada: {primary}")

        # Verificar keywords
        if self.keywords_include:
            result["conditions_total"] += 1
            text = analysis.get("original_text", "").lower()
            keywords_found = [kw for kw in self.keywords_include if kw.lower() in text]
            if self.keywords_match_all:
                if len(keywords_found) == len(self.keywords_include):
                    conditions_met.append("keywords")
                    result["reasons"].append(f"Todas keywords encontradas: {keywords_found}")
            else:
                if keywords_found:
                    conditions_met.append("keywords")
                    result["reasons"].append(f"Keywords: {keywords_found}")

        # Verificar exclusao de keywords
        if self.keywords_exclude:
            text = analysis.get("original_text", "").lower()
            excluded_found = [kw for kw in self.keywords_exclude if kw.lower() in text]
            if excluded_found:
                # Invalida a regra
                result["matched"] = False
                result["reasons"] = [f"Excluido por keywords: {excluded_found}"]
                return result

        # Verificar fonte
        if self.source_types:
            result["conditions_total"] += 1
            source = analysis.get("source_type")
            if source in self.source_types:
                conditions_met.append("source")

        # Verificar condicoes customizadas
        for condition in self.conditions or []:
            result["conditions_total"] += 1
            field = condition.get("field")
            operator = condition.get("operator")
            value = condition.get("value")
            actual = analysis.get(field)

            matched = self._evaluate_condition(actual, operator, value)
            if matched:
                conditions_met.append(f"custom_{field}")
                result["reasons"].append(f"{field} {operator} {value}")

        result["conditions_matched"] = len(conditions_met)

        # Regra match se todas condicoes forem satisfeitas
        # (ou pelo menos uma se nao houver condicoes obrigatorias)
        if result["conditions_total"] > 0:
            result["matched"] = result["conditions_matched"] >= 1
        else:
            result["matched"] = False

        return result

    def _evaluate_condition(
        self,
        actual: Any,
        operator: str,
        expected: Any,
    ) -> bool:
        """Avalia uma condicao individual."""
        if actual is None:
            return operator == "is_null"

        operators = {
            "equals": lambda a, e: a == e,
            "not_equals": lambda a, e: a != e,
            "greater_than": lambda a, e: float(a) > float(e),
            "less_than": lambda a, e: float(a) < float(e),
            "greater_than_or_equal": lambda a, e: float(a) >= float(e),
            "less_than_or_equal": lambda a, e: float(a) <= float(e),
            "contains": lambda a, e: str(e).lower() in str(a).lower(),
            "not_contains": lambda a, e: str(e).lower() not in str(a).lower(),
            "in_list": lambda a, e: a in e if isinstance(e, list) else False,
            "is_true": lambda a, e: bool(a) is True,
            "is_false": lambda a, e: bool(a) is False,
            "is_null": lambda a, e: a is None,
            "is_not_null": lambda a, e: a is not None,
        }

        try:
            func = operators.get(operator)
            if func:
                return func(actual, expected)
        except (ValueError, TypeError):
            pass

        return False

    def increment_trigger(self) -> None:
        """Incrementa contagem de triggers."""
        self.total_triggers = (self.total_triggers or 0) + 1
        self.last_triggered_at = datetime.utcnow()

    def record_feedback(self, is_correct: bool) -> None:
        """Registra feedback da regra."""
        if is_correct:
            self.true_positives = (self.true_positives or 0) + 1
        else:
            self.false_positives = (self.false_positives or 0) + 1

    def get_actions(self) -> list[dict[str, Any]]:
        """Retorna lista de acoes a executar."""
        actions = []

        # Acao primaria
        if self.primary_action:
            action_config = (self.action_config or {}).get(self.primary_action.value, {})
            actions.append(
                {
                    "action": self.primary_action.value,
                    "config": action_config,
                    "is_primary": True,
                }
            )

        # Acoes secundarias
        for action in self.secondary_actions or []:
            action_config = (self.action_config or {}).get(action, {})
            actions.append(
                {
                    "action": action,
                    "config": action_config,
                    "is_primary": False,
                }
            )

        return actions
