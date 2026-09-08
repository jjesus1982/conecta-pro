"""
Controller de Compliance — CCT 2026.

Endpoints para verificacao de conformidade geral e estabilidade.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.cct.schemas.compliance_schemas import (
    StabilityCheckRequest,
)
from modules.cct.services.compliance_service import ComplianceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["CCT — Compliance"])


@router.get("/resumo")
async def get_resumo_compliance(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    periodo: str = Query(..., description="Periodo YYYY-MM", pattern=r"^\d{4}-\d{2}$"),
    empresa_id: str | None = Query(None),
) -> Any:
    """Retorna resumo geral de compliance CCT."""
    service = ComplianceService(db)
    return await service.gerar_resumo_compliance(periodo, empresa_id)


@router.post("/estabilidade")
async def verificar_estabilidade(
    data: StabilityCheckRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Verifica estabilidade de um colaborador conforme CCT."""
    service = ComplianceService(db)
    return service.verificar_estabilidade(
        employee_id=data.employee_id,
        data_admissao=data.data_admissao,
        data_nascimento=data.data_nascimento,
        acidente_trabalho=data.acidente_trabalho,
        data_alta_inss=data.data_alta_inss,
        gestante=data.gestante,
        data_parto=data.data_parto,
    )
