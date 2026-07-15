"""Modelo Overtime - Horas Extras.

Gerenciamento de horas extras, banco de horas e compensações.
Conformidade com CLT e acordos coletivos.
"""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class OvertimeType(StrEnum):
    """Tipo de hora extra."""

    HORA_EXTRA_50 = "hora_extra_50"  # 50% adicional
    HORA_EXTRA_100 = "hora_extra_100"  # 100% adicional (domingo/feriado)
    BANCO_HORAS = "banco_horas"  # Compensação futura
    SOBREAVISO = "sobreaviso"  # Sobreaviso (1/3 salário/hora)
    PRONTIDAO = "prontidao"  # Prontidão (2/3 salário/hora)
    ADICIONAL_NOTURNO = "adicional_noturno"  # 20% adicional noturno
    INTERJORNADA = "interjornada"  # Hora entre jornadas (dobro)


class OvertimeStatus(StrEnum):
    """Status da hora extra."""

    PENDENTE = "pendente"
    EM_ANALISE = "em_analise"
    APROVADA = "aprovada"
    REJEITADA = "rejeitada"
    PAGA = "paga"
    COMPENSADA = "compensada"
    PARCIALMENTE_COMPENSADA = "parcialmente_compensada"
    EXPIRADA = "expirada"
    CANCELADA = "cancelada"


class OvertimeReason(StrEnum):
    """Motivo da hora extra."""

    DEMANDA_TRABALHO = "demanda_trabalho"
    EMERGENCIA = "emergencia"
    COBERTURA_FALTA = "cobertura_falta"
    EVENTO_ESPECIAL = "evento_especial"
    FECHAMENTO_MES = "fechamento_mes"
    MANUTENCAO = "manutencao"
    PROJETO = "projeto"
    TREINAMENTO = "treinamento"
    CLIENTE = "cliente"
    OUTRO = "outro"


class CompensationType(StrEnum):
    """Tipo de compensação."""

    FOLGA = "folga"
    REDUCAO_JORNADA = "reducao_jornada"
    SAIDA_ANTECIPADA = "saida_antecipada"
    ENTRADA_TARDIA = "entrada_tardia"
    PAGAMENTO = "pagamento"


