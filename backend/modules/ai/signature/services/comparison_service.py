"""Signature Comparison Service for matching signatures."""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FeatureScore:
    """Score for individual feature comparison."""

    feature_name: str
    score: float  # 0-1
    weight: float
    weighted_score: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "feature_name": self.feature_name,
            "score": self.score,
            "weight": self.weight,
            "weighted_score": self.weighted_score,
            "details": self.details,
        }


@dataclass
class ComparisonResult:
    """Result of signature comparison."""

    is_match: bool = False
    similarity_score: float = 0.0  # 0-1
    confidence: float = 0.0  # 0-1
    threshold_used: float = 0.75
    feature_scores: list[FeatureScore] = field(default_factory=list)
    method_used: str = "hybrid"
    anomalies: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    processing_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "is_match": self.is_match,
            "similarity_score": self.similarity_score,
            "confidence": self.confidence,
            "threshold_used": self.threshold_used,
            "feature_scores": [f.to_dict() for f in self.feature_scores],
            "method_used": self.method_used,
            "anomalies": self.anomalies,
            "warnings": self.warnings,
            "processing_time_ms": self.processing_time_ms,
            "metadata": self.metadata,
        }


@dataclass
class BiometricComparisonResult:
    """Result of biometric data comparison."""

    pressure_match: float = 0.0
    velocity_match: float = 0.0
    timing_match: float = 0.0
    overall_biometric_score: float = 0.0
    is_consistent: bool = False
    anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "pressure_match": self.pressure_match,
            "velocity_match": self.velocity_match,
            "timing_match": self.timing_match,
            "overall_biometric_score": self.overall_biometric_score,
            "is_consistent": self.is_consistent,
            "anomalies": self.anomalies,
        }


