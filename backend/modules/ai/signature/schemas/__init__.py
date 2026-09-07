"""Signature Recognition Schemas."""

from modules.ai.signature.schemas.signature_schemas import (
    # Response Schemas
    BoundingBoxResponse,
    ComparisonResultResponse,
    ExtractedSignatureResponse,
    ExtractionResultResponse,
    FeatureScoreResponse,
    FraudAnalysisResponse,
    QualityCheckResponse,
    RequestListResponse,
    SignatureCompareRequest,
    SignatureExtractRequest,
    # List Responses
    SignatureListResponse,
    SignatureRequestCreate,
    SignatureRequestResponse,
    SignatureResponse,
    SignatureStatsResponse,
    SignatureSubmitRequest,
    # Request Schemas
    SignatureUploadRequest,
    SignatureValidateRequest,
    SignedDocumentResponse,
    TemplateAddSampleRequest,
    TemplateCreateRequest,
    TemplateListResponse,
    TemplateResponse,
    ValidationResultResponse,
    VerificationResponse,
)

__all__ = [
    # Request Schemas
    "SignatureUploadRequest",
    "SignatureExtractRequest",
    "SignatureCompareRequest",
    "SignatureValidateRequest",
    "TemplateCreateRequest",
    "TemplateAddSampleRequest",
    "SignatureRequestCreate",
    "SignatureSubmitRequest",
    # Response Schemas
    "BoundingBoxResponse",
    "ExtractedSignatureResponse",
    "ExtractionResultResponse",
    "FeatureScoreResponse",
    "ComparisonResultResponse",
    "QualityCheckResponse",
    "FraudAnalysisResponse",
    "ValidationResultResponse",
    "SignatureResponse",
    "TemplateResponse",
    "VerificationResponse",
    "SignatureRequestResponse",
    "SignedDocumentResponse",
    "SignatureStatsResponse",
    # List Responses
    "SignatureListResponse",
    "TemplateListResponse",
    "RequestListResponse",
]
