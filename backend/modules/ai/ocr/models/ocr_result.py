"""OCRResult Model - Resultado do processamento OCR.

Sprint 39 - Document OCR.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from core.models.base import Base


class OCRProvider(StrEnum):
    """Provedor de OCR."""

    TESSERACT = "tesseract"  # Tesseract OCR (local)
    GOOGLE_VISION = "google_vision"  # Google Cloud Vision
    AWS_TEXTRACT = "aws_textract"  # AWS Textract
    AZURE_FORM = "azure_form"  # Azure Form Recognizer
    ABBYY = "abbyy"  # ABBYY FineReader
    CUSTOM = "custom"  # Provedor customizado


class OCRResult(Base):
    """Modelo de resultado OCR."""

    __tablename__ = "ocr_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    scan_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    result_id = Column(String(100), nullable=False, unique=True, index=True)
    page_number = Column(Integer, default=1)

    # Provider
    provider = Column(Enum(OCRProvider, values_callable=lambda x: [e.value for e in x]), nullable=False)
    provider_version = Column(String(50))
    provider_model = Column(String(100))  # Modelo especifico do provider

    # Texto extraido
    raw_text = Column(Text)  # Texto bruto completo
    normalized_text = Column(Text)  # Texto normalizado
    text_length = Column(Integer)

    # Estrutura do texto
    lines = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "text": "Texto da linha",
    #     "confidence": 0.95,
    #     "bounding_box": {"x": 10, "y": 20, "width": 100, "height": 15},
    #     "words": [
    #       {"text": "Texto", "confidence": 0.96, "bounding_box": {...}}
    #     ]
    #   }
    # ]

    blocks = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "type": "text|table|form|key_value",
    #     "text": "...",
    #     "confidence": 0.9,
    #     "bounding_box": {...},
    #     "lines": [...]
    #   }
    # ]

    # Tabelas detectadas
    tables = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "rows": 5,
    #     "columns": 3,
    #     "cells": [
    #       {"row": 0, "col": 0, "text": "Header", "is_header": true}
    #     ],
    #     "bounding_box": {...}
    #   }
    # ]

    # Pares chave-valor detectados
    key_value_pairs = Column(JSONB, default=[])
    # Estrutura: [
    #   {"key": "CNPJ", "value": "12.345.678/0001-90", "confidence": 0.98}
    # ]

    # Checkboxes/formularios
    form_fields = Column(JSONB, default=[])
    # Estrutura: [
    #   {"label": "Aceito termos", "type": "checkbox", "value": true}
    # ]

    # Metricas de confianca
    overall_confidence = Column(Float)  # Media de confianca
    min_confidence = Column(Float)  # Menor confianca
    max_confidence = Column(Float)  # Maior confianca
    low_confidence_words = Column(Integer, default=0)  # Palavras com baixa confianca

    # Idioma
    detected_language = Column(String(10))
    language_confidence = Column(Float)
    languages_found = Column(ARRAY(String), default=[])

    # Orientacao
    detected_orientation = Column(Integer)  # 0, 90, 180, 270
    orientation_confidence = Column(Float)

    # Qualidade
    image_quality_score = Column(Float)  # 0-1
    text_density = Column(Float)  # Caracteres por area
    noise_level = Column(Float)  # Nivel de ruido detectado

    # Processamento
    processing_time_ms = Column(Integer)
    api_request_id = Column(String(200))  # ID da requisicao no provider
    api_response_size = Column(Integer)  # Tamanho da resposta em bytes

    # Custos
    api_cost = Column(Float)  # Custo da chamada API
    cost_currency = Column(String(3), default="USD")

    # Erros
    has_errors = Column(Boolean, default=False)
    errors = Column(JSONB, default=[])
    # Estrutura: [{"code": "LOW_QUALITY", "message": "...", "region": {...}}]

    # Warnings
    warnings = Column(JSONB, default=[])
    # Estrutura: [{"code": "SKEWED_IMAGE", "message": "..."}]

    # Raw response
    raw_response = Column(JSONB)  # Resposta completa do provider

    # Controle
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<OCRResult {self.result_id} ({self.provider.value})>"

    def get_text_blocks(self) -> list[dict[str, Any]]:
        """Retorna blocos de texto."""
        return [b for b in (self.blocks or []) if b.get("type") == "text"]

    def get_tables(self) -> list[dict[str, Any]]:
        """Retorna tabelas detectadas."""
        return self.tables or []

    def get_key_value_pairs(self) -> list[dict[str, Any]]:
        """Retorna pares chave-valor."""
        return self.key_value_pairs or []

    def get_low_confidence_regions(self, threshold: float = 0.7) -> list[dict[str, Any]]:
        """Retorna regioes com baixa confianca."""
        regions = []
        for line in self.lines or []:
            if line.get("confidence", 1.0) < threshold:
                regions.append(line)
        return regions


class OCRLine(Base):
    """Modelo de linha OCR (para indexacao)."""

    __tablename__ = "ocr_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    result_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    line_number = Column(Integer, nullable=False)
    page_number = Column(Integer, default=1)

    # Texto
    text = Column(Text, nullable=False)
    normalized_text = Column(Text)  # Para busca

    # Posicao
    x = Column(Integer)
    y = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)

    # Confianca
    confidence = Column(Float)
    word_count = Column(Integer)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        """Representacao string."""
        preview = self.text[:30] + "..." if len(self.text) > 30 else self.text
        return f"<OCRLine {self.line_number}: {preview}>"


class OCRWord(Base):
    """Modelo de palavra OCR (para indexacao granular)."""

    __tablename__ = "ocr_words"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    result_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    line_id = Column(UUID(as_uuid=True), index=True)

    # Identificacao
    word_index = Column(Integer, nullable=False)
    page_number = Column(Integer, default=1)
    line_number = Column(Integer)

    # Texto
    text = Column(String(500), nullable=False)
    normalized_text = Column(String(500))  # Para busca

    # Posicao
    x = Column(Integer)
    y = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)

    # Confianca
    confidence = Column(Float)

    # Flags
    is_numeric = Column(Boolean, default=False)
    is_date = Column(Boolean, default=False)
    is_currency = Column(Boolean, default=False)
    is_email = Column(Boolean, default=False)
    is_phone = Column(Boolean, default=False)
    is_cpf_cnpj = Column(Boolean, default=False)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<OCRWord {self.word_index}: {self.text}>"