class SignatureComparisonService:
    """Service for comparing and matching signatures."""

    # Feature weights
    FEATURE_WEIGHTS = {
        "geometric": 0.15,
        "contour": 0.25,
        "feature_vector": 0.30,
        "stroke": 0.15,
        "quality": 0.15,
    }

    # Biometric weights (when available)
    BIOMETRIC_WEIGHTS = {
        "pressure": 0.35,
        "velocity": 0.35,
        "timing": 0.30,
    }

    def __init__(
        self,
        default_threshold: float = 0.75,
        strict_threshold: float = 0.85,
        relaxed_threshold: float = 0.65,
        enable_biometric: bool = True,
        enable_anomaly_detection: bool = True,
    ):
        """Initialize comparison service.

        Args:
            default_threshold: Default similarity threshold
            strict_threshold: Strict mode threshold
            relaxed_threshold: Relaxed mode threshold
            enable_biometric: Enable biometric comparison
            enable_anomaly_detection: Enable anomaly detection
        """
        self.default_threshold = default_threshold
        self.strict_threshold = strict_threshold
        self.relaxed_threshold = relaxed_threshold
        self.enable_biometric = enable_biometric
        self.enable_anomaly_detection = enable_anomaly_detection

    def compare(
        self,
        signature1: dict[str, Any],
        signature2: dict[str, Any],
        mode: str = "normal",
        custom_threshold: float | None = None,
    ) -> ComparisonResult:
        """Compare two signatures.

        Args:
            signature1: First signature data
            signature2: Second signature data (or template)
            mode: Comparison mode (strict, normal, relaxed)
            custom_threshold: Optional custom threshold

        Returns:
            ComparisonResult
        """
        start_time = datetime.utcnow()
        result = ComparisonResult()

        # Determine threshold
        if custom_threshold is not None:
            threshold = custom_threshold
        elif mode == "strict":
            threshold = self.strict_threshold
        elif mode == "relaxed":
            threshold = self.relaxed_threshold
        else:
            threshold = self.default_threshold

        result.threshold_used = threshold
        result.method_used = "hybrid"

        try:
            feature_scores = []

            # 1. Geometric comparison
            geo_score = self._compare_geometric(signature1, signature2)
            feature_scores.append(
                FeatureScore(
                    feature_name="geometric",
                    score=geo_score["score"],
                    weight=self.FEATURE_WEIGHTS["geometric"],
                    weighted_score=geo_score["score"] * self.FEATURE_WEIGHTS["geometric"],
                    details=geo_score,
                )
            )

            # 2. Contour comparison
            contour_score = self._compare_contours(signature1, signature2)
            feature_scores.append(
                FeatureScore(
                    feature_name="contour",
                    score=contour_score["score"],
                    weight=self.FEATURE_WEIGHTS["contour"],
                    weighted_score=contour_score["score"] * self.FEATURE_WEIGHTS["contour"],
                    details=contour_score,
                )
            )

            # 3. Feature vector comparison
            feature_score = self._compare_feature_vectors(signature1, signature2)
            feature_scores.append(
                FeatureScore(
                    feature_name="feature_vector",
                    score=feature_score["score"],
                    weight=self.FEATURE_WEIGHTS["feature_vector"],
                    weighted_score=feature_score["score"] * self.FEATURE_WEIGHTS["feature_vector"],
                    details=feature_score,
                )
            )

            # 4. Stroke comparison
            stroke_score = self._compare_strokes(signature1, signature2)
            feature_scores.append(
                FeatureScore(
                    feature_name="stroke",
                    score=stroke_score["score"],
                    weight=self.FEATURE_WEIGHTS["stroke"],
                    weighted_score=stroke_score["score"] * self.FEATURE_WEIGHTS["stroke"],
                    details=stroke_score,
                )
            )

            # 5. Quality comparison
            quality_score = self._compare_quality(signature1, signature2)
            feature_scores.append(
                FeatureScore(
                    feature_name="quality",
                    score=quality_score["score"],
                    weight=self.FEATURE_WEIGHTS["quality"],
                    weighted_score=quality_score["score"] * self.FEATURE_WEIGHTS["quality"],
                    details=quality_score,
                )
            )

            # Calculate overall similarity
            total_weighted_score = sum(f.weighted_score for f in feature_scores)
            total_weight = sum(f.weight for f in feature_scores)
            similarity = total_weighted_score / total_weight if total_weight > 0 else 0

            # Biometric comparison (if available)
            biometric_score = None
            if self.enable_biometric:
                biometric_result = self._compare_biometric(signature1, signature2)
                if biometric_result.overall_biometric_score > 0:
                    # Blend biometric score
                    similarity = similarity * 0.7 + biometric_result.overall_biometric_score * 0.3
                    biometric_score = biometric_result

            # Anomaly detection
            anomalies = []
            if self.enable_anomaly_detection:
                anomalies = self._detect_anomalies(signature1, signature2, feature_scores)

            # Calculate confidence
            confidence = self._calculate_confidence(feature_scores, anomalies)

            # Determine match
            is_match = similarity >= threshold and len(anomalies) == 0

            result.is_match = is_match
            result.similarity_score = round(similarity, 4)
            result.confidence = round(confidence, 4)
            result.feature_scores = feature_scores
            result.anomalies = anomalies
            result.metadata = {
                "mode": mode,
                "biometric_available": biometric_score is not None,
                "biometric_score": biometric_score.to_dict() if biometric_score else None,
            }

        except Exception as e:
            logger.error(f"Error comparing signatures: {e}")
            result.warnings.append(str(e))

        end_time = datetime.utcnow()
        result.processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

        return result

    def compare_with_template(
        self,
        signature: dict[str, Any],
        template: dict[str, Any],
        mode: str = "normal",
    ) -> ComparisonResult:
        """Compare signature against a template.

        Args:
            signature: Signature to verify
            template: Reference template with multiple samples

        Returns:
            ComparisonResult
        """
        # Get template's master feature vector
        master_features = template.get("master_feature_vector")
        threshold = template.get("similarity_threshold", self.default_threshold)

        if master_features:
            # Compare against master
            template_sig = {"feature_vector": master_features}
            return self.compare(signature, template_sig, mode, threshold)
        else:
            # Compare against individual samples if no master
            return self.compare(signature, template, mode, threshold)

    def compare_batch(
        self,
        signature: dict[str, Any],
        candidates: list[dict[str, Any]],
        mode: str = "normal",
        top_n: int = 5,
    ) -> list[tuple[int, ComparisonResult]]:
        """Compare signature against multiple candidates.

        Args:
            signature: Signature to verify
            candidates: List of candidate signatures
            mode: Comparison mode
            top_n: Return top N matches

        Returns:
            List of (index, ComparisonResult) sorted by similarity
        """
        results = []

        for idx, candidate in enumerate(candidates):
            result = self.compare(signature, candidate, mode)
            results.append((idx, result))

        # Sort by similarity score descending
        results.sort(key=lambda x: x[1].similarity_score, reverse=True)

        return results[:top_n]

    def _compare_geometric(
        self,
        sig1: dict[str, Any],
        sig2: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare geometric properties."""
        # Get dimensions
        w1, h1 = sig1.get("width", 100), sig1.get("height", 50)
        w2, h2 = sig2.get("width", 100), sig2.get("height", 50)

        # Aspect ratio comparison
        ar1 = w1 / max(h1, 1)
        ar2 = w2 / max(h2, 1)
        ar_diff = abs(ar1 - ar2) / max(ar1, ar2, 1)
        ar_score = max(0, 1 - ar_diff)

        # Size ratio comparison (normalized)
        area1 = w1 * h1
        area2 = w2 * h2
        area_ratio = min(area1, area2) / max(area1, area2, 1)

        # Combined score
        score = ar_score * 0.6 + area_ratio * 0.4

        return {
            "score": round(score, 4),
            "aspect_ratio_score": round(ar_score, 4),
            "area_ratio_score": round(area_ratio, 4),
            "sig1_aspect_ratio": round(ar1, 2),
            "sig2_aspect_ratio": round(ar2, 2),
        }

    def _compare_contours(
        self,
        sig1: dict[str, Any],
        sig2: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare contour data."""
        contour1 = sig1.get("contour_data", [])
        contour2 = sig2.get("contour_data", [])

        if not contour1 or not contour2:
            return {"score": 0.5, "reason": "No contour data available"}

        # Calculate centroid distance
        centroid1 = self._calculate_centroid(contour1)
        centroid2 = self._calculate_centroid(contour2)

        # Normalize contours
        norm_contour1 = self._normalize_contour(contour1, centroid1)
        norm_contour2 = self._normalize_contour(contour2, centroid2)

        # Calculate Hausdorff-like distance
        distance = self._contour_distance(norm_contour1, norm_contour2)

        # Convert distance to similarity score
        score = max(0, 1 - distance / 100)

        return {
            "score": round(score, 4),
            "distance": round(distance, 2),
            "points_compared": min(len(contour1), len(contour2)),
        }

    def _compare_feature_vectors(
        self,
        sig1: dict[str, Any],
        sig2: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare feature vectors using cosine similarity."""
        vec1 = sig1.get("feature_vector", [])
        vec2 = sig2.get("feature_vector", [])

        if not vec1 or not vec2:
            return {"score": 0.5, "reason": "No feature vectors available"}

        # Ensure same length
        min_len = min(len(vec1), len(vec2))
        vec1 = vec1[:min_len]
        vec2 = vec2[:min_len]

        # Calculate cosine similarity
        cosine_sim = self._cosine_similarity(vec1, vec2)

        # Calculate Euclidean distance (normalized)
        euclidean_dist = self._euclidean_distance(vec1, vec2)
        euclidean_score = max(0, 1 - euclidean_dist / (len(vec1) ** 0.5))

        # Combined score (weight cosine more)
        score = cosine_sim * 0.7 + euclidean_score * 0.3

        return {
            "score": round(score, 4),
            "cosine_similarity": round(cosine_sim, 4),
            "euclidean_score": round(euclidean_score, 4),
            "vector_length": min_len,
        }

    def _compare_strokes(
        self,
        sig1: dict[str, Any],
        sig2: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare stroke characteristics."""
        strokes1 = sig1.get("stroke_count", 0)
        strokes2 = sig2.get("stroke_count", 0)

        if strokes1 == 0 and strokes2 == 0:
            return {"score": 0.5, "reason": "No stroke data"}

        # Stroke count similarity
        max_strokes = max(strokes1, strokes2, 1)
        stroke_diff = abs(strokes1 - strokes2)
        stroke_score = max(0, 1 - stroke_diff / max_strokes)

        # Density comparison if available
        density1 = sig1.get("stroke_density", 0)
        density2 = sig2.get("stroke_density", 0)
        density_score = 0.5

        if density1 > 0 and density2 > 0:
            max_density = max(density1, density2)
            density_diff = abs(density1 - density2)
            density_score = max(0, 1 - density_diff / max_density)

        score = stroke_score * 0.6 + density_score * 0.4

        return {
            "score": round(score, 4),
            "stroke_count_score": round(stroke_score, 4),
            "density_score": round(density_score, 4),
            "strokes1": strokes1,
            "strokes2": strokes2,
        }

    def _compare_quality(
        self,
        sig1: dict[str, Any],
        sig2: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare quality metrics."""
        q1 = sig1.get("quality_score", 0.5)
        q2 = sig2.get("quality_score", 0.5)

        # Quality scores should be similar (both good or both degraded)
        quality_diff = abs(q1 - q2)
        quality_score = max(0, 1 - quality_diff)

        # Average quality (for weighting purposes)
        avg_quality = (q1 + q2) / 2

        return {
            "score": round(quality_score, 4),
            "average_quality": round(avg_quality, 4),
            "quality_difference": round(quality_diff, 4),
        }

    def _compare_biometric(
        self,
        sig1: dict[str, Any],
        sig2: dict[str, Any],
    ) -> BiometricComparisonResult:
        """Compare biometric data (pressure, velocity, timing)."""
        result = BiometricComparisonResult()

        pressure1 = sig1.get("pressure_data")
        pressure2 = sig2.get("pressure_data")
        velocity1 = sig1.get("velocity_data")
        velocity2 = sig2.get("velocity_data")
        timing1 = sig1.get("timing_data")
        timing2 = sig2.get("timing_data")

        scores = []

        # Pressure comparison
        if pressure1 and pressure2:
            result.pressure_match = self._compare_time_series(pressure1, pressure2)
            scores.append(result.pressure_match * self.BIOMETRIC_WEIGHTS["pressure"])

        # Velocity comparison
        if velocity1 and velocity2:
            result.velocity_match = self._compare_time_series(velocity1, velocity2)
            scores.append(result.velocity_match * self.BIOMETRIC_WEIGHTS["velocity"])

        # Timing comparison
        if timing1 and timing2:
            result.timing_match = self._compare_time_series(timing1, timing2)
            scores.append(result.timing_match * self.BIOMETRIC_WEIGHTS["timing"])

        if scores:
            result.overall_biometric_score = sum(scores) / sum(self.BIOMETRIC_WEIGHTS.values())
            result.is_consistent = result.overall_biometric_score >= 0.7

        return result

    def _detect_anomalies(
        self,
        sig1: dict[str, Any],
        sig2: dict[str, Any],
        feature_scores: list[FeatureScore],
    ) -> list[str]:
        """Detect potential forgery indicators."""
        anomalies = []

        # Check for extreme score differences
        scores = [f.score for f in feature_scores]
        if scores:
            score_std = np.std(scores)
            if score_std > 0.3:
                anomalies.append("Inconsistent feature scores detected")

        # Check if any critical feature has very low score
        for f in feature_scores:
            if f.feature_name in ["contour", "feature_vector"] and f.score < 0.3:
                anomalies.append(f"Low {f.feature_name} similarity ({f.score:.2f})")

        # Check for suspicious quality mismatch
        q1 = sig1.get("quality_score", 0.5)
        q2 = sig2.get("quality_score", 0.5)
        if abs(q1 - q2) > 0.4:
            anomalies.append("Significant quality difference")

        return anomalies

    def _calculate_confidence(
        self,
        feature_scores: list[FeatureScore],
        anomalies: list[str],
    ) -> float:
        """Calculate confidence in the comparison result."""
        # Base confidence from feature consistency
        scores = [f.score for f in feature_scores]
        if not scores:
            return 0.5

        mean_score = np.mean(scores)
        std_score = np.std(scores)

        # Higher confidence when scores are consistent
        consistency_factor = max(0, 1 - std_score * 2)

        # Reduce confidence for anomalies
        anomaly_penalty = len(anomalies) * 0.1

        confidence = mean_score * consistency_factor - anomaly_penalty
        return max(0, min(1, confidence))

    def _calculate_centroid(self, points: list[list[int]]) -> tuple[float, float]:
        """Calculate centroid of points."""
        if not points:
            return (0, 0)
        x_sum = sum(p[0] for p in points)
        y_sum = sum(p[1] for p in points)
        n = len(points)
        return (x_sum / n, y_sum / n)

    def _normalize_contour(
        self,
        points: list[list[int]],
        centroid: tuple[float, float],
    ) -> list[list[float]]:
        """Normalize contour points relative to centroid."""
        if not points:
            return []

        # Translate to origin
        translated = [[p[0] - centroid[0], p[1] - centroid[1]] for p in points]

        # Scale to unit size
        max_dist = max(math.sqrt(p[0] ** 2 + p[1] ** 2) for p in translated) or 1

        return [[p[0] / max_dist, p[1] / max_dist] for p in translated]

    def _contour_distance(
        self,
        contour1: list[list[float]],
        contour2: list[list[float]],
    ) -> float:
        """Calculate distance between contours."""
        if not contour1 or not contour2:
            return 100

        # Sample points for comparison
        sample_size = min(50, len(contour1), len(contour2))
        step1 = max(1, len(contour1) // sample_size)
        step2 = max(1, len(contour2) // sample_size)

        sampled1 = contour1[::step1][:sample_size]
        sampled2 = contour2[::step2][:sample_size]

        # Calculate average minimum distance
        total_dist = 0
        for p1 in sampled1:
            min_dist = min(math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) for p2 in sampled2)
            total_dist += min_dist

        return total_dist / len(sampled1) * 100

    def _cosine_similarity(
        self,
        vec1: list[float],
        vec2: list[float],
    ) -> float:
        """Calculate cosine similarity between vectors."""
        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        norm1 = math.sqrt(sum(a**2 for a in vec1))
        norm2 = math.sqrt(sum(b**2 for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0

        similarity = dot_product / (norm1 * norm2)
        # Normalize to 0-1 range (cosine is -1 to 1)
        return (similarity + 1) / 2

    def _euclidean_distance(
        self,
        vec1: list[float],
        vec2: list[float],
    ) -> float:
        """Calculate Euclidean distance between vectors."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec1, vec2, strict=False)))

    def _compare_time_series(
        self,
        series1: list[float],
        series2: list[float],
    ) -> float:
        """Compare two time series using DTW-like approach."""
        if not series1 or not series2:
            return 0

        # Normalize lengths
        min_len = min(len(series1), len(series2))
        s1 = np.array(series1[:min_len])
        s2 = np.array(series2[:min_len])

        # Normalize values
        s1 = (s1 - np.mean(s1)) / (np.std(s1) or 1)
        s2 = (s2 - np.mean(s2)) / (np.std(s2) or 1)

        # Calculate correlation
        correlation = np.corrcoef(s1, s2)[0, 1]

        # Convert to similarity score
        return max(0, (correlation + 1) / 2)
