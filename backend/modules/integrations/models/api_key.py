"""
APIKey Model - Chaves de API para autenticação
Sprint 32: API Gateway / Integrações
"""

import hashlib
import secrets
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


class APIKeyType(StrEnum):
    """Tipo de chave de API."""

    PRODUCTION = "production"
    SANDBOX = "sandbox"
    DEVELOPMENT = "development"
    TESTING = "testing"


class APIKeyStatus(StrEnum):
    """Status da chave de API."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    REVOKED = "revoked"


class APIKeyScope(StrEnum):
    """Escopos de permissão."""

    READ_ALL = "read:all"
    WRITE_ALL = "write:all"
    READ_CLIENTS = "read:clients"
    WRITE_CLIENTS = "write:clients"
    READ_SERVICES = "read:services"
    WRITE_SERVICES = "write:services"
    READ_FINANCIAL = "read:financial"
    WRITE_FINANCIAL = "write:financial"
    READ_DOCUMENTS = "read:documents"
    WRITE_DOCUMENTS = "write:documents"
    READ_REPORTS = "read:reports"
    WEBHOOKS_MANAGE = "webhooks:manage"
    ADMIN = "admin"


class APIKey(Base):
    """
    Model para chaves de API.
    Gerencia autenticação e autorização de integrações.
    """

    __tablename__ = "api_keys"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    client_id = Column(UUID(as_uuid=True), nullable=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)

    # Identificação
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Chave
    key_prefix = Column(String(10), nullable=False)  # Primeiros caracteres para identificação
    key_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 da chave
    key_hint = Column(String(10), nullable=True)  # Últimos caracteres para referência

    # Tipo e Status
    key_type = Column(
        Enum(APIKeyType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=APIKeyType.PRODUCTION
    )
    status = Column(
        Enum(APIKeyStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=APIKeyStatus.ACTIVE
    )

    # Permissões
    scopes = Column(JSONB, nullable=True)  # Lista de escopos
    allowed_endpoints = Column(JSONB, nullable=True)  # Endpoints específicos permitidos
    blocked_endpoints = Column(JSONB, nullable=True)  # Endpoints bloqueados

    # Rate Limiting
    rate_limit_per_minute = Column(Integer, nullable=True, default=60)
    rate_limit_per_hour = Column(Integer, nullable=True, default=1000)
    rate_limit_per_day = Column(Integer, nullable=True, default=10000)
    current_minute_calls = Column(Integer, nullable=False, default=0)
    current_hour_calls = Column(Integer, nullable=False, default=0)
    current_day_calls = Column(Integer, nullable=False, default=0)
    last_rate_reset = Column(DateTime, nullable=True)

    # Restrições de IP
    ip_whitelist = Column(JSONB, nullable=True)  # IPs permitidos
    ip_blacklist = Column(JSONB, nullable=True)  # IPs bloqueados

    # Validade
    expires_at = Column(DateTime, nullable=True)
    never_expires = Column(Boolean, nullable=False, default=False)

    # Uso
    last_used_at = Column(DateTime, nullable=True)
    last_used_ip = Column(String(45), nullable=True)
    last_used_user_agent = Column(String(500), nullable=True)
    total_requests = Column(Integer, nullable=False, default=0)
    successful_requests = Column(Integer, nullable=False, default=0)
    failed_requests = Column(Integer, nullable=False, default=0)

    # Revogação
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(UUID(as_uuid=True), nullable=True)
    revocation_reason = Column(Text, nullable=True)

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
        "IntegrationLog", back_populates="api_key", foreign_keys="IntegrationLog.api_key_id"
    )

    # Índices
    __table_args__ = (
        Index("ix_api_keys_key_hash", "key_hash"),
        Index("ix_api_keys_key_prefix", "key_prefix"),
        Index("ix_api_keys_client_id", "client_id"),
        Index("ix_api_keys_user_id", "user_id"),
        Index("ix_api_keys_status", "status"),
        Index("ix_api_keys_key_type", "key_type"),
        Index("ix_api_keys_expires_at", "expires_at"),
        Index("ix_api_keys_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<APIKey {self.name} ({self.key_prefix}...)>"

    @staticmethod
    def generate_key() -> tuple[str, str, str, str]:
        """
        Gera uma nova chave de API.
        Retorna: (chave_completa, prefix, hash, hint)
        """
        # Gera chave de 32 bytes (64 caracteres hex)
        raw_key = secrets.token_hex(32)
        prefix = raw_key[:8]
        hint = raw_key[-4:]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        return raw_key, prefix, key_hash, hint

    @staticmethod
    def hash_key(key: str) -> str:
        """Gera hash SHA-256 de uma chave."""
        return hashlib.sha256(key.encode()).hexdigest()

    def verify_key(self, key: str) -> bool:
        """Verifica se a chave fornecida é válida."""
        return self.key_hash == self.hash_key(key)

    def record_usage(self, ip: str, user_agent: str | None = None) -> None:
        """Registra uso da chave."""
        self.last_used_at = datetime.utcnow()
        self.last_used_ip = ip
        if user_agent:
            self.last_used_user_agent = user_agent[:500]
        self.total_requests += 1
        self.updated_at = datetime.utcnow()

    def record_success(self) -> None:
        """Registra chamada bem-sucedida."""
        self.successful_requests += 1
        self.current_minute_calls += 1
        self.current_hour_calls += 1
        self.current_day_calls += 1

    def record_failure(self) -> None:
        """Registra chamada com falha."""
        self.failed_requests += 1
        self.current_minute_calls += 1
        self.current_hour_calls += 1
        self.current_day_calls += 1

    def reset_rate_limits(self, period: str = "minute") -> None:
        """Reseta contadores de rate limit."""
        if period == "minute":
            self.current_minute_calls = 0
        elif period == "hour":
            self.current_hour_calls = 0
            self.current_minute_calls = 0
        elif period == "day":
            self.current_day_calls = 0
            self.current_hour_calls = 0
            self.current_minute_calls = 0
        self.last_rate_reset = datetime.utcnow()

    def check_rate_limit(self) -> tuple[bool, str]:
        """
        Verifica se está dentro do rate limit.
        Retorna: (permitido, motivo)
        """
        if self.rate_limit_per_minute:
            if self.current_minute_calls >= self.rate_limit_per_minute:
                return False, "Rate limit por minuto excedido"
        if self.rate_limit_per_hour:
            if self.current_hour_calls >= self.rate_limit_per_hour:
                return False, "Rate limit por hora excedido"
        if self.rate_limit_per_day:
            if self.current_day_calls >= self.rate_limit_per_day:
                return False, "Rate limit diário excedido"
        return True, "OK"

    def check_ip_allowed(self, ip: str) -> bool:
        """Verifica se IP é permitido."""
        if self.ip_blacklist and ip in self.ip_blacklist:
            return False
        if self.ip_whitelist and ip not in self.ip_whitelist:
            return False
        return True

    def has_scope(self, scope: str) -> bool:
        """Verifica se a chave tem o escopo."""
        if not self.scopes:
            return False
        if "admin" in self.scopes:
            return True
        if "read:all" in self.scopes and scope.startswith("read:"):
            return True
        if "write:all" in self.scopes and scope.startswith("write:"):
            return True
        return scope in self.scopes

    def suspend(self, reason: str | None = None) -> None:
        """Suspende a chave."""
        self.status = APIKeyStatus.SUSPENDED
        if reason:
            self.notes = f"Suspensa: {reason}"
        self.updated_at = datetime.utcnow()

    def revoke(self, revoked_by: str | None = None, reason: str | None = None) -> None:
        """Revoga a chave."""
        self.status = APIKeyStatus.REVOKED
        self.revoked_at = datetime.utcnow()
        if revoked_by:
            self.revoked_by = revoked_by
        if reason:
            self.revocation_reason = reason
        self.ativo = False
        self.updated_at = datetime.utcnow()

    def activate(self) -> None:
        """Ativa a chave."""
        self.status = APIKeyStatus.ACTIVE
        self.ativo = True
        self.updated_at = datetime.utcnow()

    @property
    def is_valid(self) -> bool:
        """Verifica se a chave é válida."""
        if self.status != APIKeyStatus.ACTIVE:
            return False
        if not self.ativo:
            return False
        if not self.never_expires and self.expires_at:
            if datetime.utcnow() > self.expires_at:
                return False
        return True

    @property
    def is_expired(self) -> bool:
        """Verifica se está expirada."""
        if self.never_expires:
            return False
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def days_until_expiry(self) -> int | None:
        """Dias até expiração."""
        if self.never_expires or not self.expires_at:
            return None
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    @property
    def success_rate(self) -> float:
        """Taxa de sucesso."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100
