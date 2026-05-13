"""
Model: cwi_outbox (PRD Sec. 6.1) — Outbox Pattern.

Fila durável de mensagens que o Conecta PRO QUER enviar via Chatwoot.
Worker Celery processa em background (Slice 5). Resiliente a Chatwoot
fora do ar — falhas voltam pra fila com retry.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class CwiOutbox(Base):
    """Fila de mensagens outgoing pendentes de envio ao Chatwoot."""

    __tablename__ = "cwi_outbox"
    __table_args__ = (
        # Garante que tem ao menos conversation_id OU contact_id
        CheckConstraint(
            "chatwoot_conversation_id IS NOT NULL OR chatwoot_contact_id IS NOT NULL",
            name="ck_cwi_outbox_has_target",
        ),
        Index(
            "ix_cwi_outbox_pending",
            "created_at",
            postgresql_where="status = 'pending'",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Alvo da mensagem (1 dos 2 obrigatorio — check constraint acima)
    chatwoot_conversation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chatwoot_contact_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chatwoot_inbox_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Payload
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attachments: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="[{ url, type, filename }]",
    )
    message_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="outgoing",
    )
    template_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Pra futuro Cloud API; null pra Baileys",
    )

    # Estado do worker
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="'pending', 'sent', 'failed', 'cancelled'",
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Origem (pra auditoria e correlacao com outras tabelas do CPro)
    triggered_by_module: Mapped[str] = mapped_column(String(50), nullable=False)
    triggered_by_event: Mapped[str] = mapped_column(String(100), nullable=False)
    triggered_by_entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Auditoria
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    chatwoot_message_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Preenchido apos envio bem-sucedido",
    )

    def __repr__(self) -> str:
        return (
            f"<CwiOutbox(id={self.id}, status={self.status}, "
            f"module={self.triggered_by_module}, attempts={self.attempts})>"
        )
