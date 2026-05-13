"""
Model: cwi_message_log (PRD Sec. 6.1).

Log de auditoria de todas as mensagens (entrada e saida). NAO duplica
o conteudo da mensagem (isso fica no Chatwoot) — apenas referencia +
metadata pra rastrear qual modulo do CPro disparou cada envio.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class CwiMessageLog(Base):
    """Log de mensagens (entrada/saida) — auditoria."""

    __tablename__ = "cwi_message_log"
    __table_args__ = (
        UniqueConstraint("chatwoot_message_id", name="uq_cwi_msg_log_chatwoot_msg"),
        Index("ix_cwi_msg_log_conversation", "chatwoot_conversation_id"),
        Index(
            "ix_cwi_msg_log_module",
            "triggered_by_module",
            "created_at",
            postgresql_using="btree",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    chatwoot_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chatwoot_conversation_id: Mapped[int] = mapped_column(Integer, nullable=False)

    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="'incoming', 'outgoing'",
    )
    message_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'text', 'image', 'document', 'audio'",
    )

    sender_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="'agent', 'contact', 'bot'",
    )
    sender_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="chatwoot user_id ou contact_id",
    )

    # Origem (qual modulo do CPro disparou)
    triggered_by_module: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="'crm', 'financeiro', 'operacional' ou null (manual)",
    )
    triggered_by_event: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="'fatura_vencendo', 'ocorrencia_grave', etc",
    )
    triggered_by_entity_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # Delivery status
    delivered: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    delivery_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CwiMessageLog(id={self.id}, msg={self.chatwoot_message_id}, "
            f"dir={self.direction})>"
        )
