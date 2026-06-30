"""
Extracted Clause Model - AI Contract Analysis

Model para clausulas extraidas de contratos.
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
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class ClauseType(StrEnum):
    """Tipo de clausula."""

    OBJECT = "object"  # Objeto do contrato
    OBLIGATION = "obligation"  # Obrigacoes
    PAYMENT = "payment"  # Pagamento
    PENALTY = "penalty"  # Penalidades/Multas
    TERMINATION = "termination"  # Rescisao
    RENEWAL = "renewal"  # Renovacao
    CONFIDENTIALITY = "confidentiality"  # Confidencialidade
    NON_COMPETE = "non_compete"  # Nao concorrencia
    EXCLUSIVITY = "exclusivity"  # Exclusividade
    WARRANTY = "warranty"  # Garantia
    LIABILITY = "liability"  # Responsabilidade
    FORCE_MAJEURE = "force_majeure"  # Forca maior
    DISPUTE = "dispute"  # Resolucao de disputas
    JURISDICTION = "jurisdiction"  # Foro
    ASSIGNMENT = "assignment"  # Cessao
    AMENDMENT = "amendment"  # Alteracoes
    NOTICE = "notice"  # Notificacoes
    COMPLIANCE = "compliance"  # Conformidade
    INSURANCE = "insurance"  # Seguro
    INTELLECTUAL_PROPERTY = "intellectual_property"  # PI
    DATA_PROTECTION = "data_protection"  # LGPD
    SLA = "sla"  # Nivel de servico
    PRICE_ADJUSTMENT = "price_adjustment"  # Reajuste
    OTHER = "other"


class ClauseImportance(StrEnum):
    """Importancia da clausula."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExtractedClause(Base):
    """
    Model para clausulas extraidas.

    Armazena clausulas identificadas pela analise NLP.
    """

    __tablename__ = "contract_extracted_clauses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relacionamento com analise
    analysis_id = Column(
        UUID(as_uuid=True), ForeignKey("contract_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Identificacao da clausula
    clause_number = Column(String(20))  # Ex: "5.1", "CLAUSULA QUINTA"
    clause_title = Column(String(300))
    clause_type = Column(
        Enum(ClauseType, values_callable=lambda x: [e.value for e in x]),
        default=ClauseType.OTHER,
        nullable=False,
        index=True,
    )
    clause_type_confidence = Column(Float, default=0)  # 0-100

    # Conteudo
    original_text = Column(Text, nullable=False)  # Texto original
    normalized_text = Column(Text)  # Texto normalizado/limpo
    summary = Column(Text)  # Resumo da clausula

    # Localizacao no documento
    page_number = Column(Integer)
    start_position = Column(Integer)  # Posicao inicial no texto
    end_position = Column(Integer)  # Posicao final

    # Classificacao
    importance = Column(
        Enum(ClauseImportance, values_callable=lambda x: [e.value for e in x]),
        default=ClauseImportance.MEDIUM,
        nullable=False,
    )
    is_standard = Column(Boolean, default=True)  # Clausula padrao
    is_custom = Column(Boolean, default=False)  # Customizada
    is_risky = Column(Boolean, default=False)  # Apresenta risco

    # Entidades extraidas
    entities = Column(JSONB, default=list)
    # Ex: [{"type": "date", "value": "2025-01-01", "label": "inicio"}]

    dates_found = Column(JSONB, default=list)  # Datas encontradas
    values_found = Column(JSONB, default=list)  # Valores monetarios
    parties_mentioned = Column(JSONB, default=list)  # Partes mencionadas

    # Analise de risco da clausula
    risk_score = Column(Float, default=0)  # 0-100
    risk_reasons = Column(JSONB, default=list)

    # Comparacao com template
    template_clause_id = Column(UUID(as_uuid=True))
    template_match_score = Column(Float)  # 0-100
    deviations_from_template = Column(JSONB, default=list)

    # Obrigacoes identificadas
    obligations = Column(JSONB, default=list)
    # Ex: [{"party": "contratante", "action": "pagar", "deadline": "ate dia 10"}]

    # Condicoes e termos
    conditions = Column(JSONB, default=list)
    terms = Column(JSONB, default=list)

    # Flags especificas
    has_deadline = Column(Boolean, default=False)
    has_monetary_value = Column(Boolean, default=False)
    has_percentage = Column(Boolean, default=False)
    requires_action = Column(Boolean, default=False)
    is_negotiable = Column(Boolean, default=True)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Revisao manual
    manually_reviewed = Column(Boolean, default=False)
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)

    # Relacionamento
    analysis = relationship("ContractAnalysis", back_populates="clauses")

    def __repr__(self) -> str:
        return f"<ExtractedClause {self.clause_number}: {self.clause_type.value}>"

    @property
    def is_critical(self) -> bool:
        """Verifica se e clausula critica."""
        return self.importance == ClauseImportance.CRITICAL or self.is_risky or self.risk_score >= 70

    @property
    def word_count(self) -> int:
        """Conta palavras no texto original."""
        if not self.original_text:
            return 0
        return len(self.original_text.split())
