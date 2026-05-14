"""
Controller: Brand Voice.

Endpoint:
  GET /api/v1/marketing/brand-voice
      Retorna o brand voice do condominio do usuario logado.
      Se ainda nao existe, retorna 404 (frontend cai pro fallback hardcoded).

Endpoints PUT/PATCH ficam pra Fase 2 (edicao via UI).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from core.logging import logger
from core.models import User

from ..repositories import BrandVoiceRepository
from ..schemas import BrandVoiceResponse

router = APIRouter(prefix="/marketing/brand-voice", tags=["Marketing - Brand Voice"])


@router.get("/", response_model=BrandVoiceResponse)
async def get_brand_voice(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> BrandVoiceResponse:
    """
    Retorna o brand voice do condominio do usuario logado.

    404 se o usuario nao tem condominio_id (ex: usuario novo sem assignment)
    ou se ainda nao ha brand voice cadastrado pra esse condominio.
    """
    if current_user.condominio_id is None:
        logger.warning(
            "Usuario %s sem condominio_id tentou acessar brand voice",
            current_user.email,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario sem condominio associado. Contate o admin.",
        )

    repo = BrandVoiceRepository(db)
    config = await repo.get_by_condominio(current_user.condominio_id)

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand voice ainda nao configurado para este condominio",
        )

    return BrandVoiceResponse.model_validate(config)
