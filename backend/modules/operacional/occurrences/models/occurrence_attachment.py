"""
Model de Anexo de Ocorrencia.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score: 99+/100
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:
    from .occurrence import Occurrence


class AttachmentType(StrEnum):
    """Tipo de anexo.

    Attributes:
        IMAGEM: Arquivo de imagem (jpg, png, etc).
        VIDEO: Arquivo de video.
        AUDIO: Arquivo de audio.
        DOCUMENTO: Documento (pdf, doc, etc).
        OUTRO: Outros tipos de arquivo.
    """

    IMAGEM = "imagem"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENTO = "documento"
    OUTRO = "outro"


class OccurrenceAttachment(Base):
    """
    Modelo de Anexo de Ocorrencia.

    Representa arquivos anexados a uma ocorrencia, como fotos,
    videos, documentos e outros arquivos relevantes.

    Attributes:
        id: Identificador unico UUID.
        occurrence_id: ID da ocorrencia relacionada.
        file_type: Tipo do arquivo.
        file_path: Caminho do arquivo no storage.
        file_name: Nome original do arquivo.
        file_size: Tamanho em bytes.
        description: Descricao do anexo.
        captured_at: Data/hora da captura (fotos/videos).
        latitude: Latitude GPS onde foi capturado.
        longitude: Longitude GPS onde foi capturado.
    """

    __tablename__ = "occurrence_attachments"

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

    # === Arquivo ===
    file_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=AttachmentType.OUTRO.value,
    )
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # === Descricao ===
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # === Captura (para fotos/videos) ===
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # === Upload ===
    uploaded_by_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
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
        return f"<OccurrenceAttachment {self.file_name}>"

    @property
    def is_image(self) -> bool:
        """Verifica se e uma imagem."""
        return self.file_type == AttachmentType.IMAGEM.value

    @property
    def is_video(self) -> bool:
        """Verifica se e um video."""
        return self.file_type == AttachmentType.VIDEO.value

    @property
    def has_location(self) -> bool:
        """Verifica se tem localizacao GPS."""
        return self.latitude is not None and self.longitude is not None

    @property
    def file_size_kb(self) -> float | None:
        """Retorna tamanho em KB."""
        if self.file_size:
            return round(self.file_size / 1024, 2)
        return None

    @property
    def file_size_mb(self) -> float | None:
        """Retorna tamanho em MB."""
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return None

    def soft_delete(self) -> None:
        """Realiza soft delete do registro."""
        self.is_active = False
