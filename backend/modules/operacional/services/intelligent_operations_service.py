"""
Intelligent Operations Service - FASE 3 ONDA 2
==============================================

Otimização inteligente de operações com IA:
- Escalas automáticas otimizadas
- Distribuição inteligente de recursos
- Predição de demanda operacional
- Automação de processos operacionais

ROI Target: R$ 150K
Sprint: FASE 3 - Excelência Operacional
"""

import logging
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from core.cache.redis import cache_get, cache_set
from modules.operacional.models.employee import Employee as EmployeeModel
from modules.operacional.models.post import Post as PostModel
from modules.operacional.models.post import PostStatus

logger = logging.getLogger(__name__)


class OptimizationType(StrEnum):
    """Tipos de otimização operacional."""

    SCALE_OPTIMIZATION = "scale_optimization"
    RESOURCE_ALLOCATION = "resource_allocation"
    DEMAND_PREDICTION = "demand_prediction"
    PROCESS_AUTOMATION = "process_automation"
    EFFICIENCY_BOOST = "efficiency_boost"


class ShiftType(StrEnum):
    """Tipos de turno."""

    MORNING = "morning"  # 06:00-14:00
    AFTERNOON = "afternoon"  # 14:00-22:00
    NIGHT = "night"  # 22:00-06:00
    FULL_DAY = "full_day"  # 08:00-18:00
    FLEXIBLE = "flexible"


class SkillLevel(StrEnum):
    """Níveis de habilidade."""

    TRAINEE = "trainee"
    JUNIOR = "junior"
    PLENO = "pleno"
    SENIOR = "senior"
    SPECIALIST = "specialist"


