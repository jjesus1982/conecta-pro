"""Base de Conhecimento + Playbook do Jurídico — endpoints."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db

from modules.juridico import conhecimento_service as CS

router = APIRouter(prefix="/juridico", tags=["Jurídico - Conhecimento & Playbook"])


@router.get("/conhecimento")
async def listar_conhecimento(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Precedentes/pareceres/teses da própria empresa."""
    return {"conhecimento": await CS.listar_conhecimento(db)}


@router.get("/playbook")
async def listar_playbook(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Procedimentos codificados: como agir por tipo de situação."""
    return {"playbook": await CS.listar_playbook(db)}


@router.post("/conhecimento/seed")
async def seed(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Semeia a base com os casos/procedimentos reais (idempotente)."""
    r = await CS.seed_inicial(db)
    await db.commit()
    return r


class ConhecimentoIn(BaseModel):
    tipo: str = "precedente"
    area: str
    titulo: str
    palavras_chave: str | None = None
    resumo: str | None = None
    fundamentacao: str | None = None
    desfecho: str | None = None
    fonte: str | None = None


@router.post("/conhecimento")
async def add_conhecimento(
    payload: ConhecimentoIn,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Adiciona um precedente/parecer/tese à base de conhecimento."""
    from sqlalchemy import text
    await CS.ensure_tables(db)
    await db.execute(text(
        "INSERT INTO juridico_conhecimento (tipo,area,titulo,palavras_chave,resumo,fundamentacao,desfecho,fonte) "
        "VALUES (:tipo,:area,:titulo,:palavras_chave,:resumo,:fundamentacao,:desfecho,:fonte)"),
        payload.model_dump())
    await db.commit()
    return {"ok": True}
