"""PushDevice Model - Dispositivos registrados para Push Notifications.

Sprint 37 - Push Notifications Mobile.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class DevicePlatform(StrEnum):
    """Plataforma do dispositivo."""

    IOS = "ios"
    ANDROID = "android"
    WEB = "web"
    HUAWEI = "huawei"
    WINDOWS = "windows"
    MACOS = "macos"


class DeviceStatus(StrEnum):
    """Status do dispositivo."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    UNREGISTERED = "unregistered"
    EXPIRED = "expired"
    BLOCKED = "blocked"


class PushDevice(Base):
    """Modelo de dispositivo registrado para push notifications."""

    __tablename__ = "push_devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Usuario
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_email = Column(String(200))
    user_name = Column(String(200))

    # Identificacao do dispositivo
    device_id = Column(String(200), nullable=False, index=True)  # UUID unico do device
    device_token = Column(Text, nullable=False)  # FCM/APNs token
    device_token_hash = Column(String(64), index=True)  # Hash para busca rapida

    # Plataforma
    platform = Column(Enum(DevicePlatform, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    platform_version = Column(String(50))  # Ex: "iOS 17.2", "Android 14"

    # App
    app_id = Column(String(200), nullable=False, index=True)  # Bundle ID / Package name
    app_version = Column(String(50))
    app_build = Column(String(50))

    # Provedor
    provider = Column(String(50), default="fcm")  # fcm, apns, huawei, onesignal
    provider_player_id = Column(String(200))  # OneSignal player ID

    # Status
    status = Column(
        Enum(DeviceStatus, values_callable=lambda x: [e.value for e in x]), default=DeviceStatus.ACTIVE, index=True
    )
    status_reason = Column(String(200))
    status_changed_at = Column(DateTime)

    # Token lifecycle
    token_registered_at = Column(DateTime, default=datetime.utcnow)
    token_updated_at = Column(DateTime)
    token_expires_at = Column(DateTime)
    token_invalidated_at = Column(DateTime)

    # Device info
    device_model = Column(String(100))  # Ex: "iPhone 15 Pro", "Samsung Galaxy S24"
    device_manufacturer = Column(String(100))  # Ex: "Apple", "Samsung"
    device_name = Column(String(200))  # Nome dado pelo usuario
    screen_width = Column(Integer)
    screen_height = Column(Integer)
    device_language = Column(String(10), default="pt_BR")
    device_timezone = Column(String(50), default="America/Sao_Paulo")

    # Capabilities
    supports_rich_notifications = Column(Boolean, default=True)
    supports_actions = Column(Boolean, default=True)
    supports_images = Column(Boolean, default=True)
    supports_sound = Column(Boolean, default=True)
    supports_badge = Column(Boolean, default=True)
    supports_silent = Column(Boolean, default=True)
    supports_data_only = Column(Boolean, default=True)

    # Permissions
    notifications_enabled = Column(Boolean, default=True)
    sound_enabled = Column(Boolean, default=True)
    badge_enabled = Column(Boolean, default=True)
    alert_enabled = Column(Boolean, default=True)
    critical_alerts_enabled = Column(Boolean, default=False)
    provisional_enabled = Column(Boolean, default=False)

    # Topics/Tags
    subscribed_topics = Column(ARRAY(String), default=[])  # Ex: ["news", "alerts"]
    tags = Column(JSONB, default={})  # Ex: {"segment": "premium", "city": "SP"}

    # Engagement
    last_active_at = Column(DateTime)
    last_notification_at = Column(DateTime)
    last_opened_at = Column(DateTime)
    total_notifications_sent = Column(Integer, default=0)
    total_notifications_delivered = Column(Integer, default=0)
    total_notifications_opened = Column(Integer, default=0)
    total_notifications_clicked = Column(Integer, default=0)
    engagement_score = Column(Float)  # 0-100

    # Location (opcional)
    latitude = Column(Float)
    longitude = Column(Float)
    country = Column(String(2))  # ISO code
    city = Column(String(100))

    # Errors
    consecutive_failures = Column(Integer, default=0)
    last_error = Column(Text)
    last_error_at = Column(DateTime)
    last_error_code = Column(String(50))

    # Metadata
    extra_data = Column(JSONB, default={})
    sdk_version = Column(String(50))

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    notifications = relationship(
        "PushNotification",
        back_populates="device",
        foreign_keys="PushNotification.device_id",
    )

    def __repr__(self) -> str:
        return f"<PushDevice {self.device_id[:8]}... ({self.platform.value})>"

    def increment_failures(self) -> None:
        """Incrementa contador de falhas consecutivas."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= 5:
            self.status = DeviceStatus.INACTIVE
            self.status_reason = "Too many consecutive failures"
            self.status_changed_at = datetime.utcnow()

    def reset_failures(self) -> None:
        """Reseta contador de falhas."""
        self.consecutive_failures = 0
        if self.status == DeviceStatus.INACTIVE:
            self.status = DeviceStatus.ACTIVE
            self.status_reason = "Reactivated after successful delivery"
            self.status_changed_at = datetime.utcnow()

    def invalidate_token(self, reason: str = "Token invalidated") -> None:
        """Invalida o token do dispositivo."""
        self.status = DeviceStatus.EXPIRED
        self.status_reason = reason
        self.status_changed_at = datetime.utcnow()
        self.token_invalidated_at = datetime.utcnow()

    @property
    def is_deliverable(self) -> bool:
        """Verifica se pode receber notificacoes."""
        return bool(
            self.active and self.status == DeviceStatus.ACTIVE and self.notifications_enabled and self.device_token
        )

    @property
    def open_rate(self) -> float | None:
        """Calcula taxa de abertura."""
        if self.total_notifications_delivered > 0:
            return (self.total_notifications_opened / self.total_notifications_delivered) * 100
        return None


class PushDeviceSession(Base):
    """Modelo de sessao do dispositivo (para analytics)."""

    __tablename__ = "push_device_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    device_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), index=True)

    # Sessao
    session_id = Column(String(100), nullable=False, index=True)
    session_start = Column(DateTime, nullable=False)
    session_end = Column(DateTime)
    duration_seconds = Column(Integer)

    # Contexto
    app_version = Column(String(50))
    platform_version = Column(String(50))
    ip_address = Column(String(50))
    user_agent = Column(String(500))

    # Atividade
    screens_viewed = Column(Integer, default=0)
    actions_performed = Column(Integer, default=0)
    notifications_received = Column(Integer, default=0)
    notifications_opened = Column(Integer, default=0)

    # Metadata
    extra_data = Column(JSONB, default={})

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<PushDeviceSession {self.session_id}>"
