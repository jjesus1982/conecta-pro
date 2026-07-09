"""Controllers do módulo GED (Gestão Eletrônica de Documentos)."""

from modules.ged.controllers.document_controller import router as document_router
from modules.ged.controllers.document_share_controller import router as share_router
from modules.ged.controllers.document_signature_controller import (
    router as signature_router,
)
from modules.ged.controllers.document_tag_controller import router as tag_router
from modules.ged.controllers.document_version_controller import (
    router as version_router,
)
from modules.ged.controllers.folder_controller import router as folder_router
from modules.ged.controllers.ged_config_controller import router as config_router
from modules.ged.controllers.ged_stats_controller import router as stats_router

try:
    from modules.ged.controllers.ged_integration_controller import (
        router as integration_router,
    )
except ImportError:
    integration_router = None  # type: ignore[assignment]

__all__ = [
    "folder_router",
    "document_router",
    "version_router",
    "share_router",
    "tag_router",
    "signature_router",
    "stats_router",
    "config_router",
    "integration_router",
]


# ---------------------------------------------------------------------------
# Controle de acesso por módulo — module:ged (padrão modules/financeiro/__init__.py).
# Dependency injetada em CADA ROTA individual, no import do pacote (antes de
# main_production.py obter qualquer router deste pacote).
#
# NÃO gateados aqui (domínio financeiro, montados em /financial no main):
#   nfse_controller, financial_overview_controller — fora do escopo module:ged.
#
# requer_modulo já deixa passar 'all' e o CEO. Role admin NÃO bypassa (correto).
# ---------------------------------------------------------------------------
def _gatear_rotas_ged() -> None:
    import importlib

    from core.permissions import requer_modulo

    dep_ged = requer_modulo("ged")

    routers = [
        folder_router,
        document_router,
        version_router,
        share_router,
        tag_router,
        signature_router,
        stats_router,
        config_router,
    ]
    if integration_router is not None:
        routers.append(integration_router)

    # Montados direto no main sob /ged (fora deste __all__)
    for mod_name in (
        "ged_certidoes_controller",
        "auto_assemble_controller",
        "kit_pdf_controller",
        "kit_real_controller",
    ):
        try:
            mod = importlib.import_module(f"modules.ged.controllers.{mod_name}")
            routers.append(mod.router)
        except Exception:  # noqa: BLE001 — controller ausente/quebrado não registra no main
            pass

    for r in routers:
        for route in r.routes:
            route.dependencies.append(dep_ged)


_gatear_rotas_ged()
