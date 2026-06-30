"""
WebhookConfig Model - Configuração de Webhooks
Sprint 32: API Gateway / Integrações
"""

import hashlib
import hmac
import secrets
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.integrations.models.integration_log import IntegrationLog


class WebhookEvent(StrEnum):
    """Eventos que podem disparar webhooks."""

    # Clientes
    CLIENT_CREATED = "client.created"
    CLIENT_UPDATED = "client.updated"
    CLIENT_DELETED = "client.deleted"

    # Serviços
    SERVICE_ORDER_CREATED = "service_order.created"
    SERVICE_ORDER_UPDATED = "service_order.updated"
    SERVICE_ORDER_COMPLETED = "service_order.completed"
    SERVICE_ORDER_CANCELLED = "service_order.cancelled"

    # Financeiro
    INVOICE_CREATED = "invoice.created"
    INVOICE_PAID = "invoice.paid"
    INVOICE_OVERDUE = "invoice.overdue"
    PAYMENT_RECEIVED = "payment.received"
    PAYMENT_FAILED = "payment.failed"

    # Documentos
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_SIGNED = "document.signed"
    DOCUMENT_REJECTED = "document.rejected"

    # Sistema
    SYSTEM_ALERT = "system.alert"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"


class WebhookStatus(StrEnum):
    """Status do webhook."""

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    FAILING = "failing"


class WebhookFormat(StrEnum):
    """Formato do payload."""

    JSON = "json"
    XML = "xml"
    FORM = "form"


class WebhookAuthType(StrEnum):
    """Tipo de autenticação."""

    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"
    API_KEY = "api_key"
    HMAC = "hmac"
    OAUTH2 = "oauth2"


