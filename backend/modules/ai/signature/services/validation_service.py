"""Signature Validation Service for authenticating and validating signatures."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from modules.ai.signature.services.comparison_service import (
    ComparisonResult,
    SignatureComparisonService,
)
from modules.ai.signature.services.extraction_service import (
    SignatureExtractionService,
)

logger = logging.getLogger(__name__)


@dataclass
class QualityCheckResult:
    """Result of quality check."""

    passed: bool = False
    quality_score: float = 0.0
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "quality_score": self.quality_score,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "details": self.details,
        }


@dataclass
class FraudAnalysisResult:
    """Result of fraud analysis."""

    is_suspicious: bool = False
    risk_level: str = "low"  # low, medium, high, critical
    fraud_indicators: list[str] = field(default_factory=list)
    confidence: float = 0.0
    analysis_details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "is_suspicious": self.is_suspicious,
            "risk_level": self.risk_level,
            "fraud_indicators": self.fraud_indicators,
            "confidence": self.confidence,
            "analysis_details": self.analysis_details,
        }


@dataclass
class ValidationResult:
    """Complete validation result."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_valid: bool = False
    is_authentic: bool = False
    overall_score: float = 0.0
    confidence: float = 0.0
    status: str = "pending"  # pending, valid, invalid, suspicious, error
    quality_check: QualityCheckResult | None = None
    comparison_result: ComparisonResult | None = None
    fraud_analysis: FraudAnalysisResult | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    processing_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "is_valid": self.is_valid,
            "is_authentic": self.is_authentic,
            "overall_score": self.overall_score,
            "confidence": self.confidence,
            "status": self.status,
            "quality_check": self.quality_check.to_dict() if self.quality_check else None,
            "comparison_result": self.comparison_result.to_dict() if self.comparison_result else None,
            "fraud_analysis": self.fraud_analysis.to_dict() if self.fraud_analysis else None,
            "errors": self.errors,
            "warnings": self.warnings,
            "processing_time_ms": self.processing_time_ms,
            "metadata": self.metadata,
        }


