"""Pagamentos de diaristas (VT+VR) — endpoints. Elo Operacional→Financeiro + lote p/ pagar.

A escala do Gonzaga vira pagamento PROGRAMADO aqui; o Jordan revisa e paga em lote (Inter/OTP).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db

from . import pagamentos_diaristas_service as svc

router = APIRouter(prefix="/financial/pagamentos-diaristas", tags=["Financeiro - Pagamentos Diaristas"])


@router.post("/programar/{data}", summary="Programa os pagamentos VT+VR dos diaristas escalados no dia")
async def programar(
    data: str,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Lê a escala (diarist_schedules) do dia e deixa programado o VT+VR (R$32) de cada diarista."""
    try:
        return await svc.programar_do_dia(db, data, user_id=str(getattr(current_user, "id", None)))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao programar: {e}") from e


@router.get("/lote", summary="Lista o lote de pagamentos (para revisar/pagar)")
async def lote(
    data: str | None = Query(default=None),
    status: str | None = Query(default=None),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    itens = await svc.listar(db, data=data, status=status)
    total = sum(x["valor"] for x in itens if x["status"] in ("a_revisar", "aprovado"))
    return {"total_itens": len(itens), "total_a_pagar": total, "itens": itens}


@router.get("/resumo", summary="Resumo do lote (para o painel/CFO)")
async def resumo(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.resumo(db)


class ManualIn(BaseModel):
    data: str = Field(..., description="YYYY-MM-DD")
    beneficiario: str
    pix_key: str
    quantidade: int = Field(default=1, ge=1, description="Nº de pessoas (líder c/ ajudantes → R$32×N)")
    valor: float | None = None
    cpf: str | None = None
    tipo: str = "cobertura_clt"


@router.post("/manual", summary="Adiciona pagamento ao lote (cobertura CLT ou líder com N ajudantes)")
async def manual(
    body: ManualIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.adicionar_manual(
        db, data=body.data, beneficiario=body.beneficiario, pix_key=body.pix_key,
        quantidade=body.quantidade, valor=body.valor, tipo=body.tipo, cpf=body.cpf,
        user_id=str(getattr(current_user, "id", None)))


@router.post("/{pagamento_id}/cancelar", summary="Cancela um item do lote")
async def cancelar(
    pagamento_id: int,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.cancelar(db, pagamento_id)


@router.get("/sugestoes-cadastro", summary="Sugere diaristas a cadastrar a partir do histórico de PIX R$32")
async def sugestoes(
    dias: int = Query(default=30, ge=1, le=180),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.sugestoes_cadastro_historico(db, dias=dias)


@router.post("/programar-diarias-mensais/{ano}/{mes}", summary="Gera o lote do dia 15 a partir das diárias trabalhadas do mês (FLUXO 2)")
async def programar_diarias_mensais(
    ano: int, mes: int, data_pagamento: str | None = None,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.programar_diarias_mensais(
        db, mes=mes, ano=ano, data_pagamento=data_pagamento,
        user_id=str(getattr(current_user, "id", None)))


class ExecutarIn(BaseModel):
    ids: list[int] | None = None
    data: str | None = None
    confirmar: bool = False


@router.post("/executar", summary="Paga o lote via PIX (Inter). confirmar=false = prévia; true = paga (DINHEIRO SAI)")
async def executar(
    body: ExecutarIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Pagamento em lote dos diaristas. confirmar=False devolve a PRÉVIA (nada é pago);
    confirmar=True envia os PIX de verdade (ação do gestor, dinheiro sai — trava R$5.000/lote)."""
    return await svc.executar_lote(
        db, ids=body.ids, data=body.data, confirmar=body.confirmar,
        user_id=str(getattr(current_user, "id", None)))
