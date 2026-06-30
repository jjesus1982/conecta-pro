"""Configurações do Portal do Cliente — perfil, troca de senha e preferências.

A tela /area-cliente/configuracoes consome estes endpoints (antes batiam no vazio):
  GET   /portal/settings/info         → dados do condomínio (nome, CNPJ, contato)
  GET   /portal/settings/preferences  → preferências de notificação
  PUT   /portal/settings/password     → troca de senha (verifica a atual)
  PATCH /portal/settings/preferences  → salva preferências
"""

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client
from modules.client_portal.services.auth_service import PortalAuthService
from modules.people_management.ged.models.client import GedClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Portal - Configuracoes"])


def _redis():
    import redis

    return redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/1"))


def _prefs_key(client_id: str) -> str:
    return f"portal:prefs:{client_id}"


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, description="Mínimo 8 caracteres")


class PreferencesUpdate(BaseModel):
    email_notifications: bool | None = None
    whatsapp_notifications: bool | None = None


@router.get("/info")
async def get_info(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dados do condomínio logado (perfil, somente leitura)."""
    client = (await db.execute(select(GedClient).where(GedClient.id == client_id))).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return {
        "id": str(client.id),
        "name": client.name,
        "cnpj": client.cnpj,
        "email": client.contact_email,
        "contact_name": client.contact_name,
        "username": client.portal_username,
    }


@router.get("/preferences")
async def get_preferences(client_id: str = Depends(get_current_portal_client)) -> Any:
    """Preferências de notificação (default tudo ligado)."""
    prefs = {"email_notifications": True, "whatsapp_notifications": True}
    try:
        raw = _redis().get(_prefs_key(client_id))
        if raw:
            prefs.update(json.loads(raw))
    except Exception:
        pass
    return prefs


@router.patch("/preferences")
async def update_preferences(
    data: PreferencesUpdate,
    client_id: str = Depends(get_current_portal_client),
) -> Any:
    """Salva preferências de notificação (persistido no Redis)."""
    atual = await get_preferences(client_id)
    if data.email_notifications is not None:
        atual["email_notifications"] = data.email_notifications
    if data.whatsapp_notifications is not None:
        atual["whatsapp_notifications"] = data.whatsapp_notifications
    try:
        _redis().set(_prefs_key(client_id), json.dumps(atual))
    except Exception as exc:
        logger.warning("Falha ao salvar preferências: %s", exc)
    return {"ok": True, **atual}


@router.put("/password")
async def change_password(
    data: ChangePasswordRequest,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Troca a senha do cliente (verifica a atual). Invalida as outras sessões por segurança."""
    client = (await db.execute(select(GedClient).where(GedClient.id == client_id))).scalar_one_or_none()
    if not client or not client.portal_password_hash:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if not PortalAuthService.verify_password(data.current_password, client.portal_password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    novo_hash = PortalAuthService.hash_password(data.new_password)
    await db.execute(update(GedClient).where(GedClient.id == client_id).values(portal_password_hash=novo_hash))
    # segurança: invalida TODAS as sessões ativas deste cliente (logout-all na troca de senha)
    from modules.client_portal.models.session import ClientPortalSession

    await db.execute(
        update(ClientPortalSession).where(ClientPortalSession.client_id == client_id).values(is_active=False)
    )
    await db.commit()
    return {"ok": True, "message": "Senha alterada. Faça login novamente."}
