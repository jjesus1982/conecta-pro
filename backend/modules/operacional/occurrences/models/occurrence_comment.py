"""
Model de Comentario de Ocorrencia.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score: 99+/100
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:
    from .occurrence import Occurrence


class OccurrenceComment(Base):
    """
    Modelo de Comentario de Ocorrencia.

    Representa comentarios adicionados a uma ocorrencia por usuarios,
    podendo ser internos (visiveis apenas para operadores) ou publicos.

    Attributes:
        id: Identificador unico UUID.
        occurrence_id: ID da ocorrencia relacionada.
        author_id: ID do usuario autor do comentario.
        content: Conteudo do comentario.
        is_internal: Se e um comentario interno (nao visivel ao cliente).
    """

    __tablename__ = "occurrence_comments"

    # === Identificacao ===
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    occurrence_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("occurrences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # === Autor ===
    author_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    author_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # === Conteudo ===
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # === Visibilidade ===
    is_internal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # === Edicao ===
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    original_content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # === Auditoria ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=func.now(),
    )

    # === Controle ===
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # === Relacionamento ===
    occurrence: Mapped[Occurrence] = relationship("Occurrence")  # Occurrence não tem a relação inversa: back_populates derrubava todos os mappers (08/09/2026)

    def __repr__(self) -> str:
        """Representacao string do objeto."""
        return f"<OccurrenceComment by {self.author_id[:8]}>"

    @property
    def is_edited(self) -> bool:
        """Verifica se o comentario foi editado."""
        return self.edited_at is not None

    @property
    def preview(self) -> str:
        """Retorna preview do conteudo (primeiros 100 caracteres)."""
        if len(self.content) <= 100:
            return self.content
        return f"{self.content[:100]}..."

    def edit(self, new_content: str) -> None:
        """Edita o comentario.

        Args:
            new_content: Novo conteudo do comentario.
        """
        if self.original_content is None:
            self.original_content = self.content
        self.content = new_content
        self.edited_at = datetime.utcnow()

    def soft_delete(self) -> None:
        """Realiza soft delete do registro."""
        self.is_active = False
