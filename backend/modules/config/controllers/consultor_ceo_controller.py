"""Consultor Executivo (CEO IA) — endpoints (espelha CFO IA / Consultor GED).

Chat de nível executivo ancorado na fotografia CROSS-MÓDULO real do ERP:
KPIs, contratos/MRR, pessoas, folha, NFS-e, funil comercial, vencidos,
processos jurídicos e intercorrências GED.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.config.services import consultor_ceo_service as svc

router = APIRouter(prefix="/gestao/consultor", tags=["Gestão - Consultor Executivo IA"])


class PerguntaIn(BaseModel):
    area: str = Field(..., description="Lente: visao_geral | riscos | crescimento | prioridades")
    pergunta: str = Field(..., min_length=3, examples=["Qual o estado da empresa hoje?"])


class ConsultaOut(BaseModel):
    resposta: str
    escalonar: bool = False
    disclaimer: str
    id: int | None = None
    indisponivel: bool = False
    panorama: dict | None = None


@router.get("/panorama", summary="Fotografia executiva cross-módulo (dados reais do ERP)")
async def obter_panorama(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await svc.panorama(db)


@router.post("/perguntar", response_model=ConsultaOut,
             summary="Pergunta ao Consultor Executivo (ancorado na fotografia cross-módulo)")
async def perguntar(
    body: PerguntaIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await svc.consultar(
            db=db, area=body.area, pergunta=body.pergunta,
            user_id=str(getattr(current_user, "id", None)),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/perguntar-arquivo", response_model=ConsultaOut,
             summary="Consulta executiva analisando um anexo (PDF/DOCX/planilha/TXT)")
async def perguntar_arquivo(
    arquivo: UploadFile = File(...),
    area: str = Form("visao_geral"),
    pergunta: str = Form(""),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Reusa o extrator de texto do CFO (mesmo padrão de anexos)
    from modules.financial.cfo_controller import _extrair_texto_arquivo

    if (area or "").strip().lower() not in svc.AREAS_VALIDAS:
        raise HTTPException(status_code=422, detail=f"Área inválida '{area}'.")
    data = await arquivo.read()
    texto = _extrair_texto_arquivo(arquivo.filename or "", data)
    if len(texto.strip()) < 15:
        raise HTTPException(status_code=422, detail="Não foi possível extrair texto do arquivo.")
    try:
        return await svc.consultar(
            db=db, area=area.strip().lower(),
            pergunta=(pergunta or "").strip()
            or "Analise este documento sob a ótica executiva da empresa.",
            user_id=str(getattr(current_user, "id", None)),
            anexo_texto=texto, anexo_nome=arquivo.filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/historico", summary="Histórico de consultas ao Consultor Executivo")
async def historico(
    area: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if area is not None and area.strip().lower() not in svc.AREAS_VALIDAS:
        raise HTTPException(status_code=422, detail=f"Área inválida '{area}'.")
    consultas = await svc.listar_consultas(db=db, area=area, limit=limit)
    return {"total": len(consultas), "consultas": consultas}
