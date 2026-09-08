"""
Controller de Jornada e Adicionais — CCT 2026.

Endpoints para jornadas, horas extras, adicional noturno e adicionais.
"""

import logging
from typing import Any

from fastapi import APIRouter

from core.auth.dependencies import CurrentActiveUser
from modules.cct.schemas.schedule_schemas import (
    AdicionaisCalculationRequest,
    NightShiftCalculationRequest,
    OvertimeCalculationRequest,
)
from modules.cct.services.schedule_service import ScheduleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jornadas", tags=["CCT — Jornadas e Adicionais"])


@router.get("/permitidas")
async def get_jornadas_permitidas(
    current_user: CurrentActiveUser,
) -> Any:
    """Retorna jornadas permitidas pela CCT 2026."""
    service = ScheduleService()
    return {"jornadas": service.get_jornadas_permitidas()}


@router.post("/hora-extra")
async def calcular_hora_extra(
    data: OvertimeCalculationRequest,
    current_user: CurrentActiveUser,
) -> Any:
    """Calcula horas extras conforme CCT (50% normal / 100% feriado)."""
    service = ScheduleService()
    return service.calcular_hora_extra(
        salario_base=data.salario_base,
        jornada_tipo=data.jornada_tipo,
        horas_extras_normais=data.horas_extras_normais,
        horas_extras_feriado=data.horas_extras_feriado,
        intrajornada_nao_concedida=data.intrajornada_nao_concedida,
    )


@router.post("/adicional-noturno")
async def calcular_adicional_noturno(
    data: NightShiftCalculationRequest,
    current_user: CurrentActiveUser,
) -> Any:
    """Calcula adicional noturno com hora reduzida (52min30s)."""
    service = ScheduleService()
    return service.calcular_adicional_noturno(
        salario_base=data.salario_base,
        jornada_tipo=data.jornada_tipo,
        horas_noturnas=data.horas_noturnas,
    )


@router.post("/adicionais")
async def calcular_adicionais(
    data: AdicionaisCalculationRequest,
    current_user: CurrentActiveUser,
) -> Any:
    """Calcula todos os adicionais aplicaveis conforme CCT."""
    service = ScheduleService()
    return service.calcular_adicionais(
        salario_base=data.salario_base,
        ronda_permanente=data.ronda_permanente,
        ronda_pre_2020=data.ronda_pre_2020,
        acumulo_funcao=data.acumulo_funcao,
        servicos_jardinagem_piscina=data.servicos_jardinagem_piscina,
        insalubridade=data.insalubridade,
        periculosidade=data.periculosidade,
    )
