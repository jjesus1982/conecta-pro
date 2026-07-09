"""Controllers do módulo CRM."""

from .commission_controller import router as commission_router
from .contract_controller import router as contract_router
from .dashboard_controller import router as dashboard_router
from .lead_controller import router as lead_router
from .opportunity_controller import router as opportunity_router
from .proposal_controller import router as proposal_router

__all__ = [
    "lead_router",
    "opportunity_router",
    "proposal_router",
    "commission_router",
    "dashboard_router",
    "contract_router",
]


# ---------------------------------------------------------------------------
# Controle de acesso por módulo — module:crm (padrão modules/financeiro/__init__.py).
# FastAPI não propaga router.dependencies no include_router — a dependency é
# injetada em CADA ROTA individual, aqui no import do pacote (que sempre roda
# antes de main_production.py obter qualquer router deste pacote).
#
# Também gateia os controllers montados DIRETO no main (fora do agregador
# comercial): client, enrichment, contact, growth, marketing, consultor_cmo.
# Se um import falhar aqui, o mesmo import falha no main → a rota nem registra
# (nunca fica registrada sem gate).
#
# requer_modulo já deixa passar 'all' e o CEO. Role admin NÃO bypassa (correto).
# ---------------------------------------------------------------------------
def _gatear_rotas_crm() -> None:
    import importlib

    from core.permissions import requer_modulo

    dep_crm = requer_modulo("crm")

    routers = [
        lead_router,
        opportunity_router,
        proposal_router,
        commission_router,
        dashboard_router,
        contract_router,
    ]

    for mod_name in (
        "client_controller",
        "enrichment_controller",
        "contact_controller",
        "growth_controller",
        "marketing_controller",
        "consultor_cmo_controller",
    ):
        try:
            mod = importlib.import_module(f"modules.crm.controllers.{mod_name}")
            routers.append(mod.router)
        except Exception:  # noqa: BLE001 — controller ausente/quebrado não registra no main
            pass

    for r in routers:
        for route in r.routes:
            route.dependencies.append(dep_crm)


_gatear_rotas_crm()
