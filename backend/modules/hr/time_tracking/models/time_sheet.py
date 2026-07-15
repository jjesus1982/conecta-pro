"""Modelo TimeSheet - Folha de Ponto Mensal.

Consolidação mensal dos registros de ponto, horas trabalhadas,
extras, faltas e atrasos para fechamento da folha de pagamento.
"""

import uuid
from datetime import date, datetime, timedelta
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
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class TimeSheetStatus(StrEnum):
    """Status da folha de ponto."""

    ABERTO = "aberto"
    EM_PROCESSAMENTO = "em_processamento"
    CALCULADO = "calculado"  # estado do motor de espelho (calculado, ainda não fechado)
    PENDENTE_REVISAO = "pendente_revisao"
    REVISADO = "revisado"
    APROVADO = "aprovado"
    FECHADO = "fechado"
    ENVIADO_FOLHA = "enviado_folha"
    CANCELADO = "cancelado"


class TimeSheet(Base):
    """Modelo de Folha de Ponto Mensal.

    Consolida todos os registros de ponto de um funcionário
    em um período mensal para fechamento e envio à folha.
    """

    __tablename__ = "time_sheets"

    # Identificação
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)

    # Período
    reference_month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    reference_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Funcionário
    employee_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    employee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    employee_registration: Mapped[str | None] = mapped_column(String(50))
    employee_cpf: Mapped[str | None] = mapped_column(String(14))
    employee_pis: Mapped[str | None] = mapped_column(String(15))
    department_id: Mapped[str | None] = mapped_column(String(50))
    department_name: Mapped[str | None] = mapped_column(String(100))
    position_name: Mapped[str | None] = mapped_column(String(100))

    # Jornada
    work_schedule_id: Mapped[str | None] = mapped_column(String(50))
    work_schedule_name: Mapped[str | None] = mapped_column(String(200))
    weekly_hours_expected: Mapped[int] = mapped_column(Integer, default=2640)  # 44h

    # Status
    status: Mapped[TimeSheetStatus] = mapped_column(String(20), default=TimeSheetStatus.ABERTO)

    # Dias do período
    total_days: Mapped[int] = mapped_column(Integer, default=0)
    work_days_expected: Mapped[int] = mapped_column(Integer, default=0)
    work_days_worked: Mapped[int] = mapped_column(Integer, default=0)
    absent_days: Mapped[int] = mapped_column(Integer, default=0)
    justified_absent_days: Mapped[int] = mapped_column(Integer, default=0)
    unjustified_absent_days: Mapped[int] = mapped_column(Integer, default=0)
    vacation_days: Mapped[int] = mapped_column(Integer, default=0)
    holiday_days: Mapped[int] = mapped_column(Integer, default=0)
    leave_days: Mapped[int] = mapped_column(Integer, default=0)
    medical_leave_days: Mapped[int] = mapped_column(Integer, default=0)

    # Horas (em minutos para precisão)
    hours_expected_minutes: Mapped[int] = mapped_column(Integer, default=0)
    hours_worked_minutes: Mapped[int] = mapped_column(Integer, default=0)
    hours_balance_minutes: Mapped[int] = mapped_column(Integer, default=0)

    # Horas extras (em minutos)
    overtime_50_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_100_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_total_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_approved_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_pending_minutes: Mapped[int] = mapped_column(Integer, default=0)

    # Adicional noturno (em minutos)
    night_hours_minutes: Mapped[int] = mapped_column(Integer, default=0)

    # Atrasos e saídas antecipadas (em minutos)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_departure_minutes: Mapped[int] = mapped_column(Integer, default=0)
    late_count: Mapped[int] = mapped_column(Integer, default=0)
    early_departure_count: Mapped[int] = mapped_column(Integer, default=0)

    # Intervalos
    break_expected_minutes: Mapped[int] = mapped_column(Integer, default=0)
    break_actual_minutes: Mapped[int] = mapped_column(Integer, default=0)
    break_irregular_count: Mapped[int] = mapped_column(Integer, default=0)

    # Banco de horas
    time_bank_previous_balance: Mapped[int] = mapped_column(Integer, default=0)
    time_bank_credits: Mapped[int] = mapped_column(Integer, default=0)
    time_bank_debits: Mapped[int] = mapped_column(Integer, default=0)
    time_bank_current_balance: Mapped[int] = mapped_column(Integer, default=0)
    time_bank_expiring_minutes: Mapped[int] = mapped_column(Integer, default=0)

    # DSR (Descanso Semanal Remunerado)
    dsr_entitled: Mapped[bool] = mapped_column(Boolean, default=True)
    dsr_lost_days: Mapped[int] = mapped_column(Integer, default=0)
    dsr_lost_reason: Mapped[str | None] = mapped_column(Text)

    # Valores monetários
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    overtime_50_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    overtime_100_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    night_additional_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_additional_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_deduction_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Ocorrências e justificativas
    total_entries: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_resolved_count: Mapped[int] = mapped_column(Integer, default=0)
    justification_count: Mapped[int] = mapped_column(Integer, default=0)
    justification_approved_count: Mapped[int] = mapped_column(Integer, default=0)
    justification_pending_count: Mapped[int] = mapped_column(Integer, default=0)
    manual_entries_count: Mapped[int] = mapped_column(Integer, default=0)

    # Registros detalhados por dia
    daily_summary: Mapped[list[dict] | None] = mapped_column(JSONB, default=list)
    # Formato: [{"date": "2024-01-01", "expected": 528, "worked": 540, "overtime": 12, ...}]

    # Revisão
    has_pending_issues: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_issues: Mapped[list[dict] | None] = mapped_column(JSONB, default=list)
    # Formato: [{"type": "missing_entry", "date": "2024-01-05", "description": "..."}]

    reviewed_by_id: Mapped[str | None] = mapped_column(String(50))
    reviewed_by_name: Mapped[str | None] = mapped_column(String(200))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_notes: Mapped[str | None] = mapped_column(Text)

    # Aprovação
    approved_by_employee: Mapped[bool] = mapped_column(Boolean, default=False)
    employee_approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    employee_approval_notes: Mapped[str | None] = mapped_column(Text)

    approved_by_manager: Mapped[bool] = mapped_column(Boolean, default=False)
    manager_id: Mapped[str | None] = mapped_column(String(50))
    manager_name: Mapped[str | None] = mapped_column(String(200))
    manager_approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    manager_approval_notes: Mapped[str | None] = mapped_column(Text)

    approved_by_hr: Mapped[bool] = mapped_column(Boolean, default=False)
    hr_approver_id: Mapped[str | None] = mapped_column(String(50))
    hr_approver_name: Mapped[str | None] = mapped_column(String(200))
    hr_approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    hr_approval_notes: Mapped[str | None] = mapped_column(Text)

    # Fechamento
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by_id: Mapped[str | None] = mapped_column(String(50))
    closed_by_name: Mapped[str | None] = mapped_column(String(200))

    # Envio para folha
    sent_to_payroll_at: Mapped[datetime | None] = mapped_column(DateTime)
    payroll_reference: Mapped[str | None] = mapped_column(String(100))
    payroll_batch_id: Mapped[str | None] = mapped_column(String(50))

    # Condomínio
    condominium_id: Mapped[str | None] = mapped_column(String(50), index=True)
    condominium_name: Mapped[str | None] = mapped_column(String(200))

    # Observações
    notes: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Controle
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_calculated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Índices
    __table_args__ = (
        Index(
            "ix_time_sheets_employee_period",
            "employee_id",
            "reference_year",
            "reference_month",
            unique=True,
        ),
        Index("ix_time_sheets_status_period", "status", "reference_year", "reference_month"),
    )

    def __init__(self, **kwargs) -> None:
        """Inicializa a folha de ponto."""
        super().__init__(**kwargs)
        if not self.code:
            self.code = self._generate_code()
        self._set_period_dates()

    def _generate_code(self) -> str:
        """Gera código único da folha."""
        return f"FP-{self.reference_year}{self.reference_month:02d}-{uuid.uuid4().hex[:8].upper()}"

    def _set_period_dates(self) -> None:
        """Define datas do período."""
        if self.reference_year and self.reference_month:
            self.period_start = date(self.reference_year, self.reference_month, 1)

            # Último dia do mês
            if self.reference_month == 12:
                next_month = date(self.reference_year + 1, 1, 1)
            else:
                next_month = date(self.reference_year, self.reference_month + 1, 1)

            self.period_end = next_month - timedelta(days=1)
            self.total_days = (self.period_end - self.period_start).days + 1

    def calculate_totals(self) -> None:
        """Recalcula todos os totais."""
        self._calculate_hours_balance()
        self._calculate_overtime_totals()
        self._calculate_time_bank()
        self._calculate_values()
        self._check_dsr()
        self._update_issue_flags()
        self.last_calculated_at = datetime.utcnow()

    def _calculate_hours_balance(self) -> None:
        """Calcula saldo de horas."""
        self.hours_balance_minutes = self.hours_worked_minutes - self.hours_expected_minutes

    def _calculate_overtime_totals(self) -> None:
        """Calcula totais de horas extras."""
        self.overtime_total_minutes = self.overtime_50_minutes + self.overtime_100_minutes

    def _calculate_time_bank(self) -> None:
        """Calcula banco de horas."""
        self.time_bank_current_balance = (
            self.time_bank_previous_balance + self.time_bank_credits - self.time_bank_debits
        )

    def _calculate_values(self) -> None:
        """Calcula valores monetários."""
        if not self.hourly_rate:
            return

        # Hora extra 50%
        hours_50 = Decimal(self.overtime_50_minutes) / Decimal(60)
        self.overtime_50_value = hours_50 * self.hourly_rate * Decimal("1.50")

        # Hora extra 100%
        hours_100 = Decimal(self.overtime_100_minutes) / Decimal(60)
        self.overtime_100_value = hours_100 * self.hourly_rate * Decimal("2.00")

        # Adicional noturno (20%)
        night_hours = Decimal(self.night_hours_minutes) / Decimal(60)
        self.night_additional_value = night_hours * self.hourly_rate * Decimal("0.20")

        # Total adicionais
        self.total_additional_value = self.overtime_50_value + self.overtime_100_value + self.night_additional_value

        # Descontos (atrasos e faltas injustificadas)
        deduction_minutes = self.late_minutes + self.early_departure_minutes
        absent_hours = self.unjustified_absent_days * (self.weekly_hours_expected / 6)
        deduction_hours = Decimal(deduction_minutes) / Decimal(60) + Decimal(str(absent_hours))
        self.total_deduction_value = deduction_hours * self.hourly_rate

    def _check_dsr(self) -> None:
        """Verifica direito ao DSR."""
        # Perde DSR se tiver faltas injustificadas ou atrasos > 30min
        if self.unjustified_absent_days > 0 or self.late_minutes > 30:
            self.dsr_entitled = False
            self.dsr_lost_days = 1  # Por semana com ocorrência
            reasons = []
            if self.unjustified_absent_days > 0:
                reasons.append(f"{self.unjustified_absent_days} falta(s) injustificada(s)")
            if self.late_minutes > 30:
                reasons.append(f"Atrasos totais de {self.late_minutes} minutos")
            self.dsr_lost_reason = "; ".join(reasons)
        else:
            self.dsr_entitled = True
            self.dsr_lost_days = 0
            self.dsr_lost_reason = None

    def _update_issue_flags(self) -> None:
        """Atualiza flags de pendências."""
        self.has_pending_issues = (
            self.anomaly_count > self.anomaly_resolved_count
            or self.justification_pending_count > 0
            or self.overtime_pending_minutes > 0
        )

    def add_daily_entry(
        self,
        entry_date: date,
        expected_minutes: int,
        worked_minutes: int,
        overtime_minutes: int = 0,
        night_minutes: int = 0,
        late_minutes: int = 0,
        early_minutes: int = 0,
        is_holiday: bool = False,
        is_absent: bool = False,
        notes: str = None,
    ) -> None:
        """Adiciona resumo de um dia.

        Args:
            entry_date: Data
            expected_minutes: Minutos esperados
            worked_minutes: Minutos trabalhados
            overtime_minutes: Minutos de hora extra
            night_minutes: Minutos noturnos
            late_minutes: Minutos de atraso
            early_minutes: Minutos de saída antecipada
            is_holiday: É feriado
            is_absent: É falta
            notes: Observações
        """
        if not self.daily_summary:
            self.daily_summary = []

        self.daily_summary.append(
            {
                "date": entry_date.isoformat(),
                "expected": expected_minutes,
                "worked": worked_minutes,
                "overtime": overtime_minutes,
                "night": night_minutes,
                "late": late_minutes,
                "early": early_minutes,
                "is_holiday": is_holiday,
                "is_absent": is_absent,
                "notes": notes,
            }
        )

    def add_issue(
        self,
        issue_type: str,
        issue_date: date,
        description: str,
        severity: str = "medium",
    ) -> None:
        """Adiciona pendência.

        Args:
            issue_type: Tipo da pendência
            issue_date: Data
            description: Descrição
            severity: Severidade (low, medium, high)
        """
        if not self.pending_issues:
            self.pending_issues = []

        self.pending_issues.append(
            {
                "type": issue_type,
                "date": issue_date.isoformat(),
                "description": description,
                "severity": severity,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        self.has_pending_issues = True

    def employee_approve(self, notes: str = None) -> None:
        """Funcionário aprova a folha.

        Args:
            notes: Observações
        """
        self.approved_by_employee = True
        self.employee_approved_at = datetime.utcnow()
        self.employee_approval_notes = notes

    def manager_approve(
        self,
        manager_id: str,
        manager_name: str,
        notes: str = None,
    ) -> None:
        """Gestor aprova a folha.

        Args:
            manager_id: ID do gestor
            manager_name: Nome do gestor
            notes: Observações
        """
        self.approved_by_manager = True
        self.manager_id = manager_id
        self.manager_name = manager_name
        self.manager_approved_at = datetime.utcnow()
        self.manager_approval_notes = notes

    def hr_approve(
        self,
        hr_id: str,
        hr_name: str,
        notes: str = None,
    ) -> None:
        """RH aprova a folha.

        Args:
            hr_id: ID do RH
            hr_name: Nome do RH
            notes: Observações
        """
        self.approved_by_hr = True
        self.hr_approver_id = hr_id
        self.hr_approver_name = hr_name
        self.hr_approved_at = datetime.utcnow()
        self.hr_approval_notes = notes
        self.status = TimeSheetStatus.APROVADO

    def review(
        self,
        reviewer_id: str,
        reviewer_name: str,
        notes: str = None,
    ) -> None:
        """Marca como revisado.

        Args:
            reviewer_id: ID do revisor
            reviewer_name: Nome do revisor
            notes: Observações
        """
        self.status = TimeSheetStatus.REVISADO
        self.reviewed_by_id = reviewer_id
        self.reviewed_by_name = reviewer_name
        self.reviewed_at = datetime.utcnow()
        self.review_notes = notes

    def close(self, closed_by_id: str, closed_by_name: str) -> None:
        """Fecha a folha.

        Args:
            closed_by_id: ID de quem fechou
            closed_by_name: Nome de quem fechou
        """
        self.status = TimeSheetStatus.FECHADO
        self.closed_at = datetime.utcnow()
        self.closed_by_id = closed_by_id
        self.closed_by_name = closed_by_name

    def send_to_payroll(
        self,
        payroll_reference: str,
        batch_id: str = None,
    ) -> None:
        """Envia para folha de pagamento.

        Args:
            payroll_reference: Referência da folha
            batch_id: ID do lote
        """
        self.status = TimeSheetStatus.ENVIADO_FOLHA
        self.sent_to_payroll_at = datetime.utcnow()
        self.payroll_reference = payroll_reference
        self.payroll_batch_id = batch_id

    def reopen(self, reason: str = None) -> None:
        """Reabre a folha para ajustes.

        Args:
            reason: Motivo da reabertura
        """
        self.status = TimeSheetStatus.ABERTO
        if reason:
            self.notes = f"Reaberta: {reason}"

        # Limpa aprovações
        self.approved_by_employee = False
        self.approved_by_manager = False
        self.approved_by_hr = False

    def soft_delete(self) -> None:
        """Soft delete da folha."""
        self.is_deleted = True
        self.status = TimeSheetStatus.CANCELADO

    @property
    def hours_worked(self) -> float:
        """Retorna horas trabalhadas."""
        return self.hours_worked_minutes / 60

    @property
    def hours_expected(self) -> float:
        """Retorna horas esperadas."""
        return self.hours_expected_minutes / 60

    @property
    def hours_balance(self) -> float:
        """Retorna saldo de horas."""
        return self.hours_balance_minutes / 60

    @property
    def overtime_total_hours(self) -> float:
        """Retorna total de horas extras."""
        return self.overtime_total_minutes / 60

    @property
    def is_fully_approved(self) -> bool:
        """Verifica se está totalmente aprovada."""
        return self.approved_by_employee and self.approved_by_manager and self.approved_by_hr

    @property
    def can_close(self) -> bool:
        """Verifica se pode fechar."""
        return not self.has_pending_issues and self.is_fully_approved and self.status == TimeSheetStatus.APROVADO

    @property
    def period_display(self) -> str:
        """Retorna período formatado."""
        months = [
            "",
            "Janeiro",
            "Fevereiro",
            "Março",
            "Abril",
            "Maio",
            "Junho",
            "Julho",
            "Agosto",
            "Setembro",
            "Outubro",
            "Novembro",
            "Dezembro",
        ]
        return f"{months[self.reference_month]}/{self.reference_year}"

    @property
    def status_display(self) -> str:
        """Retorna status para exibição."""
        display_map = {
            TimeSheetStatus.ABERTO: "Aberto",
            TimeSheetStatus.EM_PROCESSAMENTO: "Em Processamento",
            TimeSheetStatus.CALCULADO: "Calculado",
            TimeSheetStatus.PENDENTE_REVISAO: "Pendente Revisão",
            TimeSheetStatus.REVISADO: "Revisado",
            TimeSheetStatus.APROVADO: "Aprovado",
            TimeSheetStatus.FECHADO: "Fechado",
            TimeSheetStatus.ENVIADO_FOLHA: "Enviado p/ Folha",
            TimeSheetStatus.CANCELADO: "Cancelado",
        }
        return display_map.get(self.status, self.status.value)

    def __repr__(self) -> str:
        """Representação do objeto."""
        return f"<TimeSheet {self.code}: {self.employee_name} {self.period_display}>"
