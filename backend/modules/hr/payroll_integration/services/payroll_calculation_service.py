"""Service para cálculo de folha de pagamento."""

import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.payroll_integration.models import (
    EmployeePayrollConfig,
    EventCategory,
    EventType,
    PayrollPeriod,
    PeriodStatus,
)
from modules.hr.payroll_integration.repositories import (
    EmployeePayrollConfigRepository,
    PayrollEventRepository,
    PayrollPeriodRepository,
)
from modules.hr.payroll_integration.schemas import (
    PeriodCalculationRequest,
    PeriodCalculationResponse,
    SalaryCalculationRequest,
    SalaryCalculationResponse,
)

logger = logging.getLogger(__name__)


class PayrollCalculationService:
    """Service para cálculo de folha de pagamento."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.period_repo = PayrollPeriodRepository(db)
        self.event_repo = PayrollEventRepository(db)
        self.config_repo = EmployeePayrollConfigRepository(db)

    async def calculate_period(  # pylint: disable=too-many-locals
        self,
        period_id: UUID,
        condominio_id: UUID,
        request: PeriodCalculationRequest,
        *,
        user_id: UUID = None,
    ) -> PeriodCalculationResponse:
        """Calcula folha de pagamento do período."""
        started_at = datetime.utcnow()

        period = await self.period_repo.get_by_id(period_id)
        if not period:
            raise ValueError("Período não encontrado")

        if not period.can_calculate:
            raise ValueError(f"Período não pode ser calculado (status: {period.status})")

        # Atualizar status
        await self.period_repo.update_status(period_id, PeriodStatus.CALCULATING)

        # Buscar funcionários
        if request.employee_ids:
            employees = []
            for emp_id in request.employee_ids:
                config = await self.config_repo.get_by_employee(emp_id, condominio_id)
                if config:
                    employees.append(config)
        else:
            employees = await self.config_repo.get_active_employees(condominio_id)

        results = {
            "calculated": 0,
            "errors": [],
            "warnings": [],
            "total_events": 0,
            "new_events": 0,
            "updated_events": 0,
            "totals": {
                "earnings": Decimal("0"),
                "deductions": Decimal("0"),
                "net": Decimal("0"),
                "employer_cost": Decimal("0"),
            },
        }

        for employee in employees:
            try:
                # Limpar eventos existentes se recalculando
                if request.recalculate_all:
                    await self.event_repo.delete_by_period(period_id, employee_id=employee.employee_id)

                # Calcular eventos
                events = await self._calculate_employee_payroll(
                    employee=employee,
                    period=period,
                    condominio_id=condominio_id,
                )

                # Criar eventos
                for event_data in events:
                    await self.event_repo.create(
                        event_data,
                        condominio_id,
                        created_by=user_id,
                    )
                    results["new_events"] += 1

                results["calculated"] += 1
                results["total_events"] += len(events)

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(
                    "Erro ao calcular folha do funcionario %s: %s",
                    employee.employee_id,
                    e,
                )
                results["errors"].append(
                    {
                        "employee_id": str(employee.employee_id),
                        "error": str(e),
                    }
                )

        # Calcular totais do período
        totals = await self.event_repo.get_period_totals(period_id)
        results["totals"]["earnings"] = totals["total_earnings"]
        results["totals"]["deductions"] = totals["total_deductions"]
        results["totals"]["net"] = totals["total_net"]

        # Atualizar período
        await self.period_repo.update_totals(
            period_id,
            {
                "total_employees": totals["total_employees"],
                "total_earnings": totals["total_earnings"],
                "total_deductions": totals["total_deductions"],
                "total_net": totals["total_net"],
            },
        )

        await self.period_repo.update_status(period_id, PeriodStatus.CALCULATED)

        completed_at = datetime.utcnow()
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        return PeriodCalculationResponse(
            period_id=period_id,
            status="success" if not results["errors"] else "partial",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            total_employees=len(employees),
            calculated_employees=results["calculated"],
            total_events=results["total_events"],
            new_events=results["new_events"],
            updated_events=results["updated_events"],
            errors=results["errors"],
            warnings=results["warnings"],
            totals={
                "earnings": float(results["totals"]["earnings"]),
                "deductions": float(results["totals"]["deductions"]),
                "net": float(results["totals"]["net"]),
            },
        )

    async def _calculate_employee_payroll(
        self,
        employee: EmployeePayrollConfig,
        period: PayrollPeriod,
        condominio_id: UUID,  # pylint: disable=unused-argument
    ) -> list[dict[str, Any]]:
        """Calcula folha de um funcionário."""
        events = []

        # 1. Salário base
        salary_event = self._create_salary_event(employee, period)
        events.append(salary_event)

        # 2. Buscar dados de ponto (simulado)
        time_data = await self._get_time_tracking_data(
            employee.employee_id,
            period.start_date,
            period.end_date,
        )

        # 3. Horas extras
        if time_data["overtime_50"] > 0:
            events.append(self._create_overtime_event(employee, period, time_data["overtime_50"], 50))
        if time_data["overtime_100"] > 0:
            events.append(self._create_overtime_event(employee, period, time_data["overtime_100"], 100))

        # 4. Adicional noturno
        if time_data["night_hours"] > 0:
            events.append(self._create_night_shift_event(employee, period, time_data["night_hours"]))

        # 5. Faltas
        if time_data["absence_hours"] > 0:
            events.append(self._create_absence_event(employee, period, time_data["absence_hours"]))

        # 6. Calcular totais para impostos
        total_earnings = sum(Decimal(str(e["value"])) for e in events if e["event_type"] == EventType.EARNING)

        # 7. INSS
        inss_value = employee.calculate_inss(total_earnings)
        events.append(self._create_inss_event(employee, period, inss_value, total_earnings))

        # 8. IRRF
        irrf_value = employee.calculate_irrf(total_earnings, inss_value)
        if irrf_value > 0:
            events.append(self._create_irrf_event(employee, period, irrf_value, total_earnings - inss_value))

        # 9. Benefícios
        benefit_events = self._create_benefit_events(employee, period)
        events.extend(benefit_events)

        # 10. Empréstimos
        loan_events = self._create_loan_events(employee, period)
        events.extend(loan_events)

        return events

    def _create_salary_event(
        self,
        employee: EmployeePayrollConfig,
        period: PayrollPeriod,
    ) -> dict[str, Any]:
        """Cria evento de salario base."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.payroll_integration.schemas import PayrollEventCreate

        return PayrollEventCreate(
            employee_id=employee.employee_id,
            period_id=period.id,
            event_code="1000",
            event_name="Salário Base",
            event_type=EventType.EARNING,
            event_category=EventCategory.SALARY,
            reference=Decimal("30"),
            reference_unit="days",
            base_value=employee.base_salary,
            value=employee.base_salary,
            source="calculation",
            esocial_code="1000",
            esocial_incidences={"inss": True, "irrf": True, "fgts": True},
        )

    def _create_overtime_event(
        self,
        employee: EmployeePayrollConfig,
        period: PayrollPeriod,
        hours: Decimal,
        rate: int,
    ) -> dict[str, Any]:
        """Cria evento de hora extra."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.payroll_integration.schemas import PayrollEventCreate

        multiplier = Decimal("1.5") if rate == 50 else Decimal("2.0")
        value = hours * employee.calculated_hourly_rate * multiplier

        category = EventCategory.OVERTIME_50 if rate == 50 else EventCategory.OVERTIME_100
        code = "1050" if rate == 50 else "1051"
        name = f"Hora Extra {rate}%"

        return PayrollEventCreate(
            employee_id=employee.employee_id,
            period_id=period.id,
            event_code=code,
            event_name=name,
            event_type=EventType.EARNING,
            event_category=category,
            reference=hours,
            reference_unit="hours",
            base_value=employee.calculated_hourly_rate,
            rate=Decimal(str(rate)),
            value=value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            source="time_tracking",
            esocial_code=code,
            esocial_incidences={"inss": True, "irrf": True, "fgts": True},
        )

    def _create_night_shift_event(
        self,
        employee: EmployeePayrollConfig,
        period: PayrollPeriod,
        hours: Decimal,
    ) -> dict[str, Any]:
        """Cria evento de adicional noturno."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.payroll_integration.schemas import PayrollEventCreate

        rate = employee.night_shift_rate
        value = hours * employee.calculated_hourly_rate * (rate / 100)

        return PayrollEventCreate(
            employee_id=employee.employee_id,
            period_id=period.id,
            event_code="1060",
            event_name="Adicional Noturno",
            event_type=EventType.EARNING,
            event_category=EventCategory.NIGHT_SHIFT,
            reference=hours,
            reference_unit="hours",
            base_value=employee.calculated_hourly_rate,
            rate=rate,
            value=value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            source="time_tracking",
            esocial_code="1060",
            esocial_incidences={"inss": True, "irrf": True, "fgts": True},
        )

    def _create_absence_event(
        self,
        employee: EmployeePayrollConfig,
        period: PayrollPeriod,
        hours: Decimal,
    ) -> dict[str, Any]:
        """Cria evento de falta."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.payroll_integration.schemas import PayrollEventCreate

        value = hours * employee.calculated_hourly_rate

        return PayrollEventCreate(
            employee_id=employee.employee_id,
            period_id=period.id,
            event_code="9100",
            event_name="Faltas",
            event_type=EventType.DEDUCTION,
            event_category=EventCategory.ABSENCE,
            reference=hours,
            reference_unit="hours",
            base_value=employee.calculated_hourly_rate,
            value=value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            source="time_tracking",
            esocial_code="9100",
            esocial_incidences={"inss": False, "irrf": False, "fgts": False},
        )

    def _create_inss_event(
        self,
        employee: EmployeePayrollConfig,
        period: PayrollPeriod,
        value: Decimal,
        base: Decimal,
    ) -> dict[str, Any]:
        """Cria evento de INSS."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.payroll_integration.schemas import PayrollEventCreate

        return PayrollEventCreate(
            employee_id=employee.employee_id,
            period_id=period.id,
            event_code="9201",
            event_name="INSS",
            event_type=EventType.DEDUCTION,
            event_category=EventCategory.INSS,
            base_value=base,
            value=value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            source="calculation",
            esocial_code="9201",
            esocial_incidences={"inss": False, "irrf": False, "fgts": False},
        )

    def _create_irrf_event(
        self,
        employee: EmployeePayrollConfig,
        period: PayrollPeriod,
        value: Decimal,
        base: Decimal,
    ) -> dict[str, Any]:
        """Cria evento de IRRF."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.payroll_integration.schemas import PayrollEventCreate

        return PayrollEventCreate(
            employee_id=employee.employee_id,
            period_id=period.id,
            event_code="9202",
            event_name="IRRF",
            event_type=EventType.DEDUCTION,
            event_category=EventCategory.IRRF,
            base_value=base,
            value=value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            source="calculation",
            esocial_code="9202",
            esocial_incidences={"inss": False, "irrf": False, "fgts": False},
        )

    def _create_benefit_events(
        self,
        employee: EmployeePayrollConfig,
        period: PayrollPeriod,
    ) -> list[dict[str, Any]]:
        """Cria eventos de beneficios."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.payroll_integration.schemas import PayrollEventCreate

        events = []
        benefits = employee.benefits or {}

        benefit_config = {
            "meal_allowance": ("2100", "Vale Refeição", "2100D", "Desc. Vale Refeição"),
            "transport_allowance": ("2200", "Vale Transporte", "2200D", "Desc. Vale Transporte"),
            "health_plan": (None, None, "9300", "Plano de Saúde"),
            "dental_plan": (None, None, "9301", "Plano Odontológico"),
        }

        for benefit_type, config in benefit_config.items():
            if benefit_type not in benefits:
                continue

            benefit = benefits[benefit_type]
            value = Decimal(str(benefit.get("value", 0)))
            discount_rate = Decimal(str(benefit.get("discount_rate", 0)))

            # Provento (se aplicável)
            if config[0] and value > 0:
                events.append(
                    PayrollEventCreate(
                        employee_id=employee.employee_id,
                        period_id=period.id,
                        event_code=config[0],
                        event_name=config[1],
                        event_type=EventType.EARNING,
                        event_category=EventCategory.MEAL_ALLOWANCE,
                        value=value,
                        source="benefits",
                        esocial_incidences={"inss": False, "irrf": False, "fgts": False},
                    )
                )

            # Desconto
            if config[2]:
                if discount_rate > 0:
                    discount_value = value * (discount_rate / 100)
                else:
                    discount_value = value

                if discount_value > 0:
                    events.append(
                        PayrollEventCreate(
                            employee_id=employee.employee_id,
                            period_id=period.id,
                            event_code=config[2],
                            event_name=config[3],
                            event_type=EventType.DEDUCTION,
                            event_category=EventCategory.MEAL_DISCOUNT,
                            base_value=value,
                            rate=discount_rate,
                            value=discount_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                            source="benefits",
                            esocial_incidences={"inss": False, "irrf": False, "fgts": False},
                        )
                    )

        return events

    def _create_loan_events(
        self,
        employee: EmployeePayrollConfig,
        period: PayrollPeriod,
    ) -> list[dict[str, Any]]:
        """Cria eventos de emprestimos."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.payroll_integration.schemas import PayrollEventCreate

        events = []
        loans = employee.loans or []

        for i, loan in enumerate(loans):
            paid = loan.get("paid_installments", 0)
            total = loan.get("total_installments", 0)

            if paid >= total:
                continue

            value = Decimal(str(loan.get("installment_value", 0)))
            if value > 0:
                events.append(
                    PayrollEventCreate(
                        employee_id=employee.employee_id,
                        period_id=period.id,
                        event_code=f"9400{i + 1}",
                        event_name=f"Empréstimo {loan.get('bank', '')}",
                        event_type=EventType.DEDUCTION,
                        event_category=EventCategory.LOAN,
                        reference=Decimal(str(paid + 1)),
                        reference_unit="installment",
                        value=value,
                        source="loans",
                        notes=f"Parcela {paid + 1}/{total}",
                        esocial_incidences={"inss": False, "irrf": False, "fgts": False},
                    )
                )

        return events

    async def _get_time_tracking_data(
        self,
        employee_id: UUID,  # pylint: disable=unused-argument
        start_date,  # pylint: disable=unused-argument
        end_date,  # pylint: disable=unused-argument
    ) -> dict[str, Decimal]:
        """Busca dados de ponto (simulado)."""
        # Em producao, consultaria o modulo time_tracking
        # pylint: disable=import-outside-toplevel
        import random

        return {
            "regular_hours": Decimal(str(random.randint(160, 180))),  # noqa: S311
            "overtime_50": Decimal(str(random.randint(0, 20))),  # noqa: S311
            "overtime_100": Decimal(str(random.randint(0, 8))),  # noqa: S311
            "night_hours": Decimal(str(random.randint(0, 40))),  # noqa: S311
            "absence_hours": Decimal(str(random.randint(0, 16))),  # noqa: S311
            "late_hours": Decimal(str(random.randint(0, 4))),  # noqa: S311
        }

    async def calculate_salary_preview(  # pylint: disable=too-many-locals
        self,
        request: SalaryCalculationRequest,
        employee_config: EmployeePayrollConfig,
    ) -> SalaryCalculationResponse:
        """Calcula preview de salário."""
        # Salário base
        gross = request.gross_salary

        # Horas extras
        hourly_rate = employee_config.calculated_hourly_rate
        overtime_50_value = request.overtime_hours_50 * hourly_rate * Decimal("1.5")
        overtime_100_value = request.overtime_hours_100 * hourly_rate * Decimal("2.0")

        # Adicional noturno
        night_rate = employee_config.night_shift_rate / 100
        night_value = request.night_hours * hourly_rate * night_rate

        # Faltas
        absence_value = request.absence_hours * hourly_rate

        # Total de proventos
        total_earnings = gross + overtime_50_value + overtime_100_value + night_value

        # INSS
        inss = employee_config.calculate_inss(total_earnings)
        inss_base = min(total_earnings, Decimal("7786.02"))

        # IRRF
        irrf = employee_config.calculate_irrf(total_earnings, inss)
        irrf_base = total_earnings - inss - (request.dependents_count * Decimal("189.59"))

        # FGTS (informativo)
        fgts = total_earnings * Decimal("0.08")

        # Total descontos
        total_deductions = inss + irrf + absence_value

        # Líquido
        net_salary = total_earnings - total_deductions

        # Custo empregador
        employer_cost = total_earnings + fgts + (total_earnings * Decimal("0.28"))

        return SalaryCalculationResponse(
            gross_salary=gross,
            overtime_50_value=overtime_50_value.quantize(Decimal("0.01")),
            overtime_100_value=overtime_100_value.quantize(Decimal("0.01")),
            night_shift_value=night_value.quantize(Decimal("0.01")),
            absence_deduction=absence_value.quantize(Decimal("0.01")),
            total_earnings=total_earnings.quantize(Decimal("0.01")),
            inss=inss.quantize(Decimal("0.01")),
            inss_base=inss_base.quantize(Decimal("0.01")),
            irrf=irrf.quantize(Decimal("0.01")),
            irrf_base=max(Decimal("0"), irrf_base).quantize(Decimal("0.01")),
            fgts=fgts.quantize(Decimal("0.01")),
            total_deductions=total_deductions.quantize(Decimal("0.01")),
            net_salary=net_salary.quantize(Decimal("0.01")),
            employer_cost=employer_cost.quantize(Decimal("0.01")),
            breakdown={
                "earnings": {
                    "salary": float(gross),
                    "overtime_50": float(overtime_50_value),
                    "overtime_100": float(overtime_100_value),
                    "night_shift": float(night_value),
                },
                "deductions": {
                    "inss": float(inss),
                    "irrf": float(irrf),
                    "absence": float(absence_value),
                },
            },
        )

    # === Period delegation methods ===

    async def list_periods(self, **kwargs):
        """Lista períodos de folha via query direta."""
        from sqlalchemy import text as sql_text

        page = kwargs.get("page", 1) or 1
        page_size = kwargs.get("page_size", 20) or 20
        offset = (page - 1) * page_size

        count_result = await self.db.execute(sql_text("SELECT COUNT(*) FROM hr_payroll_periods WHERE ativo = true"))
        total = count_result.scalar() or 0

        result = await self.db.execute(
            sql_text(
                "SELECT * FROM hr_payroll_periods WHERE ativo = true ORDER BY start_date DESC LIMIT :lim OFFSET :off"
            ),
            {"lim": page_size, "off": offset},
        )
        rows = result.mappings().all()
        return rows, total

    async def get_current_period(self, condominio_id=None):
        """Busca período atual delegando ao repositório."""
        return await self.period_repo.get_current_period(condominio_id)

    async def create_period(self, data, created_by=None):
        """Cria período delegando ao repositório."""
        return await self.period_repo.create(data, created_by)

    async def get_period(self, period_id, condominio_id=None):
        """Busca período por ID."""
        # get_by_id(period_id, *, include_events) NÃO aceita condominio_id posicional
        # (dava 'takes 2 positional but 3 given'); o id já é UUID único → filtro redundante.
        return await self.period_repo.get_by_id(period_id)

    async def update_period(self, period_id, data, condominio_id=None):
        """Atualiza período."""
        return await self.period_repo.update(period_id, data, condominio_id)

    async def delete_period(self, period_id):
        """Remove período."""
        return await self.period_repo.delete(period_id)

    # Lifecycle do período (estavam sendo chamados pelo controller mas NÃO existiam →
    # 500). Usam o update_status dedicado do repo (carimba datas de aprovação/fechamento).
    async def approve_period(self, period_id, user_id=None):
        """Aprova o período (status=approved)."""
        from modules.hr.payroll_integration.models import PeriodStatus

        p = await self.period_repo.update_status(period_id, PeriodStatus.APPROVED, user_id=user_id)
        if p is None:
            raise ValueError("Período não encontrado")
        return p

    async def close_period(self, period_id, user_id=None):
        """Fecha o período (status=closed)."""
        from modules.hr.payroll_integration.models import PeriodStatus

        p = await self.period_repo.update_status(period_id, PeriodStatus.CLOSED, user_id=user_id)
        if p is None:
            raise ValueError("Período não encontrado")
        return p

    async def reopen_period(self, period_id, user_id=None):
        """Reabre o período (status=open)."""
        from modules.hr.payroll_integration.models import PeriodStatus

        p = await self.period_repo.update_status(period_id, PeriodStatus.OPEN, user_id=user_id)
        if p is None:
            raise ValueError("Período não encontrado")
        return p
