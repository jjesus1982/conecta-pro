"""
Controller de Avaliacao 360 — persistente em banco.

Endpoints para gestao completa de ciclos de avaliacao 360:
criar ciclo, coletar respostas, calcular resultado, gerar relatorio.
"""

import asyncio
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.human_resources.publishers import (
    publish_avaliacao_360_criada,
    publish_avaliacao_360_iniciada,
)
from modules.people_management.human_resources.services.evaluation_360_service import (
    Evaluation360Service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluation-360", tags=["RH - Avaliacao 360"])


class CriarCicloRequest(BaseModel):
    """Request para criacao de ciclo 360."""

    employee_id: str = Field(..., description="ID do funcionario avaliado")
    employee_name: str = Field(..., description="Nome do funcionario")
    period_start: date = Field(..., description="Inicio do periodo avaliado")
    period_end: date = Field(..., description="Fim do periodo avaliado")
    custom_weights: dict[str, float] | None = Field(
        None,
        description="Pesos customizados por tipo de avaliador",
    )


class SubmitResponseRequest(BaseModel):
    """Request para submeter resposta de avaliacao."""

    evaluator_id: str = Field(..., description="ID do avaliador")
    evaluator_type: str = Field(
        ...,
        description="Tipo: self, manager, peer, subordinate, client",
    )
    evaluator_name: str = Field(..., description="Nome do avaliador")
    scores: dict[str, float] = Field(..., description="Notas por dimensao (0-10)")
    comments: dict[str, str] | None = Field(None, description="Comentarios por dimensao")


@router.post("/ciclos", status_code=201)
async def criar_ciclo(
    request: CriarCicloRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria um novo ciclo de avaliacao 360 para um funcionario."""
    service = Evaluation360Service(db)
    try:
        cycle = await service.create_cycle(
            employee_id=request.employee_id,
            employee_name=request.employee_name,
            period_start=request.period_start,
            period_end=request.period_end,
            custom_weights=request.custom_weights,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    asyncio.create_task(publish_avaliacao_360_criada(ciclo_id=str(cycle.id), employee_id=str(request.employee_id)))
    return {
        "id": str(cycle.id),
        "employee_name": cycle.employee_name,
        "status": cycle.status.value,
        "weights": cycle.weights,
    }


@router.post("/ciclos/{ciclo_id}/start", status_code=201)
async def iniciar_coleta(
    ciclo_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Inicia a fase de coleta de respostas do ciclo."""
    service = Evaluation360Service(db)
    try:
        cycle = await service.start_collecting(ciclo_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    asyncio.create_task(publish_avaliacao_360_iniciada(ciclo_id=str(cycle.id)))
    return {"id": str(cycle.id), "status": cycle.status.value}


class ResponderRequest(BaseModel):
    """Request para o avaliador LOGADO responder um ciclo 360."""

    evaluator_type: str = Field(
        ...,
        description="Tipo: self, manager, peer, subordinate, client",
    )
    scores: dict[str, float] = Field(..., description="Notas por dimensao (0-10)")
    comments: dict[str, str] | None = Field(None, description="Comentarios por dimensao")


def _evaluator_ids(current_user: Any) -> list[str]:
    """IDs pelos quais o usuario logado pode figurar como avaliador."""
    ids = [str(getattr(current_user, "id", "") or "")]
    emp = getattr(current_user, "employee_id", None)
    if emp:
        ids.append(str(emp))
    return [i for i in ids if i]


@router.get("/ciclos")
async def listar_ciclos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = Query(None, description="Filtrar por funcionario"),
) -> Any:
    """Lista ciclos de avaliacao 360."""
    service = Evaluation360Service(db)
    cycles = await service.list_cycles(employee_id=employee_id)
    return {"items": cycles, "total": len(cycles)}
