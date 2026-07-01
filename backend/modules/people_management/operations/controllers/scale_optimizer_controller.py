"""
Controller de Otimização de Escalas — Húngaro + Greedy.

Endpoints para otimizar alocação de colaboradores em postos
usando algoritmo Húngaro (scipy) com fallback greedy.
"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.auth.dependencies import CurrentActiveUser
from modules.people_management.operations.services.scale_optimizer_service import (
    HAS_SCIPY,
    ScaleOptimizerService,
)
from modules.people_management.operations.services.scale_optimizer_service import (
    Employee as OptEmployee,
)
from modules.people_management.operations.services.scale_optimizer_service import (
    Post as OptPost,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scale-optimizer", tags=["Operations - Otimização de Escalas"])


class EmployeeInput(BaseModel):
    """Dados do colaborador para alocação."""

    id: str
    name: str
    qualifications: list[str] = []
    preferred_shift: str | None = None
    max_hours_week: int = 44
    cost_per_hour: float = 0
    score: float = 5.0


class PostInput(BaseModel):
    """Dados do posto que precisa de cobertura."""

    id: str
    name: str
    required_qualifications: list[str] = []
    shift_type: str = "12h"
    shift_hours: int = 12
    priority: int = 1
    requires_armed: bool = False


class OtimizarRequest(BaseModel):
    """Request para otimização de escala."""

    target_date: date = Field(..., description="Data para otimizar")
    employees: list[EmployeeInput] = Field(..., description="Colaboradores disponíveis")
    posts: list[PostInput] = Field(..., description="Postos que precisam de cobertura")


class OtimizarMesRequest(BaseModel):
    """Request para otimização mensal."""

    year: int = Field(..., ge=2020, le=2030)
    month: int = Field(..., ge=1, le=12)
    employees: list[EmployeeInput] = Field(..., description="Colaboradores disponíveis")
    posts: list[PostInput] = Field(..., description="Postos")


@router.post("/otimizar", status_code=201)
async def otimizar_escala(
    request: OtimizarRequest,
    current_user: CurrentActiveUser,
) -> Any:
    """Otimiza alocação de colaboradores para uma data específica.

    Usa algoritmo Húngaro (scipy) se disponível, senão greedy.
    Respeita regras CLT: interjornada 11h, qualificações, custos.
    """
    employees = [
        OptEmployee(
            id=e.id,
            name=e.name,
            qualifications=e.qualifications,
            preferred_shift=e.preferred_shift,
            max_hours_week=e.max_hours_week,
            cost_per_hour=e.cost_per_hour,
            score=e.score,
        )
        for e in request.employees
    ]
    posts = [
        OptPost(
            id=p.id,
            name=p.name,
            required_qualifications=p.required_qualifications,
            shift_type=p.shift_type,
            shift_hours=p.shift_hours,
            priority=p.priority,
            requires_armed=p.requires_armed,
        )
        for p in request.posts
    ]

    svc = ScaleOptimizerService()
    return svc.optimize(request.target_date, employees, posts)


@router.post("/otimizar-mes", status_code=201)
async def otimizar_escala_mensal(
    request: OtimizarMesRequest,
    current_user: CurrentActiveUser,
) -> Any:
    """Otimiza escalas para um mês inteiro.

    Gera alocações diárias respeitando DSR e limites mensais.
    """
    employees = [
        OptEmployee(
            id=e.id,
            name=e.name,
            qualifications=e.qualifications,
            preferred_shift=e.preferred_shift,
            max_hours_week=e.max_hours_week,
            cost_per_hour=e.cost_per_hour,
            score=e.score,
        )
        for e in request.employees
    ]
    posts = [
        OptPost(
            id=p.id,
            name=p.name,
            required_qualifications=p.required_qualifications,
            shift_type=p.shift_type,
            shift_hours=p.shift_hours,
            priority=p.priority,
            requires_armed=p.requires_armed,
        )
        for p in request.posts
    ]

    svc = ScaleOptimizerService()
    return svc.optimize_month(request.year, request.month, employees, posts)


@router.get("/status")
async def status_otimizador(
    current_user: CurrentActiveUser,
) -> Any:
    """Retorna status do otimizador (scipy disponível, algoritmo em uso)."""
    return {
        "scipy_available": HAS_SCIPY,
        "algorithm": "hungarian" if HAS_SCIPY else "greedy",
        "clt_rules": {
            "min_interjornada_hours": 11,
            "max_horas_extras_mes": 44,
            "dsr_per_week": 1,
        },
    }
