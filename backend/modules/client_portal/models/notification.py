"""Caixa de avisos do Portal do Cliente — notificações proativas (José Luís)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ClientPortalNotification(Base):
    """Aviso enviado proativamente ao condomínio (mudança de escala, falta, kit pronto…)."""

    __tablename__ = "client_portal_notifications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    client_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)  # escala|falta|advertencia|kit|certidao|aviso
    titulo: Mapped[str] = mapped_column(String(160), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    lida: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canal_email: Mapped[bool] = mapped_column(Boolean, default=False)
    canal_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
