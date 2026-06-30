"""
Marketing Content Draft — Conecta Marketing AI (F2+)

Biblioteca de conteúdo gerado pelo agente Copywriter. Guarda rascunhos e peças
aprovadas (human-in-the-loop) para reuso. Status: rascunho -> aprovado -> arquivado.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class ContentStatus(StrEnum):
    RASCUNHO = "rascunho"
    APROVADO = "aprovado"
    ARQUIVADO = "arquivado"


class MarketingContentDraft(Base):
    """Peça de conteúdo de marketing gerada por IA (biblioteca reutilizável)."""

    __tablename__ = "marketing_content_drafts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Conteúdo
    formato: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    formato_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    titulo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Contexto de geração (briefing que originou)
    briefing: Mapped[str | None] = mapped_column(Text, nullable=True)
    objetivo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publico: Mapped[str | None] = mapped_column(String(500), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Workflow
    status: Mapped[str] = mapped_column(
        String(20),
        default=ContentStatus.RASCUNHO.value,
        nullable=False,
        index=True,
    )

    # Auditoria
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
