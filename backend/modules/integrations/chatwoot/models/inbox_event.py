"""
Model: cwi_inbox_event (PRD Sec. 6.1) — Inbox Pattern.

Buffer durável de webhooks recebidos do Chatwoot. Garante idempotencia
(chatwoot_event_id UNIQUE) + retry (status='failed' -> reprocessar).
Worker Celery processa em background (Slice 5).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class CwiInboxEvent(Base):
    """Webhook entrante Chatwoot -> CPro (idempotencia + retry)."""

    __tablename__ = "cwi_inbox_event"
    __table_args__ = (
        UniqueConstraint(
            "chatwoot_event_id",
            name="uq_cwi_inbox_event_chatwoot_id",
            # NOTA: PRD usa partial unique (WHERE chatwoot_event_id IS NOT NULL).
            # Replicar isso requer Index com postgresql_where (em vez de UniqueConstraint),
            # que faremos na migration Slice 4. Por ora, a constraint normal vale.
        ),
        Index(
            "ix_cwi_inbox_event_pending",
            "received_at",
            postgresql_where="status = 'pending'",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="'message_created', 'conversation_created', etc",
    )
    chatwoot_event_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Se Chatwoot fornecer; senao hash do payload",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Processamento
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="'pending', 'processed', 'failed', 'duplicate'",
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Auditoria
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CwiInboxEvent(id={self.id}, type={self.event_type}, "
            f"status={self.status})>"
        )
