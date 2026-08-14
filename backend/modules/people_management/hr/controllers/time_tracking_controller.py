"""
Controller de Controle de Ponto — Departamento Pessoal.

Re-exporta endpoints de ponto do módulo HR e adiciona endpoint
para registro via operações.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.publishers import publish_ponto_registrado
from modules.people_management.hr.services.time_tracking_service import (
    TimeTrackingService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/time-tracking", tags=["DP - Ponto"])

# O re-export do router de `hr/time_tracking` saiu daqui em 13/08/2026.
#
# Ele era incluído NESTE router, que já tem `prefix="/time-tracking"`, e o sub-router tem o
# mesmo prefixo — as 64 rotas nasciam em `/hr/time-tracking/time-tracking/...`. A nota que
# estava aqui dizia "Mantemos para compatibilidade"; medi com quem essa compatibilidade
# existia e a resposta foi NINGUÉM: 15 dias de access log (99.841 chamadas de API), zero
# ao caminho duplicado, e nenhuma página do front importa o SDK dessas rotas.
#
# Agora o sub-router é montado direto no aggregator (`people_management/hr/aggregator.py`),
# onde o `/hr` sozinho produz `/hr/time-tracking/...`. As 64 continuam existindo, com um
# caminho a menos. Este controller mantém só o que é dele: `/employee/{id}/entries` e
# `/from-operations` — conferido que nenhuma das duas colide com as 64.


class OperationsTimeEntry(BaseModel):
    """Schema para registro de ponto via operações."""

    employee_id: str
    shift_start: datetime
    shift_end: datetime
    location_id: str | None = None
    notes: str | None = None


@router.post(
    "/from-operations",
    summary="Registrar Ponto de Turno Operacional",
    status_code=201,
    description="Registra ponto automaticamente a partir de dados de turno do módulo operacional.",
)
async def register_from_operations(
    data: OperationsTimeEntry,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra ponto a partir de dados de turno operacional."""
    service = TimeTrackingService(db)
    result = await service.register_from_operations(
        employee_id=data.employee_id,
        shift_start=data.shift_start,
        shift_end=data.shift_end,
        location_id=data.location_id,
        notes=data.notes,
    )
    await db.commit()
    asyncio.create_task(
        publish_ponto_registrado(
            employee_id=str(data.employee_id),
            tipo="from_operations",
            record_id=str(getattr(result, "id", "")),
        )
    )
    return result


@router.get(
    "/employee/{employee_id}/entries",
    summary="Registros de Ponto do Funcionário",
    description="Retorna registros de ponto de um funcionário com filtro por período.",
)
async def get_employee_entries(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
) -> Any:
    """Lista registros de ponto de um funcionário."""
    service = TimeTrackingService(db)
    entries = await service.get_entries(employee_id, start_date=start_date, end_date=end_date)
    return {"items": entries, "total": len(entries)}
