"""
Modelo TerminationProcess — Processo de Rescisão/Desligamento.

Rastreia o workflow de desligamento de um colaborador:
aviso prévio, cálculos rescisórios, entrevista de desligamento e quitação.
"""

from datetime import date, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class TerminationType(StrEnum):
    """Tipo de rescisão."""

    VOLUNTARY = "voluntary"
    INVOLUNTARY = "involuntary"
    JUST_CAUSE = "just_cause"
    MUTUAL_AGREEMENT = "mutual_agreement"
    CONTRACT_END = "contract_end"
    RETIREMENT = "retirement"


class TerminationStatus(StrEnum):
    """Status do processo de rescisão."""

    INITIATED = "initiated"
    NOTICE_PERIOD = "notice_period"
    CALCULATING = "calculating"
    PENDING_PAYMENT = "pending_payment"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TerminationProcess(Base):
    """Modelo de Processo de Rescisão.

    Controla o fluxo completo de desligamento, incluindo cálculos
    de verbas rescisórias conforme legislação trabalhista brasileira.
    """

    __tablename__ = "termination_processes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    employee_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK para employees",
    )
    type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Tipo de rescisão",
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Aviso prévio
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notice_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_working_day: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(30),
        default=TerminationStatus.INITIATED,
        nullable=False,
        index=True,
    )

    # Valores rescisórios
    severance_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    vacation_balance_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    thirteenth_salary_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    fgts_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Entrevista de desligamento
    exit_interview_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exit_interview_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # eSocial
    esocial_event_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Documentos gerados
    documents_generated: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)

    # Snapshot das verbas rescisórias na FINALIZAÇÃO (o calc COMPLETO de calculate_severance,
    # ~20 campos). Gravado UMA vez em complete_termination; é o que foi homologado. O chat/TRCT
    # renderiza SÓ daqui — nunca recalcula (recalc deriva; mesma lição do holerite). NULL em
    # rows legadas pré-snapshot → render recusa (fail-closed), nunca fabrica.
    verbas_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Auditoria
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<TerminationProcess(id={self.id}, employee_id={self.employee_id}, "
            f"type={self.type}, status={self.status})>"
        )
