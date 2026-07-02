"""Endpoints: Gestão do Escritório Jurídico Externo + ROI.

Registra demandas jurídicas (resolvidas internamente via IA vs escritório
externo pago) e mede o ROI da internalização. Dado REAL do banco; estimativas
sempre rotuladas como "referência configurável".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database.session import get_db

from . import escritorio_service as svc

router = APIRouter(prefix="/juridico/escritorio", tags=["Jurídico - Escritório & ROI"])


class ConsultaIn(BaseModel):
    assunto: str = Field(..., min_length=1, max_length=300)
    area: Optional[str] = Field(default=None, max_length=20)
    resolvido_por: str = Field(default="interno", description="'interno' ou 'escritorio'")
    custo: Optional[Decimal] = Field(default=None, ge=0)
    data: Optional[date] = None
    observacao: Optional[str] = None


@router.post("/consultas", summary="Registra uma demanda jurídica (interno vs escritório)")
async def criar_consulta(
    payload: ConsultaIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> dict:
    try:
        return await svc.registrar_consulta(
            db,
            assunto=payload.assunto,
            area=payload.area,
            resolvido_por=payload.resolvido_por,
            custo=payload.custo,
            data_demanda=payload.data,
            observacao=payload.observacao,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/consultas", summary="Lista demandas (filtro por resolvido_por/area/período)")
async def listar_consultas(
    resolvido_por: Optional[str] = Query(default=None, description="'interno' ou 'escritorio'"),
    area: Optional[str] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> dict:
    try:
        return await svc.listar_consultas(
            db,
            resolvido_por=resolvido_por,
            area=area,
            data_inicio=data_inicio,
            data_fim=data_fim,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/roi", summary="Dashboard ROI: economia por internalizar demandas jurídicas")
async def roi(
    meses: int = Query(default=6, ge=1, le=24, description="Meses na série mensal"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> dict:
    return await svc.roi_dashboard(db, meses=meses)
