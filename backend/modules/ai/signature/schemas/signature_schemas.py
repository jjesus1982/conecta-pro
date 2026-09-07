"""Signature Recognition Schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ============== Enums ==============


class SignatureTypeEnum(str):
    """Signature type enumeration."""

    HANDWRITTEN = "handwritten"
    DIGITAL = "digital"
    ELECTRONIC = "electronic"
    BIOMETRIC = "biometric"
    SCANNED = "scanned"
    DRAWN = "drawn"


class SignatureStatusEnum(str):
    """Signature status enumeration."""

    PENDING = "pending"
    EXTRACTED = "extracted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


# ============== Request Schemas ==============


class SignatureUploadRequest(BaseModel):
    """Request for uploading a signature."""

    owner_id: UUID | None = None
    owner_type: str | None = Field(None, max_length=50)
    owner_name: str | None = Field(None, max_length=255)
    owner_document: str | None = Field(None, max_length=50)
    signature_type: str = Field(default="handwritten")
    source: str = Field(default="upload")
    image_data: str | None = Field(None, description="Base64 encoded image")
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None
    notes: str | None = None


class SignatureExtractRequest(BaseModel):
    """Request for extracting signatures from image."""

    image_data: str = Field(..., description="Base64 encoded image")
    region: dict[str, int] | None = Field(None, description="Region {x, y, width, height}")
    method: str = Field(default="auto", description="auto, contour, edge, template")
    min_confidence: float = Field(default=0.5, ge=0, le=1)
    max_signatures: int = Field(default=10, ge=1, le=50)


class SignatureCompareRequest(BaseModel):
    """Request for comparing two signatures."""

    signature1_id: UUID | None = None
    signature1_data: dict[str, Any] | None = None
    signature2_id: UUID | None = None
    signature2_data: dict[str, Any] | None = None
    template_id: UUID | None = None
    mode: str = Field(default="normal", description="strict, normal, relaxed")
    custom_threshold: float | None = Field(None, ge=0, le=1)


class SignatureValidateRequest(BaseModel):
    """Request for validating a signature."""

    signature_id: UUID | None = None
    signature_data: dict[str, Any] | None = None
    template_id: UUID | None = None
    context: dict[str, Any] | None = Field(None, description="Validation context (purpose, document_type, etc.)")
    strict_mode: bool = Field(default=False)


class TemplateCreateRequest(BaseModel):
    """Request for creating a signature template."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    code: str | None = Field(None, max_length=50)
    owner_id: UUID
    owner_type: str = Field(..., max_length=50)
    owner_name: str | None = Field(None, max_length=255)
    owner_document: str | None = Field(None, max_length=50)
    template_type: str = Field(default="personal")
    matching_mode: str = Field(default="normal")
    similarity_threshold: float = Field(default=0.75, ge=0, le=1)
    min_samples_required: int = Field(default=3, ge=1, le=10)
    allowed_document_types: list[str] | None = None
    allowed_purposes: list[str] | None = None
    metadata: dict[str, Any] | None = None


class TemplateAddSampleRequest(BaseModel):
    """Request for adding sample to template."""

    signature_id: UUID | None = None
    image_data: str | None = Field(None, description="Base64 encoded image")


