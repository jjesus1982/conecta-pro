"""Diárias — endpoints. Cadastros (listas suspensas) + lançamento (valor automático) + resumos.

Modelo da planilha do Jordan: Gonzaga seleciona diarista/função/posto/turno → valor automático.
O resumo por diarista vira o lote a pagar no Financeiro (dia 15).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db

from . import diarias_service as svc

router = APIRouter(prefix="/operacional/diarias", tags=["Operacional - Diárias"])


@router.get("/cadastros", summary="Tudo para as listas suspensas (diaristas, funções, postos, turnos, preços)")
async def cadastros(current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await svc.cadastros(db)


class LancarIn(BaseModel):
    data: str = Field(..., description="YYYY-MM-DD")
    diarista_id: int
    funcao: str
    posto: str
    turno: str | None = None
    observacao: str | None = None


@router.post("/lancar", summary="Lança uma diária (valor automático pela tabela de preços)")
async def lancar(body: LancarIn, current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    res = await svc.lancar(db, data=body.data, diarista_id=body.diarista_id, funcao=body.funcao,
                           posto=body.posto, turno=body.turno, observacao=body.observacao,
                           user_id=str(getattr(current_user, "id", None)))
    if not res.get("ok"):
        raise HTTPException(status_code=422, detail=res.get("mensagem", "Falha ao lançar"))
    return res


@router.get("/lancamentos", summary="Lançamentos do mês")
async def lancamentos(mes: int = Query(...), ano: int = Query(...),
                      current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await svc.listar_lancamentos(db, mes=mes, ano=ano)


@router.delete("/lancamentos/{lancamento_id}", summary="Exclui um lançamento")
async def excluir(lancamento_id: int, current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await svc.excluir_lancamento(db, lancamento_id)


@router.get("/resumo-diarista", summary="Resumo por diarista (a lista de pagamento do dia 15)")
async def resumo_diarista(mes: int = Query(...), ano: int = Query(...),
                          current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await svc.resumo_diarista(db, mes=mes, ano=ano)


@router.get("/resumo-gerencial", summary="Resumos por posto e por função (BI)")
async def resumo_gerencial(mes: int = Query(...), ano: int = Query(...),
                           current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await svc.resumo_gerencial(db, mes=mes, ano=ano)


class DiaristaIn(BaseModel):
    nome: str
    cpf: str | None = None
    pix: str | None = None


@router.post("/diaristas", summary="Cadastra um diarista")
async def criar_diarista(body: DiaristaIn, current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await svc.criar_diarista(db, nome=body.nome, cpf=body.cpf, pix=body.pix)


class DiaristaUpdIn(BaseModel):
    cpf: str | None = None
    pix: str | None = None
    nome: str | None = None


@router.patch("/diaristas/{diarista_id}", summary="Completa CPF (obrigatório p/ pagar) e chave PIX do diarista")
async def atualizar_diarista(diarista_id: int, body: DiaristaUpdIn,
                             current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await svc.atualizar_diarista(db, diarista_id, cpf=body.cpf, pix=body.pix, nome=body.nome)
