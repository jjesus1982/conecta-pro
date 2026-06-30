"""PushNotification Model - Notificacoes Push Enviadas.

Sprint 37 - Push Notifications Mobile.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class NotificationStatus(StrEnum):
    """Status da notificacao."""

    PENDING = "pending"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    DISMISSED = "dismissed"
    FAILED = "failed"
    EXPIRED = "expired"
    UNREGISTERED = "unregistered"


class NotificationPriority(StrEnum):
    """Prioridade da notificacao."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class PushNotification(Base):
    """Modelo de notificacao push individual."""

    __tablename__ = "push_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    notification_id = Column(String(100), nullable=False, unique=True, index=True)
    external_id = Column(String(200), index=True)  # ID do provedor

    # Referencias
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("push_campaigns.id"),
        index=True,
    )
    device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("push_devices.id"),
        nullable=False,
        index=True,
    )
    user_id = Column(UUID(as_uuid=True), index=True)

    # Dispositivo snapshot
    device_token = Column(Text, nullable=False)
    platform = Column(String(20), nullable=False)  # ios, android, web
    app_id = Column(String(200))

    # Conteudo
    title = Column(String(100), nullable=False)
    body = Column(String(500), nullable=False)
    subtitle = Column(String(100))
    image_url = Column(String(500))
    icon_url = Column(String(500))

    # Acoes
    click_action = Column(String(200))
    action_buttons = Column(JSONB, default=[])
    data_payload = Column(JSONB, default={})

    # Configuracoes de entrega
    priority = Column(
        Enum(NotificationPriority, values_callable=lambda x: [e.value for e in x]), default=NotificationPriority.HIGH
    )
    ttl_seconds = Column(Integer, default=86400)
    collapse_key = Column(String(100))  # Para substituicao
    mutable_content = Column(Boolean, default=False)  # iOS rich notifications
    content_available = Column(Boolean, default=False)  # Silent push

    # Status
    status = Column(
        Enum(NotificationStatus, values_callable=lambda x: [e.value for e in x]),
        default=NotificationStatus.PENDING,
        index=True,
    )
    status_history = Column(JSONB, default=[])  # [{status, timestamp, details}]

    # Timestamps de ciclo de vida
    queued_at = Column(DateTime)
    sent_at = Column(DateTime, index=True)
    delivered_at = Column(DateTime)
    opened_at = Column(DateTime)
    clicked_at = Column(DateTime)
    dismissed_at = Column(DateTime)
    expired_at = Column(DateTime)

    # Resposta do provedor
    provider = Column(String(50))  # fcm, apns, onesignal
    provider_message_id = Column(String(200))
    provider_response = Column(JSONB)
    provider_status = Column(String(50))

    # Retry
    attempt = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    next_retry_at = Column(DateTime)
    retry_reason = Column(String(200))

    # Erro
    error_code = Column(String(50))
    error_message = Column(Text)
    error_details = Column(JSONB)

    # Interacao
    opened = Column(Boolean, default=False)
    opened_count = Column(Integer, default=0)
    clicked = Column(Boolean, default=False)
    clicked_action = Column(String(100))  # Qual acao foi clicada
    clicked_url = Column(String(500))
    dismissed = Column(Boolean, default=False)
    converted = Column(Boolean, default=False)
    conversion_value = Column(Float)
    conversion_event = Column(String(100))

    # Contexto de abertura
    opened_platform = Column(String(50))  # foreground, background, killed
    opened_source = Column(String(50))  # direct, notification_center, badge
    time_to_open_seconds = Column(Integer)  # Tempo entre entrega e abertura

    # Categoria e contexto
    category = Column(String(50), index=True)
    source_type = Column(String(50))  # campaign, transactional, triggered
    source_id = Column(UUID(as_uuid=True))

    # Geofence (se aplicavel)
    triggered_by_location = Column(Boolean, default=False)
    trigger_latitude = Column(Float)
    trigger_longitude = Column(Float)

    # Metadata
    extra_data = Column(JSONB, default={})
    user_agent = Column(String(500))
    ip_address = Column(String(50))

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    campaign = relationship(
        "PushCampaign",
        back_populates="notifications",
        foreign_keys=[campaign_id],
    )
    device = relationship(
        "PushDevice",
        back_populates="notifications",
        foreign_keys=[device_id],
    )

    def __repr__(self) -> str:
        return f"<PushNotification {self.notification_id} ({self.status.value})>"

    def update_status(self, new_status: NotificationStatus, details: dict | None = None) -> None:
        """Atualiza status com historico."""
        old_status = self.status
        self.status = new_status

        # Adiciona ao historico
        history_entry = {
            "from": old_status.value if old_status else None,
            "to": new_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
        }
        if not self.status_history:
            self.status_history = []
        self.status_history.append(history_entry)

        # Atualiza timestamps
        now = datetime.utcnow()
        if new_status == NotificationStatus.QUEUED:
            self.queued_at = now
        elif new_status == NotificationStatus.SENT:
            self.sent_at = now
        elif new_status == NotificationStatus.DELIVERED:
            self.delivered_at = now
        elif new_status == NotificationStatus.OPENED:
            self.opened_at = now
            self.opened = True
            self.opened_count += 1
            if self.delivered_at:
                self.time_to_open_seconds = int((now - self.delivered_at).total_seconds())
        elif new_status == NotificationStatus.CLICKED:
            self.clicked_at = now
            self.clicked = True
        elif new_status == NotificationStatus.DISMISSED:
            self.dismissed_at = now
            self.dismissed = True
        elif new_status == NotificationStatus.EXPIRED:
            self.expired_at = now

    @property
    def is_retryable(self) -> bool:
        """Verifica se pode tentar novamente."""
        retryable_codes = [
            "Unavailable",
            "InternalServerError",
            "QuotaExceeded",
            "ServiceUnavailable",
        ]
        return (
            self.status == NotificationStatus.FAILED
            and self.attempt < self.max_attempts
            and self.error_code in retryable_codes
        )


class PushNotificationAction(Base):
    """Modelo de acao realizada na notificacao."""

    __tablename__ = "push_notification_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Referencias
    notification_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    device_id = Column(UUID(as_uuid=True), index=True)
    user_id = Column(UUID(as_uuid=True), index=True)

    # Acao
    action_type = Column(String(50), nullable=False)  # open, click, dismiss, convert
    action_id = Column(String(100))  # ID do botao clicado
    action_value = Column(String(500))  # URL, deep link, etc.

    # Contexto
    platform = Column(String(20))
    app_state = Column(String(50))  # foreground, background, killed
    source = Column(String(50))  # notification_center, banner, badge

    # Localizacao
    latitude = Column(Float)
    longitude = Column(Float)

    # Metadata
    extra_data = Column(JSONB, default={})
    user_agent = Column(String(500))
    ip_address = Column(String(50))

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<PushNotificationAction {self.action_type}>"
