"""Simulação de custo por contrato e calculado × faturado (frente 7 — 12/09/2026).

Sub-router do growth_controller (montado em /crm) → /api/v1/crm/pricing/…  Só lê: a simulação
devolve o custo e NÃO grava preço; a divergência é relatório para o dono, nunca gatilho.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.crm.services import precificacao_contrato as prec
from modules.crm.services.precificacao_modos import MODOS, ROTULO, ParametroAusente

router = APIRouter(prefix="/pricing", tags=["CRM - Precificação de contrato"])


class SimularContratoIn(BaseModel):
    contrato: str  # id ou número (CTR-2026-00013)
    competencia: str | None = None  # AAAA-MM; vazio = mês corrente
    modo: str | None = None  # um de MODOS; vazio = preço do motor CCT
    entradas: dict | None = None  # postos, montante, horas, valor_hora, valor_total, horas_mes, horas_dia, horas_noturnas, valor_hora_noturna, dias, valor_dia


@router.get("/modos")
async def modos(_=Depends(get_current_active_user)) -> dict:
    return {"modos": [{"modo": m, "rotulo": ROTULO[m]} for m in MODOS]}


@router.post("/simular-contrato")
async def simular_contrato(data: SimularContratoIn, _=Depends(get_current_active_user),
                           db: AsyncSession = Depends(get_db)) -> dict:
    """Custo calculado do contrato (reserva técnica, PLR, taxa admin, modo) — SEM gravar."""
    try:
        return await prec.simular_contrato(db, data.contrato, data.competencia, data.modo, data.entradas)
    except ParametroAusente as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/contratos/calculado-vs-faturado")
async def calculado_vs_faturado(competencia: str | None = None, _=Depends(get_current_active_user),
                                db: AsyncSession = Depends(get_db)) -> dict:
    """Uma linha por contrato ativo: custo/preço calculado, faturado (NFS-e ou valor do contrato) e divergência."""
    try:
        linhas = await prec.relatorio_calculado_vs_faturado(db, competencia)
    except ParametroAusente as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    com = [r for r in linhas if isinstance(r["divergencia_reais"], (int, float))]
    return {
        "ok": True, "competencia": linhas and prec._ref(competencia).strftime("%Y-%m") or competencia,
        "total": len(linhas), "com_os_dois_numeros": len(com),
        "soma_faturado": round(sum(r["faturado"] for r in com), 2),
        "soma_preco_calculado": round(sum(r["preco_calculado"] for r in com), 2),
        "aviso": "Relatório para o dono. Nenhum contrato é alterado por esta rota.",
        "contratos": linhas,
    }
