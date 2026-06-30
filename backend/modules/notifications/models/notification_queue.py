"""NotificationQueue Model - Fila de Notificações.

Sprint 36 - Notification Hub.
"""

import enum
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class QueueStatus(StrEnum):
    """Status do item na fila."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    PROCESSING = "processing"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"


class QueuePriority(int, enum.Enum):
    """Prioridade na fila."""

    CRITICAL = 1
    HIGH = 2
    NORMAL = 5
    LOW = 8
    BULK = 10


class NotificationQueue(Base):
    """Modelo de fila unificada de notificações."""

    __tablename__ = "notification_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificação
    notification_id = Column(String(50), nullable=False, unique=True, index=True)
    batch_id = Column(UUID(as_uuid=True), index=True)  # Agrupamento de envios
    correlation_id = Column(String(100), index=True)  # Rastreamento entre sistemas

    # Destinatário
    user_id = Column(UUID(as_uuid=True), index=True)
    recipient_type = Column(String(20), default="user")  # user, email, phone, device
    recipient_address = Column(String(200), nullable=False)  # Email, phone, device_token
    recipient_name = Column(String(200))

    # Canal e Template
    channel_id = Column(UUID(as_uuid=True), ForeignKey("notification_channels.id"), index=True)
    channel_type = Column(String(20), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("notification_templates.id"), index=True)

    # Conteúdo
    subject = Column(String(500))
    body = Column(Text)
    body_html = Column(Text)
    content_data = Column(JSONB, default=dict)  # Dados renderizados
    template_variables = Column(JSONB, default=dict)  # Variáveis do template
    attachments = Column(JSONB, default=[])

    # Status
    status = Column(
        Enum(QueueStatus, values_callable=lambda x: [e.value for e in x]), default=QueueStatus.PENDING, index=True
    )
    priority = Column(Enum(QueuePriority), default=QueuePriority.NORMAL, index=True)

    # Agendamento
    scheduled_at = Column(DateTime, index=True)
    not_after = Column(DateTime)  # Expiração
    send_window_start = Column(String(5))  # HH:MM
    send_window_end = Column(String(5))  # HH:MM

    # Processamento
    enqueued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processing_started_at = Column(DateTime)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    completed_at = Column(DateTime)
    processing_time_ms = Column(Integer)

    # Retry
    attempt = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    next_retry_at = Column(DateTime)
    retry_count = Column(Integer, default=0)
    last_error = Column(Text)
    error_code = Column(String(50))
    error_details = Column(JSONB)

    # Resposta do provedor
    provider_message_id = Column(String(200))
    provider_status = Column(String(50))
    provider_response = Column(JSONB)

    # Tracking
    opened = Column(Boolean, default=False)
    opened_at = Column(DateTime)
    opened_count = Column(Integer, default=0)
    clicked = Column(Boolean, default=False)
    clicked_at = Column(DateTime)
    clicked_count = Column(Integer, default=0)
    clicked_links = Column(JSONB, default=[])  # [{url, clicked_at}]
    converted = Column(Boolean, default=False)
    converted_at = Column(DateTime)
    conversion_value = Column(Float)
    unsubscribed = Column(Boolean, default=False)
    unsubscribed_at = Column(DateTime)
    complained = Column(Boolean, default=False)
    complained_at = Column(DateTime)

    # Bounce
    bounced = Column(Boolean, default=False)
    bounced_at = Column(DateTime)
    bounce_type = Column(String(20))  # hard, soft, complaint
    bounce_reason = Column(Text)

    # Contexto
    trigger_type = Column(String(50))  # workflow, manual, scheduled, api, event
    trigger_id = Column(UUID(as_uuid=True))
    source_entity_type = Column(String(100))  # Ex: "lead", "invoice"
    source_entity_id = Column(UUID(as_uuid=True))

    # Categoria
    category = Column(String(50), index=True)  # transactional, marketing, etc.
    tags = Column(JSONB, default=[])

    # Custo
    cost = Column(Float, default=0.0)

    # Metadados
    extra_data = Column(JSONB, default=dict)
    user_agent = Column(String(500))
    ip_address = Column(String(50))
    device_info = Column(JSONB)

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True))

    # Relacionamentos
    channel = relationship(
        "NotificationChannel",
        back_populates="queue_items",
        foreign_keys=[channel_id],
    )
    template = relationship(
        "NotificationTemplate",
        back_populates="queue_items",
        foreign_keys=[template_id],
    )

    def __repr__(self) -> str:
        return f"<NotificationQueue {self.notification_id} ({self.status.value})>"

    @property
    def is_deliverable(self) -> bool:
        """Verifica se a notificação pode ser entregue."""
        if self.status not in [QueueStatus.PENDING, QueueStatus.SCHEDULED, QueueStatus.RETRY]:
            return False

        if self.not_after and datetime.utcnow() > self.not_after:
            return False

        if self.attempt >= self.max_attempts:
            return False

        return True

    @property
    def should_retry(self) -> bool:
        """Verifica se deve tentar novamente."""
        return (
            self.status == QueueStatus.FAILED
            and self.attempt < self.max_attempts
            and not self.bounced
            and not self.unsubscribed
        )
