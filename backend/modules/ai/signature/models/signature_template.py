"""Signature Template model for storing reference signatures."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class TemplateStatus(StrEnum):
    """Status of signature template."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    REVOKED = "revoked"


class TemplateType(StrEnum):
    """Type of template."""

    PERSONAL = "personal"  # Individual's signature
    CORPORATE = "corporate"  # Company signature/stamp
    DEPARTMENT = "department"  # Department signature
    ROLE = "role"  # Role-based signature
    PROXY = "proxy"  # Proxy/delegation signature


class MatchingMode(StrEnum):
    """Matching mode for comparison."""

    STRICT = "strict"  # High similarity required
    NORMAL = "normal"  # Standard matching
    RELAXED = "relaxed"  # Lower threshold
    BIOMETRIC = "biometric"  # Use biometric data
    HYBRID = "hybrid"  # Combine multiple methods


class SignatureTemplate(Base):
    """Model for storing reference signature templates."""

    __tablename__ = "sig_signature_templates"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Template info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    code = Column(String(50), nullable=True, index=True)

    # Owner information
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    owner_type = Column(String(50), nullable=False)  # user, employee, customer
    owner_name = Column(String(255), nullable=True)
    owner_document = Column(String(50), nullable=True)  # CPF/CNPJ

    # Template type and status
    template_type = Column(
        Enum(TemplateType),
        nullable=False,
        default=TemplateType.PERSONAL,
    )
    status = Column(
        Enum(TemplateStatus),
        nullable=False,
        default=TemplateStatus.DRAFT,
    )
    matching_mode = Column(
        Enum(MatchingMode),
        nullable=False,
        default=MatchingMode.NORMAL,
    )

    # Reference signatures (multiple samples for better matching)
    sample_count = Column(Integer, default=0)
    min_samples_required = Column(Integer, default=3)

    # Averaged/combined feature vectors
    master_feature_vector = Column(JSONB, nullable=True)
    feature_version = Column(String(20), nullable=True)
    master_contour = Column(JSONB, nullable=True)

    # Statistical data from samples
    feature_mean = Column(JSONB, nullable=True)
    feature_std = Column(JSONB, nullable=True)
    feature_variance = Column(JSONB, nullable=True)

    # Matching thresholds
    similarity_threshold = Column(Float, default=0.75)  # 0-1
    min_confidence = Column(Float, default=0.70)
    max_false_positive_rate = Column(Float, default=0.01)

    # Quality requirements
    min_quality_score = Column(Float, default=0.5)
    min_contrast = Column(Float, default=0.3)
    min_clarity = Column(Float, default=0.4)

    # Size constraints
    min_width = Column(Integer, nullable=True)
    max_width = Column(Integer, nullable=True)
    min_height = Column(Integer, nullable=True)
    max_height = Column(Integer, nullable=True)
    aspect_ratio_tolerance = Column(Float, default=0.3)

    # Biometric thresholds (if applicable)
    pressure_variance_max = Column(Float, nullable=True)
    velocity_variance_max = Column(Float, nullable=True)
    timing_variance_max = Column(Float, nullable=True)

    # Usage limits
    max_daily_uses = Column(Integer, nullable=True)
    max_monthly_uses = Column(Integer, nullable=True)
    current_daily_uses = Column(Integer, default=0)
    current_monthly_uses = Column(Integer, default=0)
    last_usage_reset = Column(DateTime, nullable=True)

    # Statistics
    total_verifications = Column(Integer, default=0)
    successful_verifications = Column(Integer, default=0)
    failed_verifications = Column(Integer, default=0)
    average_match_score = Column(Float, nullable=True)

    # Validity
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    # Approval workflow
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    approval_notes = Column(Text, nullable=True)

    # Revocation
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(UUID(as_uuid=True), nullable=True)
    revocation_reason = Column(Text, nullable=True)

    # Allowed document types
    allowed_document_types = Column(JSONB, nullable=True)  # ['contract', 'proposal']
    allowed_purposes = Column(JSONB, nullable=True)  # ['approval', 'witness']

    # Delegation/proxy
    can_delegate = Column(Boolean, default=False)
    delegated_from = Column(UUID(as_uuid=True), nullable=True)
    delegation_scope = Column(JSONB, nullable=True)

    # Metadata
    extra_data = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    signatures = relationship("Signature", back_populates="template")
    verifications = relationship("SignatureVerification", back_populates="template")

    def __repr__(self) -> str:
        """String representation."""
        return f"<SignatureTemplate {self.id} name={self.name} owner={self.owner_name}>"

    @property
    def is_valid(self) -> bool:
        """Check if template is currently valid."""
        if not self.is_active:
            return False
        if self.status not in [TemplateStatus.ACTIVE]:
            return False
        now = datetime.utcnow()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    @property
    def has_enough_samples(self) -> bool:
        """Check if template has enough samples for reliable matching."""
        return self.sample_count >= self.min_samples_required

    @property
    def success_rate(self) -> float | None:
        """Calculate verification success rate."""
        if self.total_verifications == 0:
            return None
        return self.successful_verifications / self.total_verifications

    def can_use(self) -> tuple[bool, str]:
        """Check if template can be used for verification."""
        if not self.is_valid:
            return False, "Template is not valid"

        if not self.has_enough_samples:
            return False, f"Need at least {self.min_samples_required} samples"

        if self.max_daily_uses and self.current_daily_uses >= self.max_daily_uses:
            return False, "Daily usage limit reached"

        if self.max_monthly_uses and self.current_monthly_uses >= self.max_monthly_uses:
            return False, "Monthly usage limit reached"

        return True, "OK"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "name": self.name,
            "owner_id": str(self.owner_id),
            "owner_name": self.owner_name,
            "template_type": self.template_type.value if self.template_type else None,
            "status": self.status.value if self.status else None,
            "matching_mode": self.matching_mode.value if self.matching_mode else None,
            "sample_count": self.sample_count,
            "min_samples_required": self.min_samples_required,
            "similarity_threshold": self.similarity_threshold,
            "is_valid": self.is_valid,
            "has_enough_samples": self.has_enough_samples,
            "success_rate": self.success_rate,
            "total_verifications": self.total_verifications,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
