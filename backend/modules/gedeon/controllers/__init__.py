"""
Controllers do GEDEON (robô GED).

Controle de acesso por módulo — module:ged (padrão modules/financeiro/__init__.py).
FastAPI não propaga router.dependencies no include_router — a dependency é
injetada em CADA ROTA individual, aqui no import do pacote (que sempre roda
antes de main_production.py obter qualquer router deste pacote).

Se um import falhar aqui, o mesmo import falha no main → a rota nem registra
(nunca fica registrada sem gate).

requer_modulo já deixa passar 'all' e o CEO. Role admin NÃO bypassa (correto).
"""


def _gatear_rotas_ged() -> None:
    import importlib

    from core.permissions import requer_modulo

    dep_ged = requer_modulo("ged")

    modulos = [
        "modules.gedeon.controllers.gedeon_controller",
        "modules.gedeon.controllers.kit_controller",
        "modules.gedeon.controllers.orquestrador_controller",
        "modules.gedeon.controllers.cnd_controller",
        "modules.gedeon.controllers.onvio_controller",
        "modules.gedeon.controllers.consultor_controller",
        # Onvio (pacote separado, montado direto no main em /onvio)
        "modules.gedeon.onvio.controllers.onvio_controller",
    ]

    for nome in modulos:
        try:
            mod = importlib.import_module(nome)
            for route in mod.router.routes:
                route.dependencies.append(dep_ged)
        except Exception:  # noqa: BLE001 — controller ausente/quebrado não registra no main
            pass


_gatear_rotas_ged()
