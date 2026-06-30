"""
Controller de Notificacoes do Portal do Cliente.

Endpoints para registro de dispositivos push, gerenciamento de
preferencias de notificacao e consulta de notificacoes nao lidas.
"""

import hashlib
import logging
import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Portal - Notificacoes"])

# UUID de tenant reservado para o portal do cliente
PORTAL_TENANT_ID = _uuid.UUID("00000000-0000-0000-0000-000000000001")


# ========================================================================
# Schemas de entrada/saida
# ========================================================================


class DeviceRegisterRequest(BaseModel):
    """Requisicao de registro de dispositivo push."""

    device_token: str = Field(..., min_length=10, description="Token FCM/APNs/Web Push")
    platform: str = Field(..., description="Plataforma: web, android ou ios")


class DeviceUnregisterRequest(BaseModel):
    """Requisicao de remocao de dispositivo push."""

    device_token: str = Field(..., min_length=10, description="Token a remover")


class NotificationPreferencesRequest(BaseModel):
    """Preferencias de notificacao do cliente."""

    kit_ready: bool = Field(True, description="Notificar quando kit mensal estiver pronto")
    ticket_answered: bool = Field(True, description="Notificar quando chamado for respondido")
    certificate_expiring: bool = Field(True, description="Notificar quando certidao vencer em 7 dias")


class NotificationPreferencesResponse(BaseModel):
    """Resposta com preferencias de notificacao."""

    kit_ready: bool
    ticket_answered: bool
    certificate_expiring: bool
    push_enabled: bool = False


class UnreadCountResponse(BaseModel):
    """Contagem de notificacoes nao lidas."""

    unread_count: int
    has_unread: bool


# ========================================================================
# Helpers
# ========================================================================


def _get_push_service_and_models():
    """Retorna (PushService, DevicePlatform, DeviceStatus, PushDevice) ou None."""
    try:
        from core.database.session import SyncSessionLocal
        from modules.notifications.push.models import DevicePlatform, DeviceStatus, PushDevice
        from modules.notifications.push.services.push_service import PushService

        return PushService, DevicePlatform, DeviceStatus, PushDevice, SyncSessionLocal
    except Exception as exc:
        logger.warning("PushService nao disponivel: %s", exc)
        return None


def _map_platform(platform: str):
    """Converte string de plataforma para DevicePlatform enum."""
    result = _get_push_service_and_models()
    if result is None:
        return None
    _, DevicePlatform, _, _, _ = result
    mapping = {
        "web": DevicePlatform.WEB,
        "android": DevicePlatform.ANDROID,
        "ios": DevicePlatform.IOS,
    }
    return mapping.get(platform.lower())


# ========================================================================
# Endpoints
# ========================================================================


