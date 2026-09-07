"""Signature Verification model for storing verification results."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class VerificationStatus(StrEnum):
    """Status of verification."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class VerificationMethod(StrEnum):
    """Method used for verification."""

    VISUAL = "visual"  # Visual comparison
    FEATURE = "feature"  # Feature vector matching
    CONTOUR = "contour"  # Contour analysis
    BIOMETRIC = "biometric"  # Biometric data matching
    HYBRID = "hybrid"  # Multiple methods combined
    NEURAL = "neural"  # Neural network
    MANUAL = "manual"  # Human verification


class VerificationResult(StrEnum):
    """Result of verification."""

    AUTHENTIC = "authentic"
    FORGERY = "forgery"
    SUSPICIOUS = "suspicious"
    INSUFFICIENT_DATA = "insufficient_data"
    TEMPLATE_MISMATCH = "template_mismatch"
    QUALITY_ISSUE = "quality_issue"


class RiskLevel(StrEnum):
    """Risk level of verification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SignatureVerification(Base):
    """Model for storing signature verification results."""

    __tablename__ = "sig_signature_verifications"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # References
    signature_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sig_signatures.id"),
        nullable=False,
        index=True,
    )
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sig_signature_templates.id"),
        nullable=True,
        index=True,
    )
    document_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sig_signature_requests.id"),
        nullable=True,
    )

    # Status and result
    status = Column(
        Enum(VerificationStatus),
        nullable=False,
        default=VerificationStatus.PENDING,
    )
    result = Column(Enum(VerificationResult, values_callable=lambda x: [e.value for e in x]), nullable=True)
    risk_level = Column(Enum(RiskLevel, values_callable=lambda x: [e.value for e in x]), nullable=True)

    # Verification method
    method = Column(
        Enum(VerificationMethod),
        nullable=False,
        default=VerificationMethod.FEATURE,
    )
    algorithm_version = Column(String(20), nullable=True)

    # Scores
    overall_score = Column(Float, nullable=True)  # 0-1
    similarity_score = Column(Float, nullable=True)
    feature_score = Column(Float, nullable=True)
    contour_score = Column(Float, nullable=True)
    biometric_score = Column(Float, nullable=True)

    # Confidence
    confidence = Column(Float, nullable=True)  # 0-1
    confidence_interval_low = Column(Float, nullable=True)
    confidence_interval_high = Column(Float, nullable=True)

    # Threshold used
    threshold_used = Column(Float, nullable=True)
    passed_threshold = Column(Boolean, nullable=True)

    # Detailed analysis
    feature_comparison = Column(JSONB, nullable=True)  # Per-feature scores
    contour_analysis = Column(JSONB, nullable=True)
    biometric_analysis = Column(JSONB, nullable=True)

    # Quality assessment
    input_quality_score = Column(Float, nullable=True)
    template_quality_score = Column(Float, nullable=True)
    quality_issues = Column(JSONB, nullable=True)  # List of issues found

    # Anomalies detected
    anomalies_detected = Column(JSONB, nullable=True)
    anomaly_count = Column(Integer, default=0)
    fraud_indicators = Column(JSONB, nullable=True)

    # Processing info
    processing_time_ms = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Manual review
    requires_manual_review = Column(Boolean, default=False)
    manual_review_reason = Column(Text, nullable=True)
    manually_reviewed = Column(Boolean, default=False)
    manual_reviewer_id = Column(UUID(as_uuid=True), nullable=True)
    manual_review_result = Column(String(50), nullable=True)
    manual_review_notes = Column(Text, nullable=True)
    manual_reviewed_at = Column(DateTime, nullable=True)

    # Error info
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)

    # Context
    verification_purpose = Column(String(100), nullable=True)
    verification_context = Column(JSONB, nullable=True)

    # IP and device info
    request_ip = Column(String(45), nullable=True)
    request_device = Column(String(255), nullable=True)
    request_user_agent = Column(String(500), nullable=True)
    request_location = Column(JSONB, nullable=True)

    # Audit trail
    audit_log = Column(JSONB, nullable=True)

    # Metadata
    extra_data = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    signature = relationship("Signature", back_populates="verifications")
    template = relationship("SignatureTemplate", back_populates="verifications")
    request = relationship("SignatureRequest", back_populates="verifications")

    def __repr__(self) -> str:
        """String representation."""
        return f"<SignatureVerification {self.id} status={self.status} result={self.result}>"

    @property
    def is_match(self) -> bool:
        """Check if verification resulted in a match."""
        return self.status == VerificationStatus.MATCHED

    @property
    def is_conclusive(self) -> bool:
        """Check if verification is conclusive."""
        return self.status in [
            VerificationStatus.MATCHED,
            VerificationStatus.NOT_MATCHED,
        ]

    @property
    def needs_review(self) -> bool:
        """Check if verification needs manual review."""
        return self.requires_manual_review and not self.manually_reviewed

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "signature_id": str(self.signature_id),
            "template_id": str(self.template_id) if self.template_id else None,
            "status": self.status.value if self.status else None,
            "result": self.result.value if self.result else None,
            "risk_level": self.risk_level.value if self.risk_level else None,
            "method": self.method.value if self.method else None,
            "overall_score": self.overall_score,
            "similarity_score": self.similarity_score,
            "confidence": self.confidence,
            "passed_threshold": self.passed_threshold,
            "is_match": self.is_match,
            "requires_manual_review": self.requires_manual_review,
            "processing_time_ms": self.processing_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
