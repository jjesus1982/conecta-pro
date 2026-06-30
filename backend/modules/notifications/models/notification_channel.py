"""NotificationChannel Model - Canais de Notificação.

Sprint 36 - Notification Hub.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class ChannelType(StrEnum):
    """Tipos de canal de notificação."""

    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    PUSH = "push"
    SLACK = "slack"
    TEAMS = "teams"
    WEBHOOK = "webhook"
    IN_APP = "in_app"
    TELEGRAM = "telegram"
    VOICE = "voice"


class ChannelStatus(StrEnum):
    """Status do canal."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"
    ERROR = "error"


class ChannelProvider(StrEnum):
    """Provedores de canal."""

    # Email
    SMTP = "smtp"
    SENDGRID = "sendgrid"
    MAILGUN = "mailgun"
    AWS_SES = "aws_ses"
    POSTMARK = "postmark"

    # WhatsApp
    WHATSAPP_BUSINESS = "whatsapp_business"
    TWILIO_WHATSAPP = "twilio_whatsapp"
    MESSAGEBIRD_WHATSAPP = "messagebird_whatsapp"

    # SMS
    TWILIO_SMS = "twilio_sms"
    ZENVIA = "zenvia"
    MESSAGEBIRD_SMS = "messagebird_sms"
    NEXMO = "nexmo"
    AWS_SNS = "aws_sns"

    # Push
    FCM = "fcm"
    APNS = "apns"
    ONESIGNAL = "onesignal"
    PUSHER = "pusher"

    # Chat
    SLACK_API = "slack_api"
    TEAMS_API = "teams_api"
    TELEGRAM_BOT = "telegram_bot"

    # Webhook
    CUSTOM_WEBHOOK = "custom_webhook"

    # Voice
    TWILIO_VOICE = "twilio_voice"

    # In-App
    INTERNAL = "internal"


class NotificationChannel(Base):
    """Modelo de canal de notificação."""

    __tablename__ = "notification_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificação
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False)
    description = Column(Text)
    channel_type = Column(Enum(ChannelType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    provider = Column(Enum(ChannelProvider, values_callable=lambda x: [e.value for e in x]), nullable=False)
    status = Column(
        Enum(ChannelStatus, values_callable=lambda x: [e.value for e in x]), default=ChannelStatus.ACTIVE, index=True
    )

    # Configuração do provedor
    provider_config = Column(JSONB, default=dict)  # API keys, endpoints, etc.
    sender_config = Column(JSONB, default=dict)  # From address, sender ID, etc.

    # Rate Limiting
    rate_limit_per_second = Column(Integer, default=10)
    rate_limit_per_minute = Column(Integer, default=100)
    rate_limit_per_hour = Column(Integer, default=1000)
    rate_limit_per_day = Column(Integer, default=10000)
    current_rate_count = Column(Integer, default=0)
    rate_reset_at = Column(DateTime)

    # Retry Configuration
    max_retries = Column(Integer, default=3)
    retry_delay_seconds = Column(Integer, default=60)
    retry_backoff_multiplier = Column(Float, default=2.0)

    # Prioridade e Fallback
    priority = Column(Integer, default=5)  # 1-10, menor = maior prioridade
    fallback_channel_id = Column(UUID(as_uuid=True), index=True)
    is_default = Column(Boolean, default=False)

    # Horários de funcionamento
    business_hours_only = Column(Boolean, default=False)
    business_hours_start = Column(String(5))  # HH:MM
    business_hours_end = Column(String(5))  # HH:MM
    business_days = Column(ARRAY(Integer), default=[1, 2, 3, 4, 5])  # 1=Mon, 7=Sun
    timezone = Column(String(50), default="America/Sao_Paulo")

    # Métricas
    total_sent = Column(Integer, default=0)
    total_delivered = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    total_bounced = Column(Integer, default=0)
    delivery_rate = Column(Float)
    avg_delivery_time_seconds = Column(Float)
    last_sent_at = Column(DateTime)
    last_error_at = Column(DateTime)
    last_error_message = Column(Text)

    # Custos
    cost_per_message = Column(Float, default=0.0)
    monthly_budget = Column(Float)
    current_month_spend = Column(Float, default=0.0)

    # Categorias suportadas
    supported_categories = Column(ARRAY(String), default=[])  # Ex: ["transactional", "marketing"]

    # Metadados
    extra_data = Column(JSONB, default=dict)
    tags = Column(ARRAY(String), default=[])

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))

    # templates: removido — conflito com ConfigNotificationTemplate (extend_existing na mesma tabela).
    # Acesse templates via query: session.query(NotificationTemplate).filter_by(channel_id=channel.id)
    queue_items = relationship(
        "NotificationQueue",
        back_populates="channel",
        foreign_keys="NotificationQueue.channel_id",
    )
    logs = relationship(
        "NotificationLog",
        back_populates="channel",
        foreign_keys="NotificationLog.channel_id",
    )

    def __repr__(self) -> str:
        return f"<NotificationChannel {self.name} ({self.channel_type.value})>"