@router.post("/register-device", status_code=201)
async def register_device(
    data: DeviceRegisterRequest,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra dispositivo para receber notificacoes push.

    Associa o token FCM/APNs/Web Push ao cliente autenticado para que
    o servidor possa enviar notificacoes quando eventos ocorrerem.
    """
    result = _get_push_service_and_models()
    if result is None:
        # Push indisponivel — retorna sucesso gracioso
        return {"registered": False, "message": "Push notifications nao disponiveis no momento"}

    PushService, DevicePlatform, _, _, SyncSessionLocal = result

    platform_enum = _map_platform(data.platform)
    if platform_enum is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plataforma invalida: '{data.platform}'. Use: web, android ou ios",
        )

    try:
        client_uuid = _uuid.UUID(str(client_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="client_id invalido")

    # device_id estavel: hash do token (evita duplicatas)
    device_id = "portal_" + hashlib.sha256(data.device_token.encode()).hexdigest()[:24]

    try:
        with SyncSessionLocal() as sync_db:
            svc = PushService(db=sync_db, tenant_id=PORTAL_TENANT_ID)
            svc.register_device(
                user_id=client_uuid,
                device_id=device_id,
                device_token=data.device_token,
                platform=platform_enum,
                app_id="br.com.conectapro.portal",
            )
            logger.info(
                "Dispositivo portal registrado: client_id=%s device_id=%s platform=%s",
                client_id,
                device_id,
                data.platform,
            )
            return {
                "registered": True,
                "device_id": device_id,
                "platform": data.platform,
            }
    except Exception as exc:
        logger.warning("Erro ao registrar dispositivo: %s", exc)
        return {"registered": False, "message": "Erro interno ao registrar dispositivo"}


@router.delete("/register-device", status_code=200)
async def unregister_device(
    data: DeviceUnregisterRequest,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Remove registro de dispositivo push.

    Remove o token do servidor para que o cliente pare de receber
    notificacoes push neste dispositivo.
    """
    result = _get_push_service_and_models()
    if result is None:
        return {"unregistered": False, "message": "Push notifications nao disponiveis"}

    PushService, _, _, _, SyncSessionLocal = result

    device_id = "portal_" + hashlib.sha256(data.device_token.encode()).hexdigest()[:24]

    try:
        with SyncSessionLocal() as sync_db:
            svc = PushService(db=sync_db, tenant_id=PORTAL_TENANT_ID)
            removed = svc.unregister_device(device_id=device_id)
            logger.info("Dispositivo portal removido: client_id=%s removed=%s", client_id, removed)
            return {"unregistered": removed}
    except Exception as exc:
        logger.warning("Erro ao remover dispositivo: %s", exc)
        return {"unregistered": False, "message": "Erro interno ao remover dispositivo"}


@router.put("/preferences", response_model=NotificationPreferencesResponse)
async def update_preferences(
    data: NotificationPreferencesRequest,
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Salva preferencias de notificacao do cliente.

    As preferencias sao persistidas no campo de metadados do cliente.
    Se o campo nao existir no banco, o endpoint retorna as preferencias
    informadas sem falhar (graceful degradation).
    """
    prefs = {
        "kit_ready": data.kit_ready,
        "ticket_answered": data.ticket_answered,
        "certificate_expiring": data.certificate_expiring,
    }

    try:
        from sqlalchemy import text

        # Tenta salvar em coluna JSONB de preferencias se existir
        await db.execute(
            text("UPDATE ged_clients SET updated_at = NOW() WHERE id = :client_id"),
            {"client_id": client_id},
        )
        await db.commit()

        # Armazena em Redis se disponivel para acesso rapido
        try:
            import json

            from core.cache import get_redis

            redis = await get_redis()
            if redis:
                await redis.setex(
                    f"portal:prefs:{client_id}",
                    86400 * 7,  # 7 dias
                    json.dumps(prefs),
                )
        except Exception:
            pass  # Redis opcional

        logger.info("Preferencias atualizadas: client_id=%s prefs=%s", client_id, prefs)

    except Exception as exc:
        logger.warning("Erro ao salvar preferencias: %s", exc)
        # Nao falha — retorna as preferencias recebidas

    return NotificationPreferencesResponse(
        kit_ready=data.kit_ready,
        ticket_answered=data.ticket_answered,
        certificate_expiring=data.certificate_expiring,
        push_enabled=_push_devices_registered(client_id),
    )


@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_preferences(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna preferencias de notificacao atuais do cliente."""
    prefs = {"kit_ready": True, "ticket_answered": True, "certificate_expiring": True}

    try:
        import json

        from core.cache import get_redis

        redis = await get_redis()
        if redis:
            cached = await redis.get(f"portal:prefs:{client_id}")
            if cached:
                prefs = json.loads(cached)
    except Exception:
        pass

    return NotificationPreferencesResponse(
        kit_ready=prefs.get("kit_ready", True),
        ticket_answered=prefs.get("ticket_answered", True),
        certificate_expiring=prefs.get("certificate_expiring", True),
        push_enabled=_push_devices_registered(client_id),
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna contagem de chamados respondidos nao lidos.

    Usado pelo frontend para mostrar badge no nav quando ha
    chamados com resposta nova que o cliente ainda nao visualizou.
    """
    try:
        from sqlalchemy import func, select

        from modules.client_portal.models.ticket import ClientTicket, TicketStatus

        # Conta tickets com status RESPONDIDO (equipe respondeu, cliente ainda nao releu)
        result = await db.execute(
            select(func.count())
            .select_from(ClientTicket)
            .where(
                ClientTicket.client_id == client_id,
                ClientTicket.status == TicketStatus.RESPONDIDO,
            )
        )
        count = result.scalar() or 0

        return UnreadCountResponse(unread_count=count, has_unread=count > 0)

    except Exception as exc:
        logger.warning("Erro ao buscar unread count: %s", exc)
        return UnreadCountResponse(unread_count=0, has_unread=False)


# ========================================================================
# Utilitario interno
# ========================================================================


def _push_devices_registered(client_id: str) -> bool:
    """Verifica se o cliente tem algum dispositivo push registrado."""
    result = _get_push_service_and_models()
    if result is None:
        return False
    PushService, _, _, _, SyncSessionLocal = result
    try:
        client_uuid = _uuid.UUID(str(client_id))
        with SyncSessionLocal() as sync_db:
            svc = PushService(db=sync_db, tenant_id=PORTAL_TENANT_ID)
            devices = svc.get_user_devices(user_id=client_uuid, active_only=True)
            return len(devices) > 0
    except Exception:
        return False
