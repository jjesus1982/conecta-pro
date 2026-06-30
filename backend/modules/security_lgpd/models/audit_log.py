"""
Model de Log de Auditoria LGPD.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.models import Base


class AuditAction(StrEnum):
    """Acoes de auditoria."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    CONSENT = "consent"
    LOGIN = "login"
    LOGOUT = "logout"
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"
    MASK = "mask"
    ERASURE = "erasure"


class AuditSeverity(StrEnum):
    """Severidade do evento de auditoria."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ResourceType(StrEnum):
    """Tipos de recurso auditados."""

    USER = "user"
    DOCUMENT = "document"
    CONSENT = "consent"
    DATA = "data"
    SYSTEM = "system"
    AUDIT = "audit"


class AuditLog(Base):
    """Model de Log de Auditoria.

    Registra eventos de auditoria com hash chain para
    garantir integridade e nao-repudio.
    """

    __tablename__ = "lgpd_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action = Column(Enum(AuditAction, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    resource_type = Column(
        Enum(ResourceType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True
    )
    resource_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    severity = Column(
        Enum(AuditSeverity, values_callable=lambda x: [e.value for e in x]), default=AuditSeverity.INFO, nullable=False
    )

    # Detalhes
    details = Column(JSONB, default=dict)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Hash chain para integridade
    event_hash = Column(String(64), nullable=False)
    previous_hash = Column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, resource={self.resource_type})>"

    def to_dict(self) -> dict:
        """Converte o model para dicionario."""
        return {
            "id": str(self.id),
            "action": self.action.value if self.action else None,
            "resource_type": self.resource_type.value if self.resource_type else None,
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "severity": self.severity.value if self.severity else None,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "event_hash": self.event_hash,
        }
