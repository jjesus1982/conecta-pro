"""
Model de Solicitacao de Exclusao de Dados (Direito ao Esquecimento).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.models import Base


class ErasureStatus(StrEnum):
    """Status da solicitacao de exclusao."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    PARTIAL = "partial"


class ErasureScope(StrEnum):
    """Escopo da exclusao de dados."""

    ALL = "all"
    PERSONAL = "personal"
    MARKETING = "marketing"
    ANALYTICS = "analytics"


class ErasureRequest(Base):
    """Model de Solicitacao de Exclusao de Dados.

    Gerencia solicitacoes de exclusao de dados conforme
    Art. 18 da LGPD (direito ao esquecimento).
    """

    __tablename__ = "lgpd_erasure_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titular_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    titular_email = Column(String(255), nullable=False)
    reason = Column(Text, nullable=False)
    scope = Column(
        Enum(ErasureScope, values_callable=lambda x: [e.value for e in x]), default=ErasureScope.ALL, nullable=False
    )
    status = Column(
        Enum(ErasureStatus, values_callable=lambda x: [e.value for e in x]),
        default=ErasureStatus.PENDING,
        nullable=False,
    )

    # Datas
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    deadline_at = Column(DateTime, nullable=True)

    # Processamento
    processed_by = Column(String(255), nullable=True)
    processing_notes = Column(Text, nullable=True)
    affected_systems = Column(JSONB, default=list)
    erasure_report = Column(JSONB, default=dict)

    # Auditoria
    request_hash = Column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<ErasureRequest(id={self.id}, titular={self.titular_id}, status={self.status})>"

    def to_dict(self) -> dict:
        """Converte o model para dicionario."""
        return {
            "id": str(self.id),
            "titular_id": str(self.titular_id),
            "titular_email": self.titular_email,
            "reason": self.reason,
            "scope": self.scope.value if self.scope else None,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
        }
