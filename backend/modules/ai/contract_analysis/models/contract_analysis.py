"""
Contract Analysis Model - AI Contract Analysis

Model principal para analise de contratos.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class AnalysisStatus(StrEnum):
    """Status da analise."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"


class ContractType(StrEnum):
    """Tipo de contrato."""

    SERVICE = "service"  # Prestacao de servicos
    SALES = "sales"  # Compra e venda
    LEASE = "lease"  # Locacao
    EMPLOYMENT = "employment"  # Trabalho
    PARTNERSHIP = "partnership"  # Parceria
    NDA = "nda"  # Confidencialidade
    SLA = "sla"  # Nivel de servico
    MAINTENANCE = "maintenance"  # Manutencao
    SUPPLY = "supply"  # Fornecimento
    LICENSE = "license"  # Licenciamento
    FRANCHISE = "franchise"  # Franquia
    OTHER = "other"


class RiskLevel(StrEnum):
    """Nivel de risco do contrato."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ContractAnalysis(Base):
    """
    Model principal de analise de contrato.

    Armazena resultados da analise NLP de contratos.
    """

    __tablename__ = "contract_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referencia ao contrato original (modulo de contratos)
    contract_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contract_number = Column(String(50))
    contract_title = Column(String(300))

    # Documento analisado
    document_id = Column(UUID(as_uuid=True))  # Referencia ao GED
    document_name = Column(String(300))
    document_hash = Column(String(64))  # SHA-256 do documento

    # Status e tipo
    status = Column(
        Enum(AnalysisStatus, values_callable=lambda x: [e.value for e in x]),
        default=AnalysisStatus.PENDING,
        nullable=False,
        index=True,
    )
    contract_type = Column(
        Enum(ContractType, values_callable=lambda x: [e.value for e in x]), default=ContractType.OTHER, nullable=False
    )
    contract_type_confidence = Column(Float, default=0)  # 0-100

    # Partes identificadas
    contractor_name = Column(String(300))  # Contratante
    contractor_document = Column(String(20))  # CNPJ/CPF
    contracted_name = Column(String(300))  # Contratado
    contracted_document = Column(String(20))

    # Datas extraidas
    signature_date = Column(Date)  # Data de assinatura
    start_date = Column(Date)  # Inicio da vigencia
    end_date = Column(Date)  # Fim da vigencia
    renewal_date = Column(Date)  # Data de renovacao
    notice_period_days = Column(Integer)  # Prazo de aviso previo

    # Valores extraidos
    total_value = Column(Float)
    monthly_value = Column(Float)
    currency = Column(String(3), default="BRL")
    payment_terms = Column(String(200))
    adjustment_index = Column(String(50))  # IGPM, IPCA, etc
    adjustment_date = Column(Date)

    # Analise de risco
    risk_level = Column(
        Enum(RiskLevel, values_callable=lambda x: [e.value for e in x]), default=RiskLevel.MEDIUM, nullable=False
    )
    risk_score = Column(Float, default=50)  # 0-100
    risk_factors = Column(JSONB, default=list)

    # Score de conformidade
    compliance_score = Column(Float, default=0)  # 0-100
    compliance_issues = Column(JSONB, default=list)
    missing_clauses = Column(JSONB, default=list)

    # Estatisticas da analise
    total_pages = Column(Integer, default=0)
    total_words = Column(Integer, default=0)
    total_clauses_found = Column(Integer, default=0)
    processing_time_seconds = Column(Float)

    # Comparacao com template
    template_id = Column(UUID(as_uuid=True))
    template_match_score = Column(Float)  # 0-100
    template_deviations = Column(JSONB, default=list)

    # Resumo gerado
    summary = Column(Text)  # Resumo do contrato
    key_terms = Column(JSONB, default=list)  # Termos-chave identificados
    obligations_summary = Column(Text)  # Resumo das obrigacoes

    # Flags de atencao
    has_auto_renewal = Column(Boolean, default=False)
    has_penalty_clause = Column(Boolean, default=False)
    has_exclusivity = Column(Boolean, default=False)
    has_confidentiality = Column(Boolean, default=False)
    has_non_compete = Column(Boolean, default=False)
    requires_review = Column(Boolean, default=False)

    # Metadados
    analyzed_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    # Flags
    is_active = Column(Boolean, default=True, nullable=False)
    is_latest = Column(Boolean, default=True)  # Versao mais recente da analise

    # Notas e erro
    notes = Column(Text)
    error_message = Column(Text)

    # Relacionamentos
    clauses = relationship("ExtractedClause", back_populates="analysis", cascade="all, delete-orphan")
    alerts = relationship("ContractAlert", back_populates="analysis", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ContractAnalysis {self.contract_number} - {self.status.value}>"

    @property
    def days_until_expiry(self) -> int | None:
        """Dias ate o vencimento."""
        if not self.end_date:
            return None
        delta = self.end_date - date.today()
        return delta.days

    @property
    def is_expiring_soon(self) -> bool:
        """Verifica se expira em 30 dias."""
        days = self.days_until_expiry
        return days is not None and 0 < days <= 30

    @property
    def is_expired(self) -> bool:
        """Verifica se ja expirou."""
        days = self.days_until_expiry
        return days is not None and days <= 0
