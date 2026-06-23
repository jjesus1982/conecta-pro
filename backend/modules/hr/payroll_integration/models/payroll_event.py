"""Model para eventos de folha de pagamento."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models import Base

if TYPE_CHECKING:
    from modules.hr.payroll_integration.models.payroll_period import PayrollPeriod


class EventType(StrEnum):
    """Tipo de evento."""

    EARNING = "earning"  # Provento
    DEDUCTION = "deduction"  # Desconto
    INFORMATIVE = "informative"  # Informativo (não afeta líquido)
    EMPLOYER = "employer"  # Encargo patronal


class EventCategory(StrEnum):
    """Categoria do evento."""

    # Proventos
    SALARY = "salary"  # Salário base
    OVERTIME_50 = "overtime_50"  # Hora extra 50%
    OVERTIME_100 = "overtime_100"  # Hora extra 100%
    NIGHT_SHIFT = "night_shift"  # Adicional noturno
    HAZARD_PAY = "hazard_pay"  # Periculosidade
    UNHEALTHY_PAY = "unhealthy_pay"  # Insalubridade
    COMMISSION = "commission"  # Comissão
    BONUS = "bonus"  # Bonificação
    VACATION = "vacation"  # Férias
    VACATION_BONUS = "vacation_bonus"  # 1/3 férias
    THIRTEENTH = "thirteenth"  # 13º salário
    THIRTEENTH_ADVANCE = "thirteenth_advance"  # Adiantamento 13º
    PROFIT_SHARING = "profit_sharing"  # PLR
    MEAL_ALLOWANCE = "meal_allowance"  # Vale refeição (provento)
    TRANSPORT_ALLOWANCE = "transport_allowance"  # Vale transporte (provento)
    OTHER_EARNING = "other_earning"  # Outros proventos

    # Descontos
    INSS = "inss"  # INSS funcionário
    IRRF = "irrf"  # Imposto de renda
    FGTS = "fgts"  # FGTS (informativo/patronal)
    MEAL_DISCOUNT = "meal_discount"  # Desconto VR
    TRANSPORT_DISCOUNT = "transport_discount"  # Desconto VT
    UNION_FEE = "union_fee"  # Contribuição sindical
    ADVANCE_DISCOUNT = "advance_discount"  # Desconto de adiantamento
    ABSENCE = "absence"  # Falta
    DELAY = "delay"  # Atraso
    BANK_HOURS_DEBIT = "bank_hours_debit"  # Débito banco de horas
    LOAN = "loan"  # Empréstimo consignado
    HEALTH_PLAN = "health_plan"  # Plano de saúde
    DENTAL_PLAN = "dental_plan"  # Plano odontológico
    LIFE_INSURANCE = "life_insurance"  # Seguro de vida
    PENSION = "pension"  # Previdência privada
    OTHER_DEDUCTION = "other_deduction"  # Outros descontos

    # Encargos patronais
    INSS_EMPLOYER = "inss_employer"  # INSS patronal
    FGTS_EMPLOYER = "fgts_employer"  # FGTS patronal
    RAT = "rat"  # RAT/SAT
    TERCEIROS = "terceiros"  # Terceiros (Sistema S)


class EventStatus(StrEnum):
    """Status do evento."""

    PENDING = "pending"  # Pendente de cálculo
    CALCULATED = "calculated"  # Calculado automaticamente
    MANUAL = "manual"  # Lançamento manual
    ADJUSTED = "adjusted"  # Ajustado manualmente
    CANCELLED = "cancelled"  # Cancelado
    EXPORTED = "exported"  # Exportado


# Rubricas padrão com códigos eSocial
DEFAULT_RUBRICAS = {
    EventCategory.SALARY: {"code": "1000", "name": "Salário Base", "esocial": "1000"},
    EventCategory.OVERTIME_50: {
        "code": "1050",
        "name": "Hora Extra 50%",
        "esocial": "1050",
    },
    EventCategory.OVERTIME_100: {
        "code": "1051",
        "name": "Hora Extra 100%",
        "esocial": "1051",
    },
    EventCategory.NIGHT_SHIFT: {
        "code": "1060",
        "name": "Adicional Noturno",
        "esocial": "1060",
    },
    EventCategory.INSS: {"code": "9201", "name": "INSS", "esocial": "9201"},
    EventCategory.IRRF: {"code": "9202", "name": "IRRF", "esocial": "9202"},
    EventCategory.FGTS: {"code": "9203", "name": "FGTS", "esocial": "9203"},
}


class PayrollEvent(Base):
    """Evento de folha de pagamento (rubrica)."""

    __tablename__ = "payroll_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condominio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )
    period_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payroll_periods.id"),
        nullable=False,
        index=True,
    )
    employee_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Identificação do evento
    event_code = Column(String(20), nullable=False)  # Código da rubrica
    event_name = Column(String(100), nullable=False)  # Nome da rubrica
    event_type = Column(String(20), nullable=False)  # earning, deduction, etc.
    event_category = Column(String(50), nullable=False)  # Categoria específica

    # Valores
    reference = Column(Numeric(10, 2), nullable=True)  # Referência (horas, dias, %)
    reference_unit = Column(String(20), nullable=True)  # hours, days, percentage
    base_value = Column(Numeric(15, 2), nullable=True)  # Valor base para cálculo
    rate = Column(Numeric(8, 4), nullable=True)  # Taxa/percentual
    value = Column(Numeric(15, 2), nullable=False, default=0)  # Valor final

    # Origem do cálculo
    source = Column(String(50), nullable=True)  # time_tracking, manual, import, etc.
    source_id = Column(UUID(as_uuid=True), nullable=True)  # ID do registro origem
    calculation_formula = Column(Text, nullable=True)  # Fórmula usada

    # Período específico do evento (pode diferir do período da folha)
    event_date = Column(Date, nullable=True)  # Data específica do evento
    event_start = Column(Date, nullable=True)
    event_end = Column(Date, nullable=True)

    # eSocial
    esocial_code = Column(String(20), nullable=True)  # Código eSocial
    esocial_incidences = Column(JSONB, default=dict)
    # {
    #   "inss": true,
    #   "irrf": true,
    #   "fgts": true,
    #   "fgts_13": false
    # }

    # Status e controle
    status = Column(String(20), nullable=False, default=EventStatus.PENDING.value)
    is_recurring = Column(Boolean, default=False)  # Evento recorrente
    is_proportional = Column(Boolean, default=False)  # Proporcional ao período

    # Histórico de ajustes
    original_value = Column(Numeric(15, 2), nullable=True)  # Valor antes de ajuste
    adjustment_reason = Column(Text, nullable=True)
    adjusted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    adjusted_at = Column(DateTime, nullable=True)

    # Observações
    notes = Column(Text, nullable=True)

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    period: "PayrollPeriod" = relationship(
        "PayrollPeriod",
        back_populates="events",
    )

    __table_args__ = (
        Index("ix_payroll_events_employee_period", "employee_id", "period_id"),
        Index("ix_payroll_events_category", "event_category"),
        Index("ix_payroll_events_type", "event_type"),
        Index("ix_payroll_events_code", "event_code"),
    )

    def __repr__(self) -> str:
        return f"<PayrollEvent {self.event_code} - {self.value}>"

    @property
    def is_earning(self) -> bool:
        """Verifica se é provento."""
        return self.event_type == EventType.EARNING.value

    @property
    def is_deduction(self) -> bool:
        """Verifica se é desconto."""
        return self.event_type == EventType.DEDUCTION.value

    @property
    def signed_value(self) -> Decimal:
        """Retorna valor com sinal (positivo para proventos, negativo para descontos)."""
        if self.is_deduction:
            return -abs(self.value)
        return abs(self.value)

    @property
    def has_inss_incidence(self) -> bool:
        """Verifica se incide INSS."""
        return self.esocial_incidences.get("inss", False)

    @property
    def has_irrf_incidence(self) -> bool:
        """Verifica se incide IRRF."""
        return self.esocial_incidences.get("irrf", False)

    @property
    def has_fgts_incidence(self) -> bool:
        """Verifica se incide FGTS."""
        return self.esocial_incidences.get("fgts", False)

    def adjust_value(
        self,
        new_value: Decimal,
        reason: str,
        user_id: uuid.UUID,
    ) -> None:
        """Ajusta o valor do evento."""
        self.original_value = self.value
        self.value = new_value
        self.adjustment_reason = reason
        self.adjusted_by = user_id
        self.adjusted_at = datetime.utcnow()
        self.status = EventStatus.ADJUSTED.value

    def cancel(self, reason: str, user_id: uuid.UUID) -> None:
        """Cancela o evento."""
        self.status = EventStatus.CANCELLED.value
        self.adjustment_reason = reason
        self.adjusted_by = user_id
        self.adjusted_at = datetime.utcnow()
        self.ativo = False

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "employee_id": str(self.employee_id),
            "period_id": str(self.period_id),
            "event_code": self.event_code,
            "event_name": self.event_name,
            "event_type": self.event_type,
            "event_category": self.event_category,
            "reference": float(self.reference) if self.reference else None,
            "reference_unit": self.reference_unit,
            "value": float(self.value),
            "status": self.status,
            "esocial_code": self.esocial_code,
        }
