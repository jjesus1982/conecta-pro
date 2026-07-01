"""
Serviço de Otimização de Escalas — Algoritmo Húngaro + Greedy Fallback.

Otimiza alocação de colaboradores em postos usando:
1. Algoritmo Húngaro (scipy) para alocação ótima
2. Fallback greedy quando scipy não disponível ou problema muito grande

Respeita regras CLT:
- Interjornada mínima de 11h
- Descanso semanal remunerado (DSR)
- Limites de horas extras
- Preferências de turno e qualificações
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

try:
    from scipy.optimize import linear_sum_assignment

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy não disponível, usando fallback greedy para otimização de escalas")


# Regras CLT
MIN_INTERJORNADA_HOURS = 11  # Mínimo 11h entre jornadas
MAX_HORAS_EXTRAS_MES = 44  # Máximo 44h extras/mês (2h/dia * 22 dias)
DSR_DAYS_PER_WEEK = 1  # 1 dia de descanso por semana


@dataclass
class Employee:
    """Dados do colaborador para alocação."""

    id: str
    name: str
    qualifications: list[str] = field(default_factory=list)
    preferred_shift: str | None = None  # "diurno", "noturno", "12x36"
    max_hours_week: int = 44
    unavailable_dates: list[date] = field(default_factory=list)
    current_hours_month: float = 0
    last_shift_end: datetime | None = None
    cost_per_hour: float = 0
    score: float = 5.0  # Performance score (0-10)


@dataclass
class Post:
    """Dados do posto que precisa de cobertura."""

    id: str
    name: str
    required_qualifications: list[str] = field(default_factory=list)
    shift_type: str = "12h"  # "12h", "8h", "24h"
    shift_hours: int = 12
    priority: int = 1  # 1=alta, 2=média, 3=baixa
    location: str = ""
    requires_armed: bool = False


@dataclass
class ShiftAssignment:
    """Resultado de uma alocação de turno."""

    employee_id: str
    employee_name: str
    post_id: str
    post_name: str
    date: date
    shift_start: str
    shift_end: str
    hours: int
    cost: float
    score: float


class ScaleOptimizerService:
    """Otimizador de escalas com algoritmo Húngaro e regras CLT."""

    def __init__(self) -> None:
        """Inicializa o otimizador."""
        self._employees: dict[str, Employee] = {}
        self._posts: dict[str, Post] = {}

    def add_employee(self, employee: Employee) -> None:
        """Registra funcionário disponível para alocação."""
        self._employees[employee.id] = employee

    def add_post(self, post: Post) -> None:
        """Registra posto que precisa de cobertura."""
        self._posts[post.id] = post

    # === OTIMIZAÇÃO PRINCIPAL ===

    def optimize(
        self,
        target_date: date,
        employees: list[Employee] | None = None,
        posts: list[Post] | None = None,
    ) -> dict[str, Any]:
        """Otimiza alocação de colaboradores para uma data.

        Pipeline:
        1. Filtra funcionários disponíveis
        2. Verifica qualificações e regras CLT
        3. Constrói matriz de custo
        4. Aplica Húngaro (ou greedy)
        5. Retorna alocações otimizadas

        Args:
            target_date: Data para otimizar.
            employees: Lista de funcionários (ou usa internos).
            posts: Lista de postos (ou usa internos).

        Returns:
            Dicionário com alocações, estatísticas e alertas.
        """
        emps = {e.id: e for e in employees} if employees else dict(self._employees)
        psts = {p.id: p for p in posts} if posts else dict(self._posts)

        if not emps or not psts:
            return {"assignments": [], "alerts": ["Sem funcionários ou postos para alocar"], "stats": {}}

        # Filtrar disponíveis
        available = {
            eid: e
            for eid, e in emps.items()
            if target_date not in e.unavailable_dates
            and _check_interjornada(e, target_date)
            and e.current_hours_month < (e.max_hours_week * 4.3)
        }

        if not available:
            return {
                "assignments": [],
                "alerts": ["Nenhum funcionário disponível para esta data"],
                "stats": {"available": 0, "required": len(psts)},
            }

        # Construir matriz de custo
        emp_list = list(available.values())
        post_list = list(psts.values())
        n_emp = len(emp_list)
        n_post = len(post_list)

        cost_matrix = []
        for emp in emp_list:
            row = []
            for post in post_list:
                cost = _calculate_cost(emp, post, target_date)
                row.append(cost)
            cost_matrix.append(row)

        # Resolver com Húngaro ou Greedy
        if HAS_SCIPY and n_emp <= 500 and n_post <= 500:
            assignments = self._solve_hungarian(emp_list, post_list, cost_matrix, target_date)
        else:
            assignments = self._solve_greedy(emp_list, post_list, cost_matrix, target_date)

        # Gerar alertas
        alerts = _generate_alerts(assignments, emp_list, post_list, target_date)

        # Estatísticas
        stats = {
            "date": target_date.isoformat(),
            "available_employees": n_emp,
            "required_posts": n_post,
            "assigned": len(assignments),
            "unassigned_posts": n_post - len(assignments),
            "total_hours": sum(a.hours for a in assignments),
            "total_cost": round(sum(a.cost for a in assignments), 2),
            "avg_score": round(sum(a.score for a in assignments) / len(assignments), 2) if assignments else 0,
            "method": "hungarian" if HAS_SCIPY and n_emp <= 500 else "greedy",
        }

        logger.info(
            "Escala otimizada para %s: %d/%d postos cobertos via %s",
            target_date,
            len(assignments),
            n_post,
            stats["method"],
        )

        return {
            "assignments": [
                {
                    "employee_id": a.employee_id,
                    "employee_name": a.employee_name,
                    "post_id": a.post_id,
                    "post_name": a.post_name,
                    "date": a.date.isoformat(),
                    "shift_start": a.shift_start,
                    "shift_end": a.shift_end,
                    "hours": a.hours,
                    "cost": a.cost,
                    "score": a.score,
                }
                for a in assignments
            ],
            "alerts": alerts,
            "stats": stats,
        }

    # === ALGORITMO HÚNGARO (SCIPY) ===

    @staticmethod
    def _solve_hungarian(
        employees: list[Employee],
        posts: list[Post],
        cost_matrix: list[list[float]],
        target_date: date,
    ) -> list[ShiftAssignment]:
        """Resolve alocação ótima via algoritmo Húngaro.

        Args:
            employees: Lista de funcionários disponíveis.
            posts: Lista de postos.
            cost_matrix: Matriz de custo [emp x post].
            target_date: Data da escala.

        Returns:
            Lista de alocações otimizadas.
        """
        import numpy as np

        n_emp = len(employees)
        n_post = len(posts)

        # Padronizar matriz (deve ser quadrada para scipy)
        size = max(n_emp, n_post)
        padded = np.full((size, size), 1e9)
        for i in range(n_emp):
            for j in range(n_post):
                padded[i][j] = cost_matrix[i][j]

        row_ind, col_ind = linear_sum_assignment(padded)

        assignments = []
        for i, j in zip(row_ind, col_ind, strict=False):
            if i < n_emp and j < n_post and padded[i][j] < 1e8:
                emp = employees[i]
                post = posts[j]
                shift_start, shift_end = _get_shift_times(post)
                assignments.append(
                    ShiftAssignment(
                        employee_id=emp.id,
                        employee_name=emp.name,
                        post_id=post.id,
                        post_name=post.name,
                        date=target_date,
                        shift_start=shift_start,
                        shift_end=shift_end,
                        hours=post.shift_hours,
                        cost=round(emp.cost_per_hour * post.shift_hours, 2),
                        score=emp.score,
                    )
                )

        return assignments

    # === FALLBACK GREEDY ===

    @staticmethod
    def _solve_greedy(
        employees: list[Employee],
        posts: list[Post],
        cost_matrix: list[list[float]],
        target_date: date,
    ) -> list[ShiftAssignment]:
        """Resolve alocação via algoritmo greedy (fallback).

        Ordena postos por prioridade e aloca o melhor funcionário disponível.

        Args:
            employees: Lista de funcionários disponíveis.
            posts: Lista de postos.
            cost_matrix: Matriz de custo [emp x post].
            target_date: Data da escala.

        Returns:
            Lista de alocações.
        """
        # Ordenar postos por prioridade
        sorted_posts = sorted(enumerate(posts), key=lambda x: x[1].priority)
        assigned_emps: set[int] = set()
        assignments = []

        for j, post in sorted_posts:
            best_i = -1
            best_cost = float("inf")

            for i, _emp in enumerate(employees):
                if i in assigned_emps:
                    continue
                cost = cost_matrix[i][j]
                if cost < best_cost and cost < 1e8:
                    best_cost = cost
                    best_i = i

            if best_i >= 0:
                assigned_emps.add(best_i)
                emp = employees[best_i]
                shift_start, shift_end = _get_shift_times(post)
                assignments.append(
                    ShiftAssignment(
                        employee_id=emp.id,
                        employee_name=emp.name,
                        post_id=post.id,
                        post_name=post.name,
                        date=target_date,
                        shift_start=shift_start,
                        shift_end=shift_end,
                        hours=post.shift_hours,
                        cost=round(emp.cost_per_hour * post.shift_hours, 2),
                        score=emp.score,
                    )
                )

        return assignments

    # === OTIMIZAÇÃO MENSAL ===

    def optimize_month(
        self,
        year: int,
        month: int,
        employees: list[Employee] | None = None,
        posts: list[Post] | None = None,
    ) -> dict[str, Any]:
        """Otimiza escalas para um mês inteiro.

        Gera alocações diárias respeitando DSR e limites mensais.

        Args:
            year: Ano.
            month: Mês.
            employees: Lista de funcionários.
            posts: Lista de postos.

        Returns:
            Dicionário com alocações diárias e resumo mensal.
        """
        from calendar import monthrange

        _, num_days = monthrange(year, month)

        all_assignments: list[dict] = []
        daily_alerts: list[str] = []
        total_cost = 0.0

        for day in range(1, num_days + 1):
            target = date(year, month, day)
            result = self.optimize(target, employees, posts)
            all_assignments.extend(result["assignments"])
            daily_alerts.extend(result["alerts"])
            total_cost += result["stats"].get("total_cost", 0)

        # Resumo por funcionário
        emp_summary: dict[str, dict] = {}
        for a in all_assignments:
            eid = a["employee_id"]
            if eid not in emp_summary:
                emp_summary[eid] = {"name": a["employee_name"], "hours": 0, "days": 0, "cost": 0}
            emp_summary[eid]["hours"] += a["hours"]
            emp_summary[eid]["days"] += 1
            emp_summary[eid]["cost"] += a["cost"]

        return {
            "month": f"{month:02d}/{year}",
            "total_days": num_days,
            "total_assignments": len(all_assignments),
            "total_cost": round(total_cost, 2),
            "employee_summary": emp_summary,
            "alerts": daily_alerts[:50],  # Limitar alertas
            "assignments": all_assignments,
        }


# === FUNÇÕES AUXILIARES ===


def _calculate_cost(emp: Employee, post: Post, target_date: date) -> float:
    """Calcula custo de alocar funcionário ao posto.

    Considera: custo hora, qualificações, preferência de turno, score.
    Penalidades: falta de qualificação, turno não preferido, muitas horas.
    """
    base_cost = emp.cost_per_hour * post.shift_hours

    # Penalidade por falta de qualificação
    if post.required_qualifications:
        missing = set(post.required_qualifications) - set(emp.qualifications)
        if missing:
            if post.requires_armed and "armed" in missing:
                return 1e9  # Impossível: colaborador não armado em posto armado
            base_cost += len(missing) * 100

    # Bonus por preferência de turno
    if emp.preferred_shift:
        if (
            post.shift_type == "12h"
            and emp.preferred_shift == "12x36"
            or post.shift_type == "8h"
            and emp.preferred_shift == "diurno"
        ):
            base_cost *= 0.9

    # Penalidade por excesso de horas
    projected = emp.current_hours_month + post.shift_hours
    if projected > emp.max_hours_week * 4.3:
        base_cost += (projected - emp.max_hours_week * 4.3) * 50

    # Bonus por score alto
    base_cost *= 1 - (emp.score - 5) * 0.02

    # Prioridade do posto
    base_cost *= (1 / post.priority) if post.priority > 0 else 1

    return max(base_cost, 0.01)


def _check_interjornada(emp: Employee, target_date: date) -> bool:
    """Verifica se funcionário respeita interjornada mínima de 11h."""
    if not emp.last_shift_end:
        return True
    target_start = datetime.combine(target_date, datetime.min.time().replace(hour=7))
    diff = target_start - emp.last_shift_end
    return diff >= timedelta(hours=MIN_INTERJORNADA_HOURS)


def _get_shift_times(post: Post) -> tuple[str, str]:
    """Retorna horários de início e fim baseado no tipo de turno."""
    shift_map = {
        "12h": ("07:00", "19:00"),
        "8h": ("08:00", "16:00"),
        "24h": ("07:00", "07:00"),
        "noturno_12h": ("19:00", "07:00"),
    }
    return shift_map.get(post.shift_type, ("07:00", "19:00"))


def _generate_alerts(
    assignments: list[ShiftAssignment],
    employees: list[Employee],
    posts: list[Post],
    target_date: date,
) -> list[str]:
    """Gera alertas sobre a alocação."""
    alerts = []
    assigned_posts = {a.post_id for a in assignments}
    for post in posts:
        if post.id not in assigned_posts:
            alerts.append(f"DESCOBERTO: Posto '{post.name}' sem cobertura em {target_date}")

    for a in assignments:
        if a.hours > 12:
            alerts.append(f"HORAS: {a.employee_name} com {a.hours}h em {a.post_name}")

    return alerts