class SignatureRequestCreate(BaseModel):
    """Request for creating a signature request."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: str = Field(default="normal")
    purpose: str = Field(default="approval")
    document_id: UUID | None = None
    document_name: str | None = Field(None, max_length=255)
    signer_id: UUID | None = None
    signer_type: str | None = Field(None, max_length=50)
    signer_name: str = Field(..., min_length=1, max_length=255)
    signer_email: str | None = Field(None, max_length=255)
    signer_phone: str | None = Field(None, max_length=20)
    template_id: UUID | None = None
    signature_page: int | None = None
    signature_position: dict[str, int] | None = None
    due_date: datetime | None = None
    expires_at: datetime | None = None
    reminder_frequency: str = Field(default="none")
    requires_authentication: bool = Field(default=False)
    metadata: dict[str, Any] | None = None


class SignatureSubmitRequest(BaseModel):
    """Request for submitting a signature."""

    image_data: str = Field(..., description="Base64 encoded signature image")
    biometric_data: dict[str, Any] | None = None
    device_info: str | None = None
    location: dict[str, Any] | None = None


# ============== Response Schemas ==============


class BoundingBoxResponse(BaseModel):
    """Bounding box response."""

    x: int
    y: int
    width: int
    height: int


class ExtractedSignatureResponse(BaseModel):
    """Extracted signature response."""

    id: str
    bounding_box: BoundingBoxResponse | None = None
    confidence: float
    quality_score: float
    contrast_score: float
    clarity_score: float
    completeness_score: float
    width: int
    height: int
    stroke_count: int
    extraction_method: str
    has_image: bool
    has_features: bool


class ExtractionResultResponse(BaseModel):
    """Extraction result response."""

    success: bool
    signatures: list[ExtractedSignatureResponse]
    total_found: int
    processing_time_ms: int
    errors: list[str]
    warnings: list[str]
    metadata: dict[str, Any]


class FeatureScoreResponse(BaseModel):
    """Feature score response."""

    feature_name: str
    score: float
    weight: float
    weighted_score: float
    details: dict[str, Any]


class ComparisonResultResponse(BaseModel):
    """Comparison result response."""

    is_match: bool
    similarity_score: float
    confidence: float
    threshold_used: float
    feature_scores: list[FeatureScoreResponse]
    method_used: str
    anomalies: list[str]
    warnings: list[str]
    processing_time_ms: int
    metadata: dict[str, Any]


class QualityCheckResponse(BaseModel):
    """Quality check response."""

    passed: bool
    quality_score: float
    issues: list[str]
    recommendations: list[str]
    details: dict[str, Any]


class FraudAnalysisResponse(BaseModel):
    """Fraud analysis response."""

    is_suspicious: bool
    risk_level: str
    fraud_indicators: list[str]
    confidence: float
    analysis_details: dict[str, Any]


class ValidationResultResponse(BaseModel):
    """Validation result response."""

    id: str
    is_valid: bool
    is_authentic: bool
    overall_score: float
    confidence: float
    status: str
    quality_check: QualityCheckResponse | None = None
    comparison_result: ComparisonResultResponse | None = None
    fraud_analysis: FraudAnalysisResponse | None = None
    errors: list[str]
    warnings: list[str]
    processing_time_ms: int


class SignatureResponse(BaseModel):
    """Signature response."""

    id: UUID
    tenant_id: UUID
    owner_id: UUID | None = None
    owner_name: str | None = None
    signature_type: str | None = None
    signature_format: str | None = None
    status: str | None = None
    source: str | None = None
    quality_score: float | None = None
    is_verified: bool
    is_valid: bool
    width: int | None = None
    height: int | None = None
    created_at: datetime | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class TemplateResponse(BaseModel):
    """Template response."""

    id: UUID
    tenant_id: UUID
    name: str
    owner_id: UUID
    owner_name: str | None = None
    template_type: str | None = None
    status: str | None = None
    matching_mode: str | None = None
    sample_count: int
    min_samples_required: int
    similarity_threshold: float
    is_valid: bool
    has_enough_samples: bool
    success_rate: float | None = None
    total_verifications: int
    created_at: datetime | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class VerificationResponse(BaseModel):
    """Verification response."""

    id: UUID
    tenant_id: UUID
    signature_id: UUID
    template_id: UUID | None = None
    status: str | None = None
    result: str | None = None
    risk_level: str | None = None
    method: str | None = None
    overall_score: float | None = None
    similarity_score: float | None = None
    confidence: float | None = None
    passed_threshold: bool | None = None
    is_match: bool
    requires_manual_review: bool
    processing_time_ms: int | None = None
    created_at: datetime | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class SignatureRequestResponse(BaseModel):
    """Signature request response."""

    id: UUID
    tenant_id: UUID
    title: str
    status: str | None = None
    priority: str | None = None
    purpose: str | None = None
    signer_name: str
    signer_email: str | None = None
    document_name: str | None = None
    due_date: datetime | None = None
    expires_at: datetime | None = None
    is_pending: bool
    is_signed: bool
    is_expired: bool
    is_overdue: bool
    signed_at: datetime | None = None
    created_at: datetime | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class SignedDocumentResponse(BaseModel):
    """Signed document response."""

    id: UUID
    tenant_id: UUID
    title: str
    reference_code: str | None = None
    status: str | None = None
    integrity_status: str | None = None
    total_signatures_required: int
    total_signatures_collected: int
    signatures_remaining: int
    completion_percentage: float
    is_complete: bool
    is_valid: bool
    verification_code: str | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class SignatureStatsResponse(BaseModel):
    """Signature statistics response."""

    total_signatures: int
    verified_signatures: int
    pending_signatures: int
    rejected_signatures: int
    total_templates: int
    active_templates: int
    total_verifications: int
    successful_verifications: int
    failed_verifications: int
    average_match_score: float | None = None
    pending_requests: int
    completed_requests: int
    signed_documents: int


# ============== List Response ==============


class SignatureListResponse(BaseModel):
    """Paginated signature list response."""

    items: list[SignatureResponse]
    total: int
    page: int
    size: int
    pages: int


class TemplateListResponse(BaseModel):
    """Paginated template list response."""

    items: list[TemplateResponse]
    total: int
    page: int
    size: int
    pages: int


class RequestListResponse(BaseModel):
    """Paginated request list response."""

    items: list[SignatureRequestResponse]
    total: int
    page: int
    size: int
    pages: int
