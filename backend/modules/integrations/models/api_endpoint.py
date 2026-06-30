"""
APIEndpoint Model - Endpoints de API disponíveis
Sprint 32: API Gateway / Integrações
"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.integrations.models.integration_log import IntegrationLog


class HTTPMethod(StrEnum):
    """Métodos HTTP suportados."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class EndpointCategory(StrEnum):
    """Categoria do endpoint."""

    AUTHENTICATION = "authentication"
    CLIENTS = "clients"
    SERVICES = "services"
    FINANCIAL = "financial"
    DOCUMENTS = "documents"
    REPORTS = "reports"
    ANALYTICS = "analytics"
    WEBHOOKS = "webhooks"
    SYNC = "sync"
    ADMIN = "admin"


class EndpointStatus(StrEnum):
    """Status do endpoint."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    BETA = "beta"
    MAINTENANCE = "maintenance"
    DISABLED = "disabled"


class RateLimitType(StrEnum):
    """Tipo de rate limit."""

    PER_SECOND = "per_second"
    PER_MINUTE = "per_minute"
    PER_HOUR = "per_hour"
    PER_DAY = "per_day"


class APIEndpoint(Base):
    """
    Model para endpoints de API disponíveis.
    Gerencia a documentação e controle de endpoints.
    """

    __tablename__ = "api_endpoints"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(20), nullable=False, default="v1")

    # Endpoint
    path = Column(String(500), nullable=False)
    method = Column(Enum(HTTPMethod, values_callable=lambda x: [e.value for e in x]), nullable=False)
    category = Column(
        Enum(EndpointCategory, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=EndpointCategory.SERVICES,
    )

    # Status
    status = Column(
        Enum(EndpointStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=EndpointStatus.ACTIVE,
    )
    deprecated_at = Column(DateTime, nullable=True)
    sunset_date = Column(DateTime, nullable=True)
    replacement_endpoint_id = Column(UUID(as_uuid=True), nullable=True)

    # Autenticação
    requires_auth = Column(Boolean, nullable=False, default=True)
    auth_methods = Column(JSONB, nullable=True)  # ["api_key", "oauth2", "jwt"]
    required_scopes = Column(JSONB, nullable=True)  # ["read:clients", "write:clients"]
    required_permissions = Column(JSONB, nullable=True)

    # Rate Limiting
    rate_limit_enabled = Column(Boolean, nullable=False, default=True)
    rate_limit_type = Column(
        Enum(RateLimitType, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        default=RateLimitType.PER_MINUTE,
    )
    rate_limit_value = Column(Integer, nullable=True, default=60)
    rate_limit_by_key = Column(Boolean, nullable=False, default=True)

    # Request/Response
    request_schema = Column(JSONB, nullable=True)
    response_schema = Column(JSONB, nullable=True)
    request_example = Column(JSONB, nullable=True)
    response_example = Column(JSONB, nullable=True)
    error_responses = Column(JSONB, nullable=True)

    # Validação
    request_validation_enabled = Column(Boolean, nullable=False, default=True)
    response_validation_enabled = Column(Boolean, nullable=False, default=False)
    max_request_size_bytes = Column(Integer, nullable=True, default=1048576)

    # Cache
    cache_enabled = Column(Boolean, nullable=False, default=False)
    cache_ttl_seconds = Column(Integer, nullable=True)
    cache_key_pattern = Column(String(200), nullable=True)

    # Documentação
    documentation_url = Column(String(500), nullable=True)
    tags = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # Métricas
    total_calls = Column(Integer, nullable=False, default=0)
    successful_calls = Column(Integer, nullable=False, default=0)
    failed_calls = Column(Integer, nullable=False, default=0)
    avg_response_time_ms = Column(Integer, nullable=True)
    last_called_at = Column(DateTime, nullable=True)

    # Configurações adicionais
    timeout_seconds = Column(Integer, nullable=True, default=30)
    retry_enabled = Column(Boolean, nullable=False, default=False)
    retry_count = Column(Integer, nullable=True, default=3)
    circuit_breaker_enabled = Column(Boolean, nullable=False, default=False)

    # Metadados
    extra_metadata = Column(JSONB, nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    logs: list["IntegrationLog"] = relationship(
        "IntegrationLog", back_populates="endpoint", foreign_keys="IntegrationLog.endpoint_id"
    )

    # Índices
    __table_args__ = (
        Index("ix_api_endpoints_path_method", "path", "method"),
        Index("ix_api_endpoints_category", "category"),
        Index("ix_api_endpoints_status", "status"),
        Index("ix_api_endpoints_version", "version"),
        Index("ix_api_endpoints_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<APIEndpoint {self.method.value} {self.path}>"

    def increment_calls(self, success: bool, response_time_ms: int) -> None:
        """Incrementa contadores de chamadas."""
        self.total_calls += 1
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1

        # Média móvel do tempo de resposta
        if self.avg_response_time_ms:
            self.avg_response_time_ms = int((self.avg_response_time_ms + response_time_ms) / 2)
        else:
            self.avg_response_time_ms = response_time_ms

        self.last_called_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def deprecate(self, replacement_id: str | None = None) -> None:
        """Deprecia o endpoint."""
        self.status = EndpointStatus.DEPRECATED
        self.deprecated_at = datetime.utcnow()
        if replacement_id:
            self.replacement_endpoint_id = replacement_id
        self.updated_at = datetime.utcnow()

    def activate(self) -> None:
        """Ativa o endpoint."""
        self.status = EndpointStatus.ACTIVE
        self.ativo = True
        self.updated_at = datetime.utcnow()

    def disable(self) -> None:
        """Desativa o endpoint."""
        self.status = EndpointStatus.DISABLED
        self.updated_at = datetime.utcnow()

    def set_maintenance(self) -> None:
        """Coloca em manutenção."""
        self.status = EndpointStatus.MAINTENANCE
        self.updated_at = datetime.utcnow()

    @property
    def success_rate(self) -> float:
        """Taxa de sucesso das chamadas."""
        if self.total_calls == 0:
            return 100.0
        return (self.successful_calls / self.total_calls) * 100

    @property
    def is_deprecated(self) -> bool:
        """Verifica se está depreciado."""
        return self.status == EndpointStatus.DEPRECATED

    @property
    def is_available(self) -> bool:
        """Verifica se está disponível."""
        return self.status in [EndpointStatus.ACTIVE, EndpointStatus.BETA]

    @property
    def full_path(self) -> str:
        """Retorna path completo com versão."""
        return f"/api/{self.version}{self.path}"
