"""
Base Agent - Classe base para todos os Agents de Gestao de Pessoas.
"""

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..core.audit import (
    AuditAction,
    AuditActor,
    AuditContext,
    AuditLog,
    AuditLogger,
    get_audit_logger,
)
from ..core.events import Event, EventPriority, GPEventBus, get_event_bus
from ..core.events import EventActor as EventActorCls
from ..core.events import EventContext as EventContextCls

logger = logging.getLogger(__name__)


class AgentState(StrEnum):
    """Estados possiveis de um Agent."""

    INITIALIZING = "initializing"
    IDLE = "idle"
    PROCESSING = "processing"
    PAUSED = "paused"
    ERROR = "error"
    SHUTDOWN = "shutdown"


@dataclass
class AgentHealth:
    """Status de saude de um Agent."""

    agent_name: str
    state: AgentState
    last_heartbeat: datetime
    events_processed: int
    events_failed: int
    queue_size: int
    uptime_seconds: float
    error_message: str | None = None

    @property
    def is_healthy(self) -> bool:
        return self.state not in [AgentState.ERROR, AgentState.SHUTDOWN]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "state": self.state.value,
            "is_healthy": self.is_healthy,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "events_processed": self.events_processed,
            "events_failed": self.events_failed,
            "queue_size": self.queue_size,
            "uptime_seconds": self.uptime_seconds,
            "error_message": self.error_message,
        }


class BaseAgent(ABC):
    """
    Classe base para todos os Agents de Gestao de Pessoas.

    Subclasses devem implementar:
    - AGENT_NAME: Nome do agent
    - AGENT_VERSION: Versao
    - handled_events: Lista de eventos que processa
    - _process_event: Logica de processamento
    """

    AGENT_NAME: str = "BASE_AGENT"
    AGENT_VERSION: str = "1.0.0"

    def __init__(
        self,
        event_bus: GPEventBus | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.event_bus = event_bus or get_event_bus()
        self.audit_logger = audit_logger or get_audit_logger()

        self._state = AgentState.INITIALIZING
        self._start_time = datetime.utcnow()
        self._events_processed = 0
        self._events_failed = 0
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._skills: dict[str, Any] = {}

        self._setup()

    @property
    @abstractmethod
    def handled_events(self) -> list[str]:
        """Lista de tipos de eventos que este Agent processa."""

    @abstractmethod
    async def _process_event(self, event: Event) -> None:
        """Processa um evento recebido."""

    def _setup(self) -> None:
        """Configuracao inicial do Agent."""
        for event_type in self.handled_events:
            self.event_bus.subscribe(event_type, self._on_event_received)
        self._state = AgentState.IDLE
        logger.info(f"{self.AGENT_NAME} v{self.AGENT_VERSION} inicializado")

    async def start(self) -> None:
        """Inicia o Agent."""
        if self._state == AgentState.SHUTDOWN:
            raise RuntimeError(f"{self.AGENT_NAME} foi desligado")
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info(f"{self.AGENT_NAME} iniciado")

    async def stop(self) -> None:
        """Para o Agent graciosamente."""
        self._state = AgentState.SHUTDOWN
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
        logger.info(f"{self.AGENT_NAME} parado")

    async def pause(self) -> None:
        """Pausa o processamento."""
        self._state = AgentState.PAUSED

    async def resume(self) -> None:
        """Retoma o processamento."""
        self._state = AgentState.IDLE

    async def _on_event_received(self, event: Event) -> None:
        """Callback quando um evento e recebido."""
        await self._event_queue.put(event)

    async def _worker_loop(self) -> None:
        """Loop principal de processamento."""
        while self._state != AgentState.SHUTDOWN:
            if self._state == AgentState.PAUSED:
                await asyncio.sleep(0.1)
                continue
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                self._state = AgentState.PROCESSING
                await self._handle_event(event)
                self._state = AgentState.IDLE
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._state = AgentState.ERROR
                self._events_failed += 1
                logger.error(f"{self.AGENT_NAME} erro no worker: {e}")
                await self._handle_error(e)
                self._state = AgentState.IDLE

    async def _handle_event(self, event: Event) -> None:
        """Processa um evento e atualiza metricas."""
        try:
            logger.debug(f"{self.AGENT_NAME} processando: {event.event_type} [id={event.event_id[:8]}]")
            await self._process_event(event)
            self._events_processed += 1
        except Exception as e:
            self._events_failed += 1
            logger.error(f"{self.AGENT_NAME} erro ao processar evento: {e}")
            raise

    async def _handle_error(self, error: Exception) -> None:
        """Trata erros."""
        await self.event_bus.emit(
            event_type="gp.orchestrator.alert",
            payload={
                "agent": self.AGENT_NAME,
                "error": str(error),
                "severity": "error",
            },
            source_module=self.AGENT_NAME,
            priority=EventPriority.ALTO,
        )

    async def emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        priority: EventPriority = EventPriority.NORMAL,
        affected_modules: list[str] | None = None,
        actor: AuditActor | None = None,
        context: AuditContext | None = None,
    ) -> Event:
        """Emite um evento deste Agent."""
        event_actor = None
        if actor:
            event_actor = EventActorCls(
                user_id=actor.user_id,
                user_name=actor.user_name,
                user_role=actor.user_role,
                user_module=actor.user_module,
            )
        event_context = None
        if context:
            event_context = EventContextCls(
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                device_type=context.device_type,
                session_id=context.session_id,
                geolocation=context.geolocation,
            )
        return await self.event_bus.emit(
            event_type=event_type,
            payload=payload,
            source_module=self.AGENT_NAME,
            priority=priority,
            actor=event_actor,
            context=event_context,
            affected_modules=affected_modules,
        )

    async def audit(
        self,
        action: AuditAction,
        entity: str,
        entity_id: str,
        description: str,
        actor: AuditActor,
        context: AuditContext,
        **kwargs,
    ) -> AuditLog:
        """Registra uma acao no log de auditoria."""
        return await self.audit_logger.log(
            action=action,
            entity=entity,
            entity_id=entity_id,
            description=description,
            source_module=self.AGENT_NAME,
            actor=actor,
            context=context,
            **kwargs,
        )

    def register_skill(self, skill_name: str, skill_instance: Any) -> None:
        """Registra um Skill neste Agent."""
        self._skills[skill_name] = skill_instance

    def get_skill(self, skill_name: str) -> Any | None:
        """Retorna um Skill registrado."""
        return self._skills.get(skill_name)

    def get_health(self) -> AgentHealth:
        """Retorna status de saude do Agent."""
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        return AgentHealth(
            agent_name=self.AGENT_NAME,
            state=self._state,
            last_heartbeat=datetime.utcnow(),
            events_processed=self._events_processed,
            events_failed=self._events_failed,
            queue_size=self._event_queue.qsize(),
            uptime_seconds=uptime,
        )
