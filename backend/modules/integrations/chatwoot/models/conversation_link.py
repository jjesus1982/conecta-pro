"""
Model: cwi_conversation_link (PRD Sec. 6.1).

Vincula uma conversa do Chatwoot a contextos do Conecta PRO
(funnel card, ocorrencia ou fatura), permitindo navegar do atendimento
de volta pro contexto que originou a conversa.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class CwiConversationLink(Base):
    """Vinculo Chatwoot Conversation <-> Contexto do Conecta PRO."""

    __tablename__ = "cwi_conversation_link"
    __table_args__ = (
        UniqueConstraint(
            "chatwoot_conversation_id",
            "chatwoot_account_id",
            name="uq_cwi_conv_link_chatwoot",
        ),
        Index(
            "ix_cwi_conv_link_funnel",
            "funnel_card_id",
            postgresql_where="funnel_card_id IS NOT NULL",
        ),
        Index(
            "ix_cwi_conv_link_occurrence",
            "occurrence_id",
            postgresql_where="occurrence_id IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chatwoot_conversation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chatwoot_account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chatwoot_inbox_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # FK pra cwi_contact_link (este sim, mesma "ilha")
    contact_link_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("cwi_contact_link.id", ondelete="CASCADE"),
        nullable=True,
    )

    # FKs lazy pra contextos do CPro (constraint adicionada na migration Slice 4)
    funnel_card_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK funnel_cards.id, ON DELETE SET NULL",
    )
    occurrence_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK occurrences.id, ON DELETE SET NULL",
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK invoices.id, ON DELETE SET NULL",
    )

    # Estado
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'open', 'pending', 'resolved'",
    )
    assignee_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK users.id (admin/agente atribuido)",
    )

    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CwiConversationLink(id={self.id}, conv={self.chatwoot_conversation_id}, "
            f"status={self.status})>"
        )