class Overtime(Base):
    """Modelo de Horas Extras.

    Registra e gerencia todas as horas extras realizadas,
    incluindo aprovações, pagamentos e compensações.
    """

    __tablename__ = "overtimes"

    # Identificação
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)

    # Funcionário
    employee_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    employee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    employee_registration: Mapped[str | None] = mapped_column(String(50))
    department_id: Mapped[str | None] = mapped_column(String(50))
    department_name: Mapped[str | None] = mapped_column(String(100))

    # Tipo e status
    overtime_type: Mapped[OvertimeType] = mapped_column(String(30), default=OvertimeType.HORA_EXTRA_50)
    status: Mapped[OvertimeStatus] = mapped_column(String(30), default=OvertimeStatus.PENDENTE)
    reason: Mapped[OvertimeReason] = mapped_column(String(30), default=OvertimeReason.DEMANDA_TRABALHO)
    reason_description: Mapped[str | None] = mapped_column(Text)

    # Data e horário
    overtime_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    start_datetime: Mapped[datetime | None] = mapped_column(DateTime)
    end_datetime: Mapped[datetime | None] = mapped_column(DateTime)

    # Duração (em minutos)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, default=0)
    net_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Noturno (minutos entre 22h e 05h)
    night_minutes: Mapped[int] = mapped_column(Integer, default=0)
    is_night_shift: Mapped[bool] = mapped_column(Boolean, default=False)

    # É feriado/domingo
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sunday: Mapped[bool] = mapped_column(Boolean, default=False)
    holiday_name: Mapped[str | None] = mapped_column(String(100))

    # Valores e multiplicadores
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.50"))
    total_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    night_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.20"))
    night_additional_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Pré-aprovação (solicitação prévia)
    is_pre_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    pre_approved_by_id: Mapped[str | None] = mapped_column(String(50))
    pre_approved_by_name: Mapped[str | None] = mapped_column(String(200))
    pre_approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    pre_approval_notes: Mapped[str | None] = mapped_column(Text)

    # Aprovação
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by_id: Mapped[str | None] = mapped_column(String(50))
    approved_by_name: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approval_notes: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    # Pagamento
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)
    payment_reference: Mapped[str | None] = mapped_column(String(100))
    payroll_period: Mapped[str | None] = mapped_column(String(7))  # YYYY-MM

    # Banco de horas (se aplicável)
    use_time_bank: Mapped[bool] = mapped_column(Boolean, default=False)
    time_bank_credited: Mapped[bool] = mapped_column(Boolean, default=False)
    time_bank_credited_at: Mapped[datetime | None] = mapped_column(DateTime)
    time_bank_expires_at: Mapped[date | None] = mapped_column(Date)

    # Compensação
    is_compensated: Mapped[bool] = mapped_column(Boolean, default=False)
    compensated_at: Mapped[datetime | None] = mapped_column(DateTime)
    compensation_type: Mapped[CompensationType | None] = mapped_column(String(30))
    compensation_date: Mapped[date | None] = mapped_column(Date)
    compensation_reference_id: Mapped[str | None] = mapped_column(String(50))
    compensated_minutes: Mapped[int] = mapped_column(Integer, default=0)
    remaining_minutes: Mapped[int] = mapped_column(Integer, default=0)

    # Registros de ponto vinculados
    time_entry_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)

    # Jornada
    work_schedule_id: Mapped[str | None] = mapped_column(String(50))

    # Local
    condominium_id: Mapped[str | None] = mapped_column(String(50), index=True)
    condominium_name: Mapped[str | None] = mapped_column(String(200))
    work_location: Mapped[str | None] = mapped_column(String(200))

    # Observações e metadados
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONB, default=list)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Controle
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id: Mapped[str | None] = mapped_column(String(50))

    # Índices
    __table_args__ = (
        Index("ix_overtimes_employee_date", "employee_id", "overtime_date"),
        Index("ix_overtimes_status_date", "status", "overtime_date"),
        Index("ix_overtimes_condominium_date", "condominium_id", "overtime_date"),
    )

    def __init__(self, **kwargs) -> None:
        """Inicializa a hora extra."""
        super().__init__(**kwargs)
        if not self.code:
            self.code = self._generate_code()
        self._calculate_net_duration()
        self._set_multiplier()
        self._calculate_values()

    def _generate_code(self) -> str:
        """Gera código único da hora extra."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[:16]
        return f"HE-{timestamp}"

    def _calculate_net_duration(self) -> None:
        """Calcula duração líquida descontando pausas."""
        if self.duration_minutes:
            self.net_duration_minutes = self.duration_minutes - self.break_minutes
            self.remaining_minutes = self.net_duration_minutes

    def _set_multiplier(self) -> None:
        """Define multiplicador baseado no tipo e dia."""
        if self.is_holiday or self.is_sunday:
            self.multiplier = Decimal("2.00")
            self.overtime_type = OvertimeType.HORA_EXTRA_100
        elif self.overtime_type == OvertimeType.HORA_EXTRA_100:
            self.multiplier = Decimal("2.00")
        elif self.overtime_type == OvertimeType.SOBREAVISO:
            self.multiplier = Decimal("0.33")
        elif self.overtime_type == OvertimeType.PRONTIDAO:
            self.multiplier = Decimal("0.67")
        elif self.overtime_type == OvertimeType.INTERJORNADA:
            self.multiplier = Decimal("2.00")
        else:
            self.multiplier = Decimal("1.50")

    def _calculate_values(self) -> None:
        """Calcula valores da hora extra."""
        if not self.hourly_rate or not self.net_duration_minutes:
            return

        # Valor base
        hours = Decimal(self.net_duration_minutes) / Decimal(60)
        self.total_value = hours * self.hourly_rate * self.multiplier

        # Adicional noturno
        if self.night_minutes > 0:
            night_hours = Decimal(self.night_minutes) / Decimal(60)
            self.night_additional_value = night_hours * self.hourly_rate * (self.night_multiplier - 1)
            self.total_value += self.night_additional_value

    def calculate_duration(self) -> int:
        """Calcula duração total em minutos.

        Returns:
            int: Duração em minutos
        """
        if not self.start_time or not self.end_time:
            return 0

        start_dt = datetime.combine(self.overtime_date, self.start_time)
        end_dt = datetime.combine(self.overtime_date, self.end_time)

        # Se terminou no dia seguinte
        if end_dt < start_dt:
            end_dt += timedelta(days=1)

        diff = end_dt - start_dt
        self.duration_minutes = int(diff.total_seconds() / 60)
        self._calculate_net_duration()
        return self.duration_minutes

    def calculate_night_hours(self) -> int:
        """Calcula minutos em horário noturno (22h-05h).

        Returns:
            int: Minutos noturnos
        """
        night_start = time(22, 0)
        night_end = time(5, 0)

        start_dt = datetime.combine(self.overtime_date, self.start_time)
        end_dt = datetime.combine(self.overtime_date, self.end_time)

        if end_dt < start_dt:
            end_dt += timedelta(days=1)

        night_minutes = 0
        current = start_dt

        while current < end_dt:
            current_time = current.time()

            # Verifica se está no período noturno
            if current_time >= night_start or current_time < night_end:
                night_minutes += 1

            current += timedelta(minutes=1)

        self.night_minutes = night_minutes
        self.is_night_shift = night_minutes > 0
        return night_minutes

    def pre_approve(
        self,
        approved_by_id: str,
        approved_by_name: str,
        notes: str = None,
    ) -> None:
        """Pré-aprova a hora extra (antes de realizar).

        Args:
            approved_by_id: ID do aprovador
            approved_by_name: Nome do aprovador
            notes: Observações
        """
        self.is_pre_approved = True
        self.pre_approved_by_id = approved_by_id
        self.pre_approved_by_name = approved_by_name
        self.pre_approved_at = datetime.utcnow()
        self.pre_approval_notes = notes

    def approve(
        self,
        approved_by_id: str,
        approved_by_name: str,
        notes: str = None,
    ) -> None:
        """Aprova a hora extra.

        Args:
            approved_by_id: ID do aprovador
            approved_by_name: Nome do aprovador
            notes: Observações
        """
        self.status = OvertimeStatus.APROVADA
        self.approved_by_id = approved_by_id
        self.approved_by_name = approved_by_name
        self.approved_at = datetime.utcnow()
        self.approval_notes = notes

        # Se usa banco de horas, credita
        if self.use_time_bank:
            self._credit_time_bank()

    def reject(
        self,
        rejected_by_id: str,
        rejected_by_name: str,
        reason: str,
    ) -> None:
        """Rejeita a hora extra.

        Args:
            rejected_by_id: ID de quem rejeitou
            rejected_by_name: Nome de quem rejeitou
            reason: Motivo da rejeição
        """
        self.status = OvertimeStatus.REJEITADA
        self.approved_by_id = rejected_by_id
        self.approved_by_name = rejected_by_name
        self.approved_at = datetime.utcnow()
        self.rejection_reason = reason

    def _credit_time_bank(self) -> None:
        """Credita no banco de horas."""
        self.time_bank_credited = True
        self.time_bank_credited_at = datetime.utcnow()

        # Define expiração (padrão 6 meses)
        self.time_bank_expires_at = date.today() + timedelta(days=180)

    def mark_as_paid(
        self,
        payment_reference: str = None,
        payroll_period: str = None,
    ) -> None:
        """Marca como paga.

        Args:
            payment_reference: Referência do pagamento
            payroll_period: Período da folha (YYYY-MM)
        """
        self.status = OvertimeStatus.PAGA
        self.is_paid = True
        self.paid_at = datetime.utcnow()
        self.payment_reference = payment_reference
        self.payroll_period = payroll_period

    def compensate(
        self,
        compensation_type: CompensationType,
        compensation_date: date,
        minutes: int,
        reference_id: str = None,
    ) -> None:
        """Registra compensação.

        Args:
            compensation_type: Tipo de compensação
            compensation_date: Data da compensação
            minutes: Minutos compensados
            reference_id: Referência do registro de compensação
        """
        self.compensated_minutes += minutes
        self.remaining_minutes = self.net_duration_minutes - self.compensated_minutes

        if self.remaining_minutes <= 0:
            self.status = OvertimeStatus.COMPENSADA
            self.is_compensated = True
        else:
            self.status = OvertimeStatus.PARCIALMENTE_COMPENSADA

        self.compensated_at = datetime.utcnow()
        self.compensation_type = compensation_type
        self.compensation_date = compensation_date
        self.compensation_reference_id = reference_id

    def check_expiration(self) -> bool:
        """Verifica se expirou (banco de horas).

        Returns:
            bool: True se expirou
        """
        if not self.use_time_bank or not self.time_bank_expires_at:
            return False

        if date.today() > self.time_bank_expires_at:
            self.status = OvertimeStatus.EXPIRADA
            return True
        return False

    def cancel(self, reason: str = None) -> None:
        """Cancela a hora extra.

        Args:
            reason: Motivo do cancelamento
        """
        self.status = OvertimeStatus.CANCELADA
        if reason:
            self.notes = f"Cancelada: {reason}"

    def recalculate(self) -> None:
        """Recalcula duração e valores."""
        self.calculate_duration()
        self.calculate_night_hours()
        self._set_multiplier()
        self._calculate_values()

    def soft_delete(self) -> None:
        """Soft delete da hora extra."""
        self.is_deleted = True
        self.status = OvertimeStatus.CANCELADA

    @property
    def duration_hours(self) -> float:
        """Retorna duração em horas."""
        return self.net_duration_minutes / 60 if self.net_duration_minutes else 0

    @property
    def is_pending_approval(self) -> bool:
        """Verifica se está pendente de aprovação."""
        return self.status in [
            OvertimeStatus.PENDENTE,
            OvertimeStatus.EM_ANALISE,
        ]

    @property
    def is_pending_payment(self) -> bool:
        """Verifica se está pendente de pagamento."""
        return self.status == OvertimeStatus.APROVADA and not self.use_time_bank and not self.is_paid

    @property
    def is_pending_compensation(self) -> bool:
        """Verifica se está pendente de compensação."""
        return (
            self.status in [OvertimeStatus.APROVADA, OvertimeStatus.PARCIALMENTE_COMPENSADA]
            and self.use_time_bank
            and self.remaining_minutes > 0
        )

    @property
    def days_until_expiration(self) -> int | None:
        """Dias até expirar (banco de horas)."""
        if not self.time_bank_expires_at:
            return None
        delta = self.time_bank_expires_at - date.today()
        return delta.days if delta.days > 0 else 0

    @property
    def overtime_type_display(self) -> str:
        """Retorna tipo para exibição."""
        display_map = {
            OvertimeType.HORA_EXTRA_50: "HE 50%",
            OvertimeType.HORA_EXTRA_100: "HE 100%",
            OvertimeType.BANCO_HORAS: "Banco de Horas",
            OvertimeType.SOBREAVISO: "Sobreaviso",
            OvertimeType.PRONTIDAO: "Prontidão",
            OvertimeType.ADICIONAL_NOTURNO: "Adicional Noturno",
            OvertimeType.INTERJORNADA: "Interjornada",
        }
        return display_map.get(self.overtime_type, self.overtime_type.value)

    @property
    def status_display(self) -> str:
        """Retorna status para exibição."""
        display_map = {
            OvertimeStatus.PENDENTE: "Pendente",
            OvertimeStatus.EM_ANALISE: "Em Análise",
            OvertimeStatus.APROVADA: "Aprovada",
            OvertimeStatus.REJEITADA: "Rejeitada",
            OvertimeStatus.PAGA: "Paga",
            OvertimeStatus.COMPENSADA: "Compensada",
            OvertimeStatus.PARCIALMENTE_COMPENSADA: "Parcialmente Compensada",
            OvertimeStatus.EXPIRADA: "Expirada",
            OvertimeStatus.CANCELADA: "Cancelada",
        }
        return display_map.get(self.status, self.status.value if hasattr(self.status, "value") else str(self.status))

    def __repr__(self) -> str:
        """Representação do objeto."""
        return f"<Overtime {self.code}: {self.employee_name} {self.overtime_date} {self.duration_hours:.1f}h>"
