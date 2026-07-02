"""Consultor Jurídico IA — endpoints (Conecta Mais / segurança patrimonial).

Expõe o consultor jurídico IA especializado em 3 áreas (trabalhista, cível, tributária).
A IA assiste; o escritório certifica. Toda resposta traz disclaimer e sinal de escalonamento.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from core.auth.dependencies import get_current_active_user
from core.database import get_db

from . import consultor_service as svc

router = APIRouter(prefix="/juridico/consultor", tags=["Jurídico - Consultor IA"])


class PerguntaIn(BaseModel):
    """Corpo da consulta ao consultor jurídico IA."""

    area: str = Field(
        ...,
        description="Área jurídica: trabalhista | civel | tributaria",
        examples=["trabalhista"],
    )
    pergunta: str = Field(
        ...,
        min_length=3,
        description="Dúvida jurídica do dia a dia da empresa.",
        examples=["Como calcular o adicional noturno de um agente de portaria na escala 12x36?"],
    )


class ConsultaOut(BaseModel):
    resposta: str
    fontes: list[str] = []
    escalonar: bool = False
    disclaimer: str
    id: int | None = None
    indisponivel: bool = False


@router.post(
    "/perguntar",
    summary="Faz uma pergunta jurídica fundamentada (trabalhista/cível/tributária)",
    response_model=ConsultaOut,
)
async def perguntar(
    body: PerguntaIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ConsultaOut:
    area = (body.area or "").strip().lower()
    if area not in svc.AREAS_VALIDAS:
        # 422: área inválida
        raise HTTPException(
            status_code=422,
            detail=f"Área inválida '{body.area}'. Válidas: {', '.join(svc.AREAS_VALIDAS)}.",
        )
    try:
        resultado = await svc.consultar(
            db=db,
            area=area,
            pergunta=body.pergunta,
            user_id=str(getattr(current_user, "id", None)),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return ConsultaOut(**resultado)


def _extrair_texto_arquivo(nome: str, data: bytes) -> str:
    """Extrai texto de PDF (PyMuPDF), DOCX (python-docx) ou TXT."""
    n = (nome or "").lower()
    try:
        if n.endswith(".pdf"):
            import fitz
            doc = fitz.open(stream=data, filetype="pdf")
            txt = "\n".join(p.get_text() for p in doc)
            doc.close()
            return txt.strip()
        if n.endswith(".docx"):
            import io
            from docx import Document
            d = Document(io.BytesIO(data))
            return "\n".join(p.text for p in d.paragraphs).strip()
        return data.decode("utf-8", "ignore").strip()
    except Exception:  # noqa: BLE001
        return data.decode("utf-8", "ignore").strip()


@router.post(
    "/perguntar-arquivo",
    summary="Consulta jurídica analisando um arquivo anexado (PDF/DOCX/TXT)",
)
async def perguntar_arquivo(
    arquivo: UploadFile = File(...),
    area: str = Form("trabalhista"),
    pergunta: str = Form(""),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Analisa o documento anexado à luz da pergunta (área trabalhista/cível/tributária)."""
    area_n = (area or "").strip().lower()
    if area_n not in svc.AREAS_VALIDAS:
        raise HTTPException(status_code=422, detail=f"Área inválida '{area}'.")
    data = await arquivo.read()
    texto = _extrair_texto_arquivo(arquivo.filename or "", data)
    if len(texto.strip()) < 20:
        raise HTTPException(status_code=422, detail="Não foi possível extrair texto do arquivo (PDF escaneado sem OCR?).")
    pergunta_final = (pergunta or "").strip() or "Analise juridicamente este documento e aponte pontos de atenção, riscos e recomendações."
    try:
        resultado = await svc.consultar(
            db=db, area=area_n, pergunta=pergunta_final,
            user_id=str(getattr(current_user, "id", None)),
            anexo_texto=texto, anexo_nome=arquivo.filename,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return resultado


@router.get(
    "/historico",
    summary="Histórico de consultas jurídicas (opcional por área)",
)
async def historico(
    current_user=Depends(get_current_active_user),
    area: str | None = Query(
        default=None, description="Filtra por área: trabalhista | civel | tributaria"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if area is not None and area.strip().lower() not in svc.AREAS_VALIDAS:
        raise HTTPException(
            status_code=422,
            detail=f"Área inválida '{area}'. Válidas: {', '.join(svc.AREAS_VALIDAS)}.",
        )
    consultas = await svc.listar_consultas(db=db, area=area, limit=limit)
    return {"total": len(consultas), "consultas": consultas}
