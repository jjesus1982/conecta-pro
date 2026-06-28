"""Model para contas a pagar."""

import uuid
from sqlalchemy.dialects.postgresql import ARRAY
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
    from modules.financial.models.payable_category import PayableCategory
    from modules.financial.models.payable_installment import PayableInstallment
    from modules.financial.models.supplier import Supplier


class PayableStatus(StrEnum):
    """Status da conta a pagar."""

    PENDENTE = "pendente"  # Aguardando vencimento
    VENCIDA = "vencida"  # Vencida e não paga
    PARCIAL = "parcial"  # Parcialmente paga
    PAGA = "paga"  # Totalmente paga
    CANCELADA = "cancelada"  # Cancelada
    SUSPENSA = "suspensa"  # Suspensa temporariamente
    AGENDADA = "agendada"  # Agendada para pagamento
    APROVADA = "aprovada"  # Aprovada para pagamento


class PayableType(StrEnum):
    """Tipo de conta a pagar."""

    AVULSA = "avulsa"  # Conta avulsa (única)
    PARCELADA = "parcelada"  # Conta parcelada
    RECORRENTE = "recorrente"  # Conta recorrente (mensal)
    CONTRATO = "contrato"  # Vinculada a contrato


class PayablePriority(StrEnum):
    """Prioridade de pagamento."""

    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    URGENTE = "urgente"
    CRITICA = "critica"


class RecurrenceType(StrEnum):
    """Tipo de recorrência."""

    DIARIA = "diaria"
    SEMANAL = "semanal"
    QUINZENAL = "quinzenal"
    MENSAL = "mensal"
    BIMESTRAL = "bimestral"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"


