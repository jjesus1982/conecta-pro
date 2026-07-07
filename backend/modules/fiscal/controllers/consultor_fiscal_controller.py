"""Consultor Fiscal IA — endpoints (espelha CFO IA / Consultor Jurídico / Consultor GED).

Chat ancorado nos dados fiscais reais: NFS-e nacional (emitidas/tomadas), NF-e de
entrada, histórico municipal Manaus 2019-2025, certidões (CNDs) e obrigações com prazos.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.fiscal.services import consultor_fiscal_service as svc

router = APIRouter(prefix="/fiscal/consultor", tags=["Fiscal - Consultor Fiscal IA"])


class PerguntaIn(BaseModel):
    area: str = Field(..., description="Lente: notas | apuracao | certidoes | obrigacoes")
    pergunta: str = Field(..., min_length=3, examples=["Quanto de ISS devo recolher sobre a receita de junho?"])
    ano: int | None = Field(None, ge=2019, le=2100, description="Ano de referência (default: ano corrente)")


class ConsultaOut(BaseModel):
    resposta: str
    escalonar: bool = False
    disclaimer: str
    id: int | None = None
    indisponivel: bool = False
    panorama: dict | None = None


@router.get("/panorama", summary="Fotografia fiscal real (notas, ISS, certidões, obrigações)")
async def obter_panorama(
    ano: int | None = Query(None, ge=2019, le=2100, description="Ano de referência (default: corrente)"),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await svc.panorama(db, ano)


@router.post("/perguntar", response_model=ConsultaOut, summary="Pergunta ao Consultor Fiscal (ancorado nos dados reais)")
async def perguntar(
    body: PerguntaIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await svc.consultar(
            db=db, area=body.area, pergunta=body.pergunta, ano=body.ano,
            user_id=str(getattr(current_user, "id", None)),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/perguntar-arquivo", response_model=ConsultaOut, summary="Consulta analisando um anexo (PDF/DOCX/TXT/CSV)")
async def perguntar_arquivo(
    arquivo: UploadFile = File(...),
    area: str = Form("notas"),
    pergunta: str = Form(""),
    ano: int | None = Form(None),
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
            pergunta=(pergunta or "").strip() or "Analise este documento no contexto fiscal da empresa.",
            ano=ano, user_id=str(getattr(current_user, "id", None)),
            anexo_texto=texto, anexo_nome=arquivo.filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/historico", summary="Histórico de consultas ao Consultor Fiscal")
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
