"""
Model de Avaliacao de Impacto de Privacidade (PIA/DPIA).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from core.models import Base


class RiskLevel(StrEnum):
    """Nivel de risco da avaliacao."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssessmentStatus(StrEnum):
    """Status da avaliacao."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class PIAAssessment(Base):
    """Model de Avaliacao de Impacto de Privacidade.

    Gerencia avaliacoes de impacto de privacidade conforme
    Art. 38 da LGPD (RIPD - Relatorio de Impacto a Protecao de Dados).
    """

    __tablename__ = "lgpd_pia_assessments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(
        Enum(AssessmentStatus, values_callable=lambda x: [e.value for e in x]),
        default=AssessmentStatus.DRAFT,
        nullable=False,
    )
    risk_level = Column(Enum(RiskLevel, values_callable=lambda x: [e.value for e in x]), nullable=True)
    requires_dpia = Column(Boolean, default=False)

    # Categorias e finalidades
    data_categories = Column(ARRAY(String), default=list)
    processing_purposes = Column(ARRAY(String), default=list)
    data_subjects = Column(ARRAY(String), default=list)
    risk_factors = Column(ARRAY(String), default=list)

    # Avaliacao
    risk_assessment = Column(JSONB, default=dict)
    recommendations = Column(ARRAY(String), default=list)
    mitigations = Column(JSONB, default=dict)

    # Responsaveis
    created_by = Column(String(255), nullable=True)
    reviewed_by = Column(String(255), nullable=True)
    approved_by = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # Controle de versao
    version = Column(String(20), default="1.0", nullable=False)

    def __repr__(self) -> str:
        return f"<PIAAssessment(id={self.id}, project={self.project_name}, risk={self.risk_level})>"

    def to_dict(self) -> dict:
        """Converte o model para dicionario."""
        return {
            "id": str(self.id),
            "project_name": self.project_name,
            "description": self.description,
            "status": self.status.value if self.status else None,
            "risk_level": self.risk_level.value if self.risk_level else None,
            "requires_dpia": self.requires_dpia,
            "data_categories": self.data_categories,
            "processing_purposes": self.processing_purposes,
            "recommendations": self.recommendations,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
