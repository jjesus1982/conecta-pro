"""
Model para Propostas Comerciais.
Gerencia propostas, versões, itens e workflow de aprovação.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    pass


class ProposalStatus(StrEnum):
    """Status da proposta."""

    DRAFT = "draft"  # Rascunho
    PENDING_REVIEW = "pending_review"  # Aguardando revisão
    PENDING_APPROVAL = "pending_approval"  # Aguardando aprovação
    APPROVED = "approved"  # Aprovada internamente
    SENT = "sent"  # Enviada ao cliente
    VIEWED = "viewed"  # Visualizada pelo cliente
    ACCEPTED = "accepted"  # Aceita pelo cliente
    REJECTED = "rejected"  # Rejeitada pelo cliente
    EXPIRED = "expired"  # Expirada
    CANCELLED = "cancelled"  # Cancelada


class ProposalType(StrEnum):
    """Tipo de proposta."""

    PRODUCT = "product"  # Venda de produtos
    SERVICE = "service"  # Prestação de serviços
    PROJECT = "project"  # Projeto completo
    SUBSCRIPTION = "subscription"  # Assinatura/recorrente
    MIXED = "mixed"  # Misto


class DiscountType(StrEnum):
    """Tipo de desconto."""

    PERCENTAGE = "percentage"  # Percentual
    FIXED = "fixed"  # Valor fixo


class Proposal(Base):
    """Model para proposta comercial."""

    __tablename__ = "proposals"

    # Identificação
    id = Column(UUID(as_uuid=False), primary_key=True)
    number = Column(String(50), unique=True, nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    parent_id = Column(UUID(as_uuid=False), ForeignKey("proposals.id"), nullable=True)

    # Relacionamentos
    opportunity_id = Column(
        UUID(as_uuid=False),
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    template_id = Column(
        UUID(as_uuid=False),
        ForeignKey("proposal_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Dados do cliente
    client_name = Column(String(255), nullable=False)
    client_email = Column(String(255), nullable=True)
    client_phone = Column(String(20), nullable=True)
    client_company = Column(String(255), nullable=True)
    client_document = Column(String(20), nullable=True)  # CPF/CNPJ
    client_address = Column(Text, nullable=True)

    # Conteúdo
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    proposal_type = Column(String(20), default=ProposalType.SERVICE.value, nullable=False)
    terms_conditions = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Valores
    subtotal = Column(Float, default=0.0, nullable=False)
    discount_type = Column(String(20), nullable=True)
    discount_value = Column(Float, default=0.0, nullable=False)
    discount_reason = Column(String(255), nullable=True)
    taxes = Column(Float, default=0.0, nullable=False)
    total = Column(Float, default=0.0, nullable=False)

    # Pagamento
    payment_terms = Column(Text, nullable=True)
    payment_conditions = Column(String(255), nullable=True)
    installments = Column(Integer, default=1, nullable=False)

    # Datas
    issue_date = Column(Date, default=date.today, nullable=False)
    valid_until = Column(Date, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    viewed_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)

    # Status e workflow
    status = Column(String(30), default=ProposalStatus.DRAFT.value, nullable=False, index=True)
    rejection_reason = Column(Text, nullable=True)

    # Responsáveis
    created_by_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = Column(DateTime, nullable=True)

    # Controle
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    items = relationship("ProposalItem", back_populates="proposal", cascade="all, delete-orphan")
    versions = relationship("Proposal", backref="parent", remote_side=[id])  # noqa: A003
    approvals = relationship("ProposalApproval", back_populates="proposal", cascade="all, delete-orphan")

    @property
    def is_draft(self) -> bool:
        """Verifica se está em rascunho."""
        return self.status == ProposalStatus.DRAFT.value

    @property
    def is_pending(self) -> bool:
        """Verifica se está pendente (revisão ou aprovação)."""
        return self.status in (
            ProposalStatus.PENDING_REVIEW.value,
            ProposalStatus.PENDING_APPROVAL.value,
        )

    @property
    def is_approved(self) -> bool:
        """Verifica se foi aprovada internamente."""
        return self.status == ProposalStatus.APPROVED.value

    @property
    def is_sent(self) -> bool:
        """Verifica se foi enviada ao cliente."""
        return self.status in (
            ProposalStatus.SENT.value,
            ProposalStatus.VIEWED.value,
        )

    @property
    def is_closed(self) -> bool:
        """Verifica se está fechada (aceita, rejeitada, expirada ou cancelada)."""
        return self.status in (
            ProposalStatus.ACCEPTED.value,
            ProposalStatus.REJECTED.value,
            ProposalStatus.EXPIRED.value,
            ProposalStatus.CANCELLED.value,
        )

    @property
    def is_accepted(self) -> bool:
        """Verifica se foi aceita."""
        return self.status == ProposalStatus.ACCEPTED.value

    @property
    def is_expired(self) -> bool:
        """Verifica se está expirada."""
        if self.status == ProposalStatus.EXPIRED.value:
            return True
        if self.valid_until and self.valid_until < date.today():
            if not self.is_closed:
                return True
        return False

    @property
    def days_until_expiry(self) -> int | None:
        """Dias até expirar."""
        if not self.valid_until:
            return None
        delta = self.valid_until - date.today()
        return delta.days

    @property
    def discount_amount(self) -> float:
        """Calcula valor do desconto."""
        if not self.discount_value:
            return 0.0
        if self.discount_type == DiscountType.PERCENTAGE.value:
            return self.subtotal * (self.discount_value / 100)
        return self.discount_value

    @property
    def item_count(self) -> int:
        """Quantidade de itens."""
        return len(self.items) if self.items else 0

    def calculate_totals(self) -> None:
        """Recalcula subtotal e total baseado nos itens."""
        if self.items:
            self.subtotal = sum(item.total for item in self.items)
        else:
            self.subtotal = 0.0

        discount = self.discount_amount
        self.total = self.subtotal - discount + self.taxes


class ProposalItem(Base):
    """Model para item da proposta."""

    __tablename__ = "proposal_items"

    id = Column(UUID(as_uuid=False), primary_key=True)
    proposal_id = Column(
        UUID(as_uuid=False),
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Produto/Serviço
    code = Column(String(50), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    unit = Column(String(20), default="un", nullable=False)  # un, hr, mês, etc.

    # Valores
    quantity = Column(Float, default=1.0, nullable=False)
    unit_price = Column(Float, default=0.0, nullable=False)
    discount_percent = Column(Float, default=0.0, nullable=False)
    total = Column(Float, default=0.0, nullable=False)

    # Ordem
    sort_order = Column(Integer, default=0, nullable=False)

    # Controle
    is_optional = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    proposal = relationship("Proposal", back_populates="items")

    @property
    def subtotal(self) -> float:
        """Subtotal sem desconto."""
        return self.quantity * self.unit_price

    @property
    def discount_amount(self) -> float:
        """Valor do desconto."""
        return self.subtotal * (self.discount_percent / 100)

    def calculate_total(self) -> None:
        """Calcula total do item."""
        self.total = self.subtotal - self.discount_amount


class ProposalTemplate(Base):  # pylint: disable=too-few-public-methods
    """Model para template de proposta."""

    __tablename__ = "proposal_templates"

    id = Column(UUID(as_uuid=False), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Conteúdo padrão
    default_title = Column(String(255), nullable=True)
    default_description = Column(Text, nullable=True)
    terms_conditions = Column(Text, nullable=True)
    payment_terms = Column(Text, nullable=True)
    validity_days = Column(Integer, default=30, nullable=False)

    # Configuração
    proposal_type = Column(String(20), default=ProposalType.SERVICE.value, nullable=False)
    header_html = Column(Text, nullable=True)
    footer_html = Column(Text, nullable=True)
    css_styles = Column(Text, nullable=True)

    # Controle
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ApprovalAction(StrEnum):
    """Ação de aprovação."""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class ProposalApproval(Base):  # pylint: disable=too-few-public-methods
    """Model para histórico de aprovações."""

    __tablename__ = "proposal_approvals"

    id = Column(UUID(as_uuid=False), primary_key=True)
    proposal_id = Column(
        UUID(as_uuid=False),
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Ação
    action = Column(String(20), nullable=False)
    comments = Column(Text, nullable=True)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    proposal = relationship("Proposal", back_populates="approvals")