class SignatureValidationService:
    """Service for validating and authenticating signatures."""

    # Quality thresholds
    MIN_QUALITY_SCORE = 0.5
    MIN_CONTRAST = 0.3
    MIN_CLARITY = 0.4
    MIN_COMPLETENESS = 0.5

    # Validation thresholds
    VALIDATION_THRESHOLD = 0.70
    HIGH_CONFIDENCE_THRESHOLD = 0.85

    # Fraud detection thresholds
    FRAUD_THRESHOLD = 0.4
    HIGH_RISK_THRESHOLD = 0.6

    def __init__(
        self,
        comparison_service: SignatureComparisonService | None = None,
        extraction_service: SignatureExtractionService | None = None,
        enable_fraud_detection: bool = True,
        enable_quality_check: bool = True,
        strict_mode: bool = False,
    ):
        """Initialize validation service.

        Args:
            comparison_service: Service for comparing signatures
            extraction_service: Service for extracting signatures
            enable_fraud_detection: Enable fraud analysis
            enable_quality_check: Enable quality checks
            strict_mode: Use stricter validation thresholds
        """
        self.comparison_service = comparison_service or SignatureComparisonService()
        self.extraction_service = extraction_service or SignatureExtractionService()
        self.enable_fraud_detection = enable_fraud_detection
        self.enable_quality_check = enable_quality_check
        self.strict_mode = strict_mode

        if strict_mode:
            self.VALIDATION_THRESHOLD = 0.80
            self.MIN_QUALITY_SCORE = 0.6

    def validate(
        self,
        signature: dict[str, Any],
        template: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate a signature.

        Args:
            signature: Signature data to validate
            template: Optional reference template for comparison
            context: Optional validation context (purpose, document type, etc.)

        Returns:
            ValidationResult
        """
        start_time = datetime.utcnow()
        result = ValidationResult()

        try:
            # 1. Quality check
            if self.enable_quality_check:
                result.quality_check = self.check_quality(signature)
                if not result.quality_check.passed:
                    result.status = "invalid"
                    result.warnings.append("Quality check failed")

            # 2. Compare with template if provided
            if template:
                mode = "strict" if self.strict_mode else "normal"
                result.comparison_result = self.comparison_service.compare(signature, template, mode)

                if result.comparison_result.is_match:
                    result.is_authentic = True
                else:
                    result.warnings.append("Signature does not match template")

            # 3. Fraud detection
            if self.enable_fraud_detection:
                result.fraud_analysis = self.analyze_fraud(signature, template, context)
                if result.fraud_analysis.is_suspicious:
                    result.status = "suspicious"
                    result.warnings.append(f"Fraud risk: {result.fraud_analysis.risk_level}")

            # 4. Calculate overall score and validity
            result.overall_score = self._calculate_overall_score(result)
            result.confidence = self._calculate_confidence(result)
            result.is_valid = self._determine_validity(result)

            # 5. Set final status
            if result.errors:
                result.status = "error"
            elif result.is_valid:
                result.status = "valid"
            elif result.fraud_analysis and result.fraud_analysis.is_suspicious:
                result.status = "suspicious"
            else:
                result.status = "invalid"

        except Exception as e:
            logger.error(f"Error validating signature: {e}")
            result.errors.append(str(e))
            result.status = "error"

        end_time = datetime.utcnow()
        result.processing_time_ms = int((end_time - start_time).total_seconds() * 1000)
        result.metadata["context"] = context

        return result

    def check_quality(self, signature: dict[str, Any]) -> QualityCheckResult:
        """Check signature quality.

        Args:
            signature: Signature data

        Returns:
            QualityCheckResult
        """
        result = QualityCheckResult()
        issues = []
        recommendations = []

        # Get quality metrics
        quality_score = signature.get("quality_score", 0)
        contrast = signature.get("contrast_score", 0)
        clarity = signature.get("clarity_score", 0)
        completeness = signature.get("completeness_score", 0)

        # Check overall quality
        if quality_score < self.MIN_QUALITY_SCORE:
            issues.append(f"Low quality score: {quality_score:.2f}")
            recommendations.append("Recapture signature with better lighting")

        # Check contrast
        if contrast < self.MIN_CONTRAST:
            issues.append(f"Low contrast: {contrast:.2f}")
            recommendations.append("Use darker ink or better background")

        # Check clarity
        if clarity < self.MIN_CLARITY:
            issues.append(f"Low clarity: {clarity:.2f}")
            recommendations.append("Ensure signature is in focus")

        # Check completeness
        if completeness < self.MIN_COMPLETENESS:
            issues.append(f"Incomplete signature: {completeness:.2f}")
            recommendations.append("Ensure full signature is captured")

        # Check dimensions
        width = signature.get("width", 0)
        height = signature.get("height", 0)

        if width < 50 or height < 20:
            issues.append("Signature too small")
            recommendations.append("Capture larger signature area")

        if width > 800 or height > 300:
            issues.append("Signature too large")
            recommendations.append("Reduce signature area")

        # Check aspect ratio
        if height > 0:
            aspect_ratio = width / height
            if aspect_ratio < 1.5:
                issues.append("Unusual aspect ratio (too square)")
            elif aspect_ratio > 10:
                issues.append("Unusual aspect ratio (too wide)")

        # Set result
        result.passed = len(issues) == 0
        result.quality_score = quality_score
        result.issues = issues
        result.recommendations = recommendations
        result.details = {
            "contrast": contrast,
            "clarity": clarity,
            "completeness": completeness,
            "width": width,
            "height": height,
        }

        return result

    def analyze_fraud(
        self,
        signature: dict[str, Any],
        template: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> FraudAnalysisResult:
        """Analyze signature for fraud indicators.

        Args:
            signature: Signature to analyze
            template: Reference template
            context: Validation context

        Returns:
            FraudAnalysisResult
        """
        result = FraudAnalysisResult()
        indicators = []
        analysis = {}

        # 1. Check for copy/paste indicators
        copy_paste_score = self._detect_copy_paste(signature)
        analysis["copy_paste_score"] = copy_paste_score
        if copy_paste_score > 0.7:
            indicators.append("Possible copy/paste detected")

        # 2. Check for digital manipulation
        manipulation_score = self._detect_manipulation(signature)
        analysis["manipulation_score"] = manipulation_score
        if manipulation_score > 0.6:
            indicators.append("Possible digital manipulation")

        # 3. Check for tracing indicators
        tracing_score = self._detect_tracing(signature)
        analysis["tracing_score"] = tracing_score
        if tracing_score > 0.5:
            indicators.append("Possible tracing detected")

        # 4. Check consistency with template
        if template:
            consistency = self._check_consistency(signature, template)
            analysis["consistency"] = consistency
            if consistency.get("variation_score", 0) > 0.8:
                indicators.append("Excessive variation from template")
            if consistency.get("too_perfect", False):
                indicators.append("Suspiciously perfect match")

        # 5. Context-based checks
        if context:
            context_score = self._context_check(signature, context)
            analysis["context_score"] = context_score
            if context_score < 0.5:
                indicators.append("Context anomaly detected")

        # 6. Biometric anomalies
        biometric_score = self._check_biometric_anomalies(signature)
        analysis["biometric_score"] = biometric_score
        if biometric_score > 0.6:
            indicators.append("Biometric pattern anomaly")

        # Calculate risk level
        risk_score = self._calculate_risk_score(indicators, analysis)
        analysis["risk_score"] = risk_score

        if risk_score >= self.HIGH_RISK_THRESHOLD:
            result.risk_level = "high"
        elif risk_score >= self.FRAUD_THRESHOLD:
            result.risk_level = "medium"
        else:
            result.risk_level = "low"

        result.is_suspicious = risk_score >= self.FRAUD_THRESHOLD
        result.fraud_indicators = indicators
        result.confidence = min(1.0, risk_score + 0.3)
        result.analysis_details = analysis

        return result

    def validate_certificate(
        self,
        certificate_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate digital certificate.

        Args:
            certificate_data: Certificate information

        Returns:
            Validation result
        """
        result = {
            "is_valid": False,
            "errors": [],
            "warnings": [],
            "details": {},
        }

        # Check certificate existence
        cert_id = certificate_data.get("certificate_id")
        if not cert_id:
            result["errors"].append("No certificate ID provided")
            return result

        # Check validity period
        valid_from = certificate_data.get("certificate_valid_from")
        valid_to = certificate_data.get("certificate_valid_to")
        now = datetime.utcnow()

        if valid_from and valid_from > now:
            result["errors"].append("Certificate not yet valid")
        if valid_to and valid_to < now:
            result["errors"].append("Certificate has expired")

        # Check issuer
        issuer = certificate_data.get("certificate_issuer")
        trusted_issuers = ["ICP-Brasil", "Serasa", "Certisign", "Valid"]

        if issuer and issuer not in trusted_issuers:
            result["warnings"].append(f"Unknown certificate issuer: {issuer}")

        # Check hash algorithm
        hash_algo = certificate_data.get("hash_algorithm", "")
        weak_algorithms = ["md5", "sha1"]

        if hash_algo.lower() in weak_algorithms:
            result["warnings"].append(f"Weak hash algorithm: {hash_algo}")

        # Verify signature hash if present
        signature_hash = certificate_data.get("signature_hash")
        if signature_hash:
            result["details"]["hash_present"] = True
            result["details"]["hash_length"] = len(signature_hash)

        result["is_valid"] = len(result["errors"]) == 0
        result["details"]["issuer"] = issuer
        result["details"]["algorithm"] = hash_algo

        return result

    def validate_document_integrity(
        self,
        document_hash: str,
        expected_hash: str,
        algorithm: str = "sha256",
    ) -> dict[str, Any]:
        """Validate document integrity.

        Args:
            document_hash: Current document hash
            expected_hash: Expected hash
            algorithm: Hash algorithm used

        Returns:
            Validation result
        """
        result = {
            "is_valid": False,
            "algorithm": algorithm,
            "match": False,
        }

        # Normalize hashes
        current = document_hash.lower().strip()
        expected = expected_hash.lower().strip()

        # Compare
        result["match"] = current == expected
        result["is_valid"] = result["match"]

        if not result["match"]:
            result["error"] = "Document has been modified"
            result["current_hash"] = current[:16] + "..."
            result["expected_hash"] = expected[:16] + "..."

        return result

    def _calculate_overall_score(self, result: ValidationResult) -> float:
        """Calculate overall validation score."""
        scores = []
        weights = []

        # Quality score
        if result.quality_check:
            scores.append(result.quality_check.quality_score)
            weights.append(0.2)

        # Comparison score
        if result.comparison_result:
            scores.append(result.comparison_result.similarity_score)
            weights.append(0.5)

        # Fraud score (inverted - lower is better)
        if result.fraud_analysis:
            fraud_score = 1 - result.fraud_analysis.analysis_details.get("risk_score", 0)
            scores.append(fraud_score)
            weights.append(0.3)

        if not scores:
            return 0.0

        total_weight = sum(weights)
        weighted_score = sum(s * w for s, w in zip(scores, weights, strict=False))

        return weighted_score / total_weight if total_weight > 0 else 0.0

    def _calculate_confidence(self, result: ValidationResult) -> float:
        """Calculate confidence in validation result."""
        base_confidence = result.overall_score

        # Reduce confidence for warnings
        warning_penalty = len(result.warnings) * 0.05

        # Reduce confidence if fraud detected
        if result.fraud_analysis and result.fraud_analysis.is_suspicious:
            warning_penalty += 0.2

        return max(0, min(1, base_confidence - warning_penalty))

    def _determine_validity(self, result: ValidationResult) -> bool:
        """Determine if signature is valid."""
        # Must pass minimum score
        if result.overall_score < self.VALIDATION_THRESHOLD:
            return False

        # Must not have critical errors
        if result.errors:
            return False

        # Must not be suspicious (unless overridden)
        if result.fraud_analysis and result.fraud_analysis.risk_level in ["high", "critical"]:
            return False

        return True

    def _detect_copy_paste(self, signature: dict[str, Any]) -> float:
        """Detect copy/paste indicators."""
        # Check for perfectly rectangular edges
        # Check for compression artifacts
        # Check for uniform background

        quality = signature.get("quality_score", 0.5)
        completeness = signature.get("completeness_score", 0.5)

        # Copy/paste often has perfect completeness but artifacts
        if completeness > 0.95 and quality < 0.7:
            return 0.6

        return 0.1

    def _detect_manipulation(self, signature: dict[str, Any]) -> float:
        """Detect digital manipulation."""
        # Check for inconsistent compression
        # Check for edge irregularities
        # Check for noise patterns

        clarity = signature.get("clarity_score", 0.5)
        contrast = signature.get("contrast_score", 0.5)

        # Manipulation often affects clarity/contrast relationship
        if abs(clarity - contrast) > 0.4:
            return 0.5

        return 0.1

    def _detect_tracing(self, signature: dict[str, Any]) -> float:
        """Detect tracing indicators."""
        # Check for unnatural stroke patterns
        # Check for too-smooth curves
        # Check for lack of pressure variation

        stroke_count = signature.get("stroke_count", 0)
        has_pressure = bool(signature.get("pressure_data"))

        # Tracing often has too few strokes and no pressure data
        if stroke_count < 5 and not has_pressure:
            return 0.4

        return 0.1

    def _check_consistency(
        self,
        signature: dict[str, Any],
        template: dict[str, Any],
    ) -> dict[str, Any]:
        """Check consistency with template."""
        result = {
            "variation_score": 0.0,
            "too_perfect": False,
        }

        # Get comparison if we have feature vectors
        vec1 = signature.get("feature_vector", [])
        vec2 = template.get("master_feature_vector", [])

        if vec1 and vec2:
            # Calculate variation
            min_len = min(len(vec1), len(vec2))
            if min_len > 0:
                diffs = [abs(vec1[i] - vec2[i]) for i in range(min_len)]
                avg_diff = sum(diffs) / len(diffs)
                result["variation_score"] = avg_diff

                # Check if too perfect (exact match is suspicious)
                if avg_diff < 0.01:
                    result["too_perfect"] = True

        return result

    def _context_check(
        self,
        signature: dict[str, Any],
        context: dict[str, Any],
    ) -> float:
        """Check signature against context."""
        score = 1.0

        # Check time-based anomalies
        capture_time = signature.get("created_at")
        expected_window = context.get("expected_time_window")

        if capture_time and expected_window:
            # Check if capture time is within expected window
            pass  # Implementation depends on time format

        # Check location anomalies
        capture_location = signature.get("capture_location")
        expected_location = context.get("expected_location")

        if capture_location and expected_location:
            # Check if locations match
            pass  # Implementation depends on location format

        return score

    def _check_biometric_anomalies(self, signature: dict[str, Any]) -> float:
        """Check for biometric pattern anomalies."""
        pressure = signature.get("pressure_data", [])
        velocity = signature.get("velocity_data", [])
        timing = signature.get("timing_data", [])

        anomaly_score = 0.0

        # Check for unnatural pressure patterns
        if pressure:
            # Constant pressure is suspicious
            if len(set(pressure)) < 3:
                anomaly_score += 0.3

        # Check for unnatural velocity patterns
        if velocity:
            # Constant velocity is suspicious
            if len(set(velocity)) < 3:
                anomaly_score += 0.3

        # Check for timing anomalies
        if timing:
            # Very fast or very slow is suspicious
            total_time = max(timing) - min(timing) if timing else 0
            if total_time < 0.5 or total_time > 30:
                anomaly_score += 0.2

        return min(1.0, anomaly_score)

    def _calculate_risk_score(
        self,
        indicators: list[str],
        analysis: dict[str, Any],
    ) -> float:
        """Calculate overall fraud risk score."""
        # Base score from number of indicators
        base_score = len(indicators) * 0.15

        # Add scores from analysis
        scores = [
            analysis.get("copy_paste_score", 0) * 0.25,
            analysis.get("manipulation_score", 0) * 0.25,
            analysis.get("tracing_score", 0) * 0.2,
            analysis.get("biometric_score", 0) * 0.15,
        ]

        # Context anomaly
        context_score = analysis.get("context_score", 1.0)
        if context_score < 0.5:
            scores.append((1 - context_score) * 0.15)

        total_score = base_score + sum(scores)

        return min(1.0, total_score)
