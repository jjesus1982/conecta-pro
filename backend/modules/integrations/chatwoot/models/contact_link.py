"""
Model: cwi_contact_link (PRD Sec. 6.1).

Liga um contato no Chatwoot (`chatwoot_contact_id`) a uma das entidades
de dominio do Conecta PRO: Lead, Client, Employee ou Sindico.

DECISAO: PRD define lead_id/client_id/etc como INTEGER, mas o sistema
Conecta PRO usa UUID em todos os models. Estou usando UUID nullable
SEM ForeignKey constraint a nivel de model (FK e adicionada na migration
Slice 4) pra evitar acoplamento circular de imports com modules de leads,
clients, employees, sindicos.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class CwiContactLink(Base):
    """Vinculo Chatwoot Contact <-> Entidade do Conecta PRO."""

    __tablename__ = "cwi_contact_link"
    __table_args__ = (
        UniqueConstraint(
            "chatwoot_contact_id",
            "chatwoot_account_id",
            name="uq_cwi_contact_link_chatwoot",
        ),
        Index("ix_cwi_contact_link_phone", "phone_number"),
        Index(
            "ix_cwi_contact_link_lead",
            "lead_id",
            postgresql_where="lead_id IS NOT NULL",
        ),
        Index(
            "ix_cwi_contact_link_client",
            "client_id",
            postgresql_where="client_id IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    chatwoot_contact_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chatwoot_account_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # FKs lazy (sem constraint a nivel de model — Slice 4 adiciona na migration)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK leads.id, ON DELETE SET NULL (migration Slice 4)",
    )
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK clients.id, ON DELETE SET NULL (migration Slice 4)",
    )
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK employees.id, ON DELETE SET NULL (migration Slice 4)",
    )
    sindico_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK sindicos.id, ON DELETE SET NULL (migration Slice 4)",
    )

    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    push_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CwiContactLink(id={self.id}, chatwoot={self.chatwoot_contact_id}, "
            f"phone={self.phone_number})>"
        )
