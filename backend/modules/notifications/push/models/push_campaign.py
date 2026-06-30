"""PushCampaign Model - Campanhas de Push Notifications.

Sprint 37 - Push Notifications Mobile.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class CampaignStatus(StrEnum):
    """Status da campanha."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class CampaignType(StrEnum):
    """Tipo de campanha."""

    ONE_TIME = "one_time"  # Envio unico
    SCHEDULED = "scheduled"  # Agendada
    RECURRING = "recurring"  # Recorrente
    TRIGGERED = "triggered"  # Por evento
    AB_TEST = "ab_test"  # Teste A/B
    GEOFENCE = "geofence"  # Por localizacao


class TargetType(StrEnum):
    """Tipo de segmentacao."""

    ALL = "all"  # Todos os devices
    SEGMENT = "segment"  # Por segmento
    USERS = "users"  # Lista de usuarios
    DEVICES = "devices"  # Lista de devices
    TOPIC = "topic"  # Por topico
    TAG = "tag"  # Por tag
    CONDITION = "condition"  # Condicao personalizada


class PushCampaign(Base):
    """Modelo de campanha de push notifications."""

    __tablename__ = "push_campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    name = Column(String(200), nullable=False)
    slug = Column(String(200), index=True)
    description = Column(Text)

    # Tipo e status
    campaign_type = Column(
        Enum(CampaignType, values_callable=lambda x: [e.value for e in x]), default=CampaignType.ONE_TIME, index=True
    )
    status = Column(
        Enum(CampaignStatus, values_callable=lambda x: [e.value for e in x]), default=CampaignStatus.DRAFT, index=True
    )

    # Conteudo - Padrao
    title = Column(String(100), nullable=False)
    body = Column(String(500), nullable=False)
    image_url = Column(String(500))
    icon_url = Column(String(500))

    # Conteudo - iOS especifico
    ios_title = Column(String(100))
    ios_subtitle = Column(String(100))
    ios_body = Column(String(500))
    ios_sound = Column(String(100), default="default")
    ios_badge = Column(Integer)
    ios_category = Column(String(100))  # Action category
    ios_thread_id = Column(String(100))  # Agrupamento
    ios_interruption_level = Column(String(20), default="active")  # passive, active, time-sensitive, critical
    ios_relevance_score = Column(Float)  # 0-1 para summary

    # Conteudo - Android especifico
    android_title = Column(String(100))
    android_body = Column(String(500))
    android_channel_id = Column(String(100), default="default")
    android_sound = Column(String(100), default="default")
    android_color = Column(String(10))  # Ex: "#FF5733"
    android_icon = Column(String(100))
    android_tag = Column(String(100))  # Substituicao de notificacao
    android_priority = Column(String(10), default="high")  # normal, high
    android_visibility = Column(String(20), default="private")  # public, private, secret
    android_vibration_pattern = Column(ARRAY(Integer), default=[])
    android_led_color = Column(String(10))
    android_led_on_ms = Column(Integer)
    android_led_off_ms = Column(Integer)
    android_ticker = Column(String(200))
    android_sticky = Column(Boolean, default=False)
    android_local_only = Column(Boolean, default=False)

    # Acoes
    click_action = Column(String(200))  # Deep link / URL
    action_buttons = Column(JSONB, default=[])  # [{id, title, icon, action}]
    data_payload = Column(JSONB, default={})  # Dados extras para o app

    # Targeting
    target_type = Column(Enum(TargetType, values_callable=lambda x: [e.value for e in x]), default=TargetType.ALL)
    target_segment_id = Column(UUID(as_uuid=True))
    target_users = Column(ARRAY(UUID(as_uuid=True)), default=[])
    target_devices = Column(ARRAY(UUID(as_uuid=True)), default=[])
    target_topics = Column(ARRAY(String), default=[])
    target_tags = Column(JSONB, default={})  # {"key": ["value1", "value2"]}
    target_condition = Column(Text)  # Expressao condicional
    target_platforms = Column(ARRAY(String), default=["ios", "android"])

    # Filtros adicionais
    filter_app_versions = Column(ARRAY(String), default=[])  # Versoes permitidas
    filter_languages = Column(ARRAY(String), default=[])  # Idiomas
    filter_countries = Column(ARRAY(String), default=[])  # Paises
    filter_last_active_days = Column(Integer)  # Ativos nos ultimos X dias
    filter_min_engagement_score = Column(Float)  # Score minimo

    # Agendamento
    scheduled_at = Column(DateTime, index=True)
    timezone = Column(String(50), default="America/Sao_Paulo")
    optimal_time = Column(Boolean, default=False)  # Enviar no melhor horario por usuario

    # Recorrencia (para RECURRING)
    recurrence_rule = Column(String(200))  # iCal RRULE
    recurrence_end_at = Column(DateTime)
    last_run_at = Column(DateTime)
    next_run_at = Column(DateTime)

    # Limite e throttle
    rate_limit_per_second = Column(Integer, default=1000)
    max_recipients = Column(Integer)  # Limite de destinatarios
    ttl_seconds = Column(Integer, default=86400)  # Time to live (24h default)

    # A/B Testing
    is_ab_test = Column(Boolean, default=False)
    ab_variant_name = Column(String(50))
    ab_parent_id = Column(UUID(as_uuid=True), index=True)
    ab_traffic_percentage = Column(Integer)  # % do trafego
    ab_winner_metric = Column(String(50))  # open_rate, click_rate, conversion_rate

    # Execucao
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    processing_time_ms = Column(Integer)

    # Metricas de envio
    total_targeted = Column(Integer, default=0)
    total_sent = Column(Integer, default=0)
    total_delivered = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    total_opened = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    total_dismissed = Column(Integer, default=0)
    total_converted = Column(Integer, default=0)

    # Taxas calculadas
    delivery_rate = Column(Float)
    open_rate = Column(Float)
    click_rate = Column(Float)
    conversion_rate = Column(Float)
    dismiss_rate = Column(Float)

    # Erro
    last_error = Column(Text)
    error_count = Column(Integer, default=0)

    # Categorias e tags
    category = Column(String(50), index=True)  # marketing, transactional, etc.
    tags = Column(ARRAY(String), default=[])

    # Metadata
    extra_data = Column(JSONB, default={})
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    notifications = relationship(
        "PushNotification",
        back_populates="campaign",
        foreign_keys="PushNotification.campaign_id",
    )

    def __repr__(self) -> str:
        return f"<PushCampaign {self.name} ({self.status.value})>"

    def calculate_rates(self) -> None:
        """Calcula taxas de performance."""
        if self.total_sent > 0:
            self.delivery_rate = (self.total_delivered / self.total_sent) * 100
        if self.total_delivered > 0:
            self.open_rate = (self.total_opened / self.total_delivered) * 100
            self.click_rate = (self.total_clicked / self.total_delivered) * 100
            self.dismiss_rate = (self.total_dismissed / self.total_delivered) * 100
        if self.total_opened > 0:
            self.conversion_rate = (self.total_converted / self.total_opened) * 100

    def can_send(self) -> bool:
        """Verifica se a campanha pode ser enviada."""
        if self.status not in [CampaignStatus.DRAFT, CampaignStatus.SCHEDULED]:
            return False
        if self.scheduled_at and datetime.utcnow() < self.scheduled_at:
            return False
        return True


class PushSegment(Base):
    """Modelo de segmento de usuarios para targeting."""

    __tablename__ = "push_segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    name = Column(String(200), nullable=False)
    slug = Column(String(200), index=True)
    description = Column(Text)

    # Regras de segmentacao
    rules = Column(JSONB, nullable=False, default=[])
    # Estrutura: [
    #   {"field": "platform", "operator": "eq", "value": "ios"},
    #   {"field": "app_version", "operator": "gte", "value": "2.0.0"},
    #   {"field": "last_active_at", "operator": "gte", "value": "-7d"},
    #   {"field": "tags.segment", "operator": "in", "value": ["premium", "vip"]}
    # ]
    rules_logic = Column(String(10), default="AND")  # AND, OR

    # Cache
    cached_count = Column(Integer)
    cached_at = Column(DateTime)
    cache_ttl_seconds = Column(Integer, default=3600)

    # Tipo
    is_dynamic = Column(Boolean, default=True)  # Recalcula automaticamente
    is_system = Column(Boolean, default=False)  # Segmento do sistema

    # Metadata
    extra_data = Column(JSONB, default={})
    created_by = Column(UUID(as_uuid=True))

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PushSegment {self.name}>"
