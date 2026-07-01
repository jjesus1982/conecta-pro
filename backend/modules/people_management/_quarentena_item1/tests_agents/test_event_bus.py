"""Testes do Event Bus de Gestao de Pessoas."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.people_management.core.events import (
    Event,
    EventActor,
    EventContext,
    EventPriority,
    GPEventBus,
    GPEventTypes,
)


class TestEvent:
    """Testes da classe Event."""

    def test_event_creation_with_defaults(self):
        event = Event(
            event_type=GPEventTypes.DOCUMENTO_CRIADO,
            payload={"doc_id": "123"},
            source_module="DP",
        )
        assert event.event_id is not None
        assert event.timestamp is not None
        assert event.priority == EventPriority.NORMAL

    def test_event_to_dict(self):
        event = Event(
            event_type=GPEventTypes.PONTO_BATIDO,
            payload={"employee_id": "456"},
            source_module="PONTO",
            priority=EventPriority.ALTO,
        )
        data = event.to_dict()
        assert data["event_type"] == GPEventTypes.PONTO_BATIDO
        assert data["payload"]["employee_id"] == "456"
        assert data["priority"] == 2

    def test_event_to_json(self):
        event = Event(
            event_type=GPEventTypes.FOLHA_CALCULADA,
            payload={"month": "2026-03"},
            source_module="DP",
        )
        json_str = event.to_json()
        data = json.loads(json_str)
        assert data["event_type"] == GPEventTypes.FOLHA_CALCULADA

    def test_event_from_dict(self):
        original = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={"name": "Joao"},
            source_module="DP",
            priority=EventPriority.ALTO,
        )
        data = original.to_dict()
        restored = Event.from_dict(data)
        assert restored.event_type == original.event_type
        assert restored.payload == original.payload
        assert restored.priority == EventPriority.ALTO

    def test_event_from_json(self):
        original = Event(
            event_type=GPEventTypes.PONTO_BATIDO,
            payload={"employee_id": "789"},
            source_module="PONTO",
        )
        json_str = original.to_json()
        restored = Event.from_json(json_str)
        assert restored.event_type == original.event_type
        assert restored.event_id == original.event_id

    def test_event_with_actor(self):
        actor = EventActor(
            user_id="user-123",
            user_name="Joao Silva",
            user_role="supervisor",
            user_module="OPS",
        )
        event = Event(
            event_type=GPEventTypes.ADVERTENCIA_APLICADA,
            payload={"employee_id": "789"},
            source_module="OPS",
            actor=actor,
        )
        data = event.to_dict()
        assert data["actor"]["user_name"] == "Joao Silva"

    def test_event_with_context(self):
        context = EventContext(
            ip_address="10.0.0.1",
            user_agent="Chrome",
            device_type="mobile",
            session_id="sess-123",
            geolocation={"latitude": -3.1, "longitude": -60.0},
        )
        event = Event(
            event_type=GPEventTypes.PONTO_BATIDO,
            payload={},
            source_module="PONTO",
            context=context,
        )
        data = event.to_dict()
        assert data["context"]["ip_address"] == "10.0.0.1"
        assert data["context"]["geolocation"]["latitude"] == -3.1

    def test_event_with_affected_modules(self):
        event = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={},
            source_module="DP",
            affected_modules=["RH", "GED", "SST"],
        )
        assert "RH" in event.affected_modules
        assert len(event.affected_modules) == 3

    def test_event_correlation_id(self):
        event = Event(
            event_type=GPEventTypes.DOCUMENTO_CRIADO,
            payload={},
            source_module="DP",
            correlation_id="corr-123",
        )
        assert event.correlation_id == "corr-123"
        data = event.to_dict()
        assert data["correlation_id"] == "corr-123"

    def test_event_roundtrip_with_actor_and_context(self):
        actor = EventActor("u1", "Maria", "admin", "DP")
        context = EventContext("1.2.3.4", "Firefox", "web", "s-1")
        original = Event(
            event_type=GPEventTypes.FOLHA_FECHADA,
            payload={"month": 3},
            source_module="DP",
            actor=actor,
            context=context,
            priority=EventPriority.CRITICO,
        )
        restored = Event.from_json(original.to_json())
        assert restored.actor.user_name == "Maria"
        assert restored.context.ip_address == "1.2.3.4"
        assert restored.priority == EventPriority.CRITICO


class TestEventPriority:
    """Testes de prioridade de eventos."""

    def test_priority_ordering(self):
        assert EventPriority.CRITICO < EventPriority.ALTO
        assert EventPriority.ALTO < EventPriority.NORMAL
        assert EventPriority.NORMAL < EventPriority.BAIXO

    def test_priority_values(self):
        assert EventPriority.CRITICO == 1
        assert EventPriority.ALTO == 2
        assert EventPriority.NORMAL == 3
        assert EventPriority.BAIXO == 4


class TestGPEventTypes:
    """Testes dos tipos de eventos."""

    def test_all_events_start_with_gp(self):
        for event_type in GPEventTypes:
            assert event_type.value.startswith("gp."), f"{event_type} nao comeca com gp."

    def test_documento_events_exist(self):
        assert GPEventTypes.DOCUMENTO_CRIADO == "gp.documento.criado"
        assert GPEventTypes.DOCUMENTO_ASSINADO == "gp.documento.assinado"
        assert GPEventTypes.DOCUMENTO_ARQUIVADO == "gp.documento.arquivado"
        assert GPEventTypes.DOCUMENTO_ENVIADO == "gp.documento.enviado"
        assert GPEventTypes.DOCUMENTO_REJEITADO == "gp.documento.rejeitado"

    def test_ponto_events_exist(self):
        assert GPEventTypes.PONTO_BATIDO == "gp.ponto.batido"
        assert GPEventTypes.PONTO_ATRASO == "gp.ponto.atraso"
        assert GPEventTypes.PONTO_FALTA == "gp.ponto.falta"
        assert GPEventTypes.PONTO_HORA_EXTRA == "gp.ponto.hora_extra"

    def test_folha_events_exist(self):
        assert GPEventTypes.FOLHA_CALCULADA == "gp.folha.calculada"
        assert GPEventTypes.FOLHA_FECHADA == "gp.folha.fechada"

    def test_funcionario_events_exist(self):
        assert GPEventTypes.FUNCIONARIO_ADMITIDO == "gp.funcionario.admitido"
        assert GPEventTypes.FUNCIONARIO_DEMITIDO == "gp.funcionario.demitido"

    def test_sst_events_exist(self):
        assert GPEventTypes.ASO_AGENDADO == "gp.sst.aso_agendado"
        assert GPEventTypes.CAT_ABERTA == "gp.sst.cat_aberta"
        assert GPEventTypes.LAUDO_EMITIDO == "gp.sst.laudo_emitido"

    def test_orchestrator_events_exist(self):
        assert GPEventTypes.ORCHESTRATOR_ROUTED == "gp.orchestrator.routed"
        assert GPEventTypes.ORCHESTRATOR_CONFLICT == "gp.orchestrator.conflict"

    def test_event_count_minimum(self):
        """Deve ter pelo menos 50 tipos de eventos."""
        assert len(GPEventTypes) >= 50


class TestGPEventBus:
    """Testes do Event Bus."""

    @pytest.fixture
    def event_bus(self):
        return GPEventBus(redis_url="redis://localhost:6379")

    def test_event_bus_initialization(self, event_bus):
        assert event_bus._redis is None
        assert event_bus._handlers == {}
        assert event_bus._websockets == set()
        assert event_bus._running is False

    def test_subscribe_handler(self, event_bus):
        async def my_handler(event):
            pass

        event_bus.subscribe(GPEventTypes.DOCUMENTO_CRIADO, my_handler)
        assert GPEventTypes.DOCUMENTO_CRIADO in event_bus._handlers
        assert my_handler in event_bus._handlers[GPEventTypes.DOCUMENTO_CRIADO]

    def test_subscribe_multiple_handlers(self, event_bus):
        async def handler1(event):
            pass

        async def handler2(event):
            pass

        event_bus.subscribe(GPEventTypes.PONTO_BATIDO, handler1)
        event_bus.subscribe(GPEventTypes.PONTO_BATIDO, handler2)
        assert len(event_bus._handlers[GPEventTypes.PONTO_BATIDO]) == 2

    def test_unsubscribe_handler(self, event_bus):
        async def my_handler(event):
            pass

        event_bus.subscribe(GPEventTypes.DOCUMENTO_CRIADO, my_handler)
        event_bus.unsubscribe(GPEventTypes.DOCUMENTO_CRIADO, my_handler)
        assert my_handler not in event_bus._handlers.get(GPEventTypes.DOCUMENTO_CRIADO, [])

    def test_unsubscribe_nonexistent(self, event_bus):
        async def my_handler(event):
            pass

        # Should not raise
        event_bus.unsubscribe("nonexistent", my_handler)

    def test_get_channel(self, event_bus):
        assert event_bus._get_channel("gp.documento.criado") == "gp:documento"
        assert event_bus._get_channel("gp.ponto.batido") == "gp:ponto"
        assert event_bus._get_channel("gp.folha.calculada") == "gp:folha"
        assert event_bus._get_channel("gp.sst.aso_agendado") == "gp:sst"

    def test_get_stats(self, event_bus):
        stats = event_bus.get_stats()
        assert stats["websockets_connected"] == 0
        assert stats["handlers_registered"] == 0
        assert stats["running"] is False

    def test_get_stats_with_handlers(self, event_bus):
        event_bus.subscribe("test", lambda e: None)
        event_bus.subscribe("test2", lambda e: None)
        stats = event_bus.get_stats()
        assert stats["handlers_registered"] == 2

    @pytest.mark.asyncio
    async def test_connect(self, event_bus):
        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.pubsub.return_value = AsyncMock()
            mock_redis.return_value = mock_client
            await event_bus.connect()
            assert event_bus._redis is not None

    @pytest.mark.asyncio
    async def test_publish_event(self, event_bus):
        with patch("redis.asyncio.from_url") as mock_redis:
            mock_client = AsyncMock()
            mock_client.pubsub.return_value = AsyncMock()
            mock_redis.return_value = mock_client
            event = Event(
                event_type=GPEventTypes.DOCUMENTO_CRIADO,
                payload={"test": True},
                source_module="DP",
            )
            result = await event_bus.publish(event)
            assert result is True
            mock_client.publish.assert_called_once()


class TestEventActor:
    """Testes do EventActor."""

    def test_actor_creation(self):
        actor = EventActor(
            user_id="123",
            user_name="Maria",
            user_role="admin",
            user_module="DP",
        )
        assert actor.user_id == "123"
        assert actor.user_name == "Maria"
        assert actor.user_role == "admin"
        assert actor.user_module == "DP"


class TestEventContext:
    """Testes do EventContext."""

    def test_context_creation(self):
        context = EventContext(
            ip_address="192.168.1.1",
            user_agent="Chrome",
            device_type="mobile",
            session_id="sess-123",
        )
        assert context.ip_address == "192.168.1.1"
        assert context.device_type == "mobile"

    def test_context_defaults(self):
        context = EventContext()
        assert context.ip_address == ""
        assert context.device_type == "web"
        assert context.geolocation is None

    def test_context_with_geolocation(self):
        context = EventContext(
            ip_address="10.0.0.1",
            user_agent="Safari",
            device_type="web",
            session_id="sess-456",
            geolocation={"latitude": -3.1, "longitude": -60.0},
        )
        assert context.geolocation["latitude"] == -3.1
