"""ExtractedField Model - Campos extraidos do documento.

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


class FieldType(StrEnum):
    """Tipo de campo extraido."""

    # Texto
    TEXT = "text"
    TEXT_LINE = "text_line"
    TEXT_BLOCK = "text_block"

    # Numeros
    NUMBER = "number"
    INTEGER = "integer"
    DECIMAL = "decimal"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"

    # Datas
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"

    # Identificadores
    CPF = "cpf"
    CNPJ = "cnpj"
    RG = "rg"
    CNH = "cnh"
    PASSPORT = "passport"

    # Contato
    EMAIL = "email"
    PHONE = "phone"
    CEP = "cep"
    ADDRESS = "address"

    # Financeiro
    BANK_ACCOUNT = "bank_account"
    BANK_AGENCY = "bank_agency"
    PIX_KEY = "pix_key"
    BARCODE = "barcode"
    BARCODE_BOLETO = "barcode_boleto"

    # Notas Fiscais
    NF_NUMBER = "nf_number"
    NF_SERIE = "nf_serie"
    NF_KEY = "nf_key"  # Chave de acesso NFe
    NCM = "ncm"
    CFOP = "cfop"

    # Outros
    NAME = "name"
    COMPANY_NAME = "company_name"
    SIGNATURE = "signature"
    QR_CODE = "qr_code"
    CHECKBOX = "checkbox"
    TABLE = "table"
    LIST = "list"
    CUSTOM = "custom"


class FieldValidationStatus(StrEnum):
    """Status de validacao do campo."""

    PENDING = "pending"  # Aguardando validacao
    VALID = "valid"  # Validado com sucesso
    INVALID = "invalid"  # Invalido
    WARNING = "warning"  # Valido com ressalvas
    CORRECTED = "corrected"  # Corrigido manualmente
    SKIPPED = "skipped"  # Validacao pulada


class ExtractedField(Base):
    """Modelo de campo extraido do documento."""

    __tablename__ = "ocr_extracted_fields"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    scan_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    result_id = Column(UUID(as_uuid=True), index=True)

    # Identificacao
    field_id = Column(String(100), nullable=False, index=True)
    template_field_id = Column(UUID(as_uuid=True), index=True)  # Campo do template

    # Definicao do campo
    field_name = Column(String(100), nullable=False, index=True)
    field_label = Column(String(200))  # Label amigavel
    field_type = Column(Enum(FieldType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    field_group = Column(String(100))  # Grupo do campo (ex: "emissor", "valores")

    # Valor extraido
    raw_value = Column(Text)  # Valor bruto do OCR
    extracted_value = Column(Text)  # Valor apos extracao
    normalized_value = Column(Text)  # Valor normalizado
    formatted_value = Column(Text)  # Valor formatado para exibicao

    # Valor tipado (armazenado como JSONB para flexibilidade)
    typed_value = Column(JSONB)
    # Estrutura depende do tipo:
    # - currency: {"amount": 1500.50, "currency": "BRL"}
    # - date: {"date": "2024-01-15", "format": "DD/MM/YYYY"}
    # - address: {"street": "...", "number": "...", "city": "..."}

    # Posicao no documento
    page_number = Column(Integer, default=1)
    bounding_box = Column(JSONB)
    # Estrutura: {"x": 10, "y": 20, "width": 100, "height": 15}

    # Origem
    source_line_numbers = Column(ARRAY(Integer), default=[])  # Linhas de origem
    source_text = Column(Text)  # Texto original que gerou o campo
    extraction_method = Column(String(50))  # regex, ml, template, key_value

    # Confianca
    confidence = Column(Float)  # 0-1, confianca na extracao
    ocr_confidence = Column(Float)  # Confianca do OCR original

    # Validacao
    validation_status = Column(
        Enum(FieldValidationStatus),
        default=FieldValidationStatus.PENDING,
    )
    validation_rules_applied = Column(ARRAY(String), default=[])
    validation_errors = Column(JSONB, default=[])
    # Estrutura: [{"rule": "cpf_checksum", "message": "CPF invalido"}]
    validation_warnings = Column(JSONB, default=[])

    # Correcao
    was_corrected = Column(Boolean, default=False)
    original_value = Column(Text)  # Valor antes da correcao
    corrected_by = Column(UUID(as_uuid=True))
    corrected_at = Column(DateTime)
    correction_reason = Column(String(500))

    # Mapeamento para sistema
    target_entity = Column(String(100))  # Entidade destino
    target_field = Column(String(100))  # Campo destino
    mapped_successfully = Column(Boolean)

    # Flags
    is_required = Column(Boolean, default=False)
    is_key_field = Column(Boolean, default=False)  # Campo chave do documento
    is_calculated = Column(Boolean, default=False)  # Valor calculado
    is_from_table = Column(Boolean, default=False)  # Extraido de tabela

    # Contexto
    context_before = Column(Text)  # Texto antes do valor
    context_after = Column(Text)  # Texto depois do valor
    related_fields = Column(ARRAY(String), default=[])  # Campos relacionados

    # Metadata
    extra_data = Column(JSONB, default={})

    # Controle
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        """Representacao string."""
        value_preview = str(self.extracted_value)[:20] if self.extracted_value else ""
        return f"<ExtractedField {self.field_name}: {value_preview}>"

    def is_valid(self) -> bool:
        """Verifica se campo eh valido."""
        return self.validation_status in [
            FieldValidationStatus.VALID,
            FieldValidationStatus.CORRECTED,
        ]

    def needs_review(self) -> bool:
        """Verifica se precisa de revisao."""
        if self.validation_status == FieldValidationStatus.INVALID:
            return True
        if self.validation_status == FieldValidationStatus.WARNING:
            return True
        if self.confidence and self.confidence < 0.7:
            return True
        return False

    def get_value(self) -> Any:
        """Retorna valor tipado ou normalizado."""
        if self.typed_value is not None:
            return self.typed_value
        return self.normalized_value or self.extracted_value

    def set_corrected_value(self, value: str, corrected_by: str | None = None) -> None:
        """Define valor corrigido."""
        if not self.was_corrected:
            self.original_value = self.extracted_value
        self.extracted_value = value
        self.normalized_value = value
        self.was_corrected = True
        self.corrected_at = datetime.utcnow()
        self.validation_status = FieldValidationStatus.CORRECTED
        if corrected_by:
            self.corrected_by = corrected_by
