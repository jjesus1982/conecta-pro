"""
GP Event Bus — agora aponta para o ConectaEventBus unificado.
Retrocompatibilidade total: GPEventBus, Event, get_event_bus mantidos.
"""

# Importar do barramento unificado
from infrastructure.event_bus import (
    ConectaEvent as Event,  # alias retrocompat
)
from infrastructure.event_bus import (
    ConectaEventBus as GPEventBus,  # alias retrocompat
)
from infrastructure.event_bus import (
    EventActor,
    EventContext,
    EventPriority,
    EventTypes,
    event_bus,
    get_event_bus,
)

# QUARENTENA Item −1 (2026-07-01): GPEventTypes (gp.*) movido p/ _quarentena_item1/ —
# registro órfão usado só pelos agents (também quarentenados). Use EventTypes (dp.*) de infra/event_bus.
from .handlers import EventHandler

__all__ = [
    "GPEventBus",
    "Event",
    "EventPriority",
    "EventActor",
    "EventContext",
    "EventTypes",
    "EventHandler",
    "event_bus",
    "get_event_bus",
]
