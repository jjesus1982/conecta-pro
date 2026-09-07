"""Signature Recognition Services."""

from modules.ai.signature.services.comparison_service import (
    BiometricComparisonResult,
    ComparisonResult,
    FeatureScore,
    SignatureComparisonService,
)
from modules.ai.signature.services.extraction_service import (
    BoundingBox,
    ExtractedSignature,
    ExtractionResult,
    SignatureExtractionService,
)
from modules.ai.signature.services.validation_service import (
    FraudAnalysisResult,
    QualityCheckResult,
    SignatureValidationService,
    ValidationResult,
)

__all__ = [
    # Extraction Service
    "SignatureExtractionService",
    "ExtractedSignature",
    "ExtractionResult",
    "BoundingBox",
    # Comparison Service
    "SignatureComparisonService",
    "ComparisonResult",
    "FeatureScore",
    "BiometricComparisonResult",
    # Validation Service
    "SignatureValidationService",
    "ValidationResult",
    "QualityCheckResult",
    "FraudAnalysisResult",
]
