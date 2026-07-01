"""
GP Orchestrator Agent - Cerebro central de Gestao de Pessoas.
Coordena todos os 7 modulos, resolve conflitos, garante auditoria.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..core.events import Event, EventPriority, GPEventTypes
from .base_agent import AgentHealth, AgentState, BaseAgent

logger = logging.getLogger(__name__)


class ConflictType(StrEnum):
    """Tipos de conflitos que podem ocorrer."""

    RESOURCE_LOCK = "resource_lock"
    EVENT_ORDER = "event_order"
    DATA_INCONSISTENCY = "data_inconsistency"
    PRIORITY_OVERRIDE = "priority_override"


@dataclass
class Conflict:
    """Representa um conflito entre agents."""

    conflict_id: str
    conflict_type: ConflictType
    agents_involved: list[str]
    resource: str
    description: str
    timestamp: datetime
    resolved: bool = False
    resolution: str | None = None


class GPOrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent - Coordena toda comunicacao entre modulos.

    Responsabilidades:
    1. Receber TODOS os eventos do andar
    2. Decidir roteamento (quem precisa saber?)
    3. Resolver conflitos de precedencia
    4. Garantir auditoria completa
    5. Monitorar saude dos agents
    6. Emitir alertas de sistema
    """

    AGENT_NAME = "GP_ORCHESTRATOR"
    AGENT_VERSION = "1.0.0"

    # Matriz de roteamento: evento -> modulos destino
    ROUTING_MATRIX: dict[str, list[str]] = {
        # Documento
        GPEventTypes.DOCUMENTO_CRIADO: ["GED", "PORTAL"],
        GPEventTypes.DOCUMENTO_ASSINADO: ["DP", "GED", "PORTAL"],
        GPEventTypes.DOCUMENTO_ARQUIVADO: ["GED"],
        # Ponto
        GPEventTypes.PONTO_BATIDO: ["DP", "OPS", "PORTAL"],
        GPEventTypes.PONTO_ATRASO: ["DP", "OPS", "PORTAL"],
        GPEventTypes.PONTO_FALTA: ["DP", "OPS", "PORTAL"],
        GPEventTypes.PONTO_MES_FECHADO: ["DP", "GED"],
        # Funcionario
        GPEventTypes.FUNCIONARIO_ADMITIDO: [
            "DP",
            "RH",
            "GED",
            "OPS",
            "SST",
            "PONTO",
            "PORTAL",
        ],
        GPEventTypes.FUNCIONARIO_DEMITIDO: [
            "DP",
            "RH",
            "GED",
            "OPS",
            "SST",
            "PONTO",
            "PORTAL",
        ],
        # Disciplinar
        GPEventTypes.ADVERTENCIA_APLICADA: ["DP", "RH", "GED", "PORTAL"],
        GPEventTypes.SUSPENSAO_APLICADA: ["DP", "RH", "GED", "PORTAL"],
        # SST
        GPEventTypes.ASO_REALIZADO: ["DP", "GED", "PORTAL"],
        GPEventTypes.EPI_ENTREGUE: ["DP", "GED", "PORTAL"],
        GPEventTypes.CAT_ABERTA: ["DP", "GED", "OPS", "PORTAL"],
        GPEventTypes.LAUDO_EMITIDO: ["DP", "GED", "PORTAL"],
        # Treinamento
        GPEventTypes.TREINAMENTO_REALIZADO: ["DP", "GED", "PORTAL"],
        GPEventTypes.CERTIFICADO_EMITIDO: ["DP", "GED", "OPS", "PORTAL"],
        # Folha
        GPEventTypes.FOLHA_FECHADA: ["GED", "PORTAL"],
        # Kit
        GPEventTypes.KIT_MONTADO: ["PORTAL"],
        GPEventTypes.KIT_ENVIADO: ["PORTAL"],
        # Escala
        GPEventTypes.ESCALA_PUBLICADA: ["PONTO", "PORTAL"],
    }

    # Regras de precedencia (menor = maior prioridade)
    PRECEDENCE_RULES: dict[str, int] = {
        "SST": 1,
        "PONTO": 2,
        "DP": 3,
        "OPS": 4,
        "RH": 5,
        "GED": 6,
        "PORTAL": 7,
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._registered_agents: dict[str, AgentHealth] = {}
        self._pending_conflicts: list[Conflict] = []
        self._resolved_conflicts: list[Conflict] = []
        self._event_routing_stats: dict[str, int] = {}

    @property
    def handled_events(self) -> list[str]:
        """Orchestrator escuta TODOS os eventos gp.*"""
        return ["*"]

    async def _process_event(self, event: Event) -> None:
        """Processa eventos recebidos."""
        if event.source_module == self.AGENT_NAME:
            return

        destinations = self._get_routing_destinations(event)
        conflict = await self._check_conflict(event)

        if conflict:
            await self._handle_conflict(conflict, event)
            return

        await self._route_event(event, destinations)
        self._update_stats(event)

    def _get_routing_destinations(self, event: Event) -> list[str]:
        """Determina para quais modulos o evento deve ser roteado."""
        if event.affected_modules:
            return event.affected_modules

        destinations = list(self.ROUTING_MATRIX.get(event.event_type, []))

        if event.source_module in destinations:
            destinations = [d for d in destinations if d != event.source_module]

        return destinations

    async def _check_conflict(self, event: Event) -> Conflict | None:
        """Verifica se ha conflito com eventos pendentes."""
        return None

    async def _handle_conflict(self, conflict: Conflict, event: Event) -> None:
        """Resolve um conflito detectado."""
        self._pending_conflicts.append(conflict)

        await self.emit_event(
            event_type=GPEventTypes.ORCHESTRATOR_CONFLICT,
            payload={
                "conflict_id": conflict.conflict_id,
                "conflict_type": conflict.conflict_type.value,
                "agents_involved": conflict.agents_involved,
                "resource": conflict.resource,
                "original_event_id": event.event_id,
            },
            priority=EventPriority.ALTO,
        )

        resolution = self._resolve_conflict(conflict)
        if resolution:
            conflict.resolved = True
            conflict.resolution = resolution
            self._pending_conflicts.remove(conflict)
            self._resolved_conflicts.append(conflict)

            await self.emit_event(
                event_type=GPEventTypes.ORCHESTRATOR_RESOLVED,
                payload={
                    "conflict_id": conflict.conflict_id,
                    "resolution": resolution,
                },
                priority=EventPriority.NORMAL,
            )

    def _resolve_conflict(self, conflict: Conflict) -> str | None:
        """Tenta resolver um conflito automaticamente."""
        if len(conflict.agents_involved) < 2:
            return "no_conflict"

        sorted_agents = sorted(
            conflict.agents_involved,
            key=lambda a: self.PRECEDENCE_RULES.get(a, 99),
        )
        winner = sorted_agents[0]
        return f"resolved_in_favor_of_{winner}"

    async def _route_event(self, event: Event, destinations: list[str]) -> None:
        """Roteia um evento para os destinos determinados."""
        await self.emit_event(
            event_type=GPEventTypes.ORCHESTRATOR_ROUTED,
            payload={
                "original_event_id": event.event_id,
                "original_event_type": event.event_type,
                "source_module": event.source_module,
                "destinations": destinations,
            },
            priority=EventPriority.BAIXO,
        )
        logger.debug(f"Evento roteado: {event.event_type} -> {destinations}")

    def _update_stats(self, event: Event) -> None:
        """Atualiza estatisticas de roteamento."""
        event_type = event.event_type
        self._event_routing_stats[event_type] = self._event_routing_stats.get(event_type, 0) + 1

    # Agent Management
    def register_agent(self, agent_health: AgentHealth) -> None:
        """Registra um Agent no Orchestrator."""
        self._registered_agents[agent_health.agent_name] = agent_health
        logger.info(f"Agent registrado: {agent_health.agent_name}")

    def update_agent_health(self, agent_health: AgentHealth) -> None:
        """Atualiza status de saude de um Agent."""
        self._registered_agents[agent_health.agent_name] = agent_health

    def get_agent_health(self, agent_name: str) -> AgentHealth | None:
        """Retorna status de saude de um Agent."""
        return self._registered_agents.get(agent_name)

    def get_all_agents_health(self) -> dict[str, AgentHealth]:
        """Retorna status de saude de todos os Agents."""
        return self._registered_agents.copy()

    def get_unhealthy_agents(self) -> list[str]:
        """Retorna lista de Agents nao saudaveis."""
        return [name for name, health in self._registered_agents.items() if not health.is_healthy]

    # Alertas
    async def emit_alert(
        self,
        message: str,
        severity: str = "warning",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emite um alerta de sistema."""
        await self.emit_event(
            event_type=GPEventTypes.ORCHESTRATOR_ALERT,
            payload={
                "message": message,
                "severity": severity,
                "data": data or {},
            },
            priority=(EventPriority.ALTO if severity == "error" else EventPriority.NORMAL),
        )

    async def health_check(self) -> dict[str, Any]:
        """Executa health check de todos os Agents."""
        unhealthy = self.get_unhealthy_agents()
        if unhealthy:
            await self.emit_alert(
                message=f"Agents nao saudaveis: {unhealthy}",
                severity="warning",
                data={"unhealthy_agents": unhealthy},
            )
        return {
            "orchestrator_healthy": self._state != AgentState.ERROR,
            "total_agents": len(self._registered_agents),
            "healthy_agents": len(self._registered_agents) - len(unhealthy),
            "unhealthy_agents": unhealthy,
            "pending_conflicts": len(self._pending_conflicts),
            "events_routed_total": sum(self._event_routing_stats.values()),
        }

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatisticas do Orchestrator."""
        return {
            "agent_name": self.AGENT_NAME,
            "state": self._state.value,
            "registered_agents": list(self._registered_agents.keys()),
            "pending_conflicts": len(self._pending_conflicts),
            "resolved_conflicts": len(self._resolved_conflicts),
            "event_routing_stats": self._event_routing_stats,
            "health": self.get_health().to_dict(),
        }
