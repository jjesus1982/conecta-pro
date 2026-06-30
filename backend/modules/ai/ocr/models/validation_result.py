"""ValidationResult Model - Resultado de validacao de documento.

Sprint 39 - Document OCR.
"""

import uuid
from datetime import datetime
from enum import StrEnum

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


class ValidationStatus(StrEnum):
    """Status geral de validacao."""

    PENDING = "pending"  # Aguardando validacao
    VALIDATING = "validating"  # Validacao em andamento
    PASSED = "passed"  # Todas as validacoes passaram
    FAILED = "failed"  # Falha na validacao
    PARTIAL = "partial"  # Algumas validacoes falharam
    SKIPPED = "skipped"  # Validacao pulada


class ValidationAction(StrEnum):
    """Acao pos-validacao."""

    NONE = "none"  # Nenhuma acao
    AUTO_CORRECT = "auto_correct"  # Correcao automatica aplicada
    MANUAL_REVIEW = "manual_review"  # Encaminhado para revisao
    REJECT = "reject"  # Documento rejeitado
    RETRY = "retry"  # Reprocessar documento
    ESCALATE = "escalate"  # Escalar para supervisor


class ValidationResult(Base):
    """Modelo de resultado de validacao."""

    __tablename__ = "ocr_validation_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    scan_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    validation_id = Column(String(100), nullable=False, unique=True, index=True)

    # Status
    status = Column(
        Enum(ValidationStatus, values_callable=lambda x: [e.value for e in x]), default=ValidationStatus.PENDING
    )
    action_taken = Column(
        Enum(ValidationAction, values_callable=lambda x: [e.value for e in x]), default=ValidationAction.NONE
    )

    # Metricas gerais
    total_fields = Column(Integer, default=0)
    valid_fields = Column(Integer, default=0)
    invalid_fields = Column(Integer, default=0)
    warning_fields = Column(Integer, default=0)
    skipped_fields = Column(Integer, default=0)

    # Scores
    overall_score = Column(Float)  # 0-1, score geral
    confidence_score = Column(Float)  # Score de confianca
    completeness_score = Column(Float)  # Score de completude
    consistency_score = Column(Float)  # Score de consistencia

    # Resultados por campo
    field_results = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "field_id": "...",
    #     "field_name": "cnpj",
    #     "status": "valid|invalid|warning",
    #     "rules_applied": ["cnpj_checksum", "cnpj_format"],
    #     "rules_passed": ["cnpj_checksum", "cnpj_format"],
    #     "rules_failed": [],
    #     "errors": [],
    #     "warnings": [],
    #     "auto_corrections": []
    #   }
    # ]

    # Validacoes de documento
    document_validations = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "rule": "total_matches_items",
    #     "status": "passed",
    #     "details": {"expected": 1500.00, "actual": 1500.00}
    #   }
    # ]

    # Erros encontrados
    errors = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "field": "cnpj",
    #     "code": "INVALID_CHECKSUM",
    #     "message": "Digito verificador invalido",
    #     "severity": "error",
    #     "suggestion": "Verificar CNPJ: 12.345.678/0001-XX"
    #   }
    # ]

    # Warnings
    warnings = Column(JSONB, default=[])
    # Estrutura similar a errors

    # Correcoes automaticas
    auto_corrections = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "field": "data_emissao",
    #     "original": "15/01/24",
    #     "corrected": "15/01/2024",
    #     "reason": "Ano com 2 digitos expandido"
    #   }
    # ]

    # Campos faltantes
    missing_required_fields = Column(ARRAY(String), default=[])
    missing_optional_fields = Column(ARRAY(String), default=[])

    # Campos suspeitos
    suspicious_fields = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "field": "valor_total",
    #     "reason": "Valor muito alto para o tipo de documento",
    #     "confidence": 0.3
    #   }
    # ]

    # Cross-validation
    cross_validation_results = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "type": "sum_check",
    #     "fields": ["item_1", "item_2", "item_3"],
    #     "expected_field": "total",
    #     "status": "passed",
    #     "calculated": 1500.00,
    #     "extracted": 1500.00
    #   }
    # ]

    # Validacao externa
    external_validations = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "type": "cnpj_receita",
    #     "status": "valid",
    #     "response": {"razao_social": "Empresa LTDA", ...}
    #   }
    # ]

    # Tempo de validacao
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_ms = Column(Integer)

    # Revisao
    needs_review = Column(Boolean, default=False)
    review_priority = Column(String(20))  # low, normal, high, urgent
    review_notes = Column(Text)
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime)

    # Acao final
    final_decision = Column(String(50))  # approved, rejected, corrected
    decision_by = Column(UUID(as_uuid=True))
    decision_at = Column(DateTime)
    decision_notes = Column(Text)

    # Metadata
    extra_data = Column(JSONB, default={})

    # Controle
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<ValidationResult {self.validation_id} ({self.status.value})>"

    def is_valid(self) -> bool:
        """Verifica se validacao passou."""
        return self.status == ValidationStatus.PASSED

    def has_errors(self) -> bool:
        """Verifica se tem erros."""
        return len(self.errors or []) > 0

    def has_warnings(self) -> bool:
        """Verifica se tem warnings."""
        return len(self.warnings or []) > 0

    def get_error_count(self) -> int:
        """Retorna quantidade de erros."""
        return len(self.errors or [])

    def get_warning_count(self) -> int:
        """Retorna quantidade de warnings."""
        return len(self.warnings or [])

    def calculate_score(self) -> float:
        """Calcula score geral."""
        if self.total_fields == 0:
            return 0.0
        return self.valid_fields / self.total_fields

    def add_error(
        self,
        field: str,
        code: str,
        message: str,
        severity: str = "error",
        suggestion: str | None = None,
    ) -> None:
        """Adiciona erro."""
        if self.errors is None:
            self.errors = []
        error = {
            "field": field,
            "code": code,
            "message": message,
            "severity": severity,
        }
        if suggestion:
            error["suggestion"] = suggestion
        self.errors.append(error)

    def add_warning(
        self,
        field: str,
        code: str,
        message: str,
    ) -> None:
        """Adiciona warning."""
        if self.warnings is None:
            self.warnings = []
        self.warnings.append(
            {
                "field": field,
                "code": code,
                "message": message,
            }
        )

    def add_auto_correction(
        self,
        field: str,
        original: str,
        corrected: str,
        reason: str,
    ) -> None:
        """Adiciona correcao automatica."""
        if self.auto_corrections is None:
            self.auto_corrections = []
        self.auto_corrections.append(
            {
                "field": field,
                "original": original,
                "corrected": corrected,
                "reason": reason,
            }
        )
