"""
Modelo Allocation (Alocação Funcionário-Posto) para Operações.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:
    from .post import Post


class AllocationStatus(StrEnum):
    """Status da alocação."""

    ACTIVE = "active"  # Alocação ativa
    INACTIVE = "inactive"  # Inativa
    PENDING = "pending"  # Aguardando início
    SUSPENDED = "suspended"  # Suspensa temporariamente
    TERMINATED = "terminated"  # Encerrada


class Allocation(Base):
    """
    Modelo de Alocação de Funcionário em Posto.

    Representa o vínculo entre um funcionário e um posto de trabalho.

    Attributes:
        id: Identificador único
        post_id: Posto de trabalho
        employee_id: Funcionário alocado
        status: Status da alocação
        start_date: Data de início
        end_date: Data de fim (null = indeterminado)
        is_primary: Se é a alocação principal do funcionário
        hourly_rate: Valor hora específico desta alocação
        monthly_salary: Salário mensal
        role: Função específica no posto
        notes: Observações
    """

    __tablename__ = "allocations"

    # Identificação
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Relacionamentos
    post_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
        index=True,
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default=AllocationStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )

    # Período
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Configurações
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_temporary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Valores
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    monthly_salary: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    additional_benefits: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Função
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    qualifications: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """
    Exemplo de qualifications:
    {
        "curso_formacao": true,
        "porte_arma": false,
        "cnh": "B",
        "experiencia_anos": 3
    }
    """

    # Observações
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Auditoria
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)

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
    post: Mapped["Post"] = relationship(
        "Post",
        back_populates="allocations",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Allocation {self.employee_id} -> Post {self.post_id}>"

    @property
    def is_current(self) -> bool:
        """Verifica se a alocação está ativa no momento."""
        today = date.today()
        if self.status != AllocationStatus.ACTIVE.value:
            return False
        if self.start_date > today:
            return False
        if self.end_date and self.end_date < today:
            return False
        return True

    @property
    def days_allocated(self) -> int:
        """Retorna quantidade de dias alocado."""
        end = self.end_date or date.today()
        return (end - self.start_date).days

    @property
    def total_monthly_cost(self) -> float:
        """Calcula custo mensal total."""
        return self.monthly_salary + self.additional_benefits
