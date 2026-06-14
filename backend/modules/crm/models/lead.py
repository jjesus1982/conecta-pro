"""
Modelo Lead para CRM.
"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:  # pragma: no cover
    from core.models import User


class LeadStatus(StrEnum):
    """Status do lead no funil de vendas."""

    NEW = "new"  # Novo lead
    CONTACTED = "contacted"  # Primeiro contato realizado
    QUALIFIED = "qualified"  # Lead qualificado
    PROPOSAL = "proposal"  # Proposta enviada
    NEGOTIATION = "negotiation"  # Em negociação
    WON = "won"  # Convertido em cliente
    LOST = "lost"  # Perdido


class LeadSource(StrEnum):
    """Origem do lead."""

    WEBSITE = "website"
    REFERRAL = "referral"
    SOCIAL_MEDIA = "social_media"
    COLD_CALL = "cold_call"
    EMAIL_CAMPAIGN = "email_campaign"
    EVENT = "event"
    PARTNER = "partner"
    WHATSAPP = "whatsapp"  # leads do agente WhatsApp (Jose Luis) — sem email
    OTHER = "other"


class Lead(Base):
    """
    Modelo de Lead para gestão de prospects.

    Attributes:
        id: Identificador único
        name: Nome do contato
        email: Email do contato
        phone: Telefone do contato
        company: Nome da empresa
        position: Cargo do contato
        source: Origem do lead
        status: Status no funil
        score: Pontuação de qualificação (0-100)
        probability: Probabilidade de fechamento (0-100)
        expected_value: Valor esperado do negócio
        notes: Observações
        assigned_to_id: Usuário responsável
        last_contact_at: Data do último contato
        next_contact_at: Data do próximo contato
    """

    __tablename__ = "leads"

    # Identificação
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Dados do contato
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Dados da empresa
    company: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Classificação
    source: Mapped[str] = mapped_column(
        String(50),
        default=LeadSource.OTHER.value,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=LeadStatus.NEW.value,
        nullable=False,
        index=True,
    )

    # Scoring e probabilidade
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    probability: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expected_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Observações
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Responsável
    assigned_to_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Datas de contato
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_contact_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Campos de controle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relacionamentos
    assigned_to: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[assigned_to_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Lead {self.name} ({self.email})>"

    @property
    def is_hot(self) -> bool:
        """Verifica se é um lead quente (score >= 70)."""
        return self.score >= 70

    @property
    def is_qualified(self) -> bool:
        """Verifica se o lead está qualificado."""
        return self.status in (
            LeadStatus.QUALIFIED.value,
            LeadStatus.PROPOSAL.value,
            LeadStatus.NEGOTIATION.value,
            LeadStatus.WON.value,
        )

    @property
    def weighted_value(self) -> float:
        """Calcula valor ponderado (valor esperado * probabilidade)."""
        return self.expected_value * (self.probability / 100)
