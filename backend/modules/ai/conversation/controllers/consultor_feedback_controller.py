"""Fase 4 — endpoint compartilhado de feedback + placar de aprendizado dos consultores.

POST /ai/consultor/feedback  {origem, consulta_id, util, correcao?}  → grava 👍/👎; a
correção do gestor vira memória permanente.
GET  /ai/consultor/placar    → o placar (taxa 👍, feedback, memórias, correções) = prova
de que aprendem. Restrito à diretoria (dado gerencial).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user, get_db
from modules.ai.consultores.permissions import require_consultor_executivo
from modules.ai.conversation.services import consultor_hub

router = APIRouter(prefix="/ai/consultor", tags=["IA - Consultores (feedback/placar)"])


class FeedbackIn(BaseModel):
    origem: str          # cfo | juridico | ged | comercial | operacional | rh | fiscal | ceo
    consulta_id: int
    util: bool
    correcao: str | None = None


@router.post("/feedback", summary="👍/👎 numa resposta do consultor (correção vira memória)")
async def dar_feedback(
    body: FeedbackIn,
    user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await consultor_hub.registrar_feedback(
        db, body.origem, body.consulta_id, body.util, body.correcao
    )


@router.get("/placar", summary="Placar de aprendizado (prova que aprendem) — diretoria")
async def placar(
    user=Depends(require_consultor_executivo),
    db: AsyncSession = Depends(get_db),
):
    return await consultor_hub.placar_aprendizado(db)
