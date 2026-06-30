"""NotificationLog Model - Histórico de Notificações.

Sprint 36 - Notification Hub.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class LogEventType(StrEnum):
    """Tipos de evento de log."""

    # Ciclo de vida
    CREATED = "created"
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    PROCESSING = "processing"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    # Interações
    OPENED = "opened"
    CLICKED = "clicked"
    CONVERTED = "converted"
    REPLIED = "replied"

    # Problemas
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    UNSUBSCRIBED = "unsubscribed"
    BLOCKED = "blocked"

    # Sistema
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"
    VALIDATION_ERROR = "validation_error"
    PREFERENCE_BLOCKED = "preference_blocked"


class LogLevel(StrEnum):
    """Nível do log."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationLog(Base):
    """Modelo de log/histórico de notificações."""

    __tablename__ = "notification_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Referências
    queue_id = Column(UUID(as_uuid=True), ForeignKey("notification_queue.id"), index=True)
    notification_id = Column(String(50), index=True)  # ID da notificação
    batch_id = Column(UUID(as_uuid=True), index=True)
    correlation_id = Column(String(100), index=True)

    # Canal e Template
    channel_id = Column(UUID(as_uuid=True), ForeignKey("notification_channels.id"), index=True)
    channel_type = Column(String(20), index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("notification_templates.id"), index=True)

    # Destinatário
    user_id = Column(UUID(as_uuid=True), index=True)
    recipient_address = Column(String(200))

    # Evento
    event_type = Column(Enum(LogEventType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    level = Column(Enum(LogLevel, values_callable=lambda x: [e.value for e in x]), default=LogLevel.INFO, index=True)
    message = Column(Text)
    details = Column(JSONB, default=dict)

    # Status anterior e novo
    previous_status = Column(String(30))
    new_status = Column(String(30))

    # Métricas de tempo
    processing_time_ms = Column(Integer)
    queue_wait_time_ms = Column(Integer)

    # Provider
    provider = Column(String(50))
    provider_message_id = Column(String(200))
    provider_status = Column(String(50))
    provider_response = Column(JSONB)
    provider_error_code = Column(String(50))
    provider_error_message = Column(Text)

    # Tracking (para eventos de interação)
    user_agent = Column(String(500))
    ip_address = Column(String(50))
    device_info = Column(JSONB)
    geo_location = Column(JSONB)  # {country, region, city}
    clicked_url = Column(String(1000))

    # Custo
    cost = Column(Float, default=0.0)

    # Retry info
    attempt_number = Column(Integer)
    next_retry_at = Column(DateTime)

    # Contexto
    source_entity_type = Column(String(100))
    source_entity_id = Column(UUID(as_uuid=True))
    trigger_type = Column(String(50))
    trigger_id = Column(UUID(as_uuid=True))

    # Metadados
    extra_data = Column(JSONB, default=dict)
    request_id = Column(String(100))  # Para rastreamento de requisição

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True))

    # Relacionamentos
    queue_item = relationship(
        "NotificationQueue",
        foreign_keys=[queue_id],
    )
    channel = relationship(
        "NotificationChannel",
        back_populates="logs",
        foreign_keys=[channel_id],
    )
    template = relationship(
        "NotificationTemplate",
        back_populates="logs",
        foreign_keys=[template_id],
    )

    def __repr__(self) -> str:
        return f"<NotificationLog {self.event_type.value} ({self.notification_id})>"


class NotificationMetric(Base):
    """Modelo de métricas agregadas de notificações."""

    __tablename__ = "notification_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Período
    period_type = Column(String(20), nullable=False, index=True)  # hourly, daily, weekly, monthly
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False)

    # Dimensões de agregação
    channel_type = Column(String(20), index=True)
    channel_id = Column(UUID(as_uuid=True), index=True)
    template_id = Column(UUID(as_uuid=True), index=True)
    category = Column(String(50), index=True)

    # Contadores de envio
    total_queued = Column(Integer, default=0)
    total_sent = Column(Integer, default=0)
    total_delivered = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    total_bounced = Column(Integer, default=0)
    total_cancelled = Column(Integer, default=0)
    total_expired = Column(Integer, default=0)

    # Contadores de interação
    total_opened = Column(Integer, default=0)
    unique_opens = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    unique_clicks = Column(Integer, default=0)
    total_converted = Column(Integer, default=0)
    total_replied = Column(Integer, default=0)

    # Contadores de problemas
    total_complaints = Column(Integer, default=0)
    total_unsubscribes = Column(Integer, default=0)

    # Taxas (calculadas)
    delivery_rate = Column(Float)
    open_rate = Column(Float)
    click_rate = Column(Float)
    conversion_rate = Column(Float)
    bounce_rate = Column(Float)
    complaint_rate = Column(Float)
    unsubscribe_rate = Column(Float)

    # Métricas de tempo (ms)
    avg_queue_time = Column(Float)
    avg_delivery_time = Column(Float)
    p50_delivery_time = Column(Float)
    p95_delivery_time = Column(Float)
    p99_delivery_time = Column(Float)

    # Custos
    total_cost = Column(Float, default=0.0)
    avg_cost_per_message = Column(Float)

    # Metadados
    extra_data = Column(JSONB, default=dict)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<NotificationMetric {self.period_type} {self.period_start} ({self.channel_type})>"

    def calculate_rates(self) -> None:
        """Calcula as taxas baseado nos contadores."""
        if self.total_sent > 0:
            self.delivery_rate = (self.total_delivered / self.total_sent) * 100
            self.bounce_rate = (self.total_bounced / self.total_sent) * 100
            self.complaint_rate = (self.total_complaints / self.total_sent) * 100
            self.unsubscribe_rate = (self.total_unsubscribes / self.total_sent) * 100

        if self.total_delivered > 0:
            self.open_rate = (self.unique_opens / self.total_delivered) * 100
            self.click_rate = (self.unique_clicks / self.total_delivered) * 100

        if self.total_opened > 0:
            self.conversion_rate = (self.total_converted / self.total_opened) * 100
