"""
AuditLog Model - Logs de Auditoria
Sprint 33: Auditoria e Compliance
"""

import secrets
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from core.database import Base


class AuditAction(StrEnum):
    """Tipo de ação auditada."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"  # noqa: S105
    PASSWORD_RESET = "password_reset"  # noqa: S105
    PERMISSION_GRANT = "permission_grant"
    PERMISSION_REVOKE = "permission_revoke"
    EXPORT = "export"
    IMPORT = "import"
    APPROVE = "approve"
    REJECT = "reject"
    ARCHIVE = "archive"
    RESTORE = "restore"
    BULK_OPERATION = "bulk_operation"
    CONFIGURATION_CHANGE = "configuration_change"
    API_CALL = "api_call"


class AuditCategory(StrEnum):
    """Categoria da auditoria."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    CONFIGURATION = "configuration"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    FINANCIAL = "financial"
    USER_MANAGEMENT = "user_management"
    SYSTEM = "system"
    INTEGRATION = "integration"
    REPORT = "report"


class AuditSeverity(StrEnum):
    """Severidade do evento."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditResult(StrEnum):
    """Resultado da ação."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    DENIED = "denied"
    ERROR = "error"


class AuditLog(Base):
    """
    Model para logs de auditoria.
    Registra todas as ações relevantes para compliance e segurança.
    """

    __tablename__ = "audit_logs"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação do evento
    event_id = Column(String(50), nullable=False, unique=True)
    correlation_id = Column(String(50), nullable=True)
    parent_event_id = Column(String(50), nullable=True)

    # Ação
    action = Column(Enum(AuditAction, values_callable=lambda x: [e.value for e in x]), nullable=False)
    category = Column(Enum(AuditCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    severity = Column(
        Enum(AuditSeverity, values_callable=lambda x: [e.value for e in x]), nullable=False, default=AuditSeverity.INFO
    )
    result = Column(
        Enum(AuditResult, values_callable=lambda x: [e.value for e in x]), nullable=False, default=AuditResult.SUCCESS
    )

    # Descrição
    description = Column(Text, nullable=False)
    details = Column(JSONB, nullable=True)

    # Usuário
    user_id = Column(UUID(as_uuid=True), nullable=True)
    user_email = Column(String(255), nullable=True)
    user_name = Column(String(200), nullable=True)
    user_role = Column(String(100), nullable=True)
    impersonated_by = Column(UUID(as_uuid=True), nullable=True)

    # Entidade afetada
    entity_type = Column(String(100), nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    entity_name = Column(String(300), nullable=True)

    # Dados de mudança
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)
    changed_fields = Column(JSONB, nullable=True)

    # Request/Response
    request_method = Column(String(10), nullable=True)
    request_path = Column(String(500), nullable=True)
    request_query = Column(Text, nullable=True)
    request_body_hash = Column(String(64), nullable=True)
    response_status = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)

    # Contexto de rede
    ip_address = Column(INET, nullable=True)
    user_agent = Column(String(500), nullable=True)
    session_id = Column(String(100), nullable=True)
    device_fingerprint = Column(String(64), nullable=True)

    # Geolocalização
    geo_country = Column(String(100), nullable=True)
    geo_region = Column(String(100), nullable=True)
    geo_city = Column(String(100), nullable=True)
    geo_coordinates = Column(String(50), nullable=True)

    # Contexto de sistema
    service_name = Column(String(100), nullable=True)
    service_version = Column(String(20), nullable=True)
    environment = Column(String(50), nullable=True)
    server_hostname = Column(String(200), nullable=True)

    # Compliance
    compliance_frameworks = Column(JSONB, nullable=True)
    data_classification = Column(String(50), nullable=True)
    retention_days = Column(Integer, nullable=True)
    is_sensitive = Column(Boolean, nullable=False, default=False)
    is_pii = Column(Boolean, nullable=False, default=False)

    # Alertas
    triggered_alerts = Column(JSONB, nullable=True)
    requires_review = Column(Boolean, nullable=False, default=False)
    reviewed_by = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)

    # Retenção
    archived = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Metadados
    extra_metadata = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Índices
    __table_args__ = (
        Index("ix_audit_logs_event_id", "event_id"),
        Index("ix_audit_logs_correlation_id", "correlation_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_category", "category"),
        Index("ix_audit_logs_severity", "severity"),
        Index("ix_audit_logs_result", "result"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_entity_type", "entity_type"),
        Index("ix_audit_logs_entity_id", "entity_id"),
        Index("ix_audit_logs_ip_address", "ip_address"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_requires_review", "requires_review"),
        Index("ix_audit_logs_archived", "archived"),
        Index("ix_audit_logs_user_action_date", "user_id", "action", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action.value} by {self.user_email}>"

    @classmethod
    def create_event(
        cls,
        action: AuditAction,
        category: AuditCategory,
        description: str,
        user_id: str | None = None,
        user_email: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        result: AuditResult = AuditResult.SUCCESS,
        ip_address: str | None = None,
        **kwargs,
    ) -> "AuditLog":
        """Cria um novo evento de auditoria."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        token = secrets.token_hex(4).upper()
        event_id = f"EVT-{timestamp}-{token}"

        return cls(
            event_id=event_id,
            action=action,
            category=category,
            description=description,
            user_id=user_id,
            user_email=user_email,
            entity_type=entity_type,
            entity_id=entity_id,
            severity=severity,
            result=result,
            ip_address=ip_address,
            **kwargs,
        )

    def mark_for_review(self, reason: str | None = None) -> None:
        """Marca para revisão."""
        self.requires_review = True
        if reason:
            self.metadata = self.metadata or {}
            self.metadata["review_reason"] = reason

    def complete_review(self, reviewer_id: str, notes: str | None = None) -> None:
        """Completa a revisão."""
        self.requires_review = False
        self.reviewed_by = reviewer_id
        self.reviewed_at = datetime.utcnow()
        if notes:
            self.review_notes = notes

    def archive(self) -> None:
        """Arquiva o log."""
        self.archived = True
        self.archived_at = datetime.utcnow()

    @property
    def is_security_event(self) -> bool:
        """Verifica se é evento de segurança."""
        return self.category in [AuditCategory.AUTHENTICATION, AuditCategory.AUTHORIZATION, AuditCategory.SECURITY]

    @property
    def is_high_severity(self) -> bool:
        """Verifica se é alta severidade."""
        return self.severity in [AuditSeverity.ERROR, AuditSeverity.CRITICAL]

    @property
    def has_data_change(self) -> bool:
        """Verifica se houve mudança de dados."""
        return bool(self.old_values or self.new_values)
