"""Hub Jurídico + Prazos/Compliance — endpoints consolidados.

Painel do escritório jurídico (agrega contratos, consultas IA, pareceres,
análises, prazos e certidões) e o CRUD de prazos/compliance.
Tudo async, dado REAL, autenticado.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db

from . import hub_service, prazos_service

router = APIRouter(prefix="/juridico", tags=["Jurídico - Hub"])


class PrazoCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=300)
    data_limite: date
    tipo: str | None = Field(default=None, max_length=40)
    status: str = Field(default="aberto")
    contrato_id: str | None = None
    descricao: str | None = None


@router.get("/dashboard", summary="Hub Jurídico — painel consolidado (dado real)")
async def hub(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await hub_service.hub_dashboard(db)


@router.get("/prazos", summary="Lista prazos (gravados + automáticos) com status calculado")
async def listar_prazos(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    incluir_automaticos: bool = Query(default=True, description="Inclui prazos de contratos/certidões"),
    status: str | None = Query(default=None, description="Filtra por status calculado: aberto|cumprido|atrasado"),
) -> dict:
    return await prazos_service.listar_prazos(
        db, incluir_automaticos=incluir_automaticos, status=status
    )


@router.get("/prazos/alertas", summary="Prazos vencendo em ≤7/≤15/≤30 dias + atrasados")
async def alertas_prazos(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await prazos_service.alertas_prazos(db)


@router.post("/prazos", status_code=201, summary="Cria um prazo/compliance")
async def criar_prazo(
    payload: PrazoCreate,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await prazos_service.criar_prazo(
        db,
        titulo=payload.titulo,
        data_limite=payload.data_limite,
        tipo=payload.tipo,
        status=payload.status,
        contrato_id=payload.contrato_id,
        descricao=payload.descricao,
    )
