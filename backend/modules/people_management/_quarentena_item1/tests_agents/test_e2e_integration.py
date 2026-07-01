"""Testes E2E de integracao entre agents — comunicacao bidirecional."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.people_management.agents import (
    AgentHealth,
    AgentState,
    DPAgent,
    GEDAgent,
    GPOrchestratorAgent,
    OPSAgent,
    PontoAgent,
    PortalAgent,
    RHAgent,
    SSTAgent,
)
from modules.people_management.core.events import (
    Event,
    EventPriority,
    GPEventBus,
    GPEventTypes,
)


@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=GPEventBus)
    bus.subscribe = MagicMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def all_agents(mock_bus):
    """Cria todos os 8 agents com o mesmo event bus."""
    return {
        "orchestrator": GPOrchestratorAgent(event_bus=mock_bus),
        "dp": DPAgent(event_bus=mock_bus),
        "ponto": PontoAgent(event_bus=mock_bus),
        "ged": GEDAgent(event_bus=mock_bus),
        "ops": OPSAgent(event_bus=mock_bus),
        "rh": RHAgent(event_bus=mock_bus),
        "sst": SSTAgent(event_bus=mock_bus),
        "portal": PortalAgent(event_bus=mock_bus),
    }


class TestAllAgentsInitialize:
    """Verifica que todos os 8 agents inicializam corretamente."""

    def test_all_8_agents_created(self, all_agents):
        assert len(all_agents) == 8

    def test_all_agents_idle(self, all_agents):
        for name, agent in all_agents.items():
            health = agent.get_health()
            assert health.is_healthy, f"{name} nao esta saudavel"
            assert health.state == AgentState.IDLE, f"{name} nao esta idle"

    def test_all_agents_have_name(self, all_agents):
        names = [a.AGENT_NAME for a in all_agents.values()]
        assert "GP_ORCHESTRATOR" in names
        assert "DP_AGENT" in names
        assert "PONTO_AGENT" in names
        assert "GED_AGENT" in names
        assert "OPS_AGENT" in names
        assert "RH_AGENT" in names
        assert "SST_AGENT" in names
        assert "PORTAL_AGENT" in names

    def test_orchestrator_knows_all_agents(self, all_agents):
        orch = all_agents["orchestrator"]
        for name, agent in all_agents.items():
            if name != "orchestrator":
                orch.register_agent(agent.get_health())
        assert len(orch.get_all_agents_health()) == 7


class TestAdmissionFlow:
    """Testa fluxo completo de admissao — evento propaga para todos."""

    @pytest.mark.asyncio
    async def test_admissao_propaga_para_dp(self, all_agents):
        dp = all_agents["dp"]
        event = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={"employee_id": "emp-new", "nome": "Carlos"},
            source_module="RH",
        )
        await dp._handle_event(event)
        assert dp._events_processed == 1

    @pytest.mark.asyncio
    async def test_admissao_propaga_para_sst(self, all_agents):
        sst = all_agents["sst"]
        event = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={"employee_id": "emp-new"},
            source_module="DP",
        )
        await sst._handle_event(event)
        assert sst._events_processed == 1

    @pytest.mark.asyncio
    async def test_admissao_propaga_para_rh(self, all_agents):
        rh = all_agents["rh"]
        event = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={"employee_id": "emp-new"},
            source_module="DP",
        )
        await rh._handle_event(event)
        assert rh._events_processed == 1

    @pytest.mark.asyncio
    async def test_admissao_propaga_para_ponto(self, all_agents):
        ponto = all_agents["ponto"]
        event = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={"employee_id": "emp-new"},
            source_module="DP",
        )
        await ponto._handle_event(event)
        assert ponto._events_processed == 1

    @pytest.mark.asyncio
    async def test_admissao_propaga_para_ged(self, all_agents):
        ged = all_agents["ged"]
        event = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={"employee_id": "emp-new"},
            source_module="DP",
        )
        await ged._handle_event(event)
        assert ged._events_processed == 1

    @pytest.mark.asyncio
    async def test_admissao_propaga_para_ops(self, all_agents):
        ops = all_agents["ops"]
        event = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={"employee_id": "emp-new"},
            source_module="DP",
        )
        await ops._handle_event(event)
        assert ops._events_processed == 1


class TestOrchestratorRouting:
    """Testa que o Orchestrator roteia corretamente."""

    @pytest.mark.asyncio
    async def test_admissao_routes_to_all_7(self, all_agents, mock_bus):
        orch = all_agents["orchestrator"]
        event = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={"employee_id": "emp-1"},
            source_module="DP",
        )
        destinations = orch._get_routing_destinations(event)
        # DP is source, so removed from destinations
        assert "RH" in destinations
        assert "GED" in destinations
        assert "OPS" in destinations
        assert "SST" in destinations
        assert "PONTO" in destinations
        assert "PORTAL" in destinations

    @pytest.mark.asyncio
    async def test_ponto_batido_routes(self, all_agents):
        orch = all_agents["orchestrator"]
        event = Event(
            event_type=GPEventTypes.PONTO_BATIDO,
            payload={"employee_id": "emp-1"},
            source_module="PONTO",
        )
        destinations = orch._get_routing_destinations(event)
        assert "DP" in destinations
        assert "OPS" in destinations
        assert "PORTAL" in destinations

    @pytest.mark.asyncio
    async def test_cat_aberta_routes(self, all_agents):
        orch = all_agents["orchestrator"]
        event = Event(
            event_type=GPEventTypes.CAT_ABERTA,
            payload={"employee_id": "emp-1"},
            source_module="SST",
        )
        destinations = orch._get_routing_destinations(event)
        assert "DP" in destinations
        assert "GED" in destinations
        assert "OPS" in destinations
        assert "PORTAL" in destinations

    @pytest.mark.asyncio
    async def test_folha_fechada_routes(self, all_agents):
        orch = all_agents["orchestrator"]
        event = Event(
            event_type=GPEventTypes.FOLHA_FECHADA,
            payload={},
            source_module="DP",
        )
        destinations = orch._get_routing_destinations(event)
        assert "GED" in destinations
        assert "PORTAL" in destinations

    def test_precedence_sst_always_first(self, all_agents):
        orch = all_agents["orchestrator"]
        assert orch.PRECEDENCE_RULES["SST"] == 1

    @pytest.mark.asyncio
    async def test_process_event_increments_stats(self, all_agents, mock_bus):
        orch = all_agents["orchestrator"]
        event = Event(
            event_type=GPEventTypes.DOCUMENTO_CRIADO,
            payload={},
            source_module="DP",
        )
        await orch._process_event(event)
        assert orch._event_routing_stats.get(GPEventTypes.DOCUMENTO_CRIADO) == 1


class TestPortalNotifications:
    """Testa que o Portal gera notificacoes para eventos."""

    @pytest.mark.asyncio
    async def test_folha_gera_notificacao(self, all_agents, mock_bus):
        portal = all_agents["portal"]
        event = Event(
            event_type=GPEventTypes.FOLHA_FECHADA,
            payload={"employee_id": "emp-1"},
            source_module="DP",
        )
        await portal._process_event(event)
        mock_bus.emit.assert_called()

    @pytest.mark.asyncio
    async def test_advertencia_gera_notificacao(self, all_agents, mock_bus):
        portal = all_agents["portal"]
        event = Event(
            event_type=GPEventTypes.ADVERTENCIA_APLICADA,
            payload={"employee_id": "emp-1"},
            source_module="OPS",
        )
        await portal._process_event(event)
        mock_bus.emit.assert_called()

    @pytest.mark.asyncio
    async def test_aso_agendado_gera_notificacao(self, all_agents, mock_bus):
        portal = all_agents["portal"]
        event = Event(
            event_type=GPEventTypes.ASO_AGENDADO,
            payload={"employee_id": "emp-1"},
            source_module="SST",
        )
        await portal._process_event(event)
        mock_bus.emit.assert_called()


class TestPontoFlow:
    """Testa fluxo completo do ponto."""

    @pytest.mark.asyncio
    async def test_batida_registrada_emite_evento(self, all_agents, mock_bus):
        ponto = all_agents["ponto"]
        from modules.people_management.agents.ponto_agent import ClockPunchType, FacialResult, GeoLocation

        punch = await ponto.registrar_batida(
            employee_id="emp-1",
            punch_type=ClockPunchType.ENTRADA,
            location=GeoLocation(-3.1, -60.0, 10.0, True),
            facial=FacialResult(True, 0.92),
        )
        assert punch.employee_id == "emp-1"
        mock_bus.emit.assert_called()

    @pytest.mark.asyncio
    async def test_sync_emite_evento(self, all_agents, mock_bus):
        ponto = all_agents["ponto"]
        event = Event(
            event_type=GPEventTypes.SYNC_INICIADO,
            payload={},
            source_module="PORTAL",
        )
        await ponto._process_event(event)
        mock_bus.emit.assert_called()


class TestDPSkillsIntegration:
    """Testa skills do DP em cenarios reais."""

    def test_folha_completa_vigilante(self, all_agents):
        dp = all_agents["dp"]
        payroll = dp.get_skill("PAYROLL")
        from decimal import Decimal

        result = payroll.calcular_folha(
            salario_base=Decimal("2200.00"),
            horas_extras_50=Decimal("20"),
            adicional_periculosidade=Decimal("660.00"),  # 30% de 2200
            desconto_vt=Decimal("132.00"),  # 6% de 2200
        )
        assert result["salario_liquido"] > 0
        assert result["proventos"]["adicional_periculosidade"] == 660.0
        assert result["descontos"]["vt"] == 132.0

    def test_ferias_com_abono_vigilante(self, all_agents):
        dp = all_agents["dp"]
        vacation = dp.get_skill("VACATION")
        from decimal import Decimal

        result = vacation.calcular_ferias(
            salario_base=Decimal("2200.00"),
            abono_pecuniario=True,
        )
        assert result["dias_gozo"] == 20
        assert result["dias_abono"] == 10
        assert result["total_bruto"] > 0


class TestGEDDocumentTypes:
    """Testa que GED tem todos os 70 tipos de documentos."""

    def test_70_document_types(self, all_agents):
        ged = all_agents["ged"]
        storage = ged.get_skill("STORAGE")
        assert storage.get_document_count() == 70

    def test_all_11_categories(self, all_agents):
        ged = all_agents["ged"]
        storage = ged.get_skill("STORAGE")
        cats = storage.get_categories()
        expected = [
            "admissional",
            "mensal",
            "disciplinar",
            "sst",
            "ferias",
            "rescisao",
            "treinamento",
            "avaliacao",
            "afastamento",
            "operacional",
            "certidao",
        ]
        for c in expected:
            assert c in cats, f"Categoria {c} nao encontrada"
