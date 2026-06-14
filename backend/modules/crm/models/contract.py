"""
Models para Gestão de Contratos.

Gerencia todo o ciclo de vida dos contratos:
- Contratos recorrentes e pontuais
- Templates e cláusulas
- Aditivos e renovações
- Reajustes por índices econômicos
- SLA e penalidades
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class ContractType(enum.Enum):
    """Tipos de contrato."""

    RECURRING = "recurring"  # Recorrente (mensal)
    ONE_TIME = "one_time"  # Pontual (único)


class ContractStatus(enum.Enum):
    """Status do contrato."""

    DRAFT = "draft"  # Rascunho
    PENDING_SIGNATURE = "pending_signature"  # Aguardando assinatura
    ACTIVE = "active"  # Ativo
    SUSPENDED = "suspended"  # Suspenso
    CANCELLED = "cancelled"  # Cancelado
    TERMINATED = "terminated"  # Encerrado


class AdjustmentIndex(enum.Enum):
    """Índices de reajuste."""

    IGPM = "igpm"  # IGP-M (FGV)
    IPCA = "ipca"  # IPCA (IBGE)
    INPC = "inpc"  # INPC (IBGE)
    FIXED = "fixed"  # Percentual fixo
    CUSTOM = "custom"  # Personalizado


class AddendumType(enum.Enum):
    """Tipos de aditivo."""

    ADJUSTMENT = "adjustment"  # Reajuste de valor
    SCOPE_CHANGE = "scope_change"  # Alteração de escopo
    TERM_CHANGE = "term_change"  # Alteração de prazo
    TEAM_CHANGE = "team_change"  # Alteração de equipe/postos
    EQUIPMENT_CHANGE = "equipment_change"  # Alteração de equipamentos
    OTHER = "other"  # Outras alterações


class ServiceType(enum.Enum):
    """Tipos de serviço."""

    SECURITY = "security"  # Vigilância patrimonial
    REMOTE_GATEHOUSE = "remote_gatehouse"  # Portaria remota
    ELECTRONIC_SECURITY = "electronic_security"  # Segurança eletrônica
    MONITORING_24H = "monitoring_24h"  # Monitoramento 24h
    CLEANING = "cleaning"  # Limpeza
    GARDENING = "gardening"  # Jardinagem
    MAINTENANCE = "maintenance"  # Manutenção
    FACILITIES = "facilities"  # Facilities geral


class Contract(Base):
    """
    Modelo principal de Contrato.

    Gerencia contratos recorrentes e pontuais com suporte a:
    - Renovação automática
    - Reajuste por índice econômico
    - SLA com indicadores
    - Assinatura digital
    """

    __tablename__ = "contracts"

    # Identificação
    id = Column(UUID(as_uuid=True), primary_key=True)
    contract_number = Column(String(30), unique=True, nullable=False, index=True)

    # Relacionamentos
    client_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    opportunity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id"),
        nullable=True,
    )
    proposal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("proposals.id"),
        nullable=True,
    )
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contract_templates.id"),
        nullable=True,
    )

    # Tipo e Status
    contract_type = Column(
        Enum(ContractType, values_callable=lambda obj: [e.value for e in obj], name="contracttype"),
        nullable=False,
        default=ContractType.RECURRING,
    )
    status = Column(
        Enum(ContractStatus, values_callable=lambda obj: [e.value for e in obj], name="contractstatus"),
        nullable=False,
        default=ContractStatus.DRAFT,
    )

    # Descrição
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Valores
    monthly_value = Column(Numeric(12, 2), nullable=False, default=0)
    total_value = Column(Numeric(12, 2), nullable=False, default=0)
    setup_fee = Column(Numeric(10, 2), default=0)

    # Vigência
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # Null = indeterminado
    grace_period_days = Column(Integer, default=0)
    notice_period_days = Column(Integer, default=30)

    # Renovação
    auto_renewal = Column(Boolean, default=True)
    renewal_period_months = Column(Integer, default=12)
    renewal_notification_days = Column(Integer, default=30)

    # Reajuste
    adjustment_enabled = Column(Boolean, default=True)
    adjustment_index = Column(
        Enum(AdjustmentIndex, values_callable=lambda obj: [e.value for e in obj], name="adjustmentindex"), nullable=True
    )
    adjustment_fixed_percent = Column(Numeric(5, 2), nullable=True)
    adjustment_base_date = Column(Date, nullable=True)
    last_adjustment_date = Column(Date, nullable=True)
    next_adjustment_date = Column(Date, nullable=True)

    # SLA
    has_sla = Column(Boolean, default=False)
    sla_config = Column(JSONB, nullable=True)

    # Conteúdo
    content = Column(Text, nullable=True)
    clauses = Column(JSONB, nullable=True)

    # Assinatura
    signature_required = Column(Boolean, default=True)
    signature_provider = Column(String(50), nullable=True)
    signature_document_id = Column(String(100), nullable=True)
    signed_at = Column(DateTime, nullable=True)
    signed_by_client = Column(String(200), nullable=True)
    signed_by_company = Column(String(200), nullable=True)

    # Documentos
    pdf_file_path = Column(String(500), nullable=True)

    # Responsáveis
    commercial_manager_id = Column(UUID(as_uuid=True), nullable=True)
    account_manager_id = Column(UUID(as_uuid=True), nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=False), nullable=True)  # retorna str (serializa em *Response)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    template = relationship("ContractTemplate", back_populates="contracts")
    items = relationship(
        "ContractItem",
        back_populates="contract",
        cascade="all, delete-orphan",
    )
    addendums = relationship(
        "ContractAddendum",
        back_populates="contract",
        cascade="all, delete-orphan",
    )
    sla_reports = relationship(
        "ContractSLAReport",
        back_populates="contract",
        cascade="all, delete-orphan",
    )

    # Formato do número
    NUMBER_FORMAT = "CONT-{year}-{sequence:05d}"

    @classmethod
    def generate_number(cls, sequence: int) -> str:
        """Gera número único do contrato."""
        return cls.NUMBER_FORMAT.format(
            year=date.today().year,
            sequence=sequence,
        )

    @property
    def is_draft(self) -> bool:
        """Verifica se está em rascunho."""
        return self.status == ContractStatus.DRAFT

    @property
    def is_active_contract(self) -> bool:
        """Verifica se contrato está ativo."""
        return self.status == ContractStatus.ACTIVE

    @property
    def is_pending_signature(self) -> bool:
        """Verifica se aguarda assinatura."""
        return self.status == ContractStatus.PENDING_SIGNATURE

    @property
    def is_terminated(self) -> bool:
        """Verifica se está encerrado."""
        return self.status in [ContractStatus.CANCELLED, ContractStatus.TERMINATED]

    @property
    def is_renewable(self) -> bool:
        """Verifica se pode ser renovado."""
        return (
            self.auto_renewal and self.status == ContractStatus.ACTIVE and self.contract_type == ContractType.RECURRING
        )

    @property
    def days_until_end(self) -> int | None:
        """Dias até o fim do contrato."""
        if not self.end_date:
            return None
        delta = self.end_date - date.today()
        return delta.days

    @property
    def is_expiring_soon(self) -> bool:
        """Verifica se está próximo do vencimento (30 dias)."""
        days = self.days_until_end
        return days is not None and 0 < days <= 30

    @property
    def is_expired(self) -> bool:
        """Verifica se está vencido."""
        if not self.end_date:
            return False
        return self.end_date < date.today()

    @property
    def needs_adjustment(self) -> bool:
        """Verifica se precisa de reajuste."""
        if not self.adjustment_enabled or not self.next_adjustment_date:
            return False
        return self.next_adjustment_date <= date.today()

    @property
    def days_until_adjustment(self) -> int | None:
        """Dias até o próximo reajuste."""
        if not self.next_adjustment_date:
            return None
        delta = self.next_adjustment_date - date.today()
        return delta.days

    def calculate_next_adjustment_date(self) -> date | None:
        """Calcula a próxima data de reajuste."""
        if not self.adjustment_enabled:
            return None

        base = self.last_adjustment_date or self.adjustment_base_date or self.start_date
        if not base:
            return None

        # Próximo aniversário
        next_date = date(base.year + 1, base.month, base.day)
        while next_date <= date.today():
            next_date = date(next_date.year + 1, next_date.month, next_date.day)

        return next_date

    def get_sla_indicators(self) -> list[dict]:
        """Retorna indicadores de SLA."""
        if not self.sla_config:
            return []
        try:
            return self.sla_config.get("indicators", [])
        except (AttributeError, TypeError):
            return []


class ContractTemplate(Base):  # pylint: disable=too-few-public-methods
    """
    Template de Contrato.

    Templates pré-configurados por tipo de serviço
    com variáveis dinâmicas e cláusulas.
    """

    __tablename__ = "contract_templates"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Tipo de serviço (varchar — dados históricos não conformes com o enum Python)
    service_type = Column(String(30), nullable=True)

    # Conteúdo
    content_template = Column(Text, nullable=False)
    clauses = Column(JSONB, nullable=True)
    variables = Column(JSONB, nullable=True)  # Variáveis disponíveis

    # Versionamento
    version = Column(Integer, default=1)

    # Aprovação jurídica
    approved_by_legal = Column(Boolean, default=False)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(UUID(as_uuid=True), nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=False), nullable=True)  # retorna str (serializa em *Response)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    contracts = relationship("Contract", back_populates="template")

    def render(self, context: dict[str, Any]) -> str:
        """Renderiza o template com as variáveis."""
        content = self.content_template
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value))
        return content


class ContractItem(Base):  # pylint: disable=too-few-public-methods
    """
    Item/Serviço do Contrato.

    Serviços incluídos no contrato com valores e quantidades.
    """

    __tablename__ = "contract_items"

    id = Column(UUID(as_uuid=True), primary_key=True)
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id"),
        nullable=False,
        index=True,
    )

    # Serviço
    service_type = Column(String(30), nullable=False)
    service_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Valores
    quantity = Column(Integer, default=1)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(12, 2), nullable=False)

    # Observações
    notes = Column(Text, nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    contract = relationship("Contract", back_populates="items")

    def calculate_total(self) -> Decimal:
        """Calcula total do item."""
        return Decimal(str(self.quantity)) * self.unit_price


class ContractAddendum(Base):
    """
    Aditivo Contratual.

    Alterações no contrato: reajustes, escopo, prazo, etc.
    """

    __tablename__ = "contract_addendums"

    id = Column(UUID(as_uuid=True), primary_key=True)
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id"),
        nullable=False,
        index=True,
    )
    addendum_number = Column(String(30), nullable=False, index=True)

    # Tipo
    addendum_type = Column(
        Enum(AddendumType, values_callable=lambda obj: [e.value for e in obj], name="addendumtype"), nullable=False
    )

    # Valores (para reajuste)
    previous_value = Column(Numeric(12, 2), nullable=True)
    new_value = Column(Numeric(12, 2), nullable=True)
    adjustment_percent = Column(Numeric(5, 2), nullable=True)
    adjustment_index = Column(
        Enum(AdjustmentIndex, values_callable=lambda obj: [e.value for e in obj], name="adjustmentindex"), nullable=True
    )

    # Datas
    effective_date = Column(Date, nullable=False)

    # Descrição
    description = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)

    # Assinatura
    signed = Column(Boolean, default=False)
    signed_at = Column(DateTime, nullable=True)
    signature_document_id = Column(String(100), nullable=True)

    # Documento
    pdf_file_path = Column(String(500), nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=False), nullable=True)  # retorna str (serializa em *Response)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    contract = relationship("Contract", back_populates="addendums")

    # Formato do número
    NUMBER_FORMAT = "ADI-{year}-{sequence:05d}"

    @classmethod
    def generate_number(cls, sequence: int) -> str:
        """Gera número único do aditivo."""
        return cls.NUMBER_FORMAT.format(
            year=date.today().year,
            sequence=sequence,
        )

    @property
    def is_adjustment(self) -> bool:
        """Verifica se é aditivo de reajuste."""
        return self.addendum_type == AddendumType.ADJUSTMENT

    @property
    def value_difference(self) -> Decimal | None:
        """Diferença de valor no reajuste."""
        if self.previous_value and self.new_value:
            return self.new_value - self.previous_value
        return None


class ContractSLAReport(Base):
    """
    Relatório de SLA Mensal.

    Resultados mensais dos indicadores de SLA do contrato.
    """

    __tablename__ = "contract_sla_reports"

    id = Column(UUID(as_uuid=True), primary_key=True)
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id"),
        nullable=False,
        index=True,
    )

    # Período
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)

    # Resultados
    indicators = Column(JSONB, nullable=False)
    overall_score = Column(Numeric(5, 2), nullable=False)

    # Penalidades
    penalty_applied = Column(Boolean, default=False)
    penalty_percent = Column(Numeric(5, 2), default=0)
    penalty_amount = Column(Numeric(10, 2), default=0)

    # Status
    status = Column(String(20), default="draft")  # draft, approved, disputed

    # Auditoria
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    generated_by = Column(UUID(as_uuid=True), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    contract = relationship("Contract", back_populates="sla_reports")

    @property
    def period_label(self) -> str:
        """Rótulo do período."""
        return f"{self.year}-{self.month:02d}"

    @property
    def is_approved(self) -> bool:
        """Verifica se foi aprovado."""
        return self.status == "approved"

    @property
    def is_target_met(self) -> bool:
        """Verifica se atingiu a meta."""
        return self.overall_score >= 100

    def get_indicator_result(self, indicator_name: str) -> dict | None:
        """Retorna resultado de um indicador específico."""
        if not self.indicators:
            return None
        for indicator in self.indicators:
            if indicator.get("name") == indicator_name:
                return indicator
        return None
