"""Model para configuração de folha por funcionário."""

import uuid
from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.models import Base


class OvertimeRule(StrEnum):
    """Regra de horas extras."""

    PAY = "pay"  # Pagar horas extras
    BANK = "bank"  # Compensar em banco de horas
    HYBRID = "hybrid"  # Híbrido (até X horas banco, resto paga)
    NO_OVERTIME = "no_overtime"  # Sem horas extras (cargo de confiança)


class BankHoursPolicy(StrEnum):
    """Política de banco de horas."""

    MONTHLY = "monthly"  # Compensação mensal
    QUARTERLY = "quarterly"  # Compensação trimestral
    SEMIANNUAL = "semiannual"  # Compensação semestral
    ANNUAL = "annual"  # Compensação anual
    UNLIMITED = "unlimited"  # Sem prazo (acordo individual)


class ContractType(StrEnum):
    """Tipo de contrato."""

    CLT = "clt"  # CLT padrão
    CLT_INTERMITTENT = "clt_intermittent"  # CLT intermitente
    APPRENTICE = "apprentice"  # Aprendiz
    INTERN = "intern"  # Estagiário
    TEMPORARY = "temporary"  # Temporário
    OUTSOURCED = "outsourced"  # Terceirizado
    PJ = "pj"  # Pessoa Jurídica


class WorkScheduleType(StrEnum):
    """Tipo de escala de trabalho."""

    STANDARD = "standard"  # Padrão (seg-sex)
    SHIFT_12X36 = "shift_12x36"  # 12x36
    SHIFT_6X1 = "shift_6x1"  # 6x1
    SHIFT_5X2 = "shift_5x2"  # 5x2
    FLEXIBLE = "flexible"  # Horário flexível
    PART_TIME = "part_time"  # Meio período
    CUSTOM = "custom"  # Personalizado


# Tabelas do INSS 2024
INSS_TABLE_2024 = [
    {"min": 0, "max": 1412.00, "rate": 7.5, "deduction": 0},
    {"min": 1412.01, "max": 2666.68, "rate": 9.0, "deduction": 21.18},
    {"min": 2666.69, "max": 4000.03, "rate": 12.0, "deduction": 101.18},
    {"min": 4000.04, "max": 7786.02, "rate": 14.0, "deduction": 181.18},
]

INSS_CEILING_2024 = 7786.02
INSS_MAX_DISCOUNT_2024 = 908.85

# Tabela IRRF 2024
IRRF_TABLE_2024 = [
    {"min": 0, "max": 2259.20, "rate": 0, "deduction": 0},
    {"min": 2259.21, "max": 2826.65, "rate": 7.5, "deduction": 169.44},
    {"min": 2826.66, "max": 3751.05, "rate": 15.0, "deduction": 381.44},
    {"min": 3751.06, "max": 4664.68, "rate": 22.5, "deduction": 662.77},
    {"min": 4664.69, "max": float("inf"), "rate": 27.5, "deduction": 896.00},
]

IRRF_DEPENDENT_DEDUCTION_2024 = 189.59


def calculate_inss(gross_salary: Decimal, ceiling: float = INSS_CEILING_2024) -> Decimal:
    """
    Calcula INSS progressivo conforme tabela 2024.

    Args:
        gross_salary: Salário bruto
        ceiling: Teto do INSS (padrão: 2024)

    Returns:
        Valor do INSS a descontar
    """
    salary = min(float(gross_salary), ceiling)
    total_inss = Decimal("0")
    previous_max = 0

    for bracket in INSS_TABLE_2024:
        if salary <= bracket["min"]:
            break
        taxable = min(salary, bracket["max"]) - previous_max
        if taxable > 0:
            total_inss += Decimal(str(taxable)) * Decimal(str(bracket["rate"])) / 100
        previous_max = bracket["max"]

    return min(total_inss.quantize(Decimal("0.01")), Decimal(str(INSS_MAX_DISCOUNT_2024)))


def calculate_irrf(
    gross_salary: Decimal,
    dependents_or_inss: int | Decimal = 0,
    dependents: int | None = None,
) -> Decimal:
    """
    Calcula IRRF conforme tabela 2024.

    Suporta duas assinaturas:
    - calculate_irrf(gross_salary, dependents) - INSS assumido como 0
    - calculate_irrf(gross_salary, inss, dependents) - com INSS explícito

    Args:
        gross_salary: Salário bruto
        dependents_or_inss: Número de dependentes (int) ou valor do INSS (Decimal)
        dependents: Número de dependentes (quando segundo arg é INSS)

    Returns:
        Valor do IRRF a descontar
    """
    # Detectar assinatura usada
    if dependents is None:
        # Chamada: calculate_irrf(salary, dependents)
        inss_value = Decimal("0")
        num_dependents = int(dependents_or_inss) if isinstance(dependents_or_inss, int) else 0
    else:
        # Chamada: calculate_irrf(salary, inss, dependents)
        if isinstance(dependents_or_inss, Decimal):
            inss_value = dependents_or_inss
        else:
            inss_value = Decimal(str(dependents_or_inss))
        num_dependents = dependents

    # Base de cálculo
    base = float(gross_salary) - float(inss_value)
    base -= num_dependents * IRRF_DEPENDENT_DEDUCTION_2024

    if base <= 0:
        return Decimal("0")

    # Encontrar faixa
    for bracket in IRRF_TABLE_2024:
        if base <= bracket["max"]:
            irrf = (base * bracket["rate"] / 100) - bracket["deduction"]
            return max(Decimal("0"), Decimal(str(round(irrf, 2))))

    # Última faixa
    last = IRRF_TABLE_2024[-1]
    irrf = (base * last["rate"] / 100) - last["deduction"]
    return max(Decimal("0"), Decimal(str(round(irrf, 2))))


