"""Model para documentos do funcionário."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class DocumentType(StrEnum):
    """Tipo de documento."""

    # Documentos de RH
    PAYSLIP = "payslip"  # Contracheque
    INCOME_REPORT = "income_report"  # Informe de Rendimentos
    VACATION_NOTICE = "vacation_notice"  # Aviso de Férias
    VACATION_RECEIPT = "vacation_receipt"  # Recibo de Férias

    # Contratos e termos
    EMPLOYMENT_CONTRACT = "employment_contract"  # Contrato de Trabalho
    CONTRACT_AMENDMENT = "contract_amendment"  # Aditivo Contratual
    CONFIDENTIALITY_AGREEMENT = "confidentiality_agreement"  # Termo de Confidencialidade
    WORK_TOOLS_TERM = "work_tools_term"  # Termo de Ferramentas

    # Benefícios
    BENEFIT_ENROLLMENT = "benefit_enrollment"  # Adesão a Benefício
    HEALTH_PLAN_CARD = "health_plan_card"  # Carteirinha Plano de Saúde
    MEAL_VOUCHER_STATEMENT = "meal_voucher_statement"  # Extrato VR/VA

    # Documentos pessoais (cópias)
    ID_COPY = "id_copy"  # Cópia RG
    CPF_COPY = "cpf_copy"  # Cópia CPF
    CTPS_COPY = "ctps_copy"  # Cópia CTPS
    VOTER_ID_COPY = "voter_id_copy"  # Cópia Título de Eleitor
    MILITARY_CERT_COPY = "military_cert_copy"  # Cópia Cert. Reservista
    ADDRESS_PROOF = "address_proof"  # Comprovante de Endereço
    EDUCATION_CERT = "education_cert"  # Certificado de Escolaridade
    DEPENDENT_DOCS = "dependent_docs"  # Docs de Dependentes

    # Certificados e treinamentos
    TRAINING_CERTIFICATE = "training_certificate"  # Certificado de Treinamento
    COURSE_CERTIFICATE = "course_certificate"  # Certificado de Curso
    LICENSE = "license"  # Licença/Habilitação

    # Atestados e declarações
    MEDICAL_CERTIFICATE = "medical_certificate"  # Atestado Médico
    MEDICAL_EXAM = "medical_exam"  # Exame Médico (ASO)
    DECLARATION = "declaration"  # Declaração

    # Rescisão
    TERMINATION_NOTICE = "termination_notice"  # Aviso Prévio
    TERMINATION_STATEMENT = "termination_statement"  # Termo de Rescisão
    TRCT = "trct"  # TRCT
    UNEMPLOYMENT_INSURANCE = "unemployment_insurance"  # Seguro Desemprego

    # Outros
    POLICY = "policy"  # Política da Empresa
    MEMO = "memo"  # Memorando
    WARNING = "warning"  # Advertência
    OTHER = "other"  # Outro


class DocumentStatus(StrEnum):
    """Status do documento."""

    DRAFT = "draft"  # Rascunho
    PENDING_SIGNATURE = "pending_signature"  # Aguardando assinatura
    SIGNED = "signed"  # Assinado
    PUBLISHED = "published"  # Publicado (visível)
    ACKNOWLEDGED = "acknowledged"  # Ciência dada
    ARCHIVED = "archived"  # Arquivado
    EXPIRED = "expired"  # Expirado
    CANCELLED = "cancelled"  # Cancelado


class EmployeeDocument(Base):
    """Documento do funcionário no portal."""

    __tablename__ = "employee_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )
    employee_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Identificação
    document_code = Column(String(50), nullable=False, unique=True, index=True)
    document_type = Column(String(50), nullable=False, index=True)
    status = Column(
        String(30),
        nullable=False,
        default=DocumentStatus.DRAFT.value,
        index=True,
    )

    # Informações do documento
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)  # Categoria adicional
    tags = Column(JSONB, default=list)  # Tags para busca

    # Arquivo
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)  # Bytes
    file_type = Column(String(50), nullable=True)  # MIME type
    file_hash = Column(String(64), nullable=True)  # SHA-256

    # Período de referência
    reference_date = Column(Date, nullable=True)
    reference_month = Column(Integer, nullable=True)
    reference_year = Column(Integer, nullable=True)

    # Validade
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    is_perpetual = Column(Boolean, default=False)  # Sem validade

    # Visualização
    is_visible = Column(Boolean, default=True)
    requires_acknowledgement = Column(Boolean, default=False)  # Requer ciência
    is_confidential = Column(Boolean, default=False)
    is_mandatory = Column(Boolean, default=False)  # Leitura obrigatória

    # Interação do funcionário
    first_viewed_at = Column(DateTime, nullable=True)
    view_count = Column(Integer, default=0)
    last_viewed_at = Column(DateTime, nullable=True)

    downloaded_at = Column(DateTime, nullable=True)
    download_count = Column(Integer, default=0)

    acknowledged_at = Column(DateTime, nullable=True)
    acknowledgement_ip = Column(String(45), nullable=True)
    acknowledgement_device = Column(String(200), nullable=True)

    # Assinatura digital
    requires_signature = Column(Boolean, default=False)
    signed_at = Column(DateTime, nullable=True)
    signed_by = Column(UUID(as_uuid=True), nullable=True)
    signature_hash = Column(String(64), nullable=True)
    signature_certificate = Column(Text, nullable=True)

    # Notificações
    notification_sent = Column(Boolean, default=False)
    notification_sent_at = Column(DateTime, nullable=True)
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime, nullable=True)

    # Relacionamentos
    parent_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employee_documents.id"),
        nullable=True,
    )
    related_documents = Column(JSONB, default=list)  # IDs de docs relacionados

    # Metadados
    document_extra_metadata = Column(JSONB, default=dict)
    # {
    #   "source": "hr_system",
    #   "generated_by": "auto",
    #   "template_id": "...",
    #   "custom_fields": {}
    # }

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    published_at = Column(DateTime, nullable=True)
    published_by = Column(UUID(as_uuid=True), nullable=True)
    archived_at = Column(DateTime, nullable=True)
    archived_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_document_type_status", "document_type", "status"),
        Index("ix_document_reference", "reference_year", "reference_month"),
        Index("ix_document_valid", "valid_from", "valid_until"),
        Index("ix_document_visible", "is_visible", "employee_id"),
    )

    def __repr__(self) -> str:
        return f"<EmployeeDocument {self.document_code} - {self.title}>"

    @property
    def is_expired(self) -> bool:
        """Verifica se o documento está expirado."""
        if self.is_perpetual or not self.valid_until:
            return False
        return date.today() > self.valid_until

    @property
    def is_published(self) -> bool:
        """Verifica se está publicado."""
        return self.status in [
            DocumentStatus.PUBLISHED.value,
            DocumentStatus.ACKNOWLEDGED.value,
        ]

    @property
    def needs_acknowledgement(self) -> bool:
        """Verifica se precisa de ciência."""
        return self.requires_acknowledgement and not self.acknowledged_at and self.is_published

    @property
    def needs_signature(self) -> bool:
        """Verifica se precisa de assinatura."""
        return self.requires_signature and not self.signed_at

    @property
    def days_until_expiry(self) -> int:
        """Dias até expiração."""
        if self.is_perpetual or not self.valid_until:
            return -1
        delta = self.valid_until - date.today()
        return delta.days

    def record_view(self) -> None:
        """Registra visualização do documento."""
        now = datetime.utcnow()
        if not self.first_viewed_at:
            self.first_viewed_at = now
        self.last_viewed_at = now
        self.view_count = (self.view_count or 0) + 1

    def record_download(self) -> None:
        """Registra download do documento."""
        self.downloaded_at = datetime.utcnow()
        self.download_count = (self.download_count or 0) + 1

    def to_summary(self) -> dict:
        """Retorna resumo para listagem."""
        return {
            "id": str(self.id),
            "document_code": self.document_code,
            "document_type": self.document_type,
            "title": self.title,
            "status": self.status,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "reference_date": (self.reference_date.isoformat() if self.reference_date else None),
            "is_visible": self.is_visible,
            "requires_acknowledgement": self.requires_acknowledgement,
            "acknowledged": self.acknowledged_at is not None,
            "requires_signature": self.requires_signature,
            "signed": self.signed_at is not None,
            "is_expired": self.is_expired,
            "created_at": self.created_at.isoformat(),
        }
