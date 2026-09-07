"""Signature Recognition Models."""

from modules.ai.signature.models.signature import (
    Signature,
    SignatureFormat,
    SignatureSource,
    SignatureStatus,
    SignatureType,
)
from modules.ai.signature.models.signature_request import (
    ReminderFrequency,
    RequestPriority,
    RequestStatus,
    SignaturePurpose,
    SignatureRequest,
)
from modules.ai.signature.models.signature_template import (
    MatchingMode,
    SignatureTemplate,
    TemplateStatus,
    TemplateType,
)
from modules.ai.signature.models.signature_verification import (
    RiskLevel,
    SignatureVerification,
    VerificationMethod,
    VerificationResult,
    VerificationStatus,
)
from modules.ai.signature.models.signed_document import (
    ArchiveStatus,
    DocumentIntegrityStatus,
    SignedDocument,
    SignedDocumentStatus,
)

__all__ = [
    # Signature
    "Signature",
    "SignatureType",
    "SignatureFormat",
    "SignatureStatus",
    "SignatureSource",
    # Template
    "SignatureTemplate",
    "TemplateStatus",
    "TemplateType",
    "MatchingMode",
    # Verification
    "SignatureVerification",
    "VerificationStatus",
    "VerificationMethod",
    "VerificationResult",
    "RiskLevel",
    # Request
    "SignatureRequest",
    "RequestStatus",
    "RequestPriority",
    "SignaturePurpose",
    "ReminderFrequency",
    # Signed Document
    "SignedDocument",
    "SignedDocumentStatus",
    "DocumentIntegrityStatus",
    "ArchiveStatus",
]
