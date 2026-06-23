"""Model para solicitações de férias."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class VacationStatus(StrEnum):
    """Status da solicitação de férias."""

    DRAFT = "draft"  # Rascunho
    PENDING = "pending"  # Aguardando aprovação
    APPROVED = "approved"  # Aprovada
    REJECTED = "rejected"  # Rejeitada
    SCHEDULED = "scheduled"  # Programada
    IN_PROGRESS = "in_progress"  # Em andamento
    COMPLETED = "completed"  # Concluída
    CANCELLED = "cancelled"  # Cancelada
    INTERRUPTED = "interrupted"  # Interrompida


class VacationType(StrEnum):
    """Tipo de férias."""

    FULL = "full"  # Férias integrais (30 dias)
    SPLIT = "split"  # Férias fracionadas
    SELL = "sell"  # Venda de férias (abono pecuniário)
    COLLECTIVE = "collective"  # Férias coletivas


class VacationPeriod(Base):
    """Período aquisitivo de férias."""

    __tablename__ = "employee_vacation_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )
    employee_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Período aquisitivo
    start_date = Column(Date, nullable=False)  # Início do período aquisitivo
    end_date = Column(Date, nullable=False)  # Fim do período aquisitivo

    # Período concessivo (12 meses após aquisitivo)
    concession_start = Column(Date, nullable=False)
    concession_end = Column(Date, nullable=False)

    # Dias de direito e utilizados
    total_days_entitled = Column(Integer, nullable=False, default=30)
    days_used = Column(Integer, nullable=False, default=0)
    days_sold = Column(Integer, nullable=False, default=0)  # Abono pecuniário
    days_remaining = Column(Integer, nullable=False, default=30)

    # Faltas que reduzem férias (CLT Art. 130)
    absences_count = Column(Integer, nullable=False, default=0)
    # 0-5 faltas: 30 dias
    # 6-14 faltas: 24 dias
    # 15-23 faltas: 18 dias
    # 24-32 faltas: 12 dias
    # > 32 faltas: perde o direito

    # Status do período
    is_expired = Column(Boolean, default=False)  # Período vencido (dobrar férias)
    is_fully_used = Column(Boolean, default=False)  # Todo período gozado
    double_payment = Column(Boolean, default=False)  # Pagar em dobro

    # Datas importantes
    expires_at = Column(Date, nullable=True)  # Data limite para gozo
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_vacation_period_employee", "employee_id", "start_date"),
        Index("ix_vacation_period_concession", "concession_end"),
    )

    def __repr__(self) -> str:
        return f"<VacationPeriod {self.start_date} - {self.end_date}>"

    @property
    def is_within_concession(self) -> bool:
        """Verifica se está dentro do período concessivo."""
        today = date.today()
        return self.concession_start <= today <= self.concession_end

    @property
    def days_until_expiration(self) -> int:
        """Dias até vencimento do período concessivo."""
        if not self.concession_end:
            return 0
        delta = self.concession_end - date.today()
        return max(0, delta.days)

    def calculate_entitled_days(self) -> int:  # pylint: disable=too-many-return-statements
        """Calcula dias de direito baseado em faltas (CLT Art. 130)."""
        if self.absences_count <= 5:
            return 30
        if self.absences_count <= 14:
            return 24
        if self.absences_count <= 23:
            return 18
        if self.absences_count <= 32:
            return 12
        return 0  # Perde o direito


class VacationRequest(Base):
    """Solicitação de férias do funcionário."""

    __tablename__ = "employee_vacation_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )
    employee_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    vacation_period_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employee_vacation_periods.id"),
        nullable=True,
        index=True,
    )

    # Identificação
    request_code = Column(String(30), nullable=False, unique=True, index=True)
    vacation_type = Column(
        String(20),
        nullable=False,
        default=VacationType.FULL.value,
    )
    status = Column(
        String(20),
        nullable=False,
        default=VacationStatus.DRAFT.value,
        index=True,
    )

    # Período solicitado
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days_requested = Column(Integer, nullable=False)

    # Abono pecuniário (venda de férias - máx 10 dias)
    sell_days = Column(Integer, nullable=True, default=0)
    sell_requested = Column(Boolean, default=False)

    # Adiantamento 13º
    advance_13th_requested = Column(Boolean, default=False)
    advance_13th_approved = Column(Boolean, nullable=True)

    # Valores calculados
    vacation_salary = Column(Numeric(15, 2), nullable=True)
    vacation_bonus = Column(Numeric(15, 2), nullable=True)  # 1/3 constitucional
    sell_value = Column(Numeric(15, 2), nullable=True)  # Abono pecuniário
    advance_13th_value = Column(Numeric(15, 2), nullable=True)
    inss_deduction = Column(Numeric(15, 2), nullable=True)
    irrf_deduction = Column(Numeric(15, 2), nullable=True)
    other_deductions = Column(Numeric(15, 2), nullable=True)
    net_value = Column(Numeric(15, 2), nullable=True)

    # Detalhamento dos cálculos
    calculation_details = Column(JSONB, default=dict)
    # {
    #   "base_salary": 5000,
    #   "daily_rate": 166.67,
    #   "days_value": 5000,
    #   "bonus_1_3": 1666.67,
    #   "sell_value": 0,
    #   "gross_total": 6666.67,
    #   "inss": 500,
    #   "irrf": 200,
    #   "net_total": 5966.67
    # }

    # Observações
    employee_notes = Column(Text, nullable=True)  # Justificativa do funcionário
    manager_notes = Column(Text, nullable=True)  # Observações do gestor
    hr_notes = Column(Text, nullable=True)  # Observações do RH

    # Workflow de aprovação
    submitted_at = Column(DateTime, nullable=True)

    # Aprovação nível 1 (Gestor)
    manager_approved = Column(Boolean, nullable=True)
    manager_approved_at = Column(DateTime, nullable=True)
    manager_approved_by = Column(UUID(as_uuid=True), nullable=True)
    manager_rejection_reason = Column(Text, nullable=True)

    # Aprovação nível 2 (RH)
    hr_approved = Column(Boolean, nullable=True)
    hr_approved_at = Column(DateTime, nullable=True)
    hr_approved_by = Column(UUID(as_uuid=True), nullable=True)
    hr_rejection_reason = Column(Text, nullable=True)

    # Programação
    scheduled_at = Column(DateTime, nullable=True)
    scheduled_by = Column(UUID(as_uuid=True), nullable=True)

    # Cancelamento/Interrupção
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(UUID(as_uuid=True), nullable=True)
    cancel_reason = Column(Text, nullable=True)

    interrupted_at = Column(DateTime, nullable=True)
    interrupted_by = Column(UUID(as_uuid=True), nullable=True)
    interrupt_reason = Column(Text, nullable=True)
    days_enjoyed_before_interrupt = Column(Integer, nullable=True)

    # Retorno
    return_date = Column(Date, nullable=True)  # Data prevista de retorno
    actual_return_date = Column(Date, nullable=True)  # Data real de retorno

    # Pagamento
    payment_date = Column(Date, nullable=True)  # Data de pagamento (2 dias antes)
    paid_at = Column(DateTime, nullable=True)
    payslip_id = Column(UUID(as_uuid=True), nullable=True)  # Referência ao holerite

    # Substituição
    substitute_employee_id = Column(UUID(as_uuid=True), nullable=True)
    substitute_name = Column(String(200), nullable=True)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("days_requested >= 5", name="ck_vacation_min_days"),
        CheckConstraint("days_requested <= 30", name="ck_vacation_max_days"),
        CheckConstraint("sell_days <= 10", name="ck_vacation_max_sell"),
        CheckConstraint("end_date >= start_date", name="ck_vacation_dates"),
        Index("ix_vacation_request_dates", "start_date", "end_date"),
        Index("ix_vacation_request_status", "status", "condominio_id"),
    )

    def __repr__(self) -> str:
        return f"<VacationRequest {self.request_code}>"

    @property
    def is_pending(self) -> bool:
        """Verifica se está pendente de aprovação."""
        return self.status == VacationStatus.PENDING.value

    @property
    def is_approved(self) -> bool:
        """Verifica se foi aprovada."""
        return self.status in [
            VacationStatus.APPROVED.value,
            VacationStatus.SCHEDULED.value,
            VacationStatus.IN_PROGRESS.value,
            VacationStatus.COMPLETED.value,
        ]

    @property
    def can_cancel(self) -> bool:
        """Verifica se pode ser cancelada."""
        return self.status in [
            VacationStatus.DRAFT.value,
            VacationStatus.PENDING.value,
            VacationStatus.APPROVED.value,
            VacationStatus.SCHEDULED.value,
        ]

    @property
    def days_until_start(self) -> int:
        """Dias até o início das férias."""
        if not self.start_date:
            return 0
        delta = self.start_date - date.today()
        return delta.days

    @property
    def is_within_legal_notice(self) -> bool:
        """Verifica se está dentro do aviso legal (30 dias antes)."""
        return self.days_until_start <= 30

    def to_summary(self) -> dict:
        """Retorna resumo para listagem."""
        start_date_str = self.start_date.isoformat() if self.start_date else None
        end_date_str = self.end_date.isoformat() if self.end_date else None
        net_value_float = float(self.net_value) if self.net_value else None

        return {
            "id": str(self.id),
            "request_code": self.request_code,
            "vacation_type": self.vacation_type,
            "status": self.status,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "days_requested": self.days_requested,
            "sell_days": self.sell_days,
            "net_value": net_value_float,
            "days_until_start": self.days_until_start,
        }
