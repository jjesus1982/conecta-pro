"""Model para lancamentos de fluxo de caixa."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.models import Base


class CashFlowEntryType(StrEnum):
    """Tipo de lancamento."""

    ENTRADA = "entrada"  # Receita
    SAIDA = "saida"  # Despesa
    TRANSFERENCIA = "transferencia"  # Entre contas
    PREVISAO = "previsao"  # Previsao (nao realizado)
    AJUSTE = "ajuste"  # Ajuste contabil


class CashFlowSourceType(StrEnum):
    """Origem do lancamento."""

    MANUAL = "manual"
    CONTA_PAGAR = "conta_pagar"
    CONTA_RECEBER = "conta_receber"
    TRANSFERENCIA = "transferencia"
    IMPORTACAO = "importacao"
    REGRA_COBRANCA = "regra_cobranca"
    RECORRENTE = "recorrente"


class CashFlowEntryStatus(StrEnum):
    """Status do lancamento."""

    PREVISTO = "previsto"
    CONFIRMADO = "confirmado"
    REALIZADO = "realizado"
    CANCELADO = "cancelado"
    ESTORNADO = "estornado"


class RecurrenceFrequency(StrEnum):
    """Frequencia de recorrencia."""

    DIARIA = "diaria"
    SEMANAL = "semanal"
    QUINZENAL = "quinzenal"
    MENSAL = "mensal"
    BIMESTRAL = "bimestral"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"


class CashFlowEntry(Base):
    """Lancamento de fluxo de caixa."""

    __tablename__ = "cashflow_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )
    bank_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id"),
        nullable=True,
        index=True,
    )

    # Tipo e classificacao
    # Colunas nativas de ENUM no Postgres (cashflowentrytype/cashflowsourcetype/
    # cashflowentrystatus). Mapeadas como PGEnum plano (labels string) com
    # create_type=False para o SQLAlchemy emitir o cast correto no INSERT
    # (evita DatatypeMismatchError character varying -> enum). Os labels sao
    # exatamente os do banco (fonte da verdade), nao acoplados ao StrEnum Python.
    entry_type = Column(
        PGEnum(
            "entrada",
            "saida",
            name="cashflowentrytype",
            create_type=False,
        ),
        nullable=False,
    )
    source_type = Column(
        PGEnum(
            "conta_pagar",
            "conta_receber",
            "transferencia",
            "manual",
            "recorrente",
            "previsao",
            name="cashflowsourcetype",
            create_type=False,
        ),
        nullable=False,
        default=CashFlowSourceType.MANUAL.value,
    )
    status = Column(
        PGEnum(
            "previsto",
            "confirmado",
            "realizado",
            "cancelado",
            name="cashflowentrystatus",
            create_type=False,
        ),
        nullable=False,
        default=CashFlowEntryStatus.PREVISTO.value,
    )

    # Categoria (usa categorias existentes de pagar/receber)
    payable_category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payable_categories.id"),
        nullable=True,
    )
    receivable_category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("receivable_categories.id"),
        nullable=True,
    )

    # Descricao
    description = Column(String(500), nullable=False)
    memo = Column(Text, nullable=True)

    # Valores
    expected_amount = Column(Numeric(15, 2), nullable=False)  # Valor previsto
    realized_amount = Column(Numeric(15, 2), nullable=True)  # Valor realizado
    difference = Column(Numeric(15, 2), nullable=True)  # Diferenca

    # Datas
    entry_date = Column(Date, nullable=False)  # Data do lancamento
    competence_date = Column(Date, nullable=True)  # Data de competencia
    due_date = Column(Date, nullable=True)  # Data de vencimento
    realized_date = Column(Date, nullable=True)  # Data de realizacao

    # Vinculo com contas
    payable_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payable_accounts.id"),
        nullable=True,
    )
    receivable_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("receivable_accounts.id"),
        nullable=True,
    )
    bank_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_transactions.id"),
        nullable=True,
    )

    # Transferencia
    is_transfer = Column(Boolean, default=False)
    transfer_to_account_id = Column(UUID(as_uuid=True), nullable=True)
    transfer_entry_id = Column(UUID(as_uuid=True), nullable=True)  # Lancamento par

    # Recorrencia
    is_recurring = Column(Boolean, default=False)
    # ENUM nativo no Postgres (recurrencefrequency). Mapeado como PGEnum plano
    # com create_type=False para emitir o cast correto no INSERT.
    recurrence_frequency = Column(
        PGEnum(
            "diaria",
            "semanal",
            "quinzenal",
            "mensal",
            "bimestral",
            "trimestral",
            "semestral",
            "anual",
            name="recurrencefrequency",
            create_type=False,
        ),
        nullable=True,
    )
    recurrence_day = Column(Integer, nullable=True)  # Dia do mes/semana
    recurrence_start = Column(Date, nullable=True)
    recurrence_end = Column(Date, nullable=True)
    recurrence_count = Column(Integer, nullable=True)  # Numero de ocorrencias
    recurrence_parent_id = Column(UUID(as_uuid=True), nullable=True)  # ID do lancamento pai
    recurrence_index = Column(Integer, nullable=True)  # Indice na serie

    # Terceiro (fornecedor/cliente)
    counterparty_type = Column(String(20), nullable=True)  # supplier, customer, other
    counterparty_id = Column(UUID(as_uuid=True), nullable=True)
    counterparty_name = Column(String(150), nullable=True)

    # Centro de custo
    cost_center_id = Column(UUID(as_uuid=True), nullable=True)
    cost_center_name = Column(String(100), nullable=True)

    # Tags e classificacao
    tags = Column(JSONB, default=list)

    # Flags
    is_essential = Column(Boolean, default=False)  # Despesa essencial
    is_discretionary = Column(Boolean, default=False)  # Despesa discricionaria
    is_budgeted = Column(Boolean, default=False)  # Esta no orcamento
    is_approved = Column(Boolean, default=False)
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # Anexos
    attachments = Column(JSONB, default=list)

    # Observacoes
    notes = Column(Text, nullable=True)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_cashflow_entries_condominio", "condominio_id"),
        Index("ix_cashflow_entries_account", "bank_account_id"),
        Index("ix_cashflow_entries_date", "entry_date"),
        Index("ix_cashflow_entries_type", "entry_type"),
        Index("ix_cashflow_entries_source", "source_type"),
        Index("ix_cashflow_entries_status", "status"),
        Index("ix_cashflow_entries_due", "due_date"),
        Index(
            "ix_cashflow_entries_condominio_date",
            "condominio_id",
            "entry_date",
        ),
        Index(
            "ix_cashflow_entries_condominio_type",
            "condominio_id",
            "entry_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<CashFlowEntry {self.entry_type} R${self.expected_amount}>"

    @property
    def is_income(self) -> bool:
        """Verifica se e entrada."""
        return self.entry_type == CashFlowEntryType.ENTRADA.value

    @property
    def is_expense(self) -> bool:
        """Verifica se e saida."""
        return self.entry_type == CashFlowEntryType.SAIDA.value

    @property
    def is_forecast(self) -> bool:
        """Verifica se e previsao."""
        return self.entry_type == CashFlowEntryType.PREVISAO.value

    @property
    def is_realized(self) -> bool:
        """Verifica se foi realizado."""
        return self.status == CashFlowEntryStatus.REALIZADO.value

    @property
    def is_pending(self) -> bool:
        """Verifica se esta pendente."""
        return self.status in [
            CashFlowEntryStatus.PREVISTO.value,
            CashFlowEntryStatus.CONFIRMADO.value,
        ]

    @property
    def is_overdue(self) -> bool:
        """Verifica se esta vencido."""
        if not self.due_date or self.is_realized:
            return False
        return self.due_date < date.today()

    @property
    def signed_amount(self) -> Decimal:
        """Retorna valor com sinal."""
        amount = self.realized_amount or self.expected_amount
        if self.is_expense:
            return -amount
        return amount

    @property
    def variance(self) -> Decimal | None:
        """Calcula variacao entre previsto e realizado."""
        if self.realized_amount is None:
            return None
        return self.realized_amount - self.expected_amount

    @property
    def variance_percentage(self) -> float | None:
        """Calcula variacao percentual."""
        if self.variance is None or self.expected_amount == 0:
            return None
        return float(self.variance / self.expected_amount * 100)

    def confirm(self) -> None:
        """Confirma o lancamento."""
        self.status = CashFlowEntryStatus.CONFIRMADO.value

    def realize(
        self,
        amount: Decimal | None = None,
        realized_date: date | None = None,
    ) -> None:
        """Realiza o lancamento."""
        self.status = CashFlowEntryStatus.REALIZADO.value
        self.realized_amount = amount or self.expected_amount
        self.realized_date = realized_date or date.today()
        self.difference = self.realized_amount - self.expected_amount

    def cancel(self) -> None:
        """Cancela o lancamento."""
        self.status = CashFlowEntryStatus.CANCELADO.value

    def reverse(self) -> None:
        """Estorna o lancamento."""
        self.status = CashFlowEntryStatus.ESTORNADO.value

    def approve(self, user_id: uuid.UUID) -> None:
        """Aprova o lancamento."""
        self.is_approved = True
        self.approved_by = user_id
        self.approved_at = datetime.utcnow()

    def link_to_payable(self, account_id: uuid.UUID) -> None:
        """Vincula a conta a pagar."""
        self.payable_account_id = account_id
        self.source_type = CashFlowSourceType.CONTA_PAGAR.value

    def link_to_receivable(self, account_id: uuid.UUID) -> None:
        """Vincula a conta a receber."""
        self.receivable_account_id = account_id
        self.source_type = CashFlowSourceType.CONTA_RECEBER.value

    def link_to_transaction(self, transaction_id: uuid.UUID) -> None:
        """Vincula a transacao bancaria."""
        self.bank_transaction_id = transaction_id
        self.status = CashFlowEntryStatus.REALIZADO.value

    def set_recurrence(
        self,
        frequency: str,
        start_date: date,
        end_date: date | None = None,
        count: int | None = None,
        day: int | None = None,
    ) -> None:
        """Configura recorrencia."""
        self.is_recurring = True
        self.recurrence_frequency = frequency
        self.recurrence_start = start_date
        self.recurrence_end = end_date
        self.recurrence_count = count
        self.recurrence_day = day

    def to_dict(self) -> dict:
        """Converte para dicionario."""
        return {
            "id": str(self.id),
            "condominio_id": str(self.condominio_id),
            "bank_account_id": str(self.bank_account_id) if self.bank_account_id else None,
            "entry_type": self.entry_type,
            "source_type": self.source_type,
            "status": self.status,
            "description": self.description,
            "expected_amount": float(self.expected_amount),
            "realized_amount": float(self.realized_amount) if self.realized_amount else None,
            "signed_amount": float(self.signed_amount),
            "variance": float(self.variance) if self.variance else None,
            "entry_date": self.entry_date.isoformat(),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "realized_date": self.realized_date.isoformat() if self.realized_date else None,
            "is_income": self.is_income,
            "is_expense": self.is_expense,
            "is_realized": self.is_realized,
            "is_overdue": self.is_overdue,
            "is_recurring": self.is_recurring,
            "counterparty_name": self.counterparty_name,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
