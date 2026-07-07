"""Model para contas a receber."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.financial.models.customer import Customer
    from modules.financial.models.receivable_category import ReceivableCategory
    from modules.financial.models.receivable_installment import ReceivableInstallment


class ReceivableStatus(StrEnum):
    """Status da conta a receber."""

    PENDENTE = "pendente"  # Aguardando vencimento
    VENCIDA = "vencida"  # Vencida e nao paga
    PARCIAL = "parcial"  # Parcialmente paga
    PAGA = "paga"  # Totalmente paga
    CANCELADA = "cancelada"  # Cancelada
    SUSPENSA = "suspensa"  # Suspensa temporariamente
    PROTESTADA = "protestada"  # Em protesto
    ACORDO = "acordo"  # Em acordo de pagamento
    BAIXADA = "baixada"  # Baixada (perda)


class ReceivableType(StrEnum):
    """Tipo de conta a receber."""

    AVULSA = "avulsa"  # Conta avulsa
    PARCELADA = "parcelada"  # Conta parcelada
    RECORRENTE = "recorrente"  # Conta recorrente
    BOLETO = "boleto"  # Boleto gerado
    ACORDO = "acordo"  # Acordo de divida


class ReceivablePriority(StrEnum):
    """Prioridade de cobranca."""

    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    URGENTE = "urgente"


class RecurrenceType(StrEnum):
    """Tipo de recorrencia."""

    MENSAL = "mensal"
    BIMESTRAL = "bimestral"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"


class ReceivableAccount(Base):
    """Conta a receber."""

    __tablename__ = "receivable_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Identificacao
    code = Column(String(30), nullable=True)  # Codigo interno
    document_number = Column(String(50), nullable=True)  # Numero documento
    description = Column(String(500), nullable=False)
    receivable_type = Column(String(20), nullable=False, default=ReceivableType.AVULSA.value)
    status = Column(String(20), nullable=False, default=ReceivableStatus.PENDENTE.value)
    priority = Column(String(20), default=ReceivablePriority.MEDIA.value)

    # Cliente/Devedor
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customers.id"),
        nullable=True,
        index=True,
    )
    # Nome/documento do devedor (denormalizado — usado quando customer_id e NULL,
    # ex.: contas importadas de NFS-e sem vinculo com o CRM)
    customer_name = Column(String(255), nullable=True)
    customer_document = Column(String(20), nullable=True)

    # Vinculacao com unidade/morador
    unidade_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    morador_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Categoria
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("receivable_categories.id"),
        nullable=True,
        index=True,
    )

    # Valores
    gross_value = Column(Numeric(15, 2), nullable=False)  # Valor bruto
    discount_value = Column(Numeric(15, 2), default=0)  # Descontos
    addition_value = Column(Numeric(15, 2), default=0)  # Acrescimos
    interest_value = Column(Numeric(15, 2), default=0)  # Juros
    penalty_value = Column(Numeric(15, 2), default=0)  # Multa
    net_value = Column(Numeric(15, 2), nullable=False)  # Valor liquido
    paid_value = Column(Numeric(15, 2), default=0)  # Valor recebido
    remaining_value = Column(Numeric(15, 2), nullable=True)  # Valor restante

    # Configuracoes de juros e multa
    interest_rate = Column(Numeric(8, 4), default=1)  # % juros ao mes
    penalty_rate = Column(Numeric(8, 4), default=2)  # % multa
    grace_days = Column(Integer, default=0)  # Dias de carencia

    # Datas
    issue_date = Column(Date, nullable=True)  # Data emissao
    entry_date = Column(Date, default=date.today)  # Data entrada
    due_date = Column(Date, nullable=False, index=True)  # Data vencimento
    payment_date = Column(Date, nullable=True)  # Data recebimento
    competence_date = Column(Date, nullable=True)  # Competencia (mes/ano referencia)

    # Parcelamento
    total_installments = Column(Integer, default=1)
    current_installment = Column(Integer, default=1)

    # Recorrencia
    is_recurring = Column(Boolean, default=False)
    recurrence_type = Column(String(20), nullable=True)
    recurrence_end_date = Column(Date, nullable=True)
    parent_account_id = Column(
        "parent_account_id",  # Nome real da coluna no banco
        UUID(as_uuid=True),
        ForeignKey("receivable_accounts.id"),
        nullable=True,
    )

    # Boleto
    boleto_generated = Column(Boolean, default=False)
    boleto_number = Column(String(50), nullable=True)
    boleto_barcode = Column(String(100), nullable=True)
    boleto_digitable_line = Column(String(100), nullable=True)
    boleto_url = Column(String(500), nullable=True)
    boleto_generated_at = Column(DateTime, nullable=True)

    # PIX
    pix_generated = Column(Boolean, default=False)
    pix_qrcode = Column(Text, nullable=True)
    pix_copy_paste = Column(String(500), nullable=True)
    pix_txid = Column(String(100), nullable=True)

    # Centro de custo
    cost_center = Column(String(50), nullable=True)

    # Cobranca
    collection_attempts = Column(Integer, default=0)  # Tentativas de cobranca
    last_collection_date = Column(DateTime, nullable=True)  # Ultima cobranca
    next_collection_date = Column(DateTime, nullable=True)  # Proxima cobranca
    collection_notes = Column(Text, nullable=True)  # Notas de cobranca

    # Protesto
    is_protested = Column(Boolean, default=False)
    protested_at = Column(DateTime, nullable=True)
    protest_number = Column(String(50), nullable=True)

    # Acordo
    is_in_agreement = Column(Boolean, default=False)
    agreement_id = Column(UUID(as_uuid=True), nullable=True)

    # Baixa
    is_written_off = Column(Boolean, default=False)
    written_off_at = Column(DateTime, nullable=True)
    written_off_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    written_off_reason = Column(Text, nullable=True)

    # Anexos e observacoes
    attachments = Column(JSONB, default=list)
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # Tags
    tags = Column(JSONB, default=list)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    customer: Optional["Customer"] = relationship("Customer", back_populates="receivable_accounts")
    category: Optional["ReceivableCategory"] = relationship("ReceivableCategory", back_populates="receivable_accounts")
    installments: list["ReceivableInstallment"] = relationship(
        "ReceivableInstallment",
        back_populates="receivable_account",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_receivable_accounts_due_date", "due_date"),
        Index("ix_receivable_accounts_status", "status"),
        Index("ix_receivable_accounts_customer", "customer_id"),
        Index("ix_receivable_accounts_category", "category_id"),
        Index("ix_receivable_accounts_document", "document_number"),
        Index("ix_receivable_accounts_unidade", "unidade_id"),
        Index(
            "ix_receivable_accounts_condominio_status_due",
            "condominio_id",
            "status",
            "due_date",
        ),
    )

    def __repr__(self) -> str:
        return f"<ReceivableAccount {self.document_number or self.id} - {self.net_value}>"

    @property
    def is_overdue(self) -> bool:
        """Verifica se esta vencida."""
        if self.status in [ReceivableStatus.PAGA.value, ReceivableStatus.CANCELADA.value]:
            return False
        return self.due_date < date.today()

    @property
    def days_until_due(self) -> int:
        """Dias ate o vencimento."""
        return (self.due_date - date.today()).days

    @property
    def days_overdue(self) -> int:
        """Dias de atraso."""
        if not self.is_overdue:
            return 0
        return (date.today() - self.due_date).days

    @property
    def is_paid(self) -> bool:
        """Verifica se esta paga."""
        return self.status == ReceivableStatus.PAGA.value

    @property
    def is_partially_paid(self) -> bool:
        """Verifica se esta parcialmente paga."""
        return self.paid_value > 0 and self.paid_value < self.net_value

    @property
    def payment_percentage(self) -> float:
        """Percentual pago."""
        if self.net_value == 0:
            return 0
        return float((self.paid_value / self.net_value) * 100)

    @property
    def balance(self) -> Decimal:
        """Saldo a receber."""
        return self.net_value - self.paid_value

    @property
    def current_total_value(self) -> Decimal:
        """Valor total atual com juros e multa."""
        if not self.is_overdue or self.is_paid:
            return self.net_value

        value = self.net_value
        days_late = self.days_overdue - self.grace_days
        if days_late > 0:
            # Aplica multa
            if self.penalty_rate > 0:
                penalty = value * (self.penalty_rate / 100)
                value += penalty
            # Aplica juros proporcionais
            if self.interest_rate > 0:
                daily_rate = self.interest_rate / 30
                interest = self.net_value * (daily_rate / 100) * days_late
                value += interest
        return value

    def calculate_net_value(self) -> Decimal:
        """Calcula valor liquido."""
        net = self.gross_value - self.discount_value + self.addition_value
        return max(net, Decimal("0"))

    def update_status(self) -> None:
        """Atualiza status baseado nos recebimentos."""
        if self.paid_value >= self.net_value:
            self.status = ReceivableStatus.PAGA.value
        elif self.paid_value > 0:
            self.status = ReceivableStatus.PARCIAL.value
        elif self.is_overdue:
            self.status = ReceivableStatus.VENCIDA.value
        else:
            self.status = ReceivableStatus.PENDENTE.value

    def register_payment(
        self,
        value: Decimal,
        payment_date: date,
    ) -> None:
        """Registra recebimento."""
        self.paid_value += value
        self.remaining_value = self.net_value - self.paid_value
        self.payment_date = payment_date
        self.update_status()

    def cancel(self, reason: str) -> None:
        """Cancela a conta."""
        self.status = ReceivableStatus.CANCELADA.value
        self.internal_notes = f"Cancelada: {reason}\n{self.internal_notes or ''}"

    def suspend(self, reason: str) -> None:
        """Suspende a conta."""
        self.status = ReceivableStatus.SUSPENSA.value
        self.internal_notes = f"Suspensa: {reason}\n{self.internal_notes or ''}"

    def protest(self, user_id: uuid.UUID, protest_number: str) -> None:  # pylint: disable=unused-argument
        """Envia para protesto."""
        self.is_protested = True
        self.protested_at = datetime.utcnow()
        self.protest_number = protest_number
        self.status = ReceivableStatus.PROTESTADA.value

    def write_off(self, user_id: uuid.UUID, reason: str) -> None:
        """Baixa a conta (perda)."""
        self.is_written_off = True
        self.written_off_at = datetime.utcnow()
        self.written_off_by = user_id
        self.written_off_reason = reason
        self.status = ReceivableStatus.BAIXADA.value

    def start_agreement(self, agreement_id: uuid.UUID) -> None:
        """Inicia acordo de pagamento."""
        self.is_in_agreement = True
        self.agreement_id = agreement_id
        self.status = ReceivableStatus.ACORDO.value

    def generate_boleto(
        self,
        number: str,
        barcode: str,
        digitable_line: str,
        url: str | None = None,
    ) -> None:
        """Registra geracao de boleto."""
        self.boleto_generated = True
        self.boleto_number = number
        self.boleto_barcode = barcode
        self.boleto_digitable_line = digitable_line
        self.boleto_url = url
        self.boleto_generated_at = datetime.utcnow()

    def generate_pix(
        self,
        qrcode: str,
        copy_paste: str,
        txid: str,
    ) -> None:
        """Registra geracao de PIX."""
        self.pix_generated = True
        self.pix_qrcode = qrcode
        self.pix_copy_paste = copy_paste
        self.pix_txid = txid

    def register_collection_attempt(self) -> None:
        """Registra tentativa de cobranca."""
        self.collection_attempts += 1
        self.last_collection_date = datetime.utcnow()

    def to_dict(self) -> dict:
        """Converte para dicionario."""
        return {
            "id": str(self.id),
            "code": self.code,
            "document_number": self.document_number,
            "description": self.description,
            "receivable_type": self.receivable_type,
            "status": self.status,
            "priority": self.priority,
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "category_id": str(self.category_id) if self.category_id else None,
            "unidade_id": str(self.unidade_id) if self.unidade_id else None,
            "gross_value": float(self.gross_value),
            "net_value": float(self.net_value),
            "paid_value": float(self.paid_value),
            "balance": float(self.balance),
            "current_total_value": float(self.current_total_value),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "is_overdue": self.is_overdue,
            "days_overdue": self.days_overdue,
            "payment_percentage": self.payment_percentage,
            "boleto_generated": self.boleto_generated,
            "pix_generated": self.pix_generated,
        }
