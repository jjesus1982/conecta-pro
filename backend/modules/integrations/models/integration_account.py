"""
IntegrationAccount Model - Credenciais e Configurações por Tenant
Sprint 33: Integration Framework
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class ConnectorType(StrEnum):
    """Tipos de conectores disponíveis."""

    BLING = "bling"
    SOLIDES = "solides"
    DOMINIO = "dominio"
    OMIE = "omie"
    NIBO = "nibo"
    TOTVS = "totvs"
    SAP = "sap"
    CUSTOM = "custom"


class AuthType(StrEnum):
    """Tipos de autenticação."""

    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_credentials"
    BASIC = "basic"
    MTLS = "mtls"
    CERTIFICATE = "certificate"
    CUSTOM = "custom"


class AccountStatus(StrEnum):
    """Status da conta de integração."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    ERROR = "error"
    PENDING_AUTH = "pending_auth"
    EXPIRED = "expired"


class IntegrationAccount(Base):
    """
    Model para credenciais e configurações de integração por tenant.
    Armazena tokens de forma criptografada.
    """

    __tablename__ = "integration_accounts"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Tenant (multi-tenant)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificação
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    connector_type = Column(
        Enum(ConnectorType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ConnectorType.CUSTOM,
    )

    # Autenticação
    auth_type = Column(
        Enum(AuthType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=AuthType.API_KEY
    )

    # Credenciais (CRIPTOGRAFADAS - usar security_lgpd)
    # Nunca armazenar em texto plano
    credentials_encrypted = Column(Text, nullable=True)
    credentials_iv = Column(String(64), nullable=True)  # IV para AES
    credentials_key_id = Column(String(100), nullable=True)  # ID da chave usada

    # OAuth2 específico
    oauth2_client_id = Column(String(500), nullable=True)
    oauth2_client_secret_encrypted = Column(Text, nullable=True)
    oauth2_token_url = Column(String(500), nullable=True)
    oauth2_authorization_url = Column(String(500), nullable=True)
    oauth2_scopes = Column(JSONB, nullable=True)  # ["read", "write"]
    oauth2_access_token_encrypted = Column(Text, nullable=True)
    oauth2_refresh_token_encrypted = Column(Text, nullable=True)
    oauth2_token_expires_at = Column(DateTime, nullable=True)

    # Certificado (para mTLS/GOV)
    certificate_path = Column(String(500), nullable=True)
    certificate_password_encrypted = Column(Text, nullable=True)
    certificate_expires_at = Column(DateTime, nullable=True)

    # Configuração
    base_url = Column(String(500), nullable=True)
    api_version = Column(String(50), nullable=True)
    environment = Column(String(50), nullable=False, default="production")  # sandbox/production
    extra_config = Column(JSONB, nullable=True)  # Config adicional específica

    # Rate Limiting
    rate_limit_per_second = Column(Integer, nullable=True)
    rate_limit_per_minute = Column(Integer, nullable=True)
    rate_limit_per_hour = Column(Integer, nullable=True)

    # Status
    status = Column(
        Enum(AccountStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AccountStatus.PENDING_AUTH,
    )
    status_message = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime, nullable=True)

    # Health Check
    last_health_check_at = Column(DateTime, nullable=True)
    last_health_check_status = Column(Boolean, nullable=True)
    last_health_check_latency_ms = Column(Integer, nullable=True)
    health_check_failures = Column(Integer, nullable=False, default=0)

    # Sync Config
    sync_enabled = Column(Boolean, nullable=False, default=True)
    sync_interval_minutes = Column(Integer, nullable=False, default=60)
    sync_entities = Column(JSONB, nullable=True)  # ["products", "clients"]
    sync_mode = Column(String(50), nullable=False, default="incremental")  # full/incremental
    last_sync_at = Column(DateTime, nullable=True)
    next_sync_at = Column(DateTime, nullable=True)

    # Feature Flags
    write_enabled = Column(Boolean, nullable=False, default=False)
    webhooks_enabled = Column(Boolean, nullable=False, default=False)

    # Webhook Config
    webhook_secret = Column(String(200), nullable=True)
    webhook_url = Column(String(500), nullable=True)

    # Metadados
    tags = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Índices
    __table_args__ = (
        Index("ix_integration_accounts_tenant_id", "tenant_id"),
        Index("ix_integration_accounts_connector_type", "connector_type"),
        Index("ix_integration_accounts_status", "status"),
        Index("ix_integration_accounts_environment", "environment"),
        Index("ix_integration_accounts_tenant_connector", "tenant_id", "connector_type"),
        Index("ix_integration_accounts_next_sync_at", "next_sync_at"),
        Index("ix_integration_accounts_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<IntegrationAccount {self.connector_type.value} tenant={self.tenant_id}>"

    def activate(self) -> None:
        """Ativa a conta."""
        self.status = AccountStatus.ACTIVE
        self.status_message = None
        self.updated_at = datetime.utcnow()

    def deactivate(self, reason: str | None = None) -> None:
        """Desativa a conta."""
        self.status = AccountStatus.INACTIVE
        self.status_message = reason
        self.updated_at = datetime.utcnow()

    def suspend(self, reason: str) -> None:
        """Suspende a conta."""
        self.status = AccountStatus.SUSPENDED
        self.status_message = reason
        self.updated_at = datetime.utcnow()

    def mark_error(self, error_message: str) -> None:
        """Marca erro na conta."""
        self.status = AccountStatus.ERROR
        self.last_error = error_message
        self.last_error_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_expired(self) -> None:
        """Marca como expirado."""
        self.status = AccountStatus.EXPIRED
        self.status_message = "Credenciais ou certificado expirado"
        self.updated_at = datetime.utcnow()

    def update_health_check(self, success: bool, latency_ms: int | None = None, error: str | None = None) -> None:
        """Atualiza resultado do health check."""
        self.last_health_check_at = datetime.utcnow()
        self.last_health_check_status = success
        self.last_health_check_latency_ms = latency_ms

        if success:
            self.health_check_failures = 0
            if self.status == AccountStatus.ERROR:
                self.status = AccountStatus.ACTIVE
        else:
            self.health_check_failures += 1
            if self.health_check_failures >= 3:
                self.mark_error(error or "Health check falhou 3 vezes consecutivas")

        self.updated_at = datetime.utcnow()

    def update_oauth2_tokens(
        self, access_token_encrypted: str, refresh_token_encrypted: str | None, expires_at: datetime
    ) -> None:
        """Atualiza tokens OAuth2."""
        self.oauth2_access_token_encrypted = access_token_encrypted
        if refresh_token_encrypted:
            self.oauth2_refresh_token_encrypted = refresh_token_encrypted
        self.oauth2_token_expires_at = expires_at
        self.status = AccountStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def schedule_next_sync(self, minutes_from_now: int | None = None) -> None:
        """Agenda próxima sincronização."""
        from datetime import timedelta

        interval = minutes_from_now or self.sync_interval_minutes
        self.next_sync_at = datetime.utcnow() + timedelta(minutes=interval)
        self.updated_at = datetime.utcnow()

    def mark_sync_completed(self) -> None:
        """Marca sync como completado e agenda próxima."""
        self.last_sync_at = datetime.utcnow()
        self.schedule_next_sync()

    @property
    def is_oauth2_token_expired(self) -> bool:
        """Verifica se token OAuth2 expirou."""
        if not self.oauth2_token_expires_at:
            return True
        # Considera expirado 5 minutos antes para refresh proativo
        from datetime import timedelta

        return datetime.utcnow() >= (self.oauth2_token_expires_at - timedelta(minutes=5))

    @property
    def is_certificate_expired(self) -> bool:
        """Verifica se certificado expirou."""
        if not self.certificate_expires_at:
            return False
        return datetime.utcnow() >= self.certificate_expires_at

    @property
    def needs_sync(self) -> bool:
        """Verifica se precisa sincronizar."""
        if not self.sync_enabled:
            return False
        if self.status != AccountStatus.ACTIVE:
            return False
        if not self.next_sync_at:
            return True
        return datetime.utcnow() >= self.next_sync_at

    @property
    def is_healthy(self) -> bool:
        """Verifica se está saudável."""
        return (
            self.status == AccountStatus.ACTIVE
            and self.last_health_check_status is True
            and self.health_check_failures < 3
        )
