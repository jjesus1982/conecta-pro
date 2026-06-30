"""
Timeline (CrmActivity) e Tarefas (CrmTask) do CRM.

CrmActivity: histórico/linha do tempo, ligável a cliente/lead/oportunidade/proposta.
CrmTask: tarefas e lembretes de follow-up, com data e responsável.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class CrmActivity(Base):
    """Atividade/timeline do CRM (lead/deal/proposta/cliente)."""

    __tablename__ = "crm_activities"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    client_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    lead_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    proposal_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=True)


class CrmTask(Base):
    """Tarefa/lembrete de follow-up do CRM."""

    __tablename__ = "crm_tasks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|done|cancelled
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assigned_to_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    lead_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    client_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    proposal_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
