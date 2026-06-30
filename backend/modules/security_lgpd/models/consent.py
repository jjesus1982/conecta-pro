"""
Model de Consentimento LGPD.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID

from core.models import Base


class ConsentStatus(StrEnum):
    """Status do consentimento."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    PENDING = "pending"


class ConsentPurpose(StrEnum):
    """Finalidade do consentimento conforme LGPD."""

    MARKETING = "marketing"
    ANALYTICS = "analytics"
    PERSONALIZATION = "personalization"
    SERVICE_PROVISION = "service_provision"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTEREST = "vital_interest"
    PUBLIC_INTEREST = "public_interest"
    LEGITIMATE_INTEREST = "legitimate_interest"


class LegalBasis(StrEnum):
    """Base legal conforme Art. 7 LGPD."""

    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTEREST = "vital_interest"
    PUBLIC_POLICY = "public_policy"
    RESEARCH = "research"
    LEGITIMATE_INTEREST = "legitimate_interest"
    CREDIT_PROTECTION = "credit_protection"


class Consent(Base):
    """Model de Consentimento LGPD.

    Armazena consentimentos de titulares de dados conforme
    requisitos da Lei 13.709/2018 (LGPD).
    """

    __tablename__ = "lgpd_consents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titular_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    titular_email = Column(String(255), nullable=False)
    purpose = Column(Enum(ConsentPurpose, values_callable=lambda x: [e.value for e in x]), nullable=False)
    legal_basis = Column(Enum(LegalBasis, values_callable=lambda x: [e.value for e in x]), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(
        Enum(ConsentStatus, values_callable=lambda x: [e.value for e in x]),
        default=ConsentStatus.ACTIVE,
        nullable=False,
    )

    # Datas
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    # Metadados
    revocation_reason = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    version = Column(String(20), default="1.0", nullable=False)

    # Hash para integridade
    consent_hash = Column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<Consent(id={self.id}, titular={self.titular_id}, purpose={self.purpose})>"

    def to_dict(self) -> dict:
        """Converte o model para dicionario."""
        return {
            "id": str(self.id),
            "titular_id": str(self.titular_id),
            "titular_email": self.titular_email,
            "purpose": self.purpose.value if self.purpose else None,
            "legal_basis": self.legal_basis.value if self.legal_basis else None,
            "description": self.description,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }
