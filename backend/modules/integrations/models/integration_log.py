"""
IntegrationLog Model - Logs de Integração
Sprint 32: API Gateway / Integrações
"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.integrations.models.api_endpoint import APIEndpoint
    from modules.integrations.models.api_key import APIKey
    from modules.integrations.models.webhook_config import WebhookConfig


class LogType(StrEnum):
    """Tipo de log."""

    API_CALL = "api_call"
    WEBHOOK_DELIVERY = "webhook_delivery"
    SYNC_OPERATION = "sync_operation"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    ERROR = "error"
    SYSTEM = "system"


class LogLevel(StrEnum):
    """Nível do log."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogStatus(StrEnum):
    """Status da operação logada."""

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UNAUTHORIZED = "unauthorized"
    VALIDATION_ERROR = "validation_error"


class IntegrationLog(Base):
    """
    Model para logs de integração.
    Registra todas as operações de integração para auditoria.
    """

    __tablename__ = "integration_logs"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    endpoint_id = Column(UUID(as_uuid=True), ForeignKey("api_endpoints.id", ondelete="SET NULL"), nullable=True)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    webhook_id = Column(UUID(as_uuid=True), ForeignKey("webhook_configs.id", ondelete="SET NULL"), nullable=True)
    sync_queue_id = Column(UUID(as_uuid=True), nullable=True)

    # Tipo e Nível
    # values_callable: o DB guarda o .value (ex: 'webhook_delivery'), não o nome do membro.
    log_type = Column(
        Enum(LogType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=LogType.API_CALL,
    )
    level = Column(
        Enum(LogLevel, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=LogLevel.INFO,
    )
    status = Column(
        Enum(LogStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=LogStatus.SUCCESS,
    )

    # Identificação
    correlation_id = Column(String(50), nullable=True)  # Para rastrear fluxos
    trace_id = Column(String(50), nullable=True)  # Para distributed tracing
    request_id = Column(String(50), nullable=True)

    # Request
    method = Column(String(10), nullable=True)
    path = Column(String(500), nullable=True)
    query_params = Column(JSONB, nullable=True)
    request_headers = Column(JSONB, nullable=True)
    request_body = Column(Text, nullable=True)
    request_size_bytes = Column(Integer, nullable=True)

    # Response
    response_status_code = Column(Integer, nullable=True)
    response_headers = Column(JSONB, nullable=True)
    response_body = Column(Text, nullable=True)
    response_size_bytes = Column(Integer, nullable=True)

    # Performance
    duration_ms = Column(Integer, nullable=True)
    time_to_first_byte_ms = Column(Integer, nullable=True)
    dns_lookup_ms = Column(Integer, nullable=True)
    tcp_connection_ms = Column(Integer, nullable=True)
    ssl_handshake_ms = Column(Integer, nullable=True)

    # Cliente
    client_ip = Column(String(45), nullable=True)
    client_user_agent = Column(String(500), nullable=True)
    client_country = Column(String(2), nullable=True)
    client_region = Column(String(100), nullable=True)

    # Servidor
    server_host = Column(String(200), nullable=True)
    server_region = Column(String(50), nullable=True)
    server_version = Column(String(50), nullable=True)

    # Erro
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)
    stack_trace = Column(Text, nullable=True)

    # Retry
    retry_count = Column(Integer, nullable=False, default=0)
    is_retry = Column(Boolean, nullable=False, default=False)
    original_log_id = Column(UUID(as_uuid=True), nullable=True)

    # Rate Limit
    rate_limit_remaining = Column(Integer, nullable=True)
    rate_limit_reset_at = Column(DateTime, nullable=True)

    # Contexto
    user_id = Column(UUID(as_uuid=True), nullable=True)
    client_id = Column(UUID(as_uuid=True), nullable=True)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(100), nullable=True)

    # Metadados
    extra_metadata = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)

    # Timestamp
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relacionamentos
    endpoint: Optional["APIEndpoint"] = relationship("APIEndpoint", back_populates="logs")
    api_key: Optional["APIKey"] = relationship("APIKey", back_populates="logs")
    webhook: Optional["WebhookConfig"] = relationship("WebhookConfig", back_populates="logs")

    # Índices
    __table_args__ = (
        Index("ix_integration_logs_endpoint_id", "endpoint_id"),
        Index("ix_integration_logs_api_key_id", "api_key_id"),
        Index("ix_integration_logs_webhook_id", "webhook_id"),
        Index("ix_integration_logs_log_type", "log_type"),
        Index("ix_integration_logs_level", "level"),
        Index("ix_integration_logs_status", "status"),
        Index("ix_integration_logs_correlation_id", "correlation_id"),
        Index("ix_integration_logs_trace_id", "trace_id"),
        Index("ix_integration_logs_timestamp", "timestamp"),
        Index("ix_integration_logs_client_id", "client_id"),
        Index("ix_integration_logs_user_id", "user_id"),
        Index("ix_integration_logs_timestamp_status", "timestamp", "status"),
    )

    def __repr__(self) -> str:
        return f"<IntegrationLog {self.log_type.value} {self.status.value}>"

    @classmethod
    def create_api_log(
        cls,
        endpoint_id: str | None,
        api_key_id: str | None,
        method: str,
        path: str,
        status_code: int,
        duration_ms: int,
        client_ip: str,
        **kwargs,
    ) -> "IntegrationLog":
        """Cria log de chamada de API."""
        status = LogStatus.SUCCESS if status_code < 400 else LogStatus.FAILURE
        level = LogLevel.INFO if status_code < 400 else LogLevel.ERROR

        return cls(
            endpoint_id=endpoint_id,
            api_key_id=api_key_id,
            log_type=LogType.API_CALL,
            level=level,
            status=status,
            method=method,
            path=path,
            response_status_code=status_code,
            duration_ms=duration_ms,
            client_ip=client_ip,
            **kwargs,
        )

    @classmethod
    def create_webhook_log(
        cls,
        webhook_id: str,
        success: bool,
        duration_ms: int,
        status_code: int | None = None,
        error_message: str | None = None,
        **kwargs,
    ) -> "IntegrationLog":
        """Cria log de entrega de webhook."""
        status = LogStatus.SUCCESS if success else LogStatus.FAILURE
        level = LogLevel.INFO if success else LogLevel.ERROR

        return cls(
            webhook_id=webhook_id,
            log_type=LogType.WEBHOOK_DELIVERY,
            level=level,
            status=status,
            response_status_code=status_code,
            duration_ms=duration_ms,
            error_message=error_message,
            **kwargs,
        )

    @classmethod
    def create_error_log(
        cls, error_code: str, error_message: str, level: LogLevel = LogLevel.ERROR, **kwargs
    ) -> "IntegrationLog":
        """Cria log de erro."""
        return cls(
            log_type=LogType.ERROR,
            level=level,
            status=LogStatus.FAILURE,
            error_code=error_code,
            error_message=error_message,
            **kwargs,
        )

    @classmethod
    def create_auth_log(
        cls, api_key_id: str | None, success: bool, client_ip: str, reason: str | None = None, **kwargs
    ) -> "IntegrationLog":
        """Cria log de autenticação."""
        status = LogStatus.SUCCESS if success else LogStatus.UNAUTHORIZED
        level = LogLevel.INFO if success else LogLevel.WARNING

        return cls(
            api_key_id=api_key_id,
            log_type=LogType.AUTHENTICATION,
            level=level,
            status=status,
            client_ip=client_ip,
            error_message=reason if not success else None,
            **kwargs,
        )

    @classmethod
    def create_rate_limit_log(
        cls, api_key_id: str, client_ip: str, limit_remaining: int, reset_at: datetime, **kwargs
    ) -> "IntegrationLog":
        """Cria log de rate limiting."""
        return cls(
            api_key_id=api_key_id,
            log_type=LogType.RATE_LIMIT,
            level=LogLevel.WARNING,
            status=LogStatus.RATE_LIMITED,
            client_ip=client_ip,
            rate_limit_remaining=limit_remaining,
            rate_limit_reset_at=reset_at,
            **kwargs,
        )

    def mark_as_retry(self, original_id: str) -> None:
        """Marca como retry de outra operação."""
        self.is_retry = True
        self.original_log_id = original_id
        self.retry_count += 1

    @property
    def is_error(self) -> bool:
        """Verifica se é um log de erro."""
        return self.status in [LogStatus.FAILURE, LogStatus.TIMEOUT, LogStatus.VALIDATION_ERROR]

    @property
    def is_success(self) -> bool:
        """Verifica se é um log de sucesso."""
        return self.status == LogStatus.SUCCESS

    @property
    def is_client_error(self) -> bool:
        """Verifica se é erro do cliente (4xx)."""
        if not self.response_status_code:
            return False
        return 400 <= self.response_status_code < 500

    @property
    def is_server_error(self) -> bool:
        """Verifica se é erro do servidor (5xx)."""
        if not self.response_status_code:
            return False
        return self.response_status_code >= 500
