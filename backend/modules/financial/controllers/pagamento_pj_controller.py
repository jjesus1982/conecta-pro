"""Folha de PAGAMENTO PJ (prestadores) — endpoints. Multi-CNPJ.

Eletrônica→Inter (automático, OTP) · Patrimonial→Cora (lista pra pagar no app).
Dinheiro que sai: /executar só paga com confirmar=true + OTP válido.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.financial.services import pagamento_pj_service as svc

router = APIRouter(prefix="/financial/pagamentos-pj", tags=["Financeiro - Pagamentos PJ"])


@router.get("/preview/{ano}/{mes}", summary="Prévia da folha PJ (calcula, não grava nem paga)")
async def preview(ano: int, mes: int, current_user=Depends(get_current_active_user)):
    try:
        return svc.calcular_folha_pj(mes, ano)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha no preview: {e}") from e


@router.post("/programar/{ano}/{mes}", summary="Materializa a folha PJ do mês no lote (idempotente)")
async def programar(ano: int, mes: int, current_user=Depends(get_current_active_user),
                    db: AsyncSession = Depends(get_db)):
    try:
        return await svc.programar_folha_pj(db, mes, ano)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao programar: {e}") from e


@router.get("/lote/{ano}/{mes}", summary="Lote da folha PJ (Inter pagável + lista Cora + pendências)")
async def lote(ano: int, mes: int, current_user=Depends(get_current_active_user),
               db: AsyncSession = Depends(get_db)):
    try:
        return await svc.listar_lote(db, mes, ano)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao listar: {e}") from e


@router.post("/solicitar-otp/{ano}/{mes}", summary="Gera o OTP (e-mail) que libera o lote Inter")
async def solicitar_otp(ano: int, mes: int, current_user=Depends(get_current_active_user),
                        db: AsyncSession = Depends(get_db)):
    try:
        return await svc.gerar_otp_lote(db, mes, ano)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha no OTP: {e}") from e


class ExecutarBody(BaseModel):
    confirmar: bool = False
    otp_code: str | None = None
    lote_id: str | None = None


@router.post("/executar/{ano}/{mes}",
             summary="Paga o lote Inter via PIX. confirmar=false=prévia; true+OTP=paga (DINHEIRO SAI)")
async def executar(ano: int, mes: int, body: ExecutarBody,
                   current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    try:
        return await svc.executar_lote(db, mes, ano, confirmar=body.confirmar,
                                       otp_code=body.otp_code, lote_id=body.lote_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao executar: {e}") from e


class NotaFiscalBody(BaseModel):
    ok: bool = True


@router.post("/item/{item_id}/nota-fiscal", summary="Marca a nota fiscal do prestador (libera p/ o lote)")
async def marcar_nf(item_id: int, body: NotaFiscalBody,
                    current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    try:
        return await svc.marcar_nota_fiscal(db, item_id, ok=body.ok)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao marcar NF: {e}") from e