class EmployeePayrollConfig(Base):
    """Configuração de folha de pagamento por funcionário."""

    __tablename__ = "employee_payroll_configs"

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

    # Dados contratuais
    contract_type = Column(String(30), nullable=False, default=ContractType.CLT.value)
    admission_date = Column(Date, nullable=False)
    termination_date = Column(Date, nullable=True)
    experience_end_date = Column(Date, nullable=True)  # Fim experiência

    # Salário
    base_salary = Column(Numeric(15, 2), nullable=False)
    salary_type = Column(String(20), default="monthly")  # monthly, hourly, daily
    hourly_rate = Column(Numeric(10, 4), nullable=True)  # Calculado ou informado
    daily_rate = Column(Numeric(10, 2), nullable=True)

    # Jornada de trabalho
    work_schedule_type = Column(
        String(30),
        nullable=False,
        default=WorkScheduleType.STANDARD.value,
    )
    weekly_hours = Column(Numeric(5, 2), default=44.0)  # Horas semanais
    daily_hours = Column(Numeric(5, 2), default=8.0)  # Horas diárias
    monthly_hours = Column(Numeric(6, 2), default=220.0)  # Horas mensais

    # Horário padrão
    work_start = Column(Time, nullable=True)  # Entrada
    work_end = Column(Time, nullable=True)  # Saída
    lunch_start = Column(Time, nullable=True)  # Início almoço
    lunch_end = Column(Time, nullable=True)  # Fim almoço
    lunch_duration_minutes = Column(Integer, default=60)

    # Regras de horas extras
    overtime_rule = Column(String(20), nullable=False, default=OvertimeRule.PAY.value)
    overtime_rate_50 = Column(Numeric(5, 2), default=50.0)  # % adicional HE 50%
    overtime_rate_100 = Column(Numeric(5, 2), default=100.0)  # % adicional HE 100%
    overtime_threshold = Column(Numeric(5, 2), default=44.0)  # Limite semanal

    # Adicional noturno
    night_shift_rate = Column(Numeric(5, 2), default=20.0)  # % adicional noturno
    night_shift_start = Column(Time, default=time(22, 0))
    night_shift_end = Column(Time, default=time(5, 0))
    night_hour_reduction = Column(Boolean, default=True)  # 52min30s = 1 hora

    # Banco de horas
    bank_hours_enabled = Column(Boolean, default=False)
    bank_hours_policy = Column(
        String(20),
        nullable=True,
        default=BankHoursPolicy.SEMIANNUAL.value,
    )
    bank_hours_balance = Column(Numeric(10, 2), default=0)  # Saldo atual
    bank_hours_limit = Column(Numeric(10, 2), nullable=True)  # Limite máximo
    bank_hours_hybrid_threshold = Column(
        Numeric(10, 2),
        nullable=True,
    )  # Limite para híbrido

    # Adicionais
    hazard_pay_rate = Column(Numeric(5, 2), nullable=True)  # % periculosidade
    unhealthy_pay_rate = Column(Numeric(5, 2), nullable=True)  # % insalubridade
    unhealthy_pay_base = Column(
        String(20),
        nullable=True,
    )  # salary, minimum_wage

    # Benefícios e descontos fixos
    benefits = Column(JSONB, default=dict)
    # {
    #   "meal_allowance": {"value": 500, "discount_rate": 20},
    #   "transport_allowance": {"value": 300, "discount_rate": 6},
    #   "health_plan": {"value": 400, "type": "employee_only"},
    #   "dental_plan": {"value": 50},
    #   "life_insurance": {"value": 30}
    # }

    # Empréstimos consignados
    loans = Column(JSONB, default=list)
    # [{
    #   "id": "...",
    #   "bank": "Banco X",
    #   "contract": "123456",
    #   "installment_value": 500,
    #   "total_installments": 48,
    #   "paid_installments": 12,
    #   "start_date": "2024-01-01",
    #   "end_date": "2027-12-01"
    # }]

    # Pensão alimentícia
    alimony = Column(JSONB, default=list)
    # [{
    #   "beneficiary": "...",
    #   "type": "percentage",  # percentage, fixed
    #   "value": 30,
    #   "base": "net_salary",  # gross_salary, net_salary, specific_events
    #   "account": {...}
    # }]

    # Dependentes para IRRF
    dependents_count = Column(Integer, default=0)
    dependents = Column(JSONB, default=list)
    # [{
    #   "name": "...",
    #   "cpf": "...",
    #   "birth_date": "...",
    #   "relationship": "filho"
    # }]

    # Sindicato
    union_id = Column(String(50), nullable=True)
    union_contribution_enabled = Column(Boolean, default=False)
    union_contribution_type = Column(String(20), nullable=True)  # annual, monthly
    union_contribution_value = Column(Numeric(10, 2), nullable=True)

    # Configurações de cálculo
    calculation_config = Column(JSONB, default=dict)
    # {
    #   "round_hours": true,
    #   "round_precision": 5,  # minutos
    #   "tolerance_minutes": 10,
    #   "ignore_small_overtime": true,
    #   "small_overtime_threshold": 5
    # }

    # Códigos externos (para integrações)
    external_codes = Column(JSONB, default=dict)
    # {
    #   "esocial_matricula": "...",
    #   "totvs_chapa": "...",
    #   "senior_codigo": "..."
    # }

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "condominio_id",
            "employee_id",
            name="uq_employee_payroll_config",
        ),
        Index("ix_employee_payroll_config_contract", "contract_type"),
        Index("ix_employee_payroll_config_schedule", "work_schedule_type"),
    )

    def __repr__(self) -> str:
        return f"<EmployeePayrollConfig {self.employee_id}>"

    @property
    def calculated_hourly_rate(self) -> Decimal:
        """Calcula valor hora baseado no salário."""
        if self.hourly_rate:
            return self.hourly_rate
        if self.monthly_hours and self.monthly_hours > 0:
            return Decimal(str(self.base_salary)) / Decimal(str(self.monthly_hours))
        return Decimal("0")

    @property
    def overtime_50_rate(self) -> Decimal:
        """Valor da hora extra 50%."""
        return self.calculated_hourly_rate * Decimal("1.5")

    @property
    def overtime_100_rate(self) -> Decimal:
        """Valor da hora extra 100%."""
        return self.calculated_hourly_rate * Decimal("2.0")

    @property
    def night_shift_hourly_rate(self) -> Decimal:
        """Valor hora noturna."""
        rate = 1 + (Decimal(str(self.night_shift_rate)) / 100)
        return self.calculated_hourly_rate * rate

    @property
    def is_trust_position(self) -> bool:
        """Verifica se é cargo de confiança (sem HE)."""
        return self.overtime_rule == OvertimeRule.NO_OVERTIME.value

    @property
    def total_loans_installment(self) -> Decimal:
        """Total de parcelas de empréstimos."""
        if not self.loans:
            return Decimal("0")
        total = sum(
            Decimal(str(loan.get("installment_value", 0)))
            for loan in self.loans
            if loan.get("paid_installments", 0) < loan.get("total_installments", 0)
        )
        return total

    def calculate_inss(self, gross_salary: Decimal) -> Decimal:
        """Calcula INSS progressivo."""
        salary = min(float(gross_salary), INSS_CEILING_2024)
        total_inss = Decimal("0")
        previous_max = 0

        for bracket in INSS_TABLE_2024:
            if salary <= bracket["min"]:
                break
            taxable = min(salary, bracket["max"]) - previous_max
            if taxable > 0:
                total_inss += Decimal(str(taxable)) * Decimal(str(bracket["rate"])) / 100
            previous_max = bracket["max"]

        return min(total_inss, Decimal(str(INSS_MAX_DISCOUNT_2024)))

    def calculate_irrf(
        self,
        gross_salary: Decimal,
        inss: Decimal,
    ) -> Decimal:
        """Calcula IRRF."""
        # Base de cálculo
        base = float(gross_salary) - float(inss)
        base -= self.dependents_count * IRRF_DEPENDENT_DEDUCTION_2024

        if base <= 0:
            return Decimal("0")

        # Encontrar faixa
        for bracket in IRRF_TABLE_2024:
            if base <= bracket["max"]:
                irrf = (base * bracket["rate"] / 100) - bracket["deduction"]
                return max(Decimal("0"), Decimal(str(round(irrf, 2))))

        # Última faixa
        last = IRRF_TABLE_2024[-1]
        irrf = (base * last["rate"] / 100) - last["deduction"]
        return max(Decimal("0"), Decimal(str(round(irrf, 2))))

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "employee_id": str(self.employee_id),
            "contract_type": self.contract_type,
            "base_salary": float(self.base_salary),
            "weekly_hours": float(self.weekly_hours) if self.weekly_hours else None,
            "overtime_rule": self.overtime_rule,
            "bank_hours_enabled": self.bank_hours_enabled,
            "bank_hours_balance": (float(self.bank_hours_balance) if self.bank_hours_balance else 0),
            "dependents_count": self.dependents_count,
        }
