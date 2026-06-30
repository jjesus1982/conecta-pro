"""
Portal do Cliente — Acesso externo para clientes de condominios.

Permite que clientes acessem seus kits documentais, abram tickets
de suporte e gerenciem suas sessoes atraves de um portal autenticado
separado do sistema interno.
"""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["Client Portal"])

try:
    from .controllers.auth_controller import router as auth_router

    router.include_router(auth_router)
    logger.info("Portal: auth_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar auth_controller: %s", e)

try:
    from .controllers.kit_controller import router as kit_router

    router.include_router(kit_router)
    logger.info("Portal: kit_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar kit_controller: %s", e)

try:
    from .controllers.ticket_controller import router as ticket_router

    router.include_router(ticket_router)
    logger.info("Portal: ticket_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar ticket_controller: %s", e)

try:
    from .controllers.access_management_controller import router as access_mgmt_router

    router.include_router(access_mgmt_router)
    logger.info("Portal: access_management_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar access_management_controller: %s", e)

try:
    from .controllers.assistant_controller import router as assistant_router

    router.include_router(assistant_router)
    logger.info("Portal: assistant_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar assistant_controller: %s", e)

__all__ = ["router"]

try:
    from .controllers.notifications_controller import router as notifications_router

    router.include_router(notifications_router)
    logger.info("Portal: notifications_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar notifications_controller: %s", e)

try:
    from .controllers.analytics_controller import router as analytics_router

    router.include_router(analytics_router)
    logger.info("Portal: analytics_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar analytics_controller: %s", e)

try:
    from .controllers.whatsapp_controller import router as whatsapp_router

    router.include_router(whatsapp_router)
    logger.info("Portal: whatsapp_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar whatsapp_controller: %s", e)

try:
    from .controllers.kit_approval_controller import router as kit_approval_router

    router.include_router(kit_approval_router)
    logger.info("Portal: kit_approval_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar kit_approval_controller: %s", e)

try:
    from .controllers.mcp_controller import router as mcp_router

    router.include_router(mcp_router)
    logger.info("Portal: mcp_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar mcp_controller: %s", e)

try:
    from .controllers.settings_controller import router as settings_router

    router.include_router(settings_router)
    logger.info("Portal: settings_controller registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar settings_controller: %s", e)

try:
    from .controllers.operacao_controller import router as operacao_router

    router.include_router(operacao_router)
    logger.info("Portal: operacao_controller (Raio-X) registrado")
except ImportError as e:
    logger.warning("Portal: falha ao importar operacao_controller: %s", e)