class WebhookConfig(Base):
    """
    Model para configuração de webhooks.
    Gerencia integrações via webhooks com sistemas externos.
    """

    __tablename__ = "webhook_configs"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    client_id = Column(UUID(as_uuid=True), nullable=True)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=True)

    # Identificação
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # URL de destino
    url = Column(String(1000), nullable=False)
    method = Column(String(10), nullable=False, default="POST")

    # Eventos
    events = Column(JSONB, nullable=False)  # Lista de WebhookEvent
    event_filters = Column(JSONB, nullable=True)  # Filtros adicionais

    # Status
    status = Column(
        Enum(WebhookStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=WebhookStatus.ACTIVE,
    )

    # Formato
    content_type = Column(String(100), nullable=False, default="application/json")
    payload_format = Column(
        Enum(WebhookFormat, values_callable=lambda x: [e.value for e in x]), nullable=False, default=WebhookFormat.JSON
    )
    payload_template = Column(Text, nullable=True)  # Template customizado

    # Autenticação
    auth_type = Column(
        Enum(WebhookAuthType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=WebhookAuthType.HMAC,
    )
    auth_credentials = Column(JSONB, nullable=True)  # Credenciais criptografadas

    # Segurança
    secret_key = Column(String(64), nullable=True)  # Para assinatura HMAC
    verify_ssl = Column(Boolean, nullable=False, default=True)
    allowed_ips = Column(JSONB, nullable=True)  # IPs que podem receber

    # Headers customizados
    custom_headers = Column(JSONB, nullable=True)

    # Retry
    retry_enabled = Column(Boolean, nullable=False, default=True)
    max_retries = Column(Integer, nullable=False, default=3)
    retry_delay_seconds = Column(Integer, nullable=False, default=60)
    retry_backoff_multiplier = Column(Integer, nullable=False, default=2)

    # Timeout
    timeout_seconds = Column(Integer, nullable=False, default=30)
    connect_timeout_seconds = Column(Integer, nullable=False, default=10)

    # Batching
    batch_enabled = Column(Boolean, nullable=False, default=False)
    batch_size = Column(Integer, nullable=True, default=10)
    batch_interval_seconds = Column(Integer, nullable=True, default=60)

    # Métricas
    total_deliveries = Column(Integer, nullable=False, default=0)
    successful_deliveries = Column(Integer, nullable=False, default=0)
    failed_deliveries = Column(Integer, nullable=False, default=0)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    avg_response_time_ms = Column(Integer, nullable=True)
    last_delivery_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_failure_at = Column(DateTime, nullable=True)
    last_failure_reason = Column(Text, nullable=True)

    # Configurações
    disabled_until = Column(DateTime, nullable=True)  # Auto-disable temporário
    auto_disable_on_failures = Column(Integer, nullable=True, default=10)

    # Metadados
    extra_metadata = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    logs: list["IntegrationLog"] = relationship(
        "IntegrationLog", back_populates="webhook", foreign_keys="IntegrationLog.webhook_id"
    )

    # Índices
    __table_args__ = (
        Index("ix_webhook_configs_client_id", "client_id"),
        Index("ix_webhook_configs_api_key_id", "api_key_id"),
        Index("ix_webhook_configs_status", "status"),
        Index("ix_webhook_configs_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<WebhookConfig {self.name}>"

    @staticmethod
    def generate_secret() -> str:
        """Gera um secret key para HMAC."""
        return secrets.token_hex(32)

    def sign_payload(self, payload: str) -> str:
        """Assina o payload com HMAC-SHA256."""
        if not self.secret_key:
            return ""
        signature = hmac.new(self.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"sha256={signature}"

    def verify_signature(self, payload: str, signature: str) -> bool:
        """Verifica assinatura do payload."""
        expected = self.sign_payload(payload)
        return hmac.compare_digest(expected, signature)

    def record_delivery(self, success: bool, response_time_ms: int, error: str | None = None) -> None:
        """Registra entrega de webhook."""
        self.total_deliveries += 1
        self.last_delivery_at = datetime.utcnow()

        if success:
            self.successful_deliveries += 1
            self.last_success_at = datetime.utcnow()
            self.consecutive_failures = 0
        else:
            self.failed_deliveries += 1
            self.last_failure_at = datetime.utcnow()
            self.last_failure_reason = error
            self.consecutive_failures += 1

            # Auto-disable após muitas falhas
            if self.auto_disable_on_failures:
                if self.consecutive_failures >= self.auto_disable_on_failures:
                    self.status = WebhookStatus.FAILING

        # Média móvel do tempo de resposta
        if self.avg_response_time_ms:
            self.avg_response_time_ms = int((self.avg_response_time_ms + response_time_ms) / 2)
        else:
            self.avg_response_time_ms = response_time_ms

        self.updated_at = datetime.utcnow()

    def is_subscribed_to(self, event: str) -> bool:
        """Verifica se está inscrito no evento."""
        if not self.events:
            return False
        return event in self.events

    def activate(self) -> None:
        """Ativa o webhook."""
        self.status = WebhookStatus.ACTIVE
        self.ativo = True
        self.consecutive_failures = 0
        self.disabled_until = None
        self.updated_at = datetime.utcnow()

    def pause(self) -> None:
        """Pausa o webhook."""
        self.status = WebhookStatus.PAUSED
        self.updated_at = datetime.utcnow()

    def disable(self) -> None:
        """Desativa o webhook."""
        self.status = WebhookStatus.DISABLED
        self.ativo = False
        self.updated_at = datetime.utcnow()

    def reset_failures(self) -> None:
        """Reseta contadores de falha."""
        self.consecutive_failures = 0
        self.last_failure_reason = None
        if self.status == WebhookStatus.FAILING:
            self.status = WebhookStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    @property
    def is_available(self) -> bool:
        """Verifica se webhook está disponível."""
        if not self.ativo:
            return False
        if self.status not in [WebhookStatus.ACTIVE]:
            return False
        if self.disabled_until and datetime.utcnow() < self.disabled_until:
            return False
        return True

    @property
    def delivery_rate(self) -> float:
        """Taxa de entrega bem-sucedida."""
        if self.total_deliveries == 0:
            return 100.0
        return (self.successful_deliveries / self.total_deliveries) * 100

    @property
    def health_status(self) -> str:
        """Status de saúde do webhook."""
        if not self.is_available:
            return "offline"
        if self.consecutive_failures > 5:
            return "critical"
        if self.consecutive_failures > 2:
            return "warning"
        if self.delivery_rate < 90:
            return "degraded"
        return "healthy"
