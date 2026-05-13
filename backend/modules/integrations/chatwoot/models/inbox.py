"""
Model: cwi_inbox (PRD Sec. 6.1).

Espelha localmente os inboxes Chatwoot pra que features do CPro
saibam pra qual inbox enviar mensagens (atendimento, cobranca, etc).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class CwiInbox(Base):
    """Espelho de inboxes Chatwoot conhecidos pelo Conecta PRO."""

    __tablename__ = "cwi_inbox"
    __table_args__ = (
        UniqueConstraint("chatwoot_inbox_id", name="uq_cwi_inbox_chatwoot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chatwoot_inbox_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    channel_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="'baileys', 'api', 'email'",
    )
    phone_number: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="So pra inboxes WhatsApp",
    )
    purpose: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="'atendimento', 'cobranca', 'operacional', 'comercial'",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CwiInbox(id={self.id}, name={self.name!r}, type={self.channel_type})>"
