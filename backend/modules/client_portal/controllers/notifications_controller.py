"""
Controller de Notificacoes do Portal do Cliente.

Endpoints para registro de dispositivos push, gerenciamento de
preferencias de notificacao e consulta de notificacoes nao lidas.
"""

import logging
import uuid as _uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field


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
