"""
Controller de Rescisao e Ferias — CCT 2026.

Endpoints para validacao de rescisao, ferias proporcionais e 13o salario.
"""

import logging
from typing import Any

from fastapi import APIRouter

from core.auth.dependencies import CurrentActiveUser
from modules.cct.schemas.termination_schemas import (
    TerminationValidationRequest,
    ThirteenthSalaryRequest,
)
from modules.cct.services.termination_service import TerminationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rescisao", tags=["CCT — Rescisao e Ferias"])


@router.post("/validar")
async def validar_rescisao(
    data: TerminationValidationRequest,
    current_user: CurrentActiveUser,
) -> Any:
    """Valida rescisao conforme regras CCT (homologacao, prazos, multas)."""
    service = TerminationService()
    return service.validar_rescisao(
        employee_id=data.employee_id,
        data_admissao=data.data_admissao,
        data_demissao=data.data_demissao,
        salario_base=data.salario_base,
        motivo=data.motivo,
        aviso_previo_cumprido=data.aviso_previo_cumprido,
        dias_aviso_previo=data.dias_aviso_previo,
    )


@router.post("/decimo-terceiro")
async def calcular_decimo_terceiro(
    data: ThirteenthSalaryRequest,
    current_user: CurrentActiveUser,
) -> Any:
    """Calcula 13o salario conforme CCT (2a parcela ate 20/dez)."""
    service = TerminationService()
    return service.calcular_decimo_terceiro(
        salario_base=data.salario_base,
        meses_trabalhados=data.meses_trabalhados,
        adicionais_mensais=data.adicionais_mensais,
    )
