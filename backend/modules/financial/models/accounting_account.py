"""Accounting Account model - Conta Contábil."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
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
    from modules.financial.models.chart_of_accounts import ChartOfAccounts
    from modules.financial.models.cost_center import CostCenter
    from modules.financial.models.journal_entry import JournalEntryLine


class AccountType(StrEnum):
    """Tipo da conta contábil."""

    ASSET = "ASSET"  # Ativo
    LIABILITY = "LIABILITY"  # Passivo
    EQUITY = "EQUITY"  # Patrimônio Líquido
    REVENUE = "REVENUE"  # Receita
    EXPENSE = "EXPENSE"  # Despesa
    COST = "COST"  # Custo


class AccountNature(StrEnum):
    """Natureza da conta (saldo normal)."""

    DEBIT = "DEBIT"  # Saldo devedor (Ativo, Despesa, Custo)
    CREDIT = "CREDIT"  # Saldo credor (Passivo, PL, Receita)


class AccountClassification(StrEnum):
    """Classificação da conta."""

    SYNTHETIC = "SYNTHETIC"  # Sintética (agrupadora)
    ANALYTICAL = "ANALYTICAL"  # Analítica (recebe lançamentos)


class AccountStatus(StrEnum):
    """Status da conta."""

    ACTIVE = "ACTIVE"  # Ativa
    INACTIVE = "INACTIVE"  # Inativa
    BLOCKED = "BLOCKED"  # Bloqueada
    CLOSED = "CLOSED"  # Encerrada


class SpedAccountNature(StrEnum):
    """Natureza da conta SPED."""

    # Contas de Ativo
    ATIVO_CIRCULANTE = "01"
    ATIVO_NAO_CIRCULANTE = "02"
    # Contas de Passivo
    PASSIVO_CIRCULANTE = "03"
    PASSIVO_NAO_CIRCULANTE = "04"
    PATRIMONIO_LIQUIDO = "05"
    # Contas de Resultado
    RECEITA = "06"
    CUSTO = "07"
    DESPESA = "08"
    OUTRAS_CONTAS = "09"


class AccountingAccount(Base):
    """Conta Contábil - representa uma conta do plano de contas."""

    __tablename__ = "fin_accounting_accounts"
    __table_args__ = (UniqueConstraint("chart_id", "code", name="uq_account_chart_code"),)

    # Primary Key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )

    # Multi-tenant
    condominio_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Referência ao Plano de Contas
    chart_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fin_charts_of_accounts.id"),
        nullable=False,
        index=True,
    )

    # Hierarquia
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fin_accounting_accounts.id"),
        nullable=True,
        index=True,
    )

    # Identificação
    code = Column(String(30), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    short_name = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)

    # Classificação
    # native_enum=False: a coluna real no banco é varchar (não o tipo enum nativo);
    # sem isso o ORM casta o bind p/ ::accounttype e quebra (varchar = accounttype).
    account_type = Column(
        Enum(AccountType, native_enum=False),
        nullable=False,
    )
    nature = Column(
        Enum(AccountNature, native_enum=False),
        nullable=False,
    )
    classification = Column(
        Enum(AccountClassification, native_enum=False),
        nullable=False,
    )
    status = Column(
        Enum(AccountStatus, native_enum=False),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )

    # Nível e Ordem
    level = Column(Integer, nullable=False, default=1)
    order_index = Column(Integer, nullable=True)
    path = Column(String(200), nullable=True)  # Ex: "1.1.01.001"

    # SPED
    sped_nature = Column(
        Enum(SpedAccountNature, native_enum=False),
        nullable=True,
    )
    sped_referential_code = Column(String(30), nullable=True)
    sped_description = Column(String(200), nullable=True)

    # Saldos
    opening_balance = Column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    current_balance = Column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    debit_total = Column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    credit_total = Column(Numeric(18, 2), default=Decimal("0"), nullable=False)

    # Saldos do Período
    period_debit = Column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    period_credit = Column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    period_balance = Column(Numeric(18, 2), default=Decimal("0"), nullable=False)

    # Data do último movimento
    last_movement_date = Column(DateTime(timezone=True), nullable=True)
    last_balance_update = Column(DateTime(timezone=True), nullable=True)

    # Centro de Custo Padrão
    default_cost_center_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fin_cost_centers.id"),
        nullable=True,
    )

    # Configurações
    requires_cost_center = Column(Boolean, default=False, nullable=False)
    requires_project = Column(Boolean, default=False, nullable=False)
    requires_history = Column(Boolean, default=True, nullable=False)
    allows_manual_entry = Column(Boolean, default=True, nullable=False)

    # DRE - Demonstração do Resultado
    dre_group = Column(String(50), nullable=True)
    dre_order = Column(Integer, nullable=True)

    # Balancete
    balance_sheet_group = Column(String(50), nullable=True)
    balance_sheet_order = Column(Integer, nullable=True)

    # Integração
    external_code = Column(String(50), nullable=True)
    legacy_code = Column(String(50), nullable=True)
    integration_data = Column(JSONB, nullable=True)

    # Flags
    is_system = Column(Boolean, default=False, nullable=False)  # Conta do sistema
    is_tax_related = Column(Boolean, default=False, nullable=False)  # Relacionada a impostos
    is_bank_account = Column(Boolean, default=False, nullable=False)  # É conta bancária
    bank_account_id = Column(UUID(as_uuid=True), nullable=True)  # Ref. conta bancária
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
    chart_of_accounts: "ChartOfAccounts" = relationship(
        "ChartOfAccounts",
        back_populates="accounts",
    )
    parent: Optional["AccountingAccount"] = relationship(
        "AccountingAccount",
        remote_side="AccountingAccount.id",
        back_populates="children",
    )
    children: list["AccountingAccount"] = relationship(
        "AccountingAccount",
        back_populates="parent",
        lazy="dynamic",
    )
    default_cost_center: Optional["CostCenter"] = relationship(
        "CostCenter",
        foreign_keys=[default_cost_center_id],
    )
    journal_lines: list["JournalEntryLine"] = relationship(
        "JournalEntryLine",
        back_populates="account",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        """Representação string."""
        return f"<AccountingAccount {self.code} - {self.name}>"

    @property
    def is_debit_nature(self) -> bool:
        """Verifica se a conta tem natureza devedora."""
        return self.nature == AccountNature.DEBIT

    @property
    def is_credit_nature(self) -> bool:
        """Verifica se a conta tem natureza credora."""
        return self.nature == AccountNature.CREDIT

    @property
    def is_analytical(self) -> bool:
        """Verifica se a conta é analítica."""
        return self.classification == AccountClassification.ANALYTICAL

    @property
    def is_synthetic(self) -> bool:
        """Verifica se a conta é sintética."""
        return self.classification == AccountClassification.SYNTHETIC

    @property
    def can_receive_entries(self) -> bool:
        """Verifica se a conta pode receber lançamentos."""
        return self.is_analytical and self.status == AccountStatus.ACTIVE and self.allows_manual_entry and self.active

    def calculate_balance(self) -> Decimal:
        """Calcula o saldo da conta baseado na natureza."""
        if self.is_debit_nature:
            return self.debit_total - self.credit_total + self.opening_balance
        return self.credit_total - self.debit_total + self.opening_balance
