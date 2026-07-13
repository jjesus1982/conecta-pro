"""Diárias — endpoints. Cadastros (listas suspensas) + lançamento (valor automático) + resumos.

Modelo da planilha do Jordan: Gonzaga seleciona diarista/função/posto/turno → valor automático.
O resumo por diarista vira o lote a pagar no Financeiro (dia 15).
"""
from __future__ import annotations

from datetime import date as _date

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


@router.get("/lancamentos", summary="Lançamentos do mês (mes+ano) ou de um dia exato (?data=YYYY-MM-DD)")
async def lancamentos(mes: int | None = Query(default=None, ge=1, le=12),
                      ano: int | None = Query(default=None, ge=2020, le=2100),
                      data: str | None = Query(default=None, description="YYYY-MM-DD — filtra o dia exato"),
                      current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    if data:
        try:
            _date.fromisoformat(data)
        except ValueError:
            raise HTTPException(status_code=422, detail="Data inválida — use o formato YYYY-MM-DD.")
    elif not (mes and ano):
        raise HTTPException(status_code=422, detail="Informe data=YYYY-MM-DD ou mes+ano.")
    return await svc.listar_lancamentos(db, mes=mes, ano=ano, data=data)


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
    cpf: str | None = Field(default=None, description="CPF OBRIGATÓRIO (validado por dígitos verificadores)")
    pix: str | None = Field(default=None, description="Chave PIX OBRIGATÓRIA (CPF, +55 telefone, e-mail ou UUID)")
    telefone: str | None = Field(default=None, description="Contato — exigido telefone OU e-mail")
    email: str | None = Field(default=None, description="Contato — exigido telefone OU e-mail")


@router.post("/diaristas", summary="Cadastra um diarista (CPF + PIX válidos obrigatórios; telefone ou e-mail)")
async def criar_diarista(body: DiaristaIn, current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    res = await svc.criar_diarista(db, nome=body.nome, cpf=body.cpf, pix=body.pix,
                                   telefone=body.telefone, email=body.email)
    if not res.get("ok"):
        raise HTTPException(status_code=422, detail=res.get("mensagem", "Dados inválidos para cadastro de diarista."))
    return res


class DiaristaUpdIn(BaseModel):
    cpf: str | None = None
    pix: str | None = None
    nome: str | None = None
    telefone: str | None = None
    email: str | None = None
    ativo: bool | None = Field(default=None, description="false = inativa (some dos dropdowns de lançamento)")


@router.patch("/diaristas/{diarista_id}", summary="Atualiza cadastro do diarista (CPF/PIX validados; não permite limpar; ativo=false inativa)")
async def atualizar_diarista(diarista_id: int, body: DiaristaUpdIn,
                             current_user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    res = await svc.atualizar_diarista(db, diarista_id, cpf=body.cpf, pix=body.pix, nome=body.nome,
                                       telefone=body.telefone, email=body.email, ativo=body.ativo)
    if not res.get("ok"):
        raise HTTPException(status_code=int(res.get("http_status", 422)),
                            detail=res.get("mensagem", "Dados inválidos para atualização de diarista."))
    return res


@router.delete("/diaristas/{diarista_id}", summary="Apaga o diarista (ou INATIVA se tiver histórico de lançamentos)")
async def remover_diarista(diarista_id: int, current_user=Depends(get_current_active_user),
                           db: AsyncSession = Depends(get_db)):
    res = await svc.remover_diarista(db, diarista_id)
    if not res.get("ok"):
        raise HTTPException(status_code=int(res.get("http_status", 422)),
                            detail=res.get("mensagem", "Não foi possível remover o diarista."))
    return res
