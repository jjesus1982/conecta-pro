"""Testes do PONTO Agent e Skills."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.people_management.agents.ponto_agent import (
    ClockPunch,
    ClockPunchStatus,
    ClockPunchType,
    ClockSkill,
    FacialResult,
    FacialSkill,
    GeoLocation,
    GeoSkill,
    JustificationCategory,
    JustificationStatus,
    JustifySkill,
    OfflineSkill,
    PontoAgent,
)
from modules.people_management.core.events import GPEventTypes


class TestFacialSkill:
    @pytest.fixture
    def skill(self):
        return FacialSkill()

    def test_match_identical(self, skill):
        desc = [0.1, 0.2, 0.3, 0.4]
        result = skill.validate_facial(desc, desc)
        assert result.match is True
        assert result.confidence == 1.0

    def test_no_match_different(self, skill):
        result = skill.validate_facial([0.1, 0.2], [0.9, 0.8])
        assert result.match is False
        assert result.confidence < 0.6

    def test_empty_descriptors(self, skill):
        result = skill.validate_facial([], [0.1])
        assert result.match is False
        assert result.confidence == 0.0

    def test_custom_threshold(self, skill):
        result = skill.validate_facial([0.1, 0.2], [0.15, 0.25], threshold=0.1)
        # Distance ~ 0.07, so should match with threshold 0.1
        assert result.match is True


class TestGeoSkill:
    @pytest.fixture
    def skill(self):
        return GeoSkill()

    def test_same_point_zero_distance(self, skill):
        d = skill.calculate_distance(-3.1, -60.0, -3.1, -60.0)
        assert d < 1  # menos de 1 metro

    def test_known_distance(self, skill):
        # Manaus centro -> Ponta Negra ~ 13km
        d = skill.calculate_distance(-3.1300, -60.0234, -3.0731, -60.1066)
        assert 8000 < d < 15000

    def test_geofence_dentro(self, skill):
        result = skill.check_geofence(-3.1, -60.0, -3.1, -60.0, raio_metros=100)
        assert result["dentro_geofence"] is True

    def test_geofence_fora(self, skill):
        result = skill.check_geofence(-3.1, -60.0, -3.2, -60.1, raio_metros=100)
        assert result["dentro_geofence"] is False
        assert result["distancia_metros"] > 100


class TestClockSkill:
    @pytest.fixture
    def skill(self):
        return ClockSkill()

    def test_primeira_batida_entrada(self, skill):
        assert skill.determinar_tipo_batida([]) == ClockPunchType.ENTRADA

    def test_segunda_batida_saida_almoco(self, skill):
        batidas = [ClockPunch("e1", ClockPunchType.ENTRADA, "2026-03-13T08:00:00")]
        assert skill.determinar_tipo_batida(batidas) == ClockPunchType.SAIDA_ALMOCO

    def test_terceira_batida_retorno(self, skill):
        batidas = [
            ClockPunch("e1", ClockPunchType.ENTRADA, "2026-03-13T08:00:00"),
            ClockPunch("e1", ClockPunchType.SAIDA_ALMOCO, "2026-03-13T12:00:00"),
        ]
        assert skill.determinar_tipo_batida(batidas) == ClockPunchType.RETORNO_ALMOCO

    def test_quarta_batida_saida(self, skill):
        batidas = [
            ClockPunch("e1", ClockPunchType.ENTRADA, "2026-03-13T08:00:00"),
            ClockPunch("e1", ClockPunchType.SAIDA_ALMOCO, "2026-03-13T12:00:00"),
            ClockPunch("e1", ClockPunchType.RETORNO_ALMOCO, "2026-03-13T13:00:00"),
        ]
        assert skill.determinar_tipo_batida(batidas) == ClockPunchType.SAIDA

    def test_verificar_atraso_normal(self, skill):
        esperado = datetime(2026, 3, 13, 8, 0)
        batida = datetime(2026, 3, 13, 8, 5)
        result = skill.verificar_atraso(batida, esperado)
        assert result["atrasado"] is False

    def test_verificar_atraso_sim(self, skill):
        esperado = datetime(2026, 3, 13, 8, 0)
        batida = datetime(2026, 3, 13, 8, 15)
        result = skill.verificar_atraso(batida, esperado)
        assert result["atrasado"] is True

    def test_debounce_ok(self, skill):
        ultima = datetime(2026, 3, 13, 8, 0)
        agora = datetime(2026, 3, 13, 8, 1)
        assert skill.verificar_debounce(ultima, agora) is True

    def test_debounce_muito_rapido(self, skill):
        ultima = datetime(2026, 3, 13, 8, 0, 0)
        agora = datetime(2026, 3, 13, 8, 0, 10)
        assert skill.verificar_debounce(ultima, agora) is False

    def test_debounce_sem_anterior(self, skill):
        assert skill.verificar_debounce(None, datetime.utcnow()) is True

    def test_calcular_horas_trabalhadas(self, skill):
        batidas = [
            ClockPunch("e1", ClockPunchType.ENTRADA, "2026-03-13T08:00:00"),
            ClockPunch("e1", ClockPunchType.SAIDA_ALMOCO, "2026-03-13T12:00:00"),
            ClockPunch("e1", ClockPunchType.RETORNO_ALMOCO, "2026-03-13T13:00:00"),
            ClockPunch("e1", ClockPunchType.SAIDA, "2026-03-13T17:00:00"),
        ]
        result = skill.calcular_horas_trabalhadas(batidas)
        assert result["horas_totais"] == 8.0
        assert result["completo"] is True

    def test_calcular_horas_incompleto(self, skill):
        batidas = [
            ClockPunch("e1", ClockPunchType.ENTRADA, "2026-03-13T08:00:00"),
        ]
        result = skill.calcular_horas_trabalhadas(batidas)
        assert result["completo"] is False


class TestOfflineSkill:
    @pytest.fixture
    def skill(self):
        return OfflineSkill()

    def test_validate_valid_punch(self, skill):
        result = skill.validate_offline_punch(
            {
                "employee_id": "e1",
                "timestamp": datetime.utcnow().isoformat(),
                "punch_type": "entrada",
            }
        )
        assert result["valid"] is True

    def test_validate_missing_employee(self, skill):
        result = skill.validate_offline_punch(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "punch_type": "entrada",
            }
        )
        assert result["valid"] is False

    def test_validate_old_punch(self, skill):
        old = (datetime.utcnow() - timedelta(days=10)).isoformat()
        result = skill.validate_offline_punch(
            {
                "employee_id": "e1",
                "timestamp": old,
                "punch_type": "entrada",
            }
        )
        assert result["valid"] is False

    def test_prepare_sync_batch(self, skill):
        punches = [{"timestamp": f"2026-03-{i:02d}T08:00:00"} for i in range(1, 26)]
        batches = skill.prepare_sync_batch(punches)
        assert len(batches) == 2  # 25 / 20 = 2 batches
        assert len(batches[0]) == 20
        assert len(batches[1]) == 5

    def test_check_duplicate_true(self, skill):
        punch = {"employee_id": "e1", "timestamp": "2026-03-13T08:00:00", "punch_type": "entrada"}
        existing = [punch.copy()]
        assert skill.check_duplicate(punch, existing) is True

    def test_check_duplicate_false(self, skill):
        punch = {"employee_id": "e1", "timestamp": "2026-03-13T08:00:00", "punch_type": "entrada"}
        existing = [{"employee_id": "e2", "timestamp": "2026-03-13T08:00:00", "punch_type": "entrada"}]
        assert skill.check_duplicate(punch, existing) is False


class TestJustifySkill:
    @pytest.fixture
    def skill(self):
        return JustifySkill()

    def test_create_justification(self, skill):
        j = skill.create_justification("e1", "p1", "atraso", "Transito pesado", "transito")
        assert j.employee_id == "e1"
        assert j.status == JustificationStatus.PENDENTE
        assert j.category == JustificationCategory.TRANSITO

    def test_create_invalid_category(self, skill):
        with pytest.raises(ValueError):
            skill.create_justification("e1", "p1", "atraso", "Razao", "invalida")

    def test_create_invalid_type(self, skill):
        with pytest.raises(ValueError):
            skill.create_justification("e1", "p1", "invalido", "Razao", "transito")

    def test_create_short_reason(self, skill):
        with pytest.raises(ValueError):
            skill.create_justification("e1", "p1", "atraso", "abc", "transito")

    def test_approve(self, skill):
        j = skill.create_justification("e1", "p1", "atraso", "Motivo valido", "saude")
        j = skill.approve(j, "supervisor-1")
        assert j.status == JustificationStatus.APROVADA
        assert j.reviewed_by == "supervisor-1"

    def test_reject(self, skill):
        j = skill.create_justification("e1", "p1", "falta", "Motivo valido", "outro")
        j = skill.reject(j, "supervisor-1")
        assert j.status == JustificationStatus.REJEITADA


class TestClockPunch:
    def test_punch_to_dict(self):
        punch = ClockPunch(
            employee_id="e1",
            punch_type=ClockPunchType.ENTRADA,
            timestamp="2026-03-13T08:00:00",
            location=GeoLocation(-3.1, -60.0, 10.0, True),
            facial=FacialResult(True, 0.95),
        )
        d = punch.to_dict()
        assert d["employee_id"] == "e1"
        assert d["punch_type"] == "entrada"
        assert d["location"]["latitude"] == -3.1
        assert d["facial"]["confidence"] == 0.95

    def test_punch_offline(self):
        punch = ClockPunch("e1", ClockPunchType.SAIDA, "2026-03-13T17:00:00", is_offline=True)
        assert punch.is_offline is True


class TestPontoAgent:
    @pytest.fixture
    def agent(self):
        bus = MagicMock()
        bus.subscribe = MagicMock()
        bus.emit = AsyncMock()
        return PontoAgent(event_bus=bus)

    def test_agent_name(self, agent):
        assert agent.AGENT_NAME == "PONTO_AGENT"

    def test_has_all_skills(self, agent):
        assert agent.get_skill("FACIAL") is not None
        assert agent.get_skill("GEO") is not None
        assert agent.get_skill("CLOCK") is not None
        assert agent.get_skill("OFFLINE") is not None
        assert agent.get_skill("JUSTIFY") is not None

    def test_handled_events(self, agent):
        events = agent.handled_events
        assert GPEventTypes.FUNCIONARIO_ADMITIDO in events
        assert GPEventTypes.ESCALA_PUBLICADA in events

    @pytest.mark.asyncio
    async def test_registrar_batida(self, agent):
        punch = await agent.registrar_batida(
            employee_id="e1",
            punch_type=ClockPunchType.ENTRADA,
            location=GeoLocation(-3.1, -60.0, 10.0, True),
            facial=FacialResult(True, 0.92),
        )
        assert punch.employee_id == "e1"
        assert punch.status == ClockPunchStatus.NORMAL

    @pytest.mark.asyncio
    async def test_registrar_batida_fora_geofence(self, agent):
        punch = await agent.registrar_batida(
            employee_id="e1",
            punch_type=ClockPunchType.ENTRADA,
            location=GeoLocation(-3.1, -60.0, 10.0, False),
        )
        assert punch.status == ClockPunchStatus.FORA_LOCAL

    @pytest.mark.asyncio
    async def test_registrar_batida_offline(self, agent):
        punch = await agent.registrar_batida(
            employee_id="e1",
            punch_type=ClockPunchType.ENTRADA,
            is_offline=True,
        )
        assert punch.status == ClockPunchStatus.OFFLINE
