"""Signature Request model for requesting signatures on documents."""

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


class RequestStatus(StrEnum):
    """Status of signature request."""

    DRAFT = "draft"
    PENDING = "pending"
    SENT = "sent"
    VIEWED = "viewed"
    SIGNING = "signing"
    SIGNED = "signed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class RequestPriority(StrEnum):
    """Priority of signature request."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class SignaturePurpose(StrEnum):
    """Purpose of signature."""

    APPROVAL = "approval"
    WITNESS = "witness"
    ACKNOWLEDGMENT = "acknowledgment"
    AUTHORIZATION = "authorization"
    CONSENT = "consent"
    CERTIFICATION = "certification"
    RECEIPT = "receipt"
    CONTRACT = "contract"


class ReminderFrequency(StrEnum):
    """Reminder frequency."""

    NONE = "none"
    DAILY = "daily"
    EVERY_2_DAYS = "every_2_days"
    WEEKLY = "weekly"


class SignatureRequest(Base):
    """Model for signature requests on documents."""

    __tablename__ = "sig_signature_requests"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Request info
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    reference_code = Column(String(50), nullable=True, index=True)

    # Status and priority
    # native_enum=False -> armazena como VARCHAR (o banco criou estas colunas como
    # String(50), sem tipos ENUM nativos). Mantém os objetos StrEnum na leitura.
    status = Column(
        Enum(RequestStatus, native_enum=False, length=50),
        nullable=False,
        default=RequestStatus.DRAFT,
    )
    priority = Column(
        Enum(RequestPriority, native_enum=False, length=50),
        nullable=False,
        default=RequestPriority.NORMAL,
    )
    purpose = Column(
        Enum(SignaturePurpose, native_enum=False, length=50),
        nullable=False,
        default=SignaturePurpose.APPROVAL,
    )

    # Document to sign
    document_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    document_type = Column(String(100), nullable=True)
    document_name = Column(String(255), nullable=True)
    document_path = Column(String(500), nullable=True)
    document_hash = Column(String(128), nullable=True)  # For integrity

    # Signer information
    signer_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    signer_type = Column(String(50), nullable=True)  # user, employee, customer, external
    signer_name = Column(String(255), nullable=False)
    signer_email = Column(String(255), nullable=True)
    signer_phone = Column(String(20), nullable=True)
    signer_document = Column(String(50), nullable=True)  # CPF/CNPJ

    # Template to use for verification
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sig_signature_templates.id"),
        nullable=True,
    )

    # Signature placement
    signature_page = Column(Integer, nullable=True)
    signature_position = Column(JSONB, nullable=True)  # {x, y, width, height}
    signature_field_name = Column(String(100), nullable=True)

    # Multiple signatures support
    signature_order = Column(Integer, default=1)  # Order in multi-sign flow
    total_signers = Column(Integer, default=1)
    parent_request_id = Column(UUID(as_uuid=True), nullable=True)  # For multi-sign

    # Collected signature
    signature_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sig_signatures.id"),
        nullable=True,
    )
    signed_at = Column(DateTime, nullable=True)
    signed_document_path = Column(String(500), nullable=True)
    signed_document_hash = Column(String(128), nullable=True)

    # Deadlines
    due_date = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Reminders
    reminder_frequency = Column(
        Enum(ReminderFrequency, native_enum=False, length=50),
        nullable=False,
        default=ReminderFrequency.NONE,
    )
    reminders_sent = Column(Integer, default=0)
    last_reminder_at = Column(DateTime, nullable=True)
    max_reminders = Column(Integer, default=5)

    # Access control
    access_token = Column(String(255), nullable=True, unique=True)
    access_code = Column(String(10), nullable=True)  # PIN for verification
    requires_authentication = Column(Boolean, default=False)
    allowed_ips = Column(ARRAY(String), nullable=True)

    # Notifications
    notify_on_view = Column(Boolean, default=True)
    notify_on_sign = Column(Boolean, default=True)
    notify_on_reject = Column(Boolean, default=True)
    notification_emails = Column(ARRAY(String), nullable=True)

    # Tracking
    viewed_at = Column(DateTime, nullable=True)
    view_count = Column(Integer, default=0)
    last_activity_at = Column(DateTime, nullable=True)

    # Rejection
    rejected_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Cancellation
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(UUID(as_uuid=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # IP and device info (when signed)
    signing_ip = Column(String(45), nullable=True)
    signing_device = Column(String(255), nullable=True)
    signing_user_agent = Column(String(500), nullable=True)
    signing_location = Column(JSONB, nullable=True)

    # Audit trail
    audit_log = Column(JSONB, nullable=True)

    # Custom fields
    custom_fields = Column(JSONB, nullable=True)
    required_fields = Column(JSONB, nullable=True)  # Fields signer must fill

    # Metadata
    extra_data = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # Workflow
    workflow_id = Column(UUID(as_uuid=True), nullable=True)
    workflow_step = Column(String(100), nullable=True)

    # Requester info
    requested_by = Column(UUID(as_uuid=True), nullable=False)
    requested_by_name = Column(String(255), nullable=True)
    requested_by_email = Column(String(255), nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)

    # Relationships
    template = relationship("SignatureTemplate")
    signature = relationship("Signature")
    verifications = relationship("SignatureVerification", back_populates="request")
    signed_document = relationship("SignedDocument", back_populates="request", uselist=False)

    def __repr__(self) -> str:
        """String representation."""
        return f"<SignatureRequest {self.id} title={self.title} status={self.status}>"

    @property
    def is_pending(self) -> bool:
        """Check if request is pending signature."""
        return self.status in [
            RequestStatus.PENDING,
            RequestStatus.SENT,
            RequestStatus.VIEWED,
            RequestStatus.SIGNING,
        ]

    @property
    def is_signed(self) -> bool:
        """Check if request was signed."""
        return self.status in [RequestStatus.SIGNED, RequestStatus.COMPLETED]

    @property
    def is_expired(self) -> bool:
        """Check if request has expired."""
        if self.status == RequestStatus.EXPIRED:
            return True
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return True
        return False

    @property
    def is_overdue(self) -> bool:
        """Check if request is overdue."""
        if self.is_signed or self.is_expired:
            return False
        if self.due_date and datetime.utcnow() > self.due_date:
            return True
        return False

    @property
    def can_send_reminder(self) -> bool:
        """Check if reminder can be sent."""
        if not self.is_pending:
            return False
        if self.reminder_frequency == ReminderFrequency.NONE:
            return False
        if self.reminders_sent >= self.max_reminders:
            return False
        return True

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "title": self.title,
            "status": self.status.value if self.status else None,
            "priority": self.priority.value if self.priority else None,
            "purpose": self.purpose.value if self.purpose else None,
            "signer_name": self.signer_name,
            "signer_email": self.signer_email,
            "document_name": self.document_name,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_pending": self.is_pending,
            "is_signed": self.is_signed,
            "is_expired": self.is_expired,
            "is_overdue": self.is_overdue,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
