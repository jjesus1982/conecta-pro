"""Signed Document model for storing signed documents."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class SignedDocumentStatus(StrEnum):
    """Status of signed document."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"  # Some signatures missing
    INVALID = "invalid"
    ARCHIVED = "archived"


class DocumentIntegrityStatus(StrEnum):
    """Integrity status of document."""

    VALID = "valid"
    MODIFIED = "modified"
    CORRUPTED = "corrupted"
    UNKNOWN = "unknown"


class ArchiveStatus(StrEnum):
    """Archive status."""

    NOT_ARCHIVED = "not_archived"
    PENDING = "pending"
    ARCHIVED = "archived"
    FAILED = "failed"


class SignedDocument(Base):
    """Model for storing signed documents."""

    __tablename__ = "sig_signed_documents"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Document info
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    reference_code = Column(String(100), nullable=True, index=True)
    document_number = Column(String(100), nullable=True, index=True)

    # Status
    status = Column(
        Enum(SignedDocumentStatus),
        nullable=False,
        default=SignedDocumentStatus.PENDING,
    )
    integrity_status = Column(
        Enum(DocumentIntegrityStatus),
        nullable=False,
        default=DocumentIntegrityStatus.UNKNOWN,
    )

    # Original document
    original_document_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    original_path = Column(String(500), nullable=True)
    original_filename = Column(String(255), nullable=True)
    original_hash = Column(String(128), nullable=True)
    original_size = Column(Integer, nullable=True)
    original_pages = Column(Integer, nullable=True)
    original_mime_type = Column(String(100), nullable=True)

    # Signed document
    signed_path = Column(String(500), nullable=True)
    signed_filename = Column(String(255), nullable=True)
    signed_hash = Column(String(128), nullable=True)
    signed_size = Column(Integer, nullable=True)
    signed_mime_type = Column(String(100), nullable=True)

    # Request reference
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sig_signature_requests.id"),
        nullable=True,
    )

    # Signatures info
    total_signatures_required = Column(Integer, default=1)
    total_signatures_collected = Column(Integer, default=0)
    signature_ids = Column(ARRAY(UUID), nullable=True)
    signature_positions = Column(JSONB, nullable=True)  # [{page, x, y, signature_id}]

    # Signers summary
    signers = Column(JSONB, nullable=True)  # [{name, email, signed_at, signature_id}]

    # Timestamps
    first_signature_at = Column(DateTime, nullable=True)
    last_signature_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Integrity verification
    last_integrity_check = Column(DateTime, nullable=True)
    integrity_check_count = Column(Integer, default=0)
    integrity_issues = Column(JSONB, nullable=True)

    # Certificate info (for certified documents)
    certificate_id = Column(String(255), nullable=True)
    certificate_chain = Column(JSONB, nullable=True)
    timestamp_token = Column(Text, nullable=True)
    timestamped_at = Column(DateTime, nullable=True)
    timestamp_authority = Column(String(255), nullable=True)

    # Legal validity
    is_legally_binding = Column(Boolean, default=False)
    legal_framework = Column(String(100), nullable=True)  # e.g., "MP 2.200-2/2001"
    compliance_standards = Column(ARRAY(String), nullable=True)  # ["ICP-Brasil", "eIDAS"]

    # Retention
    retention_period_days = Column(Integer, nullable=True)
    retention_expires_at = Column(DateTime, nullable=True)
    is_permanent = Column(Boolean, default=False)

    # Archive
    archive_status = Column(
        Enum(ArchiveStatus),
        nullable=False,
        default=ArchiveStatus.NOT_ARCHIVED,
    )
    archived_at = Column(DateTime, nullable=True)
    archive_location = Column(String(500), nullable=True)
    archive_reference = Column(String(255), nullable=True)

    # Access control
    is_public = Column(Boolean, default=False)
    access_password = Column(String(255), nullable=True)
    allowed_viewers = Column(ARRAY(UUID), nullable=True)
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime, nullable=True)

    # Download tracking
    download_count = Column(Integer, default=0)
    last_downloaded_at = Column(DateTime, nullable=True)
    download_log = Column(JSONB, nullable=True)

    # Verification
    verification_url = Column(String(500), nullable=True)
    verification_code = Column(String(50), nullable=True, unique=True)
    qr_code_path = Column(String(500), nullable=True)

    # Related documents
    parent_document_id = Column(UUID(as_uuid=True), nullable=True)
    related_documents = Column(ARRAY(UUID), nullable=True)
    supersedes_document_id = Column(UUID(as_uuid=True), nullable=True)
    superseded_by_document_id = Column(UUID(as_uuid=True), nullable=True)

    # Workflow
    workflow_id = Column(UUID(as_uuid=True), nullable=True)
    workflow_status = Column(String(100), nullable=True)

    # External systems
    external_id = Column(String(255), nullable=True)
    external_system = Column(String(100), nullable=True)
    sync_status = Column(String(50), nullable=True)
    last_synced_at = Column(DateTime, nullable=True)

    # Audit trail
    audit_log = Column(JSONB, nullable=True)

    # Metadata
    extra_data = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    categories = Column(ARRAY(String), nullable=True)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    request = relationship("SignatureRequest", back_populates="signed_document")

    def __repr__(self) -> str:
        """String representation."""
        return f"<SignedDocument {self.id} title={self.title} status={self.status}>"

    @property
    def is_complete(self) -> bool:
        """Check if all signatures are collected."""
        return self.total_signatures_collected >= self.total_signatures_required

    @property
    def is_valid(self) -> bool:
        """Check if document is valid."""
        if self.status != SignedDocumentStatus.COMPLETED:
            return False
        if self.integrity_status != DocumentIntegrityStatus.VALID:
            return False
        return True

    @property
    def signatures_remaining(self) -> int:
        """Get number of signatures remaining."""
        return max(0, self.total_signatures_required - self.total_signatures_collected)

    @property
    def completion_percentage(self) -> float:
        """Get completion percentage."""
        if self.total_signatures_required == 0:
            return 100.0
        return (self.total_signatures_collected / self.total_signatures_required) * 100

    @property
    def is_archived(self) -> bool:
        """Check if document is archived."""
        return self.archive_status == ArchiveStatus.ARCHIVED

    @property
    def needs_retention_warning(self) -> bool:
        """Check if retention is expiring soon (30 days)."""
        if self.is_permanent or not self.retention_expires_at:
            return False
        days_until_expiry = (self.retention_expires_at - datetime.utcnow()).days
        return 0 < days_until_expiry <= 30

    def add_signature(
        self,
        signature_id: uuid.UUID,
        signer_name: str,
        signer_email: str | None = None,
        page: int | None = None,
        position: dict | None = None,
    ) -> None:
        """Add a signature to the document."""
        # Update signature IDs
        if self.signature_ids is None:
            self.signature_ids = []
        self.signature_ids.append(signature_id)

        # Update signers
        if self.signers is None:
            self.signers = []
        self.signers.append(
            {
                "name": signer_name,
                "email": signer_email,
                "signed_at": datetime.utcnow().isoformat(),
                "signature_id": str(signature_id),
            }
        )

        # Update positions
        if page is not None and position is not None:
            if self.signature_positions is None:
                self.signature_positions = []
            self.signature_positions.append(
                {
                    "page": page,
                    "signature_id": str(signature_id),
                    **position,
                }
            )

        # Update counts and timestamps
        self.total_signatures_collected += 1
        now = datetime.utcnow()
        if self.first_signature_at is None:
            self.first_signature_at = now
        self.last_signature_at = now

        # Check if complete
        if self.is_complete:
            self.status = SignedDocumentStatus.COMPLETED
            self.completed_at = now
        else:
            self.status = SignedDocumentStatus.PARTIAL

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "title": self.title,
            "reference_code": self.reference_code,
            "status": self.status.value if self.status else None,
            "integrity_status": self.integrity_status.value if self.integrity_status else None,
            "total_signatures_required": self.total_signatures_required,
            "total_signatures_collected": self.total_signatures_collected,
            "signatures_remaining": self.signatures_remaining,
            "completion_percentage": self.completion_percentage,
            "is_complete": self.is_complete,
            "is_valid": self.is_valid,
            "verification_code": self.verification_code,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
