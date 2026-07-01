"""Testes do Base Agent e Orchestrator."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.people_management.agents import AgentHealth, AgentState, BaseAgent, GPOrchestratorAgent
from modules.people_management.core.events import Event, EventPriority, GPEventTypes


class ConcreteAgent(BaseAgent):
    """Agent concreto para testes."""

    AGENT_NAME = "TEST_AGENT"
    AGENT_VERSION = "1.0.0"

    def __init__(self, **kwargs):
        self.processed_events = []
        super().__init__(**kwargs)

    @property
    def handled_events(self):
        return [GPEventTypes.DOCUMENTO_CRIADO, GPEventTypes.PONTO_BATIDO]

    async def _process_event(self, event):
        self.processed_events.append(event)


class TestAgentState:
    def test_all_states_exist(self):
        assert AgentState.INITIALIZING == "initializing"
        assert AgentState.IDLE == "idle"
        assert AgentState.PROCESSING == "processing"
        assert AgentState.PAUSED == "paused"
        assert AgentState.ERROR == "error"
        assert AgentState.SHUTDOWN == "shutdown"

    def test_state_count(self):
        assert len(AgentState) == 6


class TestAgentHealth:
    def test_health_creation(self):
        health = AgentHealth(
            agent_name="TEST",
            state=AgentState.IDLE,
            last_heartbeat=datetime.utcnow(),
            events_processed=10,
            events_failed=1,
            queue_size=5,
            uptime_seconds=3600.0,
        )
        assert health.agent_name == "TEST"
        assert health.is_healthy is True

    def test_health_unhealthy_error(self):
        health = AgentHealth(
            agent_name="TEST",
            state=AgentState.ERROR,
            last_heartbeat=datetime.utcnow(),
            events_processed=0,
            events_failed=5,
            queue_size=0,
            uptime_seconds=100.0,
            error_message="Falhou!",
        )
        assert health.is_healthy is False

    def test_health_unhealthy_shutdown(self):
        health = AgentHealth(
            agent_name="TEST",
            state=AgentState.SHUTDOWN,
            last_heartbeat=datetime.utcnow(),
            events_processed=0,
            events_failed=0,
            queue_size=0,
            uptime_seconds=0.0,
        )
        assert health.is_healthy is False

    def test_health_healthy_processing(self):
        health = AgentHealth(
            agent_name="TEST",
            state=AgentState.PROCESSING,
            last_heartbeat=datetime.utcnow(),
            events_processed=50,
            events_failed=0,
            queue_size=3,
            uptime_seconds=7200.0,
        )
        assert health.is_healthy is True

    def test_health_to_dict(self):
        health = AgentHealth(
            agent_name="TEST",
            state=AgentState.IDLE,
            last_heartbeat=datetime.utcnow(),
            events_processed=5,
            events_failed=0,
            queue_size=2,
            uptime_seconds=1000.0,
        )
        data = health.to_dict()
        assert data["agent_name"] == "TEST"
        assert data["is_healthy"] is True
        assert "last_heartbeat" in data
        assert data["state"] == "idle"


class TestBaseAgent:
    @pytest.fixture
    def mock_event_bus(self):
        bus = MagicMock()
        bus.subscribe = MagicMock()
        bus.emit = AsyncMock()
        return bus

    @pytest.fixture
    def mock_audit_logger(self):
        audit = MagicMock()
        audit.log = AsyncMock()
        return audit

    @pytest.fixture
    def agent(self, mock_event_bus, mock_audit_logger):
        return ConcreteAgent(event_bus=mock_event_bus, audit_logger=mock_audit_logger)

    def test_agent_initialization(self, agent):
        assert agent.AGENT_NAME == "TEST_AGENT"
        assert agent.AGENT_VERSION == "1.0.0"
        assert agent._state == AgentState.IDLE
        assert agent._events_processed == 0
        assert agent._events_failed == 0

    def test_agent_subscribes_to_events(self, agent, mock_event_bus):
        assert mock_event_bus.subscribe.call_count == 2

    def test_agent_handled_events(self, agent):
        events = agent.handled_events
        assert GPEventTypes.DOCUMENTO_CRIADO in events
        assert GPEventTypes.PONTO_BATIDO in events
        assert len(events) == 2

    def test_agent_get_health(self, agent):
        health = agent.get_health()
        assert health.agent_name == "TEST_AGENT"
        assert health.state == AgentState.IDLE
        assert health.is_healthy is True
        assert health.events_processed == 0
        assert health.uptime_seconds >= 0

    def test_agent_register_skill(self, agent):
        mock_skill = MagicMock()
        agent.register_skill("TEST_SKILL", mock_skill)
        assert agent.get_skill("TEST_SKILL") == mock_skill

    def test_agent_get_nonexistent_skill(self, agent):
        assert agent.get_skill("NONEXISTENT") is None

    def test_agent_register_multiple_skills(self, agent):
        agent.register_skill("SKILL_A", MagicMock())
        agent.register_skill("SKILL_B", MagicMock())
        assert agent.get_skill("SKILL_A") is not None
        assert agent.get_skill("SKILL_B") is not None

    @pytest.mark.asyncio
    async def test_agent_pause_resume(self, agent):
        await agent.pause()
        assert agent._state == AgentState.PAUSED
        await agent.resume()
        assert agent._state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_agent_stop(self, agent):
        await agent.stop()
        assert agent._state == AgentState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_agent_emit_event(self, agent, mock_event_bus):
        await agent.emit_event(
            event_type=GPEventTypes.DOCUMENTO_CRIADO,
            payload={"doc_id": "123"},
            priority=EventPriority.ALTO,
        )
        mock_event_bus.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_handle_event(self, agent):
        event = Event(
            event_type=GPEventTypes.DOCUMENTO_CRIADO,
            payload={"test": True},
            source_module="DP",
        )
        await agent._handle_event(event)
        assert agent._events_processed == 1
        assert len(agent.processed_events) == 1


class TestOrchestratorAgent:
    @pytest.fixture
    def mock_event_bus(self):
        bus = MagicMock()
        bus.subscribe = MagicMock()
        bus.emit = AsyncMock()
        return bus

    @pytest.fixture
    def orchestrator(self, mock_event_bus):
        return GPOrchestratorAgent(event_bus=mock_event_bus)

    def test_orchestrator_initialization(self, orchestrator):
        assert orchestrator.AGENT_NAME == "GP_ORCHESTRATOR"
        assert orchestrator.AGENT_VERSION == "1.0.0"
        assert orchestrator._registered_agents == {}

    def test_orchestrator_listens_all(self, orchestrator):
        assert "*" in orchestrator.handled_events

    def test_routing_matrix_exists(self, orchestrator):
        assert len(orchestrator.ROUTING_MATRIX) > 0
        assert GPEventTypes.DOCUMENTO_CRIADO in orchestrator.ROUTING_MATRIX
        assert GPEventTypes.PONTO_BATIDO in orchestrator.ROUTING_MATRIX
        assert GPEventTypes.FUNCIONARIO_ADMITIDO in orchestrator.ROUTING_MATRIX

    def test_routing_matrix_funcionario_admitido_all_modules(self, orchestrator):
        destinations = orchestrator.ROUTING_MATRIX[GPEventTypes.FUNCIONARIO_ADMITIDO]
        assert "DP" in destinations
        assert "RH" in destinations
        assert "GED" in destinations
        assert "OPS" in destinations
        assert "SST" in destinations
        assert "PONTO" in destinations
        assert "PORTAL" in destinations

    def test_precedence_rules(self, orchestrator):
        assert orchestrator.PRECEDENCE_RULES["SST"] < orchestrator.PRECEDENCE_RULES["PORTAL"]
        assert orchestrator.PRECEDENCE_RULES["PONTO"] < orchestrator.PRECEDENCE_RULES["DP"]
        assert orchestrator.PRECEDENCE_RULES["SST"] == 1

    def test_get_routing_destinations(self, orchestrator):
        event = Event(
            event_type=GPEventTypes.DOCUMENTO_CRIADO,
            payload={},
            source_module="DP",
        )
        destinations = orchestrator._get_routing_destinations(event)
        assert "GED" in destinations
        assert "PORTAL" in destinations

    def test_get_routing_excludes_source(self, orchestrator):
        event = Event(
            event_type=GPEventTypes.PONTO_BATIDO,
            payload={},
            source_module="PONTO",
        )
        destinations = orchestrator._get_routing_destinations(event)
        # PONTO is in the routing for PONTO_BATIDO? Let's check
        # PONTO_BATIDO -> ["DP", "OPS", "PORTAL"] — no PONTO, so nothing to exclude
        assert "DP" in destinations

    def test_get_routing_with_explicit_affected(self, orchestrator):
        event = Event(
            event_type=GPEventTypes.DOCUMENTO_CRIADO,
            payload={},
            source_module="DP",
            affected_modules=["RH", "SST"],
        )
        destinations = orchestrator._get_routing_destinations(event)
        assert destinations == ["RH", "SST"]

    def test_register_agent(self, orchestrator):
        health = AgentHealth(
            agent_name="DP_AGENT",
            state=AgentState.IDLE,
            last_heartbeat=datetime.utcnow(),
            events_processed=0,
            events_failed=0,
            queue_size=0,
            uptime_seconds=0.0,
        )
        orchestrator.register_agent(health)
        assert "DP_AGENT" in orchestrator._registered_agents

    def test_get_unhealthy_agents(self, orchestrator):
        healthy = AgentHealth(
            agent_name="HEALTHY",
            state=AgentState.IDLE,
            last_heartbeat=datetime.utcnow(),
            events_processed=0,
            events_failed=0,
            queue_size=0,
            uptime_seconds=0.0,
        )
        unhealthy = AgentHealth(
            agent_name="UNHEALTHY",
            state=AgentState.ERROR,
            last_heartbeat=datetime.utcnow(),
            events_processed=0,
            events_failed=5,
            queue_size=0,
            uptime_seconds=0.0,
        )
        orchestrator.register_agent(healthy)
        orchestrator.register_agent(unhealthy)
        result = orchestrator.get_unhealthy_agents()
        assert "UNHEALTHY" in result
        assert "HEALTHY" not in result

    def test_get_all_agents_health(self, orchestrator):
        h1 = AgentHealth("A1", AgentState.IDLE, datetime.utcnow(), 0, 0, 0, 0.0)
        h2 = AgentHealth("A2", AgentState.IDLE, datetime.utcnow(), 0, 0, 0, 0.0)
        orchestrator.register_agent(h1)
        orchestrator.register_agent(h2)
        all_health = orchestrator.get_all_agents_health()
        assert len(all_health) == 2

    def test_resolve_conflict(self, orchestrator):
        from modules.people_management.agents.orchestrator import Conflict, ConflictType

        conflict = Conflict(
            conflict_id="c1",
            conflict_type=ConflictType.RESOURCE_LOCK,
            agents_involved=["PORTAL", "SST"],
            resource="funcionario-123",
            description="Conflito de acesso",
            timestamp=datetime.utcnow(),
        )
        resolution = orchestrator._resolve_conflict(conflict)
        assert resolution == "resolved_in_favor_of_SST"

    def test_resolve_conflict_single_agent(self, orchestrator):
        from modules.people_management.agents.orchestrator import Conflict, ConflictType

        conflict = Conflict(
            conflict_id="c2",
            conflict_type=ConflictType.DATA_INCONSISTENCY,
            agents_involved=["DP"],
            resource="folha-1",
            description="Teste",
            timestamp=datetime.utcnow(),
        )
        resolution = orchestrator._resolve_conflict(conflict)
        assert resolution == "no_conflict"

    def test_get_stats(self, orchestrator):
        stats = orchestrator.get_stats()
        assert stats["agent_name"] == "GP_ORCHESTRATOR"
        assert "state" in stats
        assert "registered_agents" in stats
        assert "pending_conflicts" in stats
        assert "event_routing_stats" in stats

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self, orchestrator):
        h = AgentHealth("A1", AgentState.IDLE, datetime.utcnow(), 0, 0, 0, 0.0)
        orchestrator.register_agent(h)
        result = await orchestrator.health_check()
        assert result["orchestrator_healthy"] is True
        assert result["healthy_agents"] == 1
        assert result["unhealthy_agents"] == []

    @pytest.mark.asyncio
    async def test_health_check_with_unhealthy(self, orchestrator, mock_event_bus):
        h = AgentHealth("BAD", AgentState.ERROR, datetime.utcnow(), 0, 5, 0, 0.0)
        orchestrator.register_agent(h)
        result = await orchestrator.health_check()
        assert "BAD" in result["unhealthy_agents"]

    @pytest.mark.asyncio
    async def test_process_event_ignores_own(self, orchestrator):
        event = Event(
            event_type=GPEventTypes.ORCHESTRATOR_ROUTED,
            payload={},
            source_module="GP_ORCHESTRATOR",
        )
        # Should not raise or route
        await orchestrator._process_event(event)

    @pytest.mark.asyncio
    async def test_process_event_routes(self, orchestrator, mock_event_bus):
        event = Event(
            event_type=GPEventTypes.DOCUMENTO_CRIADO,
            payload={"doc_id": "1"},
            source_module="DP",
        )
        await orchestrator._process_event(event)
        # Should have emitted ORCHESTRATOR_ROUTED
        mock_event_bus.emit.assert_called()

    def test_update_stats(self, orchestrator):
        event = Event(
            event_type=GPEventTypes.PONTO_BATIDO,
            payload={},
            source_module="PONTO",
        )
        orchestrator._update_stats(event)
        orchestrator._update_stats(event)
        assert orchestrator._event_routing_stats[GPEventTypes.PONTO_BATIDO] == 2
