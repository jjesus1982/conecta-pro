"""Signature model for storing extracted signatures."""

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


class SignatureType(StrEnum):
    """Type of signature."""

    HANDWRITTEN = "handwritten"
    DIGITAL = "digital"
    ELECTRONIC = "electronic"
    BIOMETRIC = "biometric"
    SCANNED = "scanned"
    DRAWN = "drawn"


class SignatureFormat(StrEnum):
    """Format of signature image/data."""

    PNG = "png"
    JPEG = "jpeg"
    SVG = "svg"
    PDF = "pdf"
    BASE64 = "base64"
    VECTOR = "vector"
    BIOMETRIC_DATA = "biometric_data"


class SignatureStatus(StrEnum):
    """Status of signature."""

    PENDING = "pending"
    EXTRACTED = "extracted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ARCHIVED = "archived"


class SignatureSource(StrEnum):
    """Source of signature capture."""

    DOCUMENT_SCAN = "document_scan"
    TABLET = "tablet"
    MOUSE = "mouse"
    TOUCHSCREEN = "touchscreen"
    STYLUS = "stylus"
    CERTIFICATE = "certificate"
    API = "api"
    UPLOAD = "upload"


class Signature(Base):
    """Model for storing signature data and metadata."""

    __tablename__ = "sig_signatures"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Owner information
    owner_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    owner_type = Column(String(50), nullable=True)  # user, employee, customer, etc.
    owner_name = Column(String(255), nullable=True)
    owner_document = Column(String(50), nullable=True)  # CPF/CNPJ

    # Signature type and format
    # native_enum=False -> armazena como VARCHAR (colunas criadas como String(50)
    # no banco, sem tipos ENUM nativos). Mantém StrEnum na leitura.
    signature_type = Column(
        Enum(SignatureType, native_enum=False, length=50),
        nullable=False,
        default=SignatureType.HANDWRITTEN,
    )
    signature_format = Column(
        Enum(SignatureFormat, native_enum=False, length=50),
        nullable=False,
        default=SignatureFormat.PNG,
    )
    status = Column(
        Enum(SignatureStatus, native_enum=False, length=50),
        nullable=False,
        default=SignatureStatus.PENDING,
    )
    source = Column(
        Enum(SignatureSource, native_enum=False, length=50),
        nullable=False,
        default=SignatureSource.UPLOAD,
    )

    # Image data
    image_path = Column(String(500), nullable=True)
    image_data = Column(Text, nullable=True)  # Base64 encoded
    thumbnail_path = Column(String(500), nullable=True)
    original_filename = Column(String(255), nullable=True)

    # Image properties
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=True)
    dpi = Column(Integer, nullable=True)
    color_depth = Column(Integer, nullable=True)

    # Extraction info
    extracted_from_document_id = Column(UUID(as_uuid=True), nullable=True)
    extraction_region = Column(JSONB, nullable=True)  # {x, y, width, height}
    extraction_method = Column(String(100), nullable=True)
    extraction_confidence = Column(Float, nullable=True)

    # Feature vectors for comparison
    feature_vector = Column(JSONB, nullable=True)  # Encoded features
    feature_version = Column(String(20), nullable=True)
    contour_data = Column(JSONB, nullable=True)  # Signature contours
    stroke_data = Column(JSONB, nullable=True)  # Stroke information

    # Quality metrics
    quality_score = Column(Float, nullable=True)  # 0-1
    contrast_score = Column(Float, nullable=True)
    clarity_score = Column(Float, nullable=True)
    completeness_score = Column(Float, nullable=True)

    # Biometric data (for biometric signatures)
    pressure_data = Column(JSONB, nullable=True)  # Pen pressure
    velocity_data = Column(JSONB, nullable=True)  # Writing velocity
    timing_data = Column(JSONB, nullable=True)  # Timing information

    # Digital signature info (for digital/electronic)
    certificate_id = Column(String(255), nullable=True)
    certificate_issuer = Column(String(255), nullable=True)
    certificate_serial = Column(String(100), nullable=True)
    certificate_valid_from = Column(DateTime, nullable=True)
    certificate_valid_to = Column(DateTime, nullable=True)
    hash_algorithm = Column(String(50), nullable=True)
    signature_hash = Column(String(512), nullable=True)

    # Verification
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(UUID(as_uuid=True), nullable=True)
    verification_method = Column(String(100), nullable=True)
    verification_score = Column(Float, nullable=True)

    # Template reference
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sig_signature_templates.id"),
        nullable=True,
    )
    is_template = Column(Boolean, default=False)

    # Usage tracking
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)

    # Validity
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    # Metadata
    extra_data = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # IP and device info
    capture_ip = Column(String(45), nullable=True)
    capture_device = Column(String(255), nullable=True)
    capture_user_agent = Column(String(500), nullable=True)
    capture_location = Column(JSONB, nullable=True)  # {lat, lng, address}

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    template = relationship("SignatureTemplate", back_populates="signatures")
    verifications = relationship("SignatureVerification", back_populates="signature")

    def __repr__(self) -> str:
        """String representation."""
        return f"<Signature {self.id} owner={self.owner_name} type={self.signature_type}>"

    @property
    def is_valid(self) -> bool:
        """Check if signature is currently valid."""
        if not self.is_active:
            return False
        if self.status in [
            SignatureStatus.REJECTED,
            SignatureStatus.EXPIRED,
            SignatureStatus.REVOKED,
        ]:
            return False
        now = datetime.utcnow()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    @property
    def is_digital(self) -> bool:
        """Check if signature is digital/electronic."""
        return self.signature_type in [
            SignatureType.DIGITAL,
            SignatureType.ELECTRONIC,
        ]

    @property
    def has_biometric_data(self) -> bool:
        """Check if signature has biometric data."""
        return bool(self.pressure_data or self.velocity_data or self.timing_data)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "owner_id": str(self.owner_id) if self.owner_id else None,
            "owner_name": self.owner_name,
            "signature_type": self.signature_type.value if self.signature_type else None,
            "signature_format": self.signature_format.value if self.signature_format else None,
            "status": self.status.value if self.status else None,
            "source": self.source.value if self.source else None,
            "quality_score": self.quality_score,
            "is_verified": self.is_verified,
            "is_valid": self.is_valid,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
