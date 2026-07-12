"""
Modelo Post (Posto de Trabalho) para Operações.
"""

from datetime import datetime, time
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, Time, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

if TYPE_CHECKING:
    from modules.operacional.occurrences.models import Occurrence

    from .allocation import Allocation
    from .scale import Scale


class PostType(StrEnum):
    """Tipo de posto de trabalho."""

    PORTEIRO = "porteiro"
    RECEPCIONISTA = "recepcionista"
    CONTROLADOR_ACESSO = "controlador_acesso"
    SUPERVISOR = "supervisor"
    LIDER = "lider"
    RONDANTE = "rondante"
    MONITORAMENTO = "monitoramento"
    MANUTENCAO = "manutencao"
    SERVICOS_GERAIS = "servicos_gerais"
    JARDINAGEM = "jardinagem"
    PORTARIA = "portaria"


class PostStatus(StrEnum):
    """Status do posto."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    TEMPORARY = "temporary"
    SUSPENDED = "suspended"


class ShiftType(StrEnum):
    """Tipo de turno do posto."""

    DIURNO = "diurno"  # 07h-19h
    NOTURNO = "noturno"  # 19h-07h
    MANHA = "manha"  # 06h-14h
    TARDE = "tarde"  # 14h-22h
    NOITE = "noite"  # 22h-06h
    ADMINISTRATIVO = "administrativo"  # 08h-18h
    INTEGRAL = "integral"  # 24h (revezamento)
    ESCALA_12X36 = "12x36"  # 12h trabalho / 36h descanso


class Post(Base):
    """
    Modelo de Posto de Trabalho.

    Representa um local físico onde funcionários são alocados para trabalhar.

    Attributes:
        id: Identificador único
        code: Código do posto (POST-001)
        name: Nome do posto
        description: Descrição detalhada
        post_type: Tipo de posto (porteiro, controlador de acesso, etc)
        status: Status do posto
        shift_type: Tipo de turno
        contract_id: Contrato associado
        client_id: Cliente associado
        address: Endereço completo
        latitude: Latitude GPS
        longitude: Longitude GPS
        requirements: Requisitos/qualificações necessárias
        equipment: Equipamentos necessários
        headcount: Quantidade de funcionários necessários
        hourly_rate: Valor hora do posto
        monthly_cost: Custo mensal estimado
    """

    __tablename__ = "posts"

    # Identificação
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tipo e Status
    post_type: Mapped[str] = mapped_column(
        String(50),
        default=PostType.PORTEIRO.value,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=PostStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )
    shift_type: Mapped[str] = mapped_column(
        String(50),
        default=ShiftType.DIURNO.value,
        nullable=False,
    )

    # Relacionamentos externos (IDs de outros módulos)
    contract_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    client_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    # Vínculo explícito com cliente GED (evita fuzzy match por nome)
    ged_client_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
        comment="FK para ged_clients.id — vincula posto ao cliente GED diretamente",
    )

    # Localização
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Raio do geofence (metros) para validar batida de ponto no posto (default 150m)
    geofence_raio_metros: Mapped[float] = mapped_column(Float, nullable=False, default=150.0, server_default="150")

    # Horários padrão (nomes conforme schema do banco)
    shift_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    shift_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    break_duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    night_shift_bonus_percent: Mapped[float] = mapped_column(Float, default=20.0, nullable=False)
    hazard_pay_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Requisitos e certificações (JSON)
    required_certifications: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Capacidade e Custos
    required_headcount: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_headcount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requires_experience_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    monthly_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Configurações
    requires_armed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_vehicle: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Contatos de emergência
    supervisor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    supervisor_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emergency_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

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
    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )

    # Relacionamentos (lazy="noload" para evitar erros de schema em tabelas relacionadas)
    allocations: Mapped[list["Allocation"]] = relationship(
        "Allocation",
        back_populates="post",
        lazy="noload",
    )
    scales: Mapped[list["Scale"]] = relationship(
        "Scale",
        back_populates="post",
        lazy="noload",
    )
    occurrences: Mapped[list["Occurrence"]] = relationship(
        "Occurrence",
        back_populates="post",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Post {self.code} - {self.name}>"

    @property
    def is_filled(self) -> bool:
        """Verifica se o posto está preenchido com funcionários."""
        # Com lazy="noload", current_headcount é usado em vez de contar allocations
        return self.current_headcount >= self.required_headcount

    @property
    def vacancy_count(self) -> int:
        """Retorna quantidade de vagas disponíveis."""
        return max(0, self.required_headcount - self.current_headcount)

    @property
    def daily_hours(self) -> float:
        """Calcula horas diárias do posto baseado no tipo de turno."""
        hours_map = {
            ShiftType.DIURNO.value: 12.0,
            ShiftType.NOTURNO.value: 12.0,
            ShiftType.MANHA.value: 8.0,
            ShiftType.TARDE.value: 8.0,
            ShiftType.NOITE.value: 8.0,
            ShiftType.ADMINISTRATIVO.value: 8.0,
            ShiftType.INTEGRAL.value: 24.0,
        }
        return hours_map.get(self.shift_type, 8.0)
