"""
Controller de Salarios — CCT 2026.

Endpoints para tabela salarial, validacao e reajuste.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.cct.schemas.salary_schemas import (
    SalaryAdjustmentRequest,
    SalaryValidationRequest,
)
from modules.cct.services.salary_service import SalaryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/salarios", tags=["CCT — Salarios"])


@router.get("/tabela")
async def get_tabela_salarial(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna tabela salarial completa da CCT 2026 (50 cargos)."""
    service = SalaryService(db)
    return service.get_tabela_salarial()


@router.post("/validar")
async def validar_salario(
    data: SalaryValidationRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Valida salario de um colaborador contra piso CCT."""
    service = SalaryService(db)
    return service.validar_salario(data.cargo, data.salario_atual)


@router.post("/reajuste")
async def calcular_reajuste(
    data: SalaryAdjustmentRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Calcula reajuste salarial CCT (7,1% piso / 4,5% acima do piso)."""
    service = SalaryService(db)
    return service.calcular_reajuste(data.salario_atual, data.cargo)


@router.post("/auditar")
async def auditar_salario(
    data: SalaryValidationRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Valida salario e registra auditoria no banco."""
    service = SalaryService(db)
    audit = await service.registrar_auditoria(
        employee_id=data.employee_id or "N/A",
        cargo=data.cargo,
        salario_atual=data.salario_atual,
        auditado_por=current_user.email if hasattr(current_user, "email") else None,
    )
    await db.commit()
    return {
        "id": audit.id,
        "employee_id": audit.employee_id,
        "cargo_cct": audit.cargo_cct,
        "piso_cct": float(audit.piso_cct),
        "salario_atual": float(audit.salario_atual),
        "conforme": audit.conforme,
        "diferenca": float(audit.diferenca),
    }


