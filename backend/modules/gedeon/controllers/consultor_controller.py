"""Consultor GED IA — endpoints (espelha CFO IA / Consultor Jurídico).

Chat ancorado nos kits reais + registro de INTERCORRÊNCIAS do mês por condomínio
(contratações, demissões, faltas, atrasos, suspensões...) para fechamento de folha perfeito.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.gedeon.services import consultor_service as svc

router = APIRouter(prefix="/gedeon/consultor", tags=["GEDEON - Consultor GED IA"])


class PerguntaIn(BaseModel):
    area: str = Field(..., description="Lente: montagem | checklist | intercorrencias | folha")
    pergunta: str = Field(..., min_length=3, examples=["O kit do PRIME ARENA está pronto para fechar?"])
    condominio: str | None = Field(None, description="Filtrar contexto por condomínio")
    competencia: str | None = Field(None, description="YYYY-MM (default: mês anterior)")


class ConsultaOut(BaseModel):
    resposta: str
    escalonar: bool = False
    disclaimer: str
    id: int | None = None
    indisponivel: bool = False
    panorama: dict | None = None


class IntercorrenciaIn(BaseModel):
    condominio: str = Field(..., min_length=2)
    tipo: str = Field(..., description="contratacao|demissao|falta|atraso|suspensao|afastamento|ferias|advertencia|acidente|hora_extra|troca_posto|outro")
    descricao: str = Field(..., min_length=3)
    competencia: str | None = Field(None, description="YYYY-MM (default: mês anterior)")
    funcionario: str | None = None
    data_evento: date | None = None
    impacto_folha: bool = True


@router.get("/panorama", summary="Fotografia real dos kits + intercorrências por condomínio")
async def obter_panorama(
    competencia: str | None = Query(None, description="YYYY-MM (default: mês anterior)"),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await svc.panorama(db, competencia)


@router.post("/perguntar", response_model=ConsultaOut, summary="Pergunta ao Consultor GED (ancorado nos kits reais)")
async def perguntar(
    body: PerguntaIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await svc.consultar(
            db=db, area=body.area, pergunta=body.pergunta,
            condominio=body.condominio, competencia=body.competencia,
            user_id=str(getattr(current_user, "id", None)),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/perguntar-arquivo", response_model=ConsultaOut, summary="Consulta analisando um anexo (PDF/DOCX/TXT/CSV)")
async def perguntar_arquivo(
    arquivo: UploadFile = File(...),
    area: str = Form("checklist"),
    pergunta: str = Form(""),
    condominio: str | None = Form(None),
    competencia: str | None = Form(None),
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
            pergunta=(pergunta or "").strip() or "Analise este documento no contexto do fechamento do kit.",
            condominio=condominio, competencia=competencia,
            user_id=str(getattr(current_user, "id", None)),
            anexo_texto=texto, anexo_nome=arquivo.filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/historico", summary="Histórico de consultas ao Consultor GED")
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


# ── Intercorrências do mês (registrar ANTES de fechar o kit) ──────────────────
@router.get("/intercorrencias", summary="Lista intercorrências (filtros: condomínio, competência, status)")
async def listar_intercorrencias(
    condominio: str | None = Query(None),
    competencia: str | None = Query(None, description="YYYY-MM"),
    status: str | None = Query(None, description="aberta | tratada"),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    itens = await svc.listar_intercorrencias(
        db, condominio=condominio, competencia=competencia, status=status
    )
    return {"total": len(itens), "intercorrencias": itens}


@router.post("/intercorrencias", status_code=201, summary="Registra intercorrência do mês (contratação, demissão, falta...)")
async def registrar_intercorrencia(
    body: IntercorrenciaIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await svc.registrar_intercorrencia(
            db, condominio=body.condominio, tipo=body.tipo, descricao=body.descricao,
            competencia=body.competencia, funcionario=body.funcionario,
            data_evento=body.data_evento, impacto_folha=body.impacto_folha,
            created_by=str(getattr(current_user, "email", None) or getattr(current_user, "id", None)),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.patch("/intercorrencias/{intercorrencia_id}/tratar", summary="Marca intercorrência como tratada")
async def tratar_intercorrencia(
    intercorrencia_id: int,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await svc.tratar_intercorrencia(db, intercorrencia_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/intercorrencias/{intercorrencia_id}", summary="Exclui intercorrência (registro errado)")
async def excluir_intercorrencia(
    intercorrencia_id: int,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await svc.excluir_intercorrencia(db, intercorrencia_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
