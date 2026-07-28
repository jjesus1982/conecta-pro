"""Fase 4 — endpoint compartilhado de feedback + placar de aprendizado dos consultores.

POST /ai/consultor/feedback  {origem, consulta_id, util, correcao?}  → grava 👍/👎; a
correção do gestor vira memória permanente.
GET  /ai/consultor/placar    → o placar (taxa 👍, feedback, memórias, correções) = prova
de que aprendem. Restrito à diretoria (dado gerencial).

Fase 5.5 Task 6 — fila de revisão de memória (propor→aprovar aplicado a memória):
GET  /ai/consultor/memorias/pendentes         → lista status='pendente_revisao'.
POST /ai/consultor/memorias/{id}/aprovar      → status='ativo' (entra no contexto
                                                 compartilhado) + audit.
POST /ai/consultor/memorias/{id}/rejeitar     → status='rejeitado' (some de vez) + audit.
Todas gated à diretoria (require_consultor_executivo — mesma allowlist do Consultor
Executivo, jjesus+pjesus).
"""
from fastapi import APIRouter, Depends, HTTPException
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


@router.post(
    "/feedback",
    summary="👍/👎 numa resposta do consultor (correção só vira memória permanente se diretoria)",
)
async def dar_feedback(
    body: FeedbackIn,
    user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # 👍/👎 simples vale para qualquer user ativo; a promoção da correção a
    # memória PERMANENTE (compartilhada entre todos os consultores) é gated por
    # diretoria dentro de registrar_feedback (user_role="admin").
    return await consultor_hub.registrar_feedback(
        db, body.origem, body.consulta_id, body.util, body.correcao,
        user_role=getattr(user, "role", None),
        autor=getattr(user, "email", None) or getattr(user, "username", None),
    )


@router.get("/placar", summary="Placar de aprendizado (prova que aprendem) — diretoria")
async def placar(
    user=Depends(require_consultor_executivo),
    db: AsyncSession = Depends(get_db),
):
    return await consultor_hub.placar_aprendizado(db)


@router.get(
    "/memorias/pendentes",
    summary="Fila de memórias aguardando revisão (propor→aprovar) — diretoria",
)
async def memorias_pendentes(
    user=Depends(require_consultor_executivo),
    db: AsyncSession = Depends(get_db),
):
    return await consultor_hub.listar_memorias_pendentes(db)


@router.post(
    "/memorias/{memoria_id}/aprovar",
    summary="Aprova memória pendente → entra no contexto compartilhado — diretoria",
)
async def aprovar_memoria_pendente(
    memoria_id: int,
    user=Depends(require_consultor_executivo),
    db: AsyncSession = Depends(get_db),
):
    r = await consultor_hub.aprovar_memoria(db, memoria_id, autor=getattr(user, "email", None))
    if not r.get("ok"):
        raise HTTPException(status_code=404, detail=r.get("erro", "erro"))
    return r


@router.post(
    "/memorias/{memoria_id}/rejeitar",
    summary="Rejeita memória pendente (some de vez) — diretoria",
)
async def rejeitar_memoria_pendente(
    memoria_id: int,
    user=Depends(require_consultor_executivo),
    db: AsyncSession = Depends(get_db),
):
    r = await consultor_hub.rejeitar_memoria(db, memoria_id, autor=getattr(user, "email", None))
    if not r.get("ok"):
        raise HTTPException(status_code=404, detail=r.get("erro", "erro"))
    return r