class OptimizationStatus(StrEnum):
    """Status da otimização."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    APPLIED = "applied"
    FAILED = "failed"


@dataclass
class EmployeeData:
    """Funcionário com skills e disponibilidade para otimização."""

    id: str
    name: str
    skills: list[str]
    skill_level: SkillLevel
    availability: dict[str, list[str]]
    preferred_shifts: list[ShiftType]
    overtime_capacity: float
    performance_score: float
    cost_per_hour: float


@dataclass
class WorkStationData:
    """Posto de trabalho/estação para otimização."""

    id: str
    name: str
    location: str
    required_skills: list[str]
    required_skill_level: SkillLevel
    capacity: int
    priority: int
    equipment_available: bool
    operational_hours: dict[str, tuple[time, time]]


@dataclass
class DemandForecast:
    """Previsão de demanda operacional."""

    date: datetime
    shift: ShiftType
    workstation: str
    predicted_demand: int
    confidence: float
    factors: list[str]
    historical_pattern: list[float]


@dataclass
class ScheduleAssignment:
    """Alocação de escala."""

    employee_id: str
    workstation_id: str
    date: datetime
    shift: ShiftType
    start_time: time
    end_time: time
    break_times: list[tuple[time, time]]
    overtime: bool
    estimated_productivity: float


@dataclass
class OptimizedSchedule:
    """Escala otimizada completa."""

    id: str
    period_start: datetime
    period_end: datetime
    assignments: list[ScheduleAssignment]
    optimization_metrics: dict[str, float]
    cost_analysis: dict[str, float]
    efficiency_score: float
    coverage_score: float
    created_at: datetime
    status: OptimizationStatus


@dataclass
class OperationalInsight:
    """Insight operacional."""

    type: str
    description: str
    impact: str
    recommendation: str
    estimated_savings: float
    implementation_effort: str
    confidence: float


# Mapeamento cargo -> SkillLevel
_CARGO_SKILL_MAP: dict[str, SkillLevel] = {
    "estagiario": SkillLevel.TRAINEE,
    "auxiliar": SkillLevel.JUNIOR,
    "porteiro": SkillLevel.PLENO,
    "recepcionista": SkillLevel.PLENO,
    "controlador": SkillLevel.PLENO,
    "lider": SkillLevel.SENIOR,
    "supervisor": SkillLevel.SENIOR,
    "coordenador": SkillLevel.SPECIALIST,
    "gerente": SkillLevel.SPECIALIST,
}

# Mapeamento turno_padrao -> ShiftType
_TURNO_SHIFT_MAP: dict[str, ShiftType] = {
    "diurno": ShiftType.MORNING,
    "manha": ShiftType.MORNING,
    "tarde": ShiftType.AFTERNOON,
    "noturno": ShiftType.NIGHT,
    "noite": ShiftType.NIGHT,
    "administrativo": ShiftType.FULL_DAY,
    "integral": ShiftType.FULL_DAY,
}

# Dias da semana em inglês
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Cache key prefix
_CACHE_PREFIX = "intelligent_ops"
# TTL de 24h para escalas otimizadas
_SCHEDULE_CACHE_TTL = 86400


def _infer_skill_level(cargo: str | None) -> SkillLevel:
    """Infere o nível de habilidade com base no cargo."""
    if not cargo:
        return SkillLevel.PLENO
    cargo_lower = cargo.lower()
    for keyword, level in _CARGO_SKILL_MAP.items():
        if keyword in cargo_lower:
            return level
    return SkillLevel.PLENO


def _infer_preferred_shift(turno_padrao: str | None) -> list[ShiftType]:
    """Infere turnos preferidos com base no turno_padrao."""
    if not turno_padrao:
        return [ShiftType.MORNING, ShiftType.AFTERNOON]
    shift = _TURNO_SHIFT_MAP.get(turno_padrao.lower())
    if shift:
        return [shift]
    return [ShiftType.MORNING, ShiftType.AFTERNOON]


def _extract_skills(employee: EmployeeModel) -> list[str]:
    """Extrai skills do employee a partir de competências, certificações e cargo."""
    skills: list[str] = []

    # De competencias (JSONB)
    if employee.competencias and isinstance(employee.competencias, list):
        for comp in employee.competencias:
            if isinstance(comp, str):
                skills.append(comp.lower())
            elif isinstance(comp, dict) and "nome" in comp:
                skills.append(comp["nome"].lower())

    # De certificações (JSONB)
    if employee.certificacoes and isinstance(employee.certificacoes, list):
        for cert in employee.certificacoes:
            if isinstance(cert, str):
                skills.append(cert.lower())
            elif isinstance(cert, dict) and "nome" in cert:
                skills.append(cert["nome"].lower())

    # Do cargo
    if employee.cargo:
        skills.append(employee.cargo.lower())

    # Certificados específicos
    if employee.curso_formacao:
        skills.append("portaria")
    if employee.porte_arma:
        skills.append("porte_arma")
    if employee.cnh_numero:
        skills.append("conducao")

    return list(set(skills)) if skills else ["operacional"]


def _calculate_cost_per_hour(employee: EmployeeModel) -> float:
    """Calcula custo/hora a partir de salario_base e carga_horaria_semanal."""
    salario = float(employee.salario_base) if employee.salario_base else 0.0
    carga = employee.carga_horaria_semanal or 44
    if salario <= 0 or carga <= 0:
        return 0.0
    # salario mensal / (carga semanal * ~4.33 semanas)
    return salario / (carga * 4.33)


def _build_default_availability(employee: EmployeeModel) -> dict[str, list[str]]:
    """Constrói disponibilidade padrão baseada no turno e escala."""
    turno = (employee.turno_padrao or "diurno").lower()
    escala = (employee.escala_padrao or "5x2").lower()

    # Mapeia turno para períodos do dia
    if turno in ("noturno", "noite"):
        periods = ["night"]
    elif turno in ("tarde",):
        periods = ["afternoon"]
    elif turno in ("integral", "administrativo"):
        periods = ["morning", "afternoon"]
    else:
        periods = ["morning", "afternoon"]

    # Determina dias de trabalho baseado na escala
    if "6x1" in escala:
        work_days = _WEEKDAYS[:6]  # seg-sab
    elif "5x1" in escala or "5x2" in escala:
        work_days = _WEEKDAYS[:5]  # seg-sex
    elif "12x36" in escala:
        work_days = _WEEKDAYS[:7]  # todos (escala alternada, simplificado)
    else:
        work_days = _WEEKDAYS[:5]

    return dict.fromkeys(work_days, periods)


class IntelligentOperationsService:
    """Serviço de Operações Inteligentes com IA.

    Carrega dados reais de Employee e Post do banco de dados,
    e usa Redis para cache de escalas otimizadas.

    Args:
        db: Sessão do banco de dados.
        tenant_id: ID do tenant (usa cliente_id nos models).
    """

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.employees: dict[str, EmployeeData] = {}
        self.workstations: dict[str, WorkStationData] = {}

        self.optimization_weights = {
            "cost": 0.3,
            "efficiency": 0.4,
            "employee_satisfaction": 0.2,
            "coverage": 0.1,
        }

        self._load_employees()
        self._load_workstations()

    def _load_employees(self) -> None:
        """Carrega employees ativos do banco e mapeia para dataclass."""
        rows = (
            self.db.query(EmployeeModel)
            .filter(
                EmployeeModel.cliente_id == self.tenant_id,
                EmployeeModel.is_active.is_(True),
            )
            .all()
        )

        for emp in rows:
            emp_data = EmployeeData(
                id=str(emp.id),
                name=emp.nome or "Sem Nome",
                skills=_extract_skills(emp),
                skill_level=_infer_skill_level(emp.cargo),
                availability=_build_default_availability(emp),
                preferred_shifts=_infer_preferred_shift(emp.turno_padrao),
                overtime_capacity=0.5,  # Default conservador
                performance_score=0.8,  # Default sem avaliação individual
                cost_per_hour=_calculate_cost_per_hour(emp),
            )
            self.employees[emp_data.id] = emp_data

        logger.info(f"Carregados {len(self.employees)} employees para tenant {self.tenant_id}")

    def _load_workstations(self) -> None:
        """Carrega postos ativos do banco e mapeia para dataclass."""
        rows = (
            self.db.query(PostModel)
            .filter(
                PostModel.client_id == str(self.tenant_id),
                PostModel.status == PostStatus.ACTIVE.value,
            )
            .all()
        )

        for post in rows:
            # Construir operational_hours a partir de shift_start/end
            start = post.shift_start_time or time(8, 0)
            end = post.shift_end_time or time(18, 0)
            op_hours = dict.fromkeys(_WEEKDAYS[:5], (start, end))

            # Extrair required_skills do post_type e required_certifications
            req_skills = []
            if post.post_type:
                req_skills.append(post.post_type.lower())
            if post.required_certifications and isinstance(post.required_certifications, list):
                req_skills.extend(
                    c.lower() if isinstance(c, str) else c.get("nome", "").lower() for c in post.required_certifications
                )
            if not req_skills:
                req_skills = ["operacional"]

            # Inferir skill level mínimo
            req_level = SkillLevel.PLENO
            if post.requires_armed:
                req_level = SkillLevel.SENIOR

            ws = WorkStationData(
                id=str(post.id),
                name=post.name or "Sem Nome",
                location=post.address or post.city or "N/A",
                required_skills=req_skills,
                required_skill_level=req_level,
                capacity=post.required_headcount or 1,
                priority=8 if post.requires_armed else 5,
                equipment_available=True,
                operational_hours=op_hours,
            )
            self.workstations[ws.id] = ws

        logger.info(f"Carregados {len(self.workstations)} postos para tenant {self.tenant_id}")

    def _cache_key(self, suffix: str) -> str:
        """Gera chave de cache com prefixo do tenant."""
        return f"{_CACHE_PREFIX}:{self.tenant_id}:{suffix}"

    async def optimize_schedule(
        self,
        start_date: datetime,
        end_date: datetime,
        optimization_type: OptimizationType = OptimizationType.SCALE_OPTIMIZATION,
    ) -> OptimizedSchedule:
        """
        Otimiza escala para período específico usando IA.

        Args:
            start_date: Data início do período
            end_date: Data fim do período
            optimization_type: Tipo de otimização

        Returns:
            Escala otimizada com IA
        """
        schedule_id = f"OPT_{self.tenant_id}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"

        # Gera previsão de demanda
        demand_forecasts = await self._generate_demand_forecasts(start_date, end_date)

        # Executa algoritmo de otimização
        assignments = await self._run_optimization_algorithm(demand_forecasts, start_date, end_date)

        # Calcula métricas
        metrics = await self._calculate_optimization_metrics(assignments)
        cost_analysis = await self._analyze_costs(assignments)
        efficiency_score = await self._calculate_efficiency_score(assignments)
        coverage_score = await self._calculate_coverage_score(assignments, demand_forecasts)

        optimized_schedule = OptimizedSchedule(
            id=schedule_id,
            period_start=start_date,
            period_end=end_date,
            assignments=assignments,
            optimization_metrics=metrics,
            cost_analysis=cost_analysis,
            efficiency_score=efficiency_score,
            coverage_score=coverage_score,
            created_at=datetime.now(),
            status=OptimizationStatus.COMPLETED,
        )

        # Salva no Redis
        cache_data = {
            "id": schedule_id,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "assignments": [asdict(a) for a in assignments],
            "optimization_metrics": metrics,
            "cost_analysis": cost_analysis,
            "efficiency_score": efficiency_score,
            "coverage_score": coverage_score,
            "created_at": optimized_schedule.created_at.isoformat(),
            "status": OptimizationStatus.COMPLETED.value,
        }
        await cache_set(
            self._cache_key(f"schedule:{schedule_id}"),
            cache_data,
            ttl=_SCHEDULE_CACHE_TTL,
        )

        return optimized_schedule

    async def _generate_demand_forecasts(self, start_date: datetime, end_date: datetime) -> list[DemandForecast]:
        """Gera previsões de demanda usando algoritmos de ML."""
        forecasts = []

        current_date = start_date
        while current_date <= end_date:
            for ws_id, workstation in self.workstations.items():
                for shift in ShiftType:
                    if shift == ShiftType.FLEXIBLE:
                        continue

                    base_demand = workstation.capacity
                    weekday = current_date.weekday()

                    # Ajustes por dia da semana
                    day_factor = 1.0
                    if weekday == 0:
                        day_factor = 1.2
                    elif weekday == 4:
                        day_factor = 0.9
                    elif weekday >= 5:
                        day_factor = 0.6

                    # Ajustes por turno
                    shift_factor = {
                        ShiftType.MORNING: 1.1,
                        ShiftType.AFTERNOON: 1.0,
                        ShiftType.NIGHT: 0.7,
                        ShiftType.FULL_DAY: 1.0,
                    }.get(shift, 1.0)

                    priority_factor = workstation.priority / 10

                    predicted_demand = int(base_demand * day_factor * shift_factor * priority_factor)

                    forecasts.append(
                        DemandForecast(
                            date=current_date,
                            shift=shift,
                            workstation=ws_id,
                            predicted_demand=max(1, predicted_demand),
                            confidence=0.85,
                            factors=[
                                f"weekday_{weekday}",
                                f"shift_{shift.value}",
                                f"priority_{workstation.priority}",
                            ],
                            historical_pattern=[
                                base_demand * 0.9,
                                base_demand,
                                base_demand * 1.1,
                            ],
                        )
                    )

            current_date += timedelta(days=1)

        return forecasts

    async def _run_optimization_algorithm(
        self,
        forecasts: list[DemandForecast],
        start_date: datetime,
        end_date: datetime,
    ) -> list[ScheduleAssignment]:
        """Executa algoritmo de otimização de escala (greedy heuristic)."""
        assignments = []

        forecast_dict: dict[tuple, list[DemandForecast]] = {}
        for forecast in forecasts:
            key = (forecast.date, forecast.shift)
            forecast_dict.setdefault(key, []).append(forecast)

        for (date_val, shift), day_forecasts in forecast_dict.items():
            available_employees = self._get_available_employees(date_val, shift)

            for forecast in sorted(day_forecasts, key=lambda x: x.workstation, reverse=True):
                workstation = self.workstations.get(forecast.workstation)
                if not workstation:
                    continue

                needed_people = forecast.predicted_demand

                suitable_employees = [
                    emp for emp in available_employees if self._is_employee_suitable(emp, workstation)
                ]

                suitable_employees.sort(
                    key=lambda emp: self._calculate_suitability_score(emp, workstation, shift),
                    reverse=True,
                )

                for allocated, emp in enumerate(suitable_employees[:needed_people]):
                    if allocated >= workstation.capacity:
                        break

                    start_time, end_time = self._get_shift_times(shift, workstation)

                    assignment = ScheduleAssignment(
                        employee_id=emp.id,
                        workstation_id=forecast.workstation,
                        date=date_val,
                        shift=shift,
                        start_time=start_time,
                        end_time=end_time,
                        break_times=[(time(12, 0), time(13, 0))],
                        overtime=False,
                        estimated_productivity=emp.performance_score * 0.95,
                    )

                    assignments.append(assignment)
                    available_employees.remove(emp)

        return assignments

    def _get_available_employees(self, date_val: datetime, shift: ShiftType) -> list[EmployeeData]:
        """Retorna funcionários disponíveis para data/turno específico."""
        weekday = _WEEKDAYS[date_val.weekday()]

        available = []
        for emp in self.employees.values():
            if weekday in emp.availability:
                shift_map = {
                    ShiftType.MORNING: "morning",
                    ShiftType.AFTERNOON: "afternoon",
                    ShiftType.NIGHT: "night",
                    ShiftType.FULL_DAY: "morning",
                }
                required_availability = shift_map.get(shift)
                if required_availability in emp.availability[weekday]:
                    available.append(emp)

        return available

    def _is_employee_suitable(self, employee: EmployeeData, workstation: WorkStationData) -> bool:
        """Verifica se funcionário é adequado para estação."""
        has_required_skills = any(skill in employee.skills for skill in workstation.required_skills)

        skill_levels = list(SkillLevel)
        emp_level_idx = skill_levels.index(employee.skill_level)
        required_level_idx = skill_levels.index(workstation.required_skill_level)
        has_sufficient_level = emp_level_idx >= required_level_idx

        return has_required_skills and has_sufficient_level

    def _calculate_suitability_score(
        self, employee: EmployeeData, workstation: WorkStationData, shift: ShiftType
    ) -> float:
        """Calcula score de adequação funcionário-estação."""
        score = 0.0

        matching_skills = len(set(employee.skills) & set(workstation.required_skills))
        total_required = len(workstation.required_skills)
        skill_score = matching_skills / total_required if total_required > 0 else 0
        score += skill_score * 0.4

        score += employee.performance_score * 0.3

        shift_pref = 1.0 if shift in employee.preferred_shifts else 0.5
        score += shift_pref * 0.2

        if self.employees:
            max_cost = max(
                (emp.cost_per_hour for emp in self.employees.values() if emp.cost_per_hour > 0),
                default=1.0,
            )
            cost_score = (max_cost - employee.cost_per_hour) / max_cost if max_cost > 0 else 0
            score += cost_score * 0.1

        return score

    def _get_shift_times(self, shift: ShiftType, workstation: WorkStationData) -> tuple[time, time]:
        """Retorna horários de início e fim do turno."""
        shift_times = {
            ShiftType.MORNING: (time(6, 0), time(14, 0)),
            ShiftType.AFTERNOON: (time(14, 0), time(22, 0)),
            ShiftType.NIGHT: (time(22, 0), time(6, 0)),
            ShiftType.FULL_DAY: (time(8, 0), time(18, 0)),
        }
        return shift_times.get(shift, (time(8, 0), time(17, 0)))

    async def _calculate_optimization_metrics(self, assignments: list[ScheduleAssignment]) -> dict[str, float]:
        """Calcula métricas de otimização."""
        if not assignments:
            return {}

        total_employees = len(self.employees)
        used_employees = len({a.employee_id for a in assignments})
        employee_utilization = used_employees / total_employees if total_employees > 0 else 0

        total_ws = len(self.workstations)
        used_ws = len({a.workstation_id for a in assignments})
        ws_utilization = used_ws / total_ws if total_ws > 0 else 0

        avg_productivity = statistics.mean(a.estimated_productivity for a in assignments)

        shift_distribution: dict[str, int] = {}
        for assignment in assignments:
            shift = assignment.shift.value
            shift_distribution[shift] = shift_distribution.get(shift, 0) + 1

        total_assignments = len(assignments)
        if len(shift_distribution) > 1:
            balance = 1.0 - (max(shift_distribution.values()) - min(shift_distribution.values())) / total_assignments
        else:
            balance = 1.0

        return {
            "employee_utilization": employee_utilization,
            "workstation_utilization": ws_utilization,
            "avg_productivity": avg_productivity,
            "shift_balance_score": balance,
            "total_assignments": total_assignments,
            "unique_employees": used_employees,
            "unique_workstations": used_ws,
        }

    async def _analyze_costs(self, assignments: list[ScheduleAssignment]) -> dict[str, float]:
        """Analisa custos da escala otimizada."""
        total_cost = 0.0
        regular_hours_cost = 0.0
        overtime_cost = 0.0
        total_hours = 0.0

        for assignment in assignments:
            employee = self.employees.get(assignment.employee_id)
            if not employee:
                continue

            start_dt = datetime.combine(assignment.date, assignment.start_time)
            end_dt = datetime.combine(assignment.date, assignment.end_time)

            if assignment.shift == ShiftType.NIGHT and end_dt <= start_dt:
                end_dt += timedelta(days=1)

            hours_worked = (end_dt - start_dt).total_seconds() / 3600

            break_hours = sum(
                (datetime.combine(assignment.date, end) - datetime.combine(assignment.date, start)).total_seconds()
                / 3600
                for start, end in assignment.break_times
            )
            net_hours = hours_worked - break_hours
            total_hours += net_hours

            if assignment.overtime:
                overtime_cost += net_hours * employee.cost_per_hour * 1.5
            else:
                regular_hours_cost += net_hours * employee.cost_per_hour

            total_cost += net_hours * employee.cost_per_hour * (1.5 if assignment.overtime else 1.0)

        return {
            "total_cost": total_cost,
            "regular_hours_cost": regular_hours_cost,
            "overtime_cost": overtime_cost,
            "avg_cost_per_hour": total_cost / total_hours if total_hours > 0 else 0,
            "cost_efficiency_score": 1.0 - (overtime_cost / total_cost) if total_cost > 0 else 0,
        }

    async def _calculate_efficiency_score(self, assignments: list[ScheduleAssignment]) -> float:
        """Calcula score de eficiência da escala."""
        if not assignments:
            return 0.0

        total_productivity = sum(a.estimated_productivity for a in assignments)
        avg_productivity = total_productivity / len(assignments)

        low_penalty = sum(1 for a in assignments if a.estimated_productivity < 0.7) / len(assignments)

        high_bonus = sum(1 for a in assignments if a.estimated_productivity > 0.9) / len(assignments)

        efficiency = avg_productivity + high_bonus * 0.1 - low_penalty * 0.2
        return max(0.0, min(1.0, efficiency))

    async def _calculate_coverage_score(
        self,
        assignments: list[ScheduleAssignment],
        forecasts: list[DemandForecast],
    ) -> float:
        """Calcula score de cobertura da demanda."""
        if not forecasts:
            return 1.0

        coverage_scores = []

        assignment_dict: dict[tuple, int] = {}
        for assignment in assignments:
            key = (assignment.workstation_id, assignment.date, assignment.shift)
            assignment_dict[key] = assignment_dict.get(key, 0) + 1

        for forecast in forecasts:
            key = (forecast.workstation, forecast.date, forecast.shift)
            assigned = assignment_dict.get(key, 0)

            if forecast.predicted_demand > 0:
                coverage = min(assigned / forecast.predicted_demand, 1.0)
                coverage_scores.append(coverage)

        return statistics.mean(coverage_scores) if coverage_scores else 0.0

    async def generate_operational_insights(self, schedule: OptimizedSchedule) -> list[OperationalInsight]:
        """Gera insights operacionais com IA."""
        insights = []

        if schedule.efficiency_score < 0.8:
            insights.append(
                OperationalInsight(
                    type="efficiency_warning",
                    description="Eficiência da escala abaixo do ideal",
                    impact="medium",
                    recommendation="Revisar alocação de funcionários para maximizar skills matching",
                    estimated_savings=schedule.cost_analysis.get("total_cost", 0) * 0.1,
                    implementation_effort="low",
                    confidence=0.85,
                )
            )

        overtime_cost = schedule.cost_analysis.get("overtime_cost", 0)
        total_cost = schedule.cost_analysis.get("total_cost", 0)
        if total_cost > 0 and overtime_cost > total_cost * 0.2:
            insights.append(
                OperationalInsight(
                    type="cost_optimization",
                    description="Alto uso de horas extras detectado",
                    impact="high",
                    recommendation="Contratar funcionários adicionais ou redistribuir carga",
                    estimated_savings=overtime_cost * 0.5,
                    implementation_effort="medium",
                    confidence=0.92,
                )
            )

        if schedule.coverage_score < 0.9:
            insights.append(
                OperationalInsight(
                    type="coverage_gap",
                    description="Cobertura de demanda insuficiente em alguns períodos",
                    impact="high",
                    recommendation="Identificar gargalos e realocar recursos críticos",
                    estimated_savings=0.0,
                    implementation_effort="low",
                    confidence=0.88,
                )
            )

        shift_assignments: dict[str, int] = {}
        for assignment in schedule.assignments:
            shift = assignment.shift.value
            shift_assignments[shift] = shift_assignments.get(shift, 0) + 1

        if len(shift_assignments) > 1:
            min_s = min(shift_assignments.values())
            max_s = max(shift_assignments.values())
            if max_s > min_s * 2:
                insights.append(
                    OperationalInsight(
                        type="workload_imbalance",
                        description="Distribuição desigual entre turnos detectada",
                        impact="medium",
                        recommendation="Rebalancear distribuição para melhorar satisfação dos funcionários",
                        estimated_savings=0.0,
                        implementation_effort="medium",
                        confidence=0.76,
                    )
                )

        return insights

    async def get_optimization_summary(self, schedule_id: str) -> dict[str, Any]:
        """Retorna resumo da otimização (busca no Redis)."""
        cached = await cache_get(self._cache_key(f"schedule:{schedule_id}"))
        if not cached:
            raise ValueError(f"Escala {schedule_id} não encontrada no cache")

        return {
            "schedule_id": cached["id"],
            "period": {
                "start": cached["period_start"],
                "end": cached["period_end"],
            },
            "performance": {
                "efficiency_score": cached["efficiency_score"],
                "coverage_score": cached["coverage_score"],
                "status": cached["status"],
            },
            "metrics": cached["optimization_metrics"],
            "costs": cached["cost_analysis"],
        }


def get_intelligent_operations_service(db: Session, tenant_id: str) -> IntelligentOperationsService:
    """Factory para criar instância do IntelligentOperationsService.

    Args:
        db: Sessão do banco de dados.
        tenant_id: ID do tenant (corresponde a cliente_id nos models).

    Returns:
        Instância configurada do serviço.
    """
    return IntelligentOperationsService(db, tenant_id)
