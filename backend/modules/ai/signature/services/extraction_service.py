"""Signature Extraction Service for extracting signatures from images."""

import base64
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    """Bounding box for detected region."""

    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @property
    def area(self) -> int:
        """Calculate area."""
        return self.width * self.height

    @property
    def aspect_ratio(self) -> float:
        """Calculate aspect ratio."""
        if self.height == 0:
            return 0
        return self.width / self.height


@dataclass
class ExtractedSignature:
    """Extracted signature data."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    image_data: str | None = None  # Base64
    bounding_box: BoundingBox | None = None
    confidence: float = 0.0
    quality_score: float = 0.0
    contrast_score: float = 0.0
    clarity_score: float = 0.0
    completeness_score: float = 0.0
    width: int = 0
    height: int = 0
    feature_vector: list[float] | None = None
    contour_data: list[list[int]] | None = None
    stroke_count: int = 0
    extraction_method: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "bounding_box": self.bounding_box.to_dict() if self.bounding_box else None,
            "confidence": self.confidence,
            "quality_score": self.quality_score,
            "contrast_score": self.contrast_score,
            "clarity_score": self.clarity_score,
            "completeness_score": self.completeness_score,
            "width": self.width,
            "height": self.height,
            "stroke_count": self.stroke_count,
            "extraction_method": self.extraction_method,
            "has_image": self.image_data is not None,
            "has_features": self.feature_vector is not None,
        }


@dataclass
class ExtractionResult:
    """Result of signature extraction."""

    success: bool = False
    signatures: list[ExtractedSignature] = field(default_factory=list)
    total_found: int = 0
    processing_time_ms: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "signatures": [s.to_dict() for s in self.signatures],
            "total_found": self.total_found,
            "processing_time_ms": self.processing_time_ms,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


class SignatureExtractionService:
    """Service for extracting signatures from images and documents."""

    # Signature detection parameters
    MIN_SIGNATURE_WIDTH = 50
    MAX_SIGNATURE_WIDTH = 800
    MIN_SIGNATURE_HEIGHT = 20
    MAX_SIGNATURE_HEIGHT = 300
    MIN_ASPECT_RATIO = 1.5
    MAX_ASPECT_RATIO = 10.0
    MIN_AREA = 2000
    MAX_AREA = 200000

    # Quality thresholds
    MIN_CONTRAST = 0.2
    MIN_CLARITY = 0.3
    MIN_COMPLETENESS = 0.4

    def __init__(
        self,
        min_confidence: float = 0.5,
        enable_preprocessing: bool = True,
        enable_feature_extraction: bool = True,
        max_signatures: int = 10,
    ):
        """Initialize extraction service.

        Args:
            min_confidence: Minimum confidence threshold
            enable_preprocessing: Enable image preprocessing
            enable_feature_extraction: Enable feature vector extraction
            max_signatures: Maximum signatures to extract
        """
        self.min_confidence = min_confidence
        self.enable_preprocessing = enable_preprocessing
        self.enable_feature_extraction = enable_feature_extraction
        self.max_signatures = max_signatures

    def extract_from_image(
        self,
        image_data: bytes,
        region: BoundingBox | None = None,
        method: str = "auto",
    ) -> ExtractionResult:
        """Extract signatures from image.

        Args:
            image_data: Image bytes
            region: Optional region to search
            method: Extraction method (auto, contour, edge, template)

        Returns:
            ExtractionResult with extracted signatures
        """
        start_time = datetime.utcnow()
        result = ExtractionResult()

        try:
            # Simulate image processing
            # In production, use OpenCV, PIL, or similar library

            # Decode image (simulated)
            image_hash = hashlib.sha256(image_data).hexdigest()

            # Preprocess if enabled
            if self.enable_preprocessing:
                processed_data = self._preprocess_image(image_data)
            else:
                processed_data = image_data

            # Detect signature regions
            if method == "auto":
                method = self._select_best_method(processed_data)

            if method == "contour":
                candidates = self._detect_by_contour(processed_data, region)
            elif method == "edge":
                candidates = self._detect_by_edge(processed_data, region)
            elif method == "template":
                candidates = self._detect_by_template(processed_data, region)
            else:
                candidates = self._detect_by_contour(processed_data, region)

            # Filter and validate candidates
            valid_signatures = []
            for candidate in candidates[: self.max_signatures]:
                signature = self._validate_and_extract(candidate, processed_data)
                if signature and signature.confidence >= self.min_confidence:
                    # Extract features if enabled
                    if self.enable_feature_extraction:
                        signature.feature_vector = self._extract_features(signature)
                        signature.contour_data = self._extract_contours(signature)

                    valid_signatures.append(signature)

            result.signatures = valid_signatures
            result.total_found = len(valid_signatures)
            result.success = len(valid_signatures) > 0
            result.metadata = {
                "method": method,
                "image_hash": image_hash,
                "preprocessing": self.enable_preprocessing,
            }

        except Exception as e:
            logger.error(f"Error extracting signatures: {e}")
            result.errors.append(str(e))

        end_time = datetime.utcnow()
        result.processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

        return result

    def extract_from_base64(
        self,
        base64_data: str,
        region: BoundingBox | None = None,
    ) -> ExtractionResult:
        """Extract signatures from base64 encoded image.

        Args:
            base64_data: Base64 encoded image
            region: Optional region to search

        Returns:
            ExtractionResult
        """
        try:
            # Remove data URL prefix if present
            if "," in base64_data:
                base64_data = base64_data.split(",")[1]

            image_data = base64.b64decode(base64_data)
            return self.extract_from_image(image_data, region)
        except Exception as e:
            logger.error(f"Error decoding base64: {e}")
            return ExtractionResult(errors=[f"Invalid base64 data: {e}"])

    def extract_from_region(
        self,
        image_data: bytes,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> ExtractionResult:
        """Extract signature from specific region.

        Args:
            image_data: Image bytes
            x, y: Top-left corner
            width, height: Region dimensions

        Returns:
            ExtractionResult
        """
        region = BoundingBox(x=x, y=y, width=width, height=height)
        return self.extract_from_image(image_data, region)

    def _preprocess_image(self, image_data: bytes) -> bytes:
        """Preprocess image for better extraction.

        Steps:
        1. Convert to grayscale
        2. Apply adaptive threshold
        3. Remove noise
        4. Enhance contrast
        """
        # Simulated preprocessing
        # In production: use OpenCV cv2.cvtColor, cv2.adaptiveThreshold, etc.
        return image_data

    def _select_best_method(self, image_data: bytes) -> str:
        """Select best extraction method based on image characteristics."""
        # Analyze image and select method
        # For now, default to contour detection
        return "contour"

    def _detect_by_contour(
        self,
        image_data: bytes,
        region: BoundingBox | None,
    ) -> list[dict[str, Any]]:
        """Detect signatures using contour analysis.

        Args:
            image_data: Preprocessed image
            region: Optional search region

        Returns:
            List of candidate regions
        """
        # Simulated contour detection
        # In production: use cv2.findContours, cv2.boundingRect, etc.

        # Generate sample candidates based on image hash for consistency
        image_hash = hashlib.sha256(image_data).hexdigest()
        seed = int(image_hash[:8], 16)
        np.random.seed(seed % (2**31))

        candidates = []

        # Generate 1-3 candidates
        num_candidates = np.random.randint(1, 4)

        for _i in range(num_candidates):
            width = np.random.randint(self.MIN_SIGNATURE_WIDTH, self.MAX_SIGNATURE_WIDTH)
            height = np.random.randint(self.MIN_SIGNATURE_HEIGHT, self.MAX_SIGNATURE_HEIGHT)

            # Ensure valid aspect ratio
            if width / height < self.MIN_ASPECT_RATIO:
                width = int(height * self.MIN_ASPECT_RATIO * 1.2)

            candidate = {
                "bbox": BoundingBox(
                    x=np.random.randint(10, 500),
                    y=np.random.randint(10, 500),
                    width=width,
                    height=height,
                ),
                "confidence": np.random.uniform(0.6, 0.95),
                "contour_points": np.random.randint(50, 200),
                "method": "contour",
            }
            candidates.append(candidate)

        return candidates

    def _detect_by_edge(
        self,
        image_data: bytes,
        region: BoundingBox | None,
    ) -> list[dict[str, Any]]:
        """Detect signatures using edge detection."""
        # Use Canny edge detection
        # In production: cv2.Canny, cv2.HoughLinesP
        return self._detect_by_contour(image_data, region)

    def _detect_by_template(
        self,
        image_data: bytes,
        region: BoundingBox | None,
    ) -> list[dict[str, Any]]:
        """Detect signatures using template matching."""
        # Match against known signature patterns
        return self._detect_by_contour(image_data, region)

    def _validate_and_extract(
        self,
        candidate: dict[str, Any],
        image_data: bytes,
    ) -> ExtractedSignature | None:
        """Validate candidate and extract signature data.

        Args:
            candidate: Candidate region data
            image_data: Original image

        Returns:
            ExtractedSignature if valid, None otherwise
        """
        bbox = candidate.get("bbox")
        if not bbox:
            return None

        # Validate dimensions
        if not self._validate_dimensions(bbox):
            return None

        # Calculate quality metrics
        contrast = self._calculate_contrast(image_data, bbox)
        clarity = self._calculate_clarity(image_data, bbox)
        completeness = self._calculate_completeness(image_data, bbox)

        # Check minimum quality
        if contrast < self.MIN_CONTRAST:
            return None
        if clarity < self.MIN_CLARITY:
            return None
        if completeness < self.MIN_COMPLETENESS:
            return None

        # Calculate overall quality score
        quality_score = contrast * 0.3 + clarity * 0.4 + completeness * 0.3

        # Extract signature image (simulated)
        signature_image = self._crop_region(image_data, bbox)

        return ExtractedSignature(
            image_data=base64.b64encode(signature_image).decode() if signature_image else None,
            bounding_box=bbox,
            confidence=candidate.get("confidence", 0.5),
            quality_score=quality_score,
            contrast_score=contrast,
            clarity_score=clarity,
            completeness_score=completeness,
            width=bbox.width,
            height=bbox.height,
            stroke_count=candidate.get("contour_points", 0) // 10,
            extraction_method=candidate.get("method", "unknown"),
        )

    def _validate_dimensions(self, bbox: BoundingBox) -> bool:
        """Validate signature dimensions."""
        # Check size constraints
        if bbox.width < self.MIN_SIGNATURE_WIDTH or bbox.width > self.MAX_SIGNATURE_WIDTH:
            return False
        if bbox.height < self.MIN_SIGNATURE_HEIGHT or bbox.height > self.MAX_SIGNATURE_HEIGHT:
            return False

        # Check area
        if bbox.area < self.MIN_AREA or bbox.area > self.MAX_AREA:
            return False

        # Check aspect ratio
        if bbox.aspect_ratio < self.MIN_ASPECT_RATIO or bbox.aspect_ratio > self.MAX_ASPECT_RATIO:
            return False

        return True

    def _calculate_contrast(self, image_data: bytes, bbox: BoundingBox) -> float:
        """Calculate contrast score for region."""
        # In production: calculate actual contrast using pixel values
        # Simulated: use image hash for consistency
        image_hash = hashlib.sha256(image_data).hexdigest()
        seed = int(image_hash[:8], 16) + bbox.x + bbox.y
        np.random.seed(seed % (2**31))
        return np.random.uniform(0.4, 0.9)

    def _calculate_clarity(self, image_data: bytes, bbox: BoundingBox) -> float:
        """Calculate clarity score for region."""
        # In production: calculate actual sharpness/blur metrics
        image_hash = hashlib.sha256(image_data).hexdigest()
        seed = int(image_hash[:8], 16) + bbox.width
        np.random.seed(seed % (2**31))
        return np.random.uniform(0.5, 0.95)

    def _calculate_completeness(self, image_data: bytes, bbox: BoundingBox) -> float:
        """Calculate completeness score (no cut-off edges)."""
        # In production: check if signature touches edges
        image_hash = hashlib.sha256(image_data).hexdigest()
        seed = int(image_hash[:8], 16) + bbox.height
        np.random.seed(seed % (2**31))
        return np.random.uniform(0.6, 0.98)

    def _crop_region(self, image_data: bytes, bbox: BoundingBox) -> bytes:
        """Crop region from image."""
        # In production: use PIL or OpenCV to crop
        # Return simulated cropped data
        return image_data[: min(len(image_data), bbox.area)]

    def _extract_features(self, signature: ExtractedSignature) -> list[float]:
        """Extract feature vector from signature.

        Features include:
        - Geometric features (aspect ratio, area ratio)
        - Stroke features (density, curvature)
        - Statistical features (moments, histograms)
        """
        # Generate deterministic feature vector based on signature properties
        features = []

        # Geometric features
        features.append(signature.bounding_box.aspect_ratio if signature.bounding_box else 2.0)
        features.append(signature.width / 100.0)
        features.append(signature.height / 50.0)

        # Quality features
        features.append(signature.contrast_score)
        features.append(signature.clarity_score)
        features.append(signature.completeness_score)

        # Stroke features
        features.append(signature.stroke_count / 10.0)

        # Pad to fixed size (128 features)
        np.random.seed(int(signature.quality_score * 1000) % (2**31))
        while len(features) < 128:
            features.append(np.random.uniform(-1, 1))

        return features

    def _extract_contours(self, signature: ExtractedSignature) -> list[list[int]]:
        """Extract contour points from signature."""
        # In production: use cv2.findContours
        # Generate simulated contour points
        points = []
        num_points = signature.stroke_count * 5

        np.random.seed(int(signature.confidence * 1000) % (2**31))

        for _ in range(min(num_points, 100)):
            x = np.random.randint(0, signature.width)
            y = np.random.randint(0, signature.height)
            points.append([int(x), int(y)])

        return points

    def calculate_image_hash(self, image_data: bytes) -> str:
        """Calculate perceptual hash for image.

        Used for detecting duplicate signatures.
        """
        # In production: use imagehash library for perceptual hashing
        return hashlib.sha256(image_data).hexdigest()

    def estimate_stroke_data(
        self,
        signature: ExtractedSignature,
    ) -> dict[str, Any]:
        """Estimate stroke characteristics from static signature."""
        return {
            "estimated_strokes": signature.stroke_count,
            "stroke_density": signature.stroke_count / max(signature.width * signature.height, 1) * 10000,
            "estimated_pressure": "medium",
            "estimated_velocity": "normal",
            "complexity": "medium" if signature.stroke_count < 15 else "high",
        }