class PayableAccount(Base):
    """Conta a pagar."""

    __tablename__ = "payable_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Identificação
    code = Column(String(30), nullable=True)  # Código interno
    document_number = Column(String(50), nullable=True)  # Número NF/documento
    description = Column(String(500), nullable=False)
    payable_type = Column(String(20), nullable=False, default=PayableType.AVULSA.value)
    status = Column(String(20), nullable=False, default=PayableStatus.PENDENTE.value)
    priority = Column(String(20), default=PayablePriority.MEDIA.value)

    # Fornecedor
    supplier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id"),
        nullable=True,
        index=True,
    )

    # Categoria
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payable_categories.id"),
        nullable=True,
        index=True,
    )

    # Valores
    gross_value = Column(Numeric(15, 2), nullable=False)  # Valor bruto
    discount_value = Column(Numeric(15, 2), default=0)  # Descontos
    addition_value = Column(Numeric(15, 2), default=0)  # Acréscimos
    net_value = Column(Numeric(15, 2), nullable=False)  # Valor líquido
    paid_value = Column(Numeric(15, 2), default=0)  # Valor pago
    remaining_value = Column(Numeric(15, 2), nullable=True)  # Valor restante

    # Retenções
    withhold_iss = Column(Numeric(15, 2), default=0)
    withhold_ir = Column(Numeric(15, 2), default=0)
    withhold_pis = Column(Numeric(15, 2), default=0)
    withhold_cofins = Column(Numeric(15, 2), default=0)
    withhold_csll = Column(Numeric(15, 2), default=0)
    withhold_inss = Column(Numeric(15, 2), default=0)
    total_withholdings = Column(Numeric(15, 2), default=0)  # Total retenções

    # Datas
    issue_date = Column(Date, nullable=True)  # Data emissão
    entry_date = Column(Date, default=date.today)  # Data entrada
    due_date = Column(Date, nullable=False, index=True)  # Data vencimento
    payment_date = Column(Date, nullable=True)  # Data pagamento
    competence_date = Column(Date, nullable=True)  # Data competência

    # Parcelamento
    total_installments = Column(Integer, default=1)  # Total de parcelas
    current_installment = Column(Integer, default=1)  # Parcela atual (para recorrentes)

    # Recorrência
    is_recurring = Column(Boolean, default=False)
    recurrence_type = Column(String(20), nullable=True)
    recurrence_end_date = Column(Date, nullable=True)
    parent_recurrence_id = Column(
        "parent_recurrence_id",  # Nome real da coluna no banco
        UUID(as_uuid=True),
        ForeignKey("payable_accounts.id"),
        nullable=True,
    )  # Conta pai (para recorrências)

    # Centro de custo e projeto
    cost_center = Column(String(50), nullable=True)
    project = Column(String(50), nullable=True)

    # Documento fiscal
    fiscal_document_type = Column(String(30), nullable=True)  # NF, NFS, Recibo, etc
    fiscal_document_key = Column(String(50), nullable=True)  # Chave NFe
    fiscal_document_url = Column(String(500), nullable=True)

    # Contrato relacionado
    contract_id = Column(UUID(as_uuid=True), nullable=True)

    # Forma de pagamento preferencial
    payment_method_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payment_methods.id"),
        nullable=True,
    )

    # Conta bancária para débito
    bank_account_id = Column(UUID(as_uuid=True), nullable=True)

    # Aprovação
    requires_approval = Column(Boolean, default=False)
    approval_status = Column(String(20), nullable=True)  # pending, approved, rejected
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)

    # Agendamento de pagamento
    scheduled_payment_date = Column(Date, nullable=True)
    scheduled_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    scheduled_at = Column(DateTime, nullable=True)

    # Anexos e observações
    attachments = Column(JSONB, default=list)
    # [{"name": "nf.pdf", "url": "...", "type": "nota_fiscal"}]
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)  # Notas internas

    # Tags
    tags = Column(ARRAY(String), default=list)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    supplier: Optional["Supplier"] = relationship("Supplier", back_populates="payable_accounts")
    category: Optional["PayableCategory"] = relationship("PayableCategory", back_populates="payable_accounts")
    installments: list["PayableInstallment"] = relationship(
        "PayableInstallment",
        back_populates="payable_account",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_payable_accounts_due_date", "due_date"),
        Index("ix_payable_accounts_status", "status"),
        Index("ix_payable_accounts_supplier", "supplier_id"),
        Index("ix_payable_accounts_category", "category_id"),
        Index("ix_payable_accounts_document", "document_number"),
        Index(
            "ix_payable_accounts_condominio_status_due",
            "condominio_id",
            "status",
            "due_date",
        ),
    )

    def __repr__(self) -> str:
        return f"<PayableAccount {self.document_number or self.id} - {self.net_value}>"

    @property
    def is_overdue(self) -> bool:
        """Verifica se está vencida."""
        if self.status in [PayableStatus.PAGA.value, PayableStatus.CANCELADA.value]:
            return False
        return self.due_date < date.today()

    @property
    def days_until_due(self) -> int:
        """Dias até o vencimento (negativo se vencida)."""
        return (self.due_date - date.today()).days

    @property
    def days_overdue(self) -> int:
        """Dias de atraso (0 se não vencida)."""
        if not self.is_overdue:
            return 0
        return (date.today() - self.due_date).days

    @property
    def is_paid(self) -> bool:
        """Verifica se está totalmente paga."""
        return self.status == PayableStatus.PAGA.value

    @property
    def is_partially_paid(self) -> bool:
        """Verifica se está parcialmente paga."""
        return self.paid_value > 0 and self.paid_value < self.net_value

    @property
    def payment_percentage(self) -> float:
        """Percentual pago."""
        if self.net_value == 0:
            return 0
        return float((self.paid_value / self.net_value) * 100)

    @property
    def balance(self) -> Decimal:
        """Saldo a pagar."""
        return self.net_value - self.paid_value

    def calculate_net_value(self) -> Decimal:
        """Calcula valor líquido."""
        net = self.gross_value - self.discount_value + self.addition_value - self.total_withholdings
        return max(net, Decimal("0"))

    def update_status(self) -> None:
        """Atualiza status baseado nos pagamentos."""
        if self.paid_value >= self.net_value:
            self.status = PayableStatus.PAGA.value
        elif self.paid_value > 0:
            self.status = PayableStatus.PARCIAL.value
        elif self.is_overdue:
            self.status = PayableStatus.VENCIDA.value
        else:
            self.status = PayableStatus.PENDENTE.value

    def register_payment(
        self,
        value: Decimal,
        payment_date: date,
    ) -> None:
        """Registra pagamento."""
        self.paid_value += value
        self.remaining_value = self.net_value - self.paid_value
        self.payment_date = payment_date
        self.update_status()

    def cancel(self, reason: str) -> None:
        """Cancela a conta."""
        self.status = PayableStatus.CANCELADA.value
        self.internal_notes = f"Cancelada: {reason}\n{self.internal_notes or ''}"

    def suspend(self, reason: str) -> None:
        """Suspende a conta."""
        self.status = PayableStatus.SUSPENSA.value
        self.internal_notes = f"Suspensa: {reason}\n{self.internal_notes or ''}"

    def schedule_payment(
        self,
        scheduled_date: date,
        user_id: uuid.UUID,
    ) -> None:
        """Agenda pagamento."""
        self.scheduled_payment_date = scheduled_date
        self.scheduled_by = user_id
        self.scheduled_at = datetime.utcnow()
        self.status = PayableStatus.AGENDADA.value

    def approve(self, user_id: uuid.UUID, notes: str | None = None) -> None:
        """Aprova para pagamento."""
        self.approval_status = "approved"
        self.approved_by = user_id
        self.approved_at = datetime.utcnow()
        self.approval_notes = notes
        self.status = PayableStatus.APROVADA.value

    def reject(self, user_id: uuid.UUID, notes: str) -> None:
        """Rejeita aprovação."""
        self.approval_status = "rejected"
        self.approved_by = user_id
        self.approved_at = datetime.utcnow()
        self.approval_notes = notes

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "code": self.code,
            "document_number": self.document_number,
            "description": self.description,
            "payable_type": self.payable_type,
            "status": self.status,
            "priority": self.priority,
            "supplier_id": str(self.supplier_id) if self.supplier_id else None,
            "category_id": str(self.category_id) if self.category_id else None,
            "gross_value": float(self.gross_value),
            "net_value": float(self.net_value),
            "paid_value": float(self.paid_value),
            "balance": float(self.balance),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "is_overdue": self.is_overdue,
            "days_overdue": self.days_overdue,
            "payment_percentage": self.payment_percentage,
        }
