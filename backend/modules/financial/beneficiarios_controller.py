"""Agenda de beneficiários PIX — endpoints de autocomplete e cadastro.

Prefixo: /api/v1/financial/beneficiarios  (gate financeiro no main_production)
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database.session import get_db
from modules.financial import beneficiarios_service as svc

router = APIRouter(prefix="/financial/beneficiarios", tags=["Financeiro - Beneficiários"])


class BeneficiarioIn(BaseModel):
    nome: str = Field(min_length=2)
    chave_pix: str = Field(min_length=2)
    tipo_chave: str | None = None
    cpf_cnpj: str | None = None
    categoria: str = "avulso"


@router.get("", summary="Busca beneficiários salvos (autocomplete nome→chave PIX)")
async def listar(
    q: str = Query(default="", description="nome, chave ou CPF/CNPJ (parcial)"),
    limite: int = Query(default=12, ge=1, le=50),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return {"beneficiarios": await svc.buscar(db, q=q, limite=limite)}


@router.post("", summary="Cadastra/atualiza um beneficiário manualmente")
async def salvar(
    body: BeneficiarioIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await svc.upsert_beneficiario(
        db, nome=body.nome, chave_pix=body.chave_pix, tipo_chave=body.tipo_chave,
        cpf_cnpj=body.cpf_cnpj, categoria=body.categoria, origem="manual")
    await db.commit()
    return {"ok": ok}


@router.post("/seed", summary="Popula a agenda com o que já existe (pagamentos/fornecedores/funcionários/diaristas)")
async def seed(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.seed_de_fontes(db)


@router.delete("/{beneficiario_id}", summary="Remove (inativa) um beneficiário da agenda")
async def remover(
    beneficiario_id: int,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await svc._ensure(db)
    r = await db.execute(text("UPDATE financial_beneficiarios SET ativo=FALSE, updated_at=now() WHERE id=:id"),
                         {"id": beneficiario_id})
    await db.commit()
    return {"ok": bool(r.rowcount)}
