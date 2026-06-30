"""NotificationPreference Model - Preferências de Notificação.

Sprint 36 - Notification Hub.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from core.models.base import Base


class FrequencyType(StrEnum):
    """Frequência de notificações."""

    INSTANT = "instant"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    NEVER = "never"


class DigestType(StrEnum):
    """Tipo de digest."""

    NONE = "none"
    DAILY_SUMMARY = "daily_summary"
    WEEKLY_SUMMARY = "weekly_summary"
    SMART = "smart"  # IA decide


class NotificationPreference(Base):
    """Modelo de preferências de notificação do usuário."""

    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Usuário
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_email = Column(String(200))
    user_phone = Column(String(20))
    user_device_tokens = Column(JSONB, default=[])  # [{platform, token, device_id}]

    # Preferências Globais
    notifications_enabled = Column(Boolean, default=True)
    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_hours_start = Column(String(5))  # HH:MM
    quiet_hours_end = Column(String(5))  # HH:MM
    timezone = Column(String(50), default="America/Sao_Paulo")
    locale = Column(String(10), default="pt_BR")

    # Preferências por Canal
    email_enabled = Column(Boolean, default=True)
    email_address = Column(String(200))
    email_frequency = Column(
        Enum(FrequencyType, values_callable=lambda x: [e.value for e in x]), default=FrequencyType.INSTANT
    )
    email_digest = Column(Enum(DigestType, values_callable=lambda x: [e.value for e in x]), default=DigestType.NONE)

    whatsapp_enabled = Column(Boolean, default=True)
    whatsapp_number = Column(String(20))
    whatsapp_frequency = Column(
        Enum(FrequencyType, values_callable=lambda x: [e.value for e in x]), default=FrequencyType.INSTANT
    )

    sms_enabled = Column(Boolean, default=True)
    sms_number = Column(String(20))
    sms_frequency = Column(
        Enum(FrequencyType, values_callable=lambda x: [e.value for e in x]), default=FrequencyType.INSTANT
    )

    push_enabled = Column(Boolean, default=True)
    push_frequency = Column(
        Enum(FrequencyType, values_callable=lambda x: [e.value for e in x]), default=FrequencyType.INSTANT
    )
    push_sound_enabled = Column(Boolean, default=True)
    push_vibration_enabled = Column(Boolean, default=True)
    push_badge_enabled = Column(Boolean, default=True)

    in_app_enabled = Column(Boolean, default=True)
    in_app_sound_enabled = Column(Boolean, default=True)

    slack_enabled = Column(Boolean, default=False)
    slack_user_id = Column(String(50))
    slack_channel_id = Column(String(50))

    # Preferências por Categoria
    category_preferences = Column(JSONB, default=dict)
    # Estrutura: {
    #   "transactional": {"enabled": true, "channels": ["email", "push"]},
    #   "marketing": {"enabled": false, "channels": []},
    #   ...
    # }

    # Canais preferidos (ordem de prioridade)
    preferred_channels = Column(ARRAY(String), default=["email", "push", "in_app"])

    # Unsubscribes
    unsubscribed_categories = Column(ARRAY(String), default=[])
    unsubscribed_channels = Column(ARRAY(String), default=[])
    global_unsubscribe = Column(Boolean, default=False)
    unsubscribe_reason = Column(Text)
    unsubscribed_at = Column(DateTime)

    # Double Opt-in
    email_verified = Column(Boolean, default=False)
    email_verified_at = Column(DateTime)
    phone_verified = Column(Boolean, default=False)
    phone_verified_at = Column(DateTime)
    verification_token = Column(String(100))
    verification_expires_at = Column(DateTime)

    # Consent
    marketing_consent = Column(Boolean, default=False)
    marketing_consent_at = Column(DateTime)
    marketing_consent_source = Column(String(100))
    transactional_consent = Column(Boolean, default=True)
    data_processing_consent = Column(Boolean, default=True)
    data_processing_consent_at = Column(DateTime)

    # Métricas do Usuário
    total_received = Column(Integer, default=0)
    total_opened = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    last_notification_at = Column(DateTime)
    last_opened_at = Column(DateTime)
    last_clicked_at = Column(DateTime)
    engagement_score = Column(Float)  # 0-100

    # Metadados
    extra_data = Column(JSONB, default=dict)

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<NotificationPreference user={self.user_id}>"

    def is_channel_enabled(self, channel_type: str) -> bool:
        """Verifica se um canal está habilitado para o usuário."""
        if self.global_unsubscribe:
            return False

        if channel_type in self.unsubscribed_channels:
            return False

        channel_map = {
            "email": self.email_enabled,
            "whatsapp": self.whatsapp_enabled,
            "sms": self.sms_enabled,
            "push": self.push_enabled,
            "in_app": self.in_app_enabled,
            "slack": self.slack_enabled,
        }

        return channel_map.get(channel_type, False)

    def is_category_enabled(self, category: str) -> bool:
        """Verifica se uma categoria está habilitada para o usuário."""
        if self.global_unsubscribe:
            return False

        if category in self.unsubscribed_categories:
            return False

        if category in self.category_preferences:
            return self.category_preferences[category].get("enabled", True)

        return True

    def get_channels_for_category(self, category: str) -> list:
        """Retorna os canais habilitados para uma categoria."""
        if not self.is_category_enabled(category):
            return []

        if category in self.category_preferences:
            channels = self.category_preferences[category].get("channels", [])
        else:
            channels = self.preferred_channels or []

        return [ch for ch in channels if self.is_channel_enabled(ch)]


class NotificationSubscription(Base):
    """Modelo de inscrição em tópicos de notificação."""

    __tablename__ = "notification_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Usuário
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    preference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("notification_preferences.id"),
        index=True,
    )

    # Tópico
    topic = Column(String(200), nullable=False, index=True)
    topic_type = Column(String(50))  # entity_type, category, tag, custom
    entity_type = Column(String(100))  # Ex: "lead", "contract", "invoice"
    entity_id = Column(UUID(as_uuid=True))  # ID específico da entidade

    # Configuração
    channels = Column(ARRAY(String), default=[])  # Canais para este tópico
    frequency = Column(
        Enum(FrequencyType, values_callable=lambda x: [e.value for e in x]), default=FrequencyType.INSTANT
    )
    priority_only = Column(Boolean, default=False)  # Só alta prioridade

    # Status
    subscribed = Column(Boolean, default=True)
    subscribed_at = Column(DateTime, default=datetime.utcnow)
    unsubscribed_at = Column(DateTime)

    # Metadados
    extra_data = Column(JSONB, default=dict)

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<NotificationSubscription user={self.user_id} topic={self.topic}>"
