"""Accounting Period model - Período Contábil."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.financial.models.journal_entry import JournalEntry


class PeriodType(StrEnum):
    """Tipo do período contábil."""

    MONTHLY = "MONTHLY"  # Mensal
    QUARTERLY = "QUARTERLY"  # Trimestral
    SEMIANNUAL = "SEMIANNUAL"  # Semestral
    ANNUAL = "ANNUAL"  # Anual
    SPECIAL = "SPECIAL"  # Especial (ajuste, auditoria)


class PeriodStatus(StrEnum):
    """Status do período contábil."""

    PENDING = "PENDING"  # Pendente (drift do banco)
    FUTURE = "FUTURE"  # Futuro (não iniciado)
    OPEN = "OPEN"  # Aberto (aceita lançamentos)
    CLOSING = "CLOSING"  # Em fechamento
    CLOSED = "CLOSED"  # Fechado
    REOPENED = "REOPENED"  # Reaberto
    LOCKED = "LOCKED"  # Bloqueado (permanente)


class ClosingType(StrEnum):
    """Tipo de fechamento."""

    PROVISIONAL = "PROVISIONAL"  # Provisório
    DEFINITIVE = "DEFINITIVE"  # Definitivo
    AUDIT = "AUDIT"  # Para auditoria


class AccountingPeriod(Base):
    """Período Contábil - controle de períodos abertos/fechados."""

    __tablename__ = "fin_accounting_periods"
    __table_args__ = (UniqueConstraint("condominio_id", "year", "month", name="uq_period_year_month"),)

    # Primary Key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # Multi-tenant
    condominio_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # chart_id removido: não existe na tabela fin_accounting_periods

    # Identificação do Período
    code = Column(String(20), nullable=False)  # Ex: "2024-01", "2024-Q1"
    name = Column(String(100), nullable=False)  # Ex: "Janeiro 2024"
    description = Column(Text, nullable=True)

    # Período
    year = Column(Integer, nullable=False, index=True)
    month = Column(Integer, nullable=True)  # Null para períodos não mensais
    quarter = Column(Integer, nullable=True)  # 1-4 para trimestres

    # Tipo e Status
    period_type = Column(
        Enum(PeriodType, name="periodtype", create_type=True),
        nullable=False,
        default=PeriodType.MONTHLY,
    )
    status = Column(
        Enum(PeriodStatus, name="periodstatus", create_type=True),
        nullable=False,
        default=PeriodStatus.FUTURE,
    )

    # Datas
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=True)  # Quando foi aberto (era opening_date)
    opened_by = Column(UUID(as_uuid=True), nullable=True)  # Quem abriu
    closed_at = Column(DateTime(timezone=True), nullable=True)  # Quando foi fechado (era closing_date)
    # opening_date e closing_date removidos: banco usa opened_at e closed_at

    # Tipo de Fechamento
    closing_type = Column(
        Enum(ClosingType, name="closingtype", create_type=True),
        nullable=True,
    )

    # Estatísticas
    total_entries = Column(Integer, default=0, nullable=False)
    total_debit = Column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    total_credit = Column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    # total_documents, opening_balance_total, closing_balance_total removidos: não existem
    # period_revenue, period_expenses, period_result removidos: não existem

    # Fechamento
    closed_by = Column(UUID(as_uuid=True), nullable=True)
    closing_notes = Column(Text, nullable=True)
    # closing_journal_id removido: não existe na tabela

    # Reabertura
    reopened_by = Column(UUID(as_uuid=True), nullable=True)
    reopened_at = Column(DateTime(timezone=True), nullable=True)
    reopen_reason = Column(Text, nullable=True)
    reopen_count = Column(Integer, default=0, nullable=False)

    # Aprovação removida: requires_approval, approved_by, approved_at, approval_notes não existem

    # SPED
    sped_transmitted = Column(Boolean, default=False, nullable=False)
    sped_transmission_date = Column(DateTime(timezone=True), nullable=True)
    sped_receipt = Column(String(100), nullable=True)

    # Integração
    external_reference = Column(String(50), nullable=True)  # era external_code no modelo antigo
    integration_data = Column(JSONB, nullable=True)

    # Flags
    # is_initial removido: não existe na tabela
    is_adjustment = Column(Boolean, default=False, nullable=False)  # Período de ajuste
    is_closing = Column(Boolean, default=False, nullable=False)  # É período de fechamento
    is_opening = Column(Boolean, default=False, nullable=False)  # É período de abertura
    allow_posting = Column(Boolean, default=True, nullable=False)  # Permite lançamentos
    active = Column(Boolean, default=True, nullable=False)

    # Observações
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    deleted_by = Column(UUID(as_uuid=True), nullable=True)

    # Relationships
    journal_entries: list["JournalEntry"] = relationship(
        "JournalEntry",
        back_populates="period",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        """Representação string."""
        return f"<AccountingPeriod {self.code} - {self.status.value}>"

    @property
    def is_open(self) -> bool:
        """Verifica se o período está aberto."""
        return self.status in [PeriodStatus.OPEN, PeriodStatus.REOPENED]

    @property
    def is_closed(self) -> bool:
        """Verifica se o período está fechado."""
        return self.status in [PeriodStatus.CLOSED, PeriodStatus.LOCKED]

    @property
    def can_receive_entries(self) -> bool:
        """Verifica se o período pode receber lançamentos."""
        return self.is_open and self.allows_entries and self.active

    @property
    def can_close(self) -> bool:
        """Verifica se o período pode ser fechado."""
        return self.status == PeriodStatus.OPEN and self.total_debit == self.total_credit

    @property
    def can_reopen(self) -> bool:
        """Verifica se o período pode ser reaberto."""
        return self.status == PeriodStatus.CLOSED and not self.sped_transmitted

    @property
    def days_remaining(self) -> int:
        """Dias restantes até o fim do período."""
        if self.end_date:
            delta = self.end_date - date.today()
            return max(0, delta.days)
        return 0
