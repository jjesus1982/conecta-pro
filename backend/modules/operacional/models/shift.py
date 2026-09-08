"""
Modelo Shift (Turno de Trabalho) para Operações.
"""

from datetime import date, datetime, time
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:
    from .scale import Scale


class ShiftStatus(StrEnum):
    """Status do turno."""

    SCHEDULED = "scheduled"  # Agendado
    IN_PROGRESS = "in_progress"  # Em andamento
    COMPLETED = "completed"  # Concluído
    MISSED = "missed"  # Falta
    PARTIAL = "partial"  # Parcial (saiu antes/chegou depois)
    SUBSTITUTED = "substituted"  # Substituído
    CANCELLED = "cancelled"  # Cancelado
    OFF_DAY = "off_day"  # Folga


class Shift(Base):
    """
    Modelo de Turno de Trabalho.

    Representa um turno individual dentro de uma escala.

    Attributes:
        id: Identificador único
        scale_id: Escala associada
        employee_id: Funcionário alocado
        shift_date: Data do turno
        start_time: Hora de início prevista
        end_time: Hora de fim prevista
        actual_start_time: Hora real de início
        actual_end_time: Hora real de fim
        status: Status do turno
        is_holiday: Se é feriado
        is_sunday: Se é domingo
        is_night_shift: Se é turno noturno
        planned_hours: Horas planejadas
        actual_hours: Horas trabalhadas
        overtime_hours: Horas extras
    """

    __tablename__ = "shifts"

    # Identificação
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Relacionamentos
    scale_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("scales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    post_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Data e Horários (nomes conforme schema do banco)
    shift_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    planned_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    planned_end_time: Mapped[time] = mapped_column(Time, nullable=False)
    planned_break_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    # Horários reais (preenchido via ponto - DateTime no banco)
    actual_start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_break_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default=ShiftStatus.SCHEDULED.value,
        nullable=False,
        index=True,
    )

    # Características do dia
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_night_shift: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_overtime: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_off_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_substitution: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Horas
    planned_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overtime_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    night_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Custos (nomes conforme schema do banco: pay ao invés de cost)
    base_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overtime_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    night_bonus: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    holiday_bonus: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_pay: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Observações
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Campos de controle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relacionamentos (lazy="noload" para evitar erros de schema em tabelas relacionadas)
    scale: Mapped["Scale"] = relationship(
        "Scale",
        back_populates="shifts",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Shift {self.shift_date} {self.planned_start_time}-{self.planned_end_time}>"

    @property
    def is_future(self) -> bool:
        """Verifica se é um turno futuro."""
        return self.shift_date > date.today()

    @property
    def is_today(self) -> bool:
        """Verifica se é um turno de hoje."""
        return self.shift_date == date.today()

    @property
    def is_filled(self) -> bool:
        """Verifica se o turno tem funcionário alocado."""
        return self.employee_id is not None

    @property
    def was_worked(self) -> bool:
        """Verifica se o turno foi trabalhado."""
        return self.status == ShiftStatus.COMPLETED.value

    def calculate_hours(self) -> float:
        """Calcula horas do turno baseado nos horários."""
        if self.is_off_day:
            return 0.0

        start = datetime.combine(self.shift_date, self.planned_start_time)
        end = datetime.combine(self.shift_date, self.planned_end_time)

        # Se termina no dia seguinte (turno noturno)
        if end <= start:
            end = datetime.combine(
                self.shift_date.replace(day=self.shift_date.day + 1),
                self.planned_end_time,
            )

        duration = (end - start).total_seconds() / 3600
        return max(0, duration)

    def calculate_overtime(self, regular_hours: float | None = None) -> float:
        """Calcula horas extras. Base = horas PLANEJADAS do turno (12x36 não gera 4h extras por dia, 08/09/2026)."""
        actual = self.actual_hours or self.planned_hours
        regular_hours = regular_hours or self.planned_hours or 8.0
        if actual > regular_hours:
            return actual - regular_hours
        return 0.0
