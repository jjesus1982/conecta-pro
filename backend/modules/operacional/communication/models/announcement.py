"""
Model de Comunicado Operacional.

Author: Conecta PRO Team
Date: 2026-01-18
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:
    from .announcement_read import AnnouncementRead


class AnnouncementTargetType(StrEnum):
    """Tipo de destinatario do comunicado."""

    ALL = "all"
    DEPARTMENT = "department"
    CLIENT = "client"
    POST = "post"
    EMPLOYEE = "employee"
    ROLE = "role"


class AnnouncementType(StrEnum):
    """Tipo de comunicado."""

    INFORMATIVO = "informativo"
    URGENTE = "urgente"
    ALERTA = "alerta"
    PROCEDIMENTO = "procedimento"
    ESCALA = "escala"


class AnnouncementCategory(StrEnum):
    """Categoria do comunicado."""

    INFORMATIVO = "informativo"
    PROCEDIMENTO = "procedimento"
    ALERTA = "alerta"
    TREINAMENTO = "treinamento"
    POLITICA = "politica"


class AnnouncementPriority(StrEnum):
    """Prioridade do comunicado."""

    BAIXA = "baixa"
    NORMAL = "normal"
    ALTA = "alta"
    URGENTE = "urgente"


class AnnouncementStatus(StrEnum):
    """Status do comunicado."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    RASCUNHO = "rascunho"
    AGENDADO = "agendado"
    PUBLICADO = "publicado"
    ARQUIVADO = "arquivado"


class Announcement(Base):
    """Modelo de Comunicado."""

    __tablename__ = "communication_announcements"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(
        String(30), default=AnnouncementType.INFORMATIVO.value, nullable=False, index=True
    )
    prioridade: Mapped[str] = mapped_column(
        String(20), default=AnnouncementPriority.NORMAL.value, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=AnnouncementStatus.RASCUNHO.value, nullable=False, index=True
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    resumo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    anexos: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True, default=list)
    destinatarios_tipo: Mapped[str] = mapped_column(String(30), default="todos", nullable=False)
    destinatarios_postos: Mapped[list[str] | None] = mapped_column(ARRAY(UUID(as_uuid=False)), nullable=True)
    destinatarios_funcionarios: Mapped[list[str] | None] = mapped_column(ARRAY(UUID(as_uuid=False)), nullable=True)
    data_publicacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_expiracao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    requer_confirmacao: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enviar_push: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enviar_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_destinatarios: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_visualizacoes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_confirmacoes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fixado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=dict)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    reads: Mapped[list[AnnouncementRead]] = relationship(
        "AnnouncementRead",
        back_populates="announcement",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Announcement {self.titulo[:50]}>"

    # ── Property aliases for Pydantic schema (expects English field names) ──

    @property
    def title(self) -> str:
        return self.titulo

    @property
    def content(self) -> str:
        return self.conteudo

    @property
    def priority(self) -> str:
        return self.prioridade

    @property
    def category(self) -> str:
        return self.tipo

    @property
    def target_type(self) -> str:
        return self.destinatarios_tipo

    @property
    def target_ids(self) -> list[str] | None:
        ids: list[str] = []
        if self.destinatarios_postos:
            ids.extend(self.destinatarios_postos)
        if self.destinatarios_funcionarios:
            ids.extend(self.destinatarios_funcionarios)
        return ids or None

    @property
    def target_roles(self) -> list[str] | None:
        return None

    @property
    def publish_at(self) -> datetime | None:
        return self.data_publicacao

    def can_be_published(self) -> bool:  # faltava: publicar dava 500 (08/09/2026)
        return self.status in (AnnouncementStatus.DRAFT.value, AnnouncementStatus.RASCUNHO.value,
                               AnnouncementStatus.SCHEDULED.value, AnnouncementStatus.AGENDADO.value)

    def _get_total_targets(self) -> int:
        return int(self.total_destinatarios or 0)

    @property
    def expires_at(self) -> datetime | None:
        return self.data_expiracao

    @property
    def requires_acknowledgment(self) -> bool:
        return self.requer_confirmacao

    @property
    def attachments(self) -> list[dict[str, Any]] | None:
        return self.anexos

    @property
    def published_by(self) -> str | None:
        return self.created_by

    @property
    def published_at(self) -> datetime | None:
        return self.data_publicacao

    @property
    def is_published(self) -> bool:
        return self.status in (AnnouncementStatus.PUBLISHED.value, AnnouncementStatus.PUBLICADO.value)

    @property
    def is_expired(self) -> bool:
        return self.status in (AnnouncementStatus.EXPIRED.value, AnnouncementStatus.ARQUIVADO.value)

    @property
    def is_scheduled(self) -> bool:
        return self.status in (AnnouncementStatus.SCHEDULED.value, AnnouncementStatus.AGENDADO.value)

    @property
    def read_count(self) -> int:
        return self.total_visualizacoes

    @property
    def acknowledgment_count(self) -> int:
        return self.total_confirmacoes

    @property
    def read_percentage(self) -> float:
        if self.total_destinatarios == 0:
            return 0.0
        return round((self.total_visualizacoes / self.total_destinatarios) * 100, 2)
