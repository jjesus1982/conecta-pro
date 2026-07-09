"""
Controllers do modulo GED — Gestao Eletronica de Documentos.

Exporta todos os routers para registro no aggregator.
"""

from modules.people_management.ged.controllers.client_controller import router as client_router
from modules.people_management.ged.controllers.document_controller import router as document_router
from modules.people_management.ged.controllers.kit_controller import router as kit_router

__all__ = [
    "client_router",
    "document_router",
    "kit_router",
]


# ---------------------------------------------------------------------------
# Controle de acesso por módulo — module:ged.
# As rotas do aggregator (/people-management/ged/*) são gateadas no
# modules/people_management/__init__.py por prefixo. A coleta automática é
# montada DIRETO no main (prefix /ged) e bypassa o aggregator — gate aqui.
# ---------------------------------------------------------------------------
def _gatear_coleta_automatica() -> None:
    import importlib

    from core.permissions import requer_modulo

    dep_ged = requer_modulo("ged")
    try:
        mod = importlib.import_module(
            "modules.people_management.ged.controllers.coleta_automatica_controller"
        )
        for route in mod.router.routes:
            route.dependencies.append(dep_ged)
    except Exception:  # noqa: BLE001 — se falhar aqui, falha no main e a rota nem registra
        pass


_gatear_coleta_automatica()
