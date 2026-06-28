"""Model para clientes/devedores de contas a receber."""

import uuid
from sqlalchemy import Integer
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.financial.models.receivable_account import ReceivableAccount


class CustomerType(StrEnum):
    """Tipo de cliente."""

    MORADOR = "morador"  # Morador do condominio
    PROPRIETARIO = "proprietario"  # Proprietario de unidade
    INQUILINO = "inquilino"  # Inquilino
    EXTERNO = "externo"  # Cliente externo
    EMPRESA = "empresa"  # Empresa


class CustomerStatus(StrEnum):
    """Status do cliente."""

    ATIVO = "ativo"
    INATIVO = "inativo"
    BLOQUEADO = "bloqueado"
    INADIMPLENTE = "inadimplente"


class Customer(Base):
    """Cliente/Devedor de contas a receber."""

    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Vinculacao com morador/unidade
    morador_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    unidade_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Identificacao
    cpf_cnpj = Column(String(20), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    trade_name = Column(String(200), nullable=True)  # Nome fantasia
    customer_type = Column(String(20), nullable=False, default=CustomerType.MORADOR.value)
    status = Column(String(20), nullable=False, default=CustomerStatus.ATIVO.value)

    # Contato
    email = Column(String(200), nullable=True)
    email_secondary = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=True)
    phone_secondary = Column(String(20), nullable=True)
    whatsapp = Column(String(20), nullable=True)

    # Endereco
    address_street = Column(String(200), nullable=True)
    address_number = Column(String(20), nullable=True)
    address_complement = Column(String(100), nullable=True)
    address_neighborhood = Column(String(100), nullable=True)
    address_city = Column(String(100), nullable=True)
    address_state = Column(String(2), nullable=True)
    address_zipcode = Column(String(10), nullable=True)

    # Financeiro
    credit_limit = Column(Numeric(15, 2), default=0)  # Limite de credito
    total_debt = Column(Numeric(15, 2), default=0)  # Divida total
    overdue_debt = Column(Numeric(15, 2), default=0)  # Divida vencida

    # Cobranca
    billing_email = Column(String(200), nullable=True)  # Email para cobranca
    billing_day = Column(Integer, nullable=True)  # Dia preferencial cobranca
    auto_billing = Column(Boolean, default=True)  # Gerar cobranca automatica

    # Notificacoes
    notify_email = Column(Boolean, default=True)
    notify_sms = Column(Boolean, default=False)
    notify_whatsapp = Column(Boolean, default=True)
    notify_push = Column(Boolean, default=True)

    # Bloqueio
    is_blocked = Column(Boolean, default=False)
    blocked_reason = Column(Text, nullable=True)
    blocked_at = Column(DateTime, nullable=True)
    blocked_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Dados adicionais
    extra_data = Column(JSONB, default=dict)
    notes = Column(Text, nullable=True)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    receivable_accounts: list["ReceivableAccount"] = relationship(
        "ReceivableAccount",
        back_populates="customer",
    )

    __table_args__ = (
        Index("ix_customers_cpf_cnpj", "cpf_cnpj"),
        Index("ix_customers_name", "name"),
        Index("ix_customers_type", "customer_type"),
        Index("ix_customers_status", "status"),
        Index("ix_customers_morador", "morador_id"),
        Index("ix_customers_unidade", "unidade_id"),
        Index(
            "ix_customers_condominio_status",
            "condominio_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Customer {self.cpf_cnpj} - {self.name}>"

    @property
    def is_inadimplente(self) -> bool:
        """Verifica se esta inadimplente."""
        return self.overdue_debt > 0

    @property
    def available_credit(self) -> float:
        """Credito disponivel."""
        return float(self.credit_limit - self.total_debt)

    @property
    def display_name(self) -> str:
        """Nome de exibicao."""
        return self.trade_name or self.name

    @property
    def formatted_cpf_cnpj(self) -> str:
        """CPF/CNPJ formatado."""
        doc = self.cpf_cnpj.replace(".", "").replace("-", "").replace("/", "")
        if len(doc) == 11:
            return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
        if len(doc) == 14:
            return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
        return self.cpf_cnpj

    def block(self, reason: str, user_id: uuid.UUID) -> None:
        """Bloqueia o cliente."""
        self.is_blocked = True
        self.blocked_reason = reason
        self.blocked_at = datetime.utcnow()
        self.blocked_by = user_id
        self.status = CustomerStatus.BLOQUEADO.value

    def unblock(self) -> None:
        """Desbloqueia o cliente."""
        self.is_blocked = False
        self.blocked_reason = None
        self.blocked_at = None
        self.blocked_by = None
        if self.overdue_debt > 0:
            self.status = CustomerStatus.INADIMPLENTE.value
        else:
            self.status = CustomerStatus.ATIVO.value

    def update_debt(self, total: float, overdue: float) -> None:
        """Atualiza divida do cliente."""
        self.total_debt = Decimal(str(total))
        self.overdue_debt = Decimal(str(overdue))
        if overdue > 0 and not self.is_blocked:
            self.status = CustomerStatus.INADIMPLENTE.value
        elif not self.is_blocked:
            self.status = CustomerStatus.ATIVO.value

    def to_dict(self) -> dict:
        """Converte para dicionario."""
        return {
            "id": str(self.id),
            "cpf_cnpj": self.cpf_cnpj,
            "formatted_cpf_cnpj": self.formatted_cpf_cnpj,
            "name": self.name,
            "trade_name": self.trade_name,
            "display_name": self.display_name,
            "customer_type": self.customer_type,
            "status": self.status,
            "email": self.email,
            "phone": self.phone,
            "whatsapp": self.whatsapp,
            "credit_limit": float(self.credit_limit),
            "total_debt": float(self.total_debt),
            "overdue_debt": float(self.overdue_debt),
            "available_credit": self.available_credit,
            "is_inadimplente": self.is_inadimplente,
            "is_blocked": self.is_blocked,
            "ativo": self.ativo,
        }
