"""
Categoria: Gestao de Pessoas (People Management)

Agrupa os modulos:
- hr (Departamento Pessoal)
- human_resources (Recursos Humanos)
- operations (Operacoes)
- employee_portal (Portal do Funcionario)
- ged (Gestao Eletronica de Documentos / Kits Documentais)

Integracao bidirecional entre todos os modulos.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/people-management", tags=["Gestao de Pessoas"])


def register_routers() -> None:
    """Registra sub-routers quando disponiveis."""
    try:
        from .hr.aggregator import router as hr_router

        router.include_router(hr_router)
    except Exception:
        pass

    try:
        from .human_resources.aggregator import router as human_resources_router

        router.include_router(human_resources_router)
    except Exception:
        pass

    # REMOVIDO 2026-07-09 (fase 2 do enxugamento): espelho /operations/* desativado.
    # Rotas exclusivas migradas p/ /operacional/unificado/* e /operacional/scale-optimizer/*.
    # Consumidor migrado (dashboardStatsService -> /operacional/*).

    try:
        from .employee_portal.aggregator import router as portal_router

        router.include_router(portal_router)
    except Exception:
        pass

    try:
        from .ged.aggregator import router as ged_router

        router.include_router(ged_router)
    except Exception:
        pass

    try:
        from .integration.aggregator import router as integration_router

        router.include_router(integration_router)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Integration router not loaded: {e}")

    # Ponto Eletronico
    try:
        from .ponto.controllers import router as ponto_router

        router.include_router(ponto_router)
    except Exception:
        pass

    # Folha de Pagamento
    try:
        from .folha.controllers.folha_controller import router as folha_router

        router.include_router(folha_router)
    except Exception:
        pass

    # SST - Saude e Seguranca
    try:
        from .sst.controllers import router as sst_router

        router.include_router(sst_router)
    except Exception:
        pass

    # Certificacao Humana (gate C dos calculos de risco juridico)
    try:
        from .certification.controllers import router as certification_router

        router.include_router(certification_router)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Certification router not loaded: {e}")

    # WebSocket GP
    try:
        from .core.websocket import gp_ws_router

        router.include_router(gp_ws_router)
    except Exception:
        pass


register_routers()


# ---------------------------------------------------------------------------
# Controle de acesso por módulo (padrão modules/financeiro/__init__.py):
# FastAPI não propaga router.dependencies no include_router — a dependency é
# injetada em CADA ROTA individual, antes do include em main_production.py.
#
#   /people-management/portal/*  → SEM gate (audience própria do funcionário)
#   /people-management/sst/*     → module:sst
#   /people-management/ged/*     → module:ged
#   demais rotas                 → module:dp
#
# requer_modulo já deixa passar 'all' e o CEO. Role admin NÃO bypassa (correto).
# ---------------------------------------------------------------------------
def _gatear_rotas_por_modulo() -> None:
    from fastapi.routing import APIRoute

    from core.permissions import requer_modulo

    dep_dp = requer_modulo("dp")
    dep_sst = requer_modulo("sst")
    dep_ged = requer_modulo("ged")

    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue  # websockets (gp_ws_router) ficam fora do gate HTTP
        path = route.path
        if path.startswith("/people-management/portal"):
            continue  # Portal do Funcionário: auth própria, não gatear
        if path.startswith("/people-management/sst"):
            route.dependencies.append(dep_sst)
        elif path.startswith("/people-management/ged"):
            route.dependencies.append(dep_ged)
        else:
            route.dependencies.append(dep_dp)


_gatear_rotas_por_modulo()
