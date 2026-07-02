"""Endpoints do Jurídico: Pareceres IA + Análise de Contrato.

A IA fundamenta, o humano certifica. Nenhum endpoint fabrica direito: quando a IA está
indisponível, a resposta é honesta e o registro é marcado como tal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentUser
from core.database import get_db

from . import analise_service as analise_svc
from . import parecer_service as parecer_svc

router = APIRouter(prefix="/juridico", tags=["Jurídico - Pareceres e Análise"])


# ── Schemas ──────────────────────────────────────────────────────────────────
class ParecerRequest(BaseModel):
    area: str = Field(..., description="Área jurídica: trabalhista | civel | tributaria")
    titulo: str = Field(..., min_length=3, description="Título/assunto da consulta")
    contexto: str = Field(..., min_length=10, description="Fatos e questão posta")


class AnaliseRequest(BaseModel):
    nome: str = Field(..., min_length=1, description="Nome/identificação do contrato")
    conteudo: str = Field(..., min_length=20, description="Texto integral do contrato a revisar")


# ── Pareceres ─────────────────────────────────────────────────────────────────
@router.post("/pareceres", summary="Gera um parecer jurídico com IA (rascunho)")
async def criar_parecer(
    body: ParecerRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = None,  # noqa: RUF013
) -> dict:
    return await parecer_svc.gerar_parecer(
        db, area=body.area, titulo=body.titulo, contexto=body.contexto, user_id=str(getattr(user, "id", None))
    )


@router.get("/pareceres", summary="Lista os pareceres mais recentes")
async def listar_pareceres(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = None,  # noqa: RUF013
) -> dict:
    itens = await parecer_svc.listar_pareceres(db, limit=limit)
    return {"total": len(itens), "pareceres": itens}


@router.get("/pareceres/{id}", summary="Detalhe de um parecer")
async def obter_parecer(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = None,  # noqa: RUF013
) -> dict:
    p = await parecer_svc.obter_parecer(db, id)
    if not p:
        raise HTTPException(status_code=404, detail="Parecer não encontrado")
    return p


@router.get("/pareceres/{id}/pdf", summary="PDF do parecer (padrão-ouro)")
async def parecer_pdf(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = None,  # noqa: RUF013
) -> Response:
    p = await parecer_svc.obter_parecer(db, id)
    if not p:
        raise HTTPException(status_code=404, detail="Parecer não encontrado")
    pdf = parecer_svc.gerar_pdf_parecer(p)
    filename = f"parecer_{id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Análise de contrato ─────────────────────────────────────────────────────
@router.post("/analises", summary="Analisa um contrato cláusula-a-cláusula com IA")
async def criar_analise(
    body: AnaliseRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = None,  # noqa: RUF013
) -> dict:
    try:
        return await analise_svc.analisar_contrato(
            db, nome=body.nome, conteudo=body.conteudo, user_id=str(getattr(user, "id", None))
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/analises", summary="Lista as análises de contrato mais recentes")
async def listar_analises(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = None,  # noqa: RUF013
) -> dict:
    itens = await analise_svc.listar_analises(db, limit=limit)
    return {"total": len(itens), "analises": itens}
