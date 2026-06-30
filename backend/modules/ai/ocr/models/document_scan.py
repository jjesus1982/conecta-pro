"""DocumentScan Model - Documento escaneado para OCR.

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


class DocumentScanStatus(StrEnum):
    """Status do scan do documento."""

    PENDING = "pending"  # Aguardando processamento
    UPLOADING = "uploading"  # Upload em andamento
    UPLOADED = "uploaded"  # Upload concluido
    PREPROCESSING = "preprocessing"  # Pre-processamento (rotacao, deskew)
    PROCESSING = "processing"  # OCR em andamento
    EXTRACTING = "extracting"  # Extracao de dados
    VALIDATING = "validating"  # Validacao de dados
    REVIEW = "review"  # Aguardando revisao humana
    COMPLETED = "completed"  # Processamento concluido
    FAILED = "failed"  # Falha no processamento
    CANCELLED = "cancelled"  # Cancelado


class DocumentScanType(StrEnum):
    """Tipo de documento."""

    # Financeiro
    INVOICE = "invoice"  # Nota fiscal
    RECEIPT = "receipt"  # Recibo
    BANK_STATEMENT = "bank_statement"  # Extrato bancario
    BOLETO = "boleto"  # Boleto bancario
    CHECK = "check"  # Cheque

    # Contratos
    CONTRACT = "contract"  # Contrato
    ADDENDUM = "addendum"  # Aditivo
    PROPOSAL = "proposal"  # Proposta

    # Identificacao
    ID_CARD = "id_card"  # RG
    CPF_CARD = "cpf_card"  # CPF
    CNH = "cnh"  # CNH
    PASSPORT = "passport"  # Passaporte
    CNPJ_CARD = "cnpj_card"  # Cartao CNPJ

    # RH
    WORK_CARD = "work_card"  # Carteira de trabalho
    PAYSLIP = "payslip"  # Holerite
    RESUME = "resume"  # Curriculo
    CERTIFICATE = "certificate"  # Certificado

    # Outros
    FORM = "form"  # Formulario
    LETTER = "letter"  # Carta
    REPORT = "report"  # Relatorio
    OTHER = "other"  # Outro


class DocumentScan(Base):
    """Modelo de documento escaneado para OCR."""

    __tablename__ = "ocr_document_scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    scan_id = Column(String(100), nullable=False, unique=True, index=True)
    external_id = Column(String(200), index=True)  # ID no sistema de origem
    batch_id = Column(UUID(as_uuid=True), index=True)  # Lote de processamento

    # Arquivo
    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000))
    file_url = Column(String(2000))
    file_size = Column(Integer)  # Bytes
    file_hash = Column(String(64))  # SHA-256
    mime_type = Column(String(100))
    file_extension = Column(String(20))

    # Imagem
    image_width = Column(Integer)
    image_height = Column(Integer)
    image_dpi = Column(Integer)
    page_count = Column(Integer, default=1)
    current_page = Column(Integer, default=1)

    # Tipo e classificacao
    document_type = Column(Enum(DocumentScanType, values_callable=lambda x: [e.value for e in x]), index=True)
    detected_type = Column(
        Enum(DocumentScanType, values_callable=lambda x: [e.value for e in x])
    )  # Tipo detectado por IA
    type_confidence = Column(Float)  # Confianca na deteccao
    template_id = Column(UUID(as_uuid=True), index=True)  # Template usado

    # Status
    status = Column(
        Enum(DocumentScanStatus),
        default=DocumentScanStatus.PENDING,
        index=True,
    )
    status_message = Column(String(500))
    status_changed_at = Column(DateTime)

    # Pre-processamento
    preprocessing_applied = Column(JSONB, default=[])
    # Estrutura: ["deskew", "rotate_90", "enhance_contrast", "remove_noise"]
    rotation_angle = Column(Float, default=0)
    deskew_angle = Column(Float, default=0)
    quality_score = Column(Float)  # 0-1, qualidade da imagem

    # OCR
    ocr_provider = Column(String(50))  # tesseract, google_vision, aws_textract
    ocr_language = Column(String(10), default="por")  # Idioma principal
    ocr_languages = Column(ARRAY(String), default=["por", "eng"])
    ocr_started_at = Column(DateTime)
    ocr_completed_at = Column(DateTime)
    ocr_duration_ms = Column(Integer)
    ocr_confidence = Column(Float)  # Confianca media do OCR

    # Extracao
    extraction_started_at = Column(DateTime)
    extraction_completed_at = Column(DateTime)
    extraction_duration_ms = Column(Integer)
    fields_extracted = Column(Integer, default=0)
    fields_validated = Column(Integer, default=0)
    fields_with_errors = Column(Integer, default=0)

    # Validacao
    validation_started_at = Column(DateTime)
    validation_completed_at = Column(DateTime)
    validation_score = Column(Float)  # 0-1, score de validacao
    requires_review = Column(Boolean, default=False)
    review_reason = Column(String(500))

    # Revisao
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    corrections_made = Column(Integer, default=0)

    # Integracao
    source_module = Column(String(100))  # Modulo de origem
    source_entity = Column(String(100))  # Entidade de origem
    source_id = Column(UUID(as_uuid=True))  # ID da entidade
    target_module = Column(String(100))  # Modulo destino
    target_entity = Column(String(100))  # Entidade destino
    target_id = Column(UUID(as_uuid=True))  # ID no destino

    # GED Integration
    ged_document_id = Column(UUID(as_uuid=True))  # ID no GED
    ged_folder_id = Column(UUID(as_uuid=True))  # Pasta no GED

    # Metricas
    processing_attempts = Column(Integer, default=0)
    last_error = Column(Text)
    total_processing_time_ms = Column(Integer)

    # Tags e categorias
    tags = Column(ARRAY(String), default=[])
    category = Column(String(100))
    priority = Column(String(20), default="normal")  # low, normal, high, urgent

    # Metadata
    extra_data = Column(JSONB, default={})
    original_extra_metadata = Column(JSONB, default={})  # Metadata do arquivo original

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<DocumentScan {self.scan_id} ({self.status.value})>"

    def can_process(self) -> bool:
        """Verifica se pode processar."""
        return self.status in [
            DocumentScanStatus.PENDING,
            DocumentScanStatus.UPLOADED,
        ]

    def can_retry(self) -> bool:
        """Verifica se pode tentar novamente."""
        return self.status == DocumentScanStatus.FAILED and self.processing_attempts < 3

    def get_processing_time(self) -> int | None:
        """Retorna tempo total de processamento em ms."""
        if self.total_processing_time_ms:
            return self.total_processing_time_ms

        total = 0
        if self.ocr_duration_ms:
            total += self.ocr_duration_ms
        if self.extraction_duration_ms:
            total += self.extraction_duration_ms
        return total if total > 0 else None
