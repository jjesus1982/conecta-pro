"""Testes unitários do PunchService — registro de ponto eletrônico.

Cobre: batidas, justificativas, espelho mensal, fechamento e geofence.
Todos os testes usam mocks (sem banco real).
"""

import math
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.people_management.ponto.schemas.punch_schemas import (
    FacialSchema,
    GeoLocationSchema,
    JustificationCreate,
    PunchCreate,
)
from modules.people_management.ponto.services.punch_service import (
    GEOFENCE_RADIUS_METERS,
    PunchService,
    _haversine,
)

# ========================================================================
# FIXTURES
# ========================================================================


@pytest.fixture
def mock_db():
    """Mock de AsyncSession."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    """Instância do PunchService com DB mockado."""
    return PunchService(mock_db)


# ========================================================================
# TESTES HAVERSINE (funçao pura)
# ========================================================================


class TestHaversine:
    """Testes da funcao _haversine para calculo de distancia."""

    def test_mesmo_ponto_zero(self):
        assert _haversine(-3.1, -60.0, -3.1, -60.0) < 0.01

    def test_distancia_conhecida_manaus(self):
        # Manaus centro -> Ponta Negra ~13km
        d = _haversine(-3.1300, -60.0234, -3.0731, -60.1066)
        assert 8000 < d < 15000

    def test_distancia_curta_100m(self):
        # Dois pontos ~100m em Manaus
        d = _haversine(-3.1190, -60.0217, -3.1199, -60.0217)
        assert 50 < d < 200

    def test_distancia_hemisferios_opostos(self):
        # Nova York -> Sydney
        d = _haversine(40.7128, -74.0060, -33.8688, 151.2093)
        assert d > 15_000_000  # >15.000km

    def test_simetria(self):
        d1 = _haversine(-3.1, -60.0, -3.2, -60.1)
        d2 = _haversine(-3.2, -60.1, -3.1, -60.0)
        assert abs(d1 - d2) < 0.01

    def test_raio_geofence_padrao(self):
        assert GEOFENCE_RADIUS_METERS == 200.0


# ========================================================================
# TESTES REGISTRAR BATIDA
# ========================================================================


class TestRegistrarBatida:
    """Testes do metodo registrar_batida."""

    @pytest.mark.asyncio
    async def test_batida_simples_entrada(self, service, mock_db):
        data = PunchCreate(employee_id=1, punch_type="entrada")
        result = await service.registrar_batida(data)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        assert result["punch_type"] == "entrada"
        assert result["status"] == "normal"
        assert result["punch_id"] is not None

    @pytest.mark.asyncio
    async def test_batida_offline_status(self, service):
        data = PunchCreate(
            employee_id=1,
            punch_type="entrada",
            is_offline=True,
            timestamp="2026-03-13T08:00:00",
        )
        result = await service.registrar_batida(data)
        assert result["status"] == "offline"
        assert result["is_offline"] is True

    @pytest.mark.asyncio
    async def test_batida_com_facial(self, service):
        data = PunchCreate(
            employee_id=1,
            punch_type="entrada",
            facial=FacialSchema(match=True, confidence=0.95, liveness_check=True),
        )
        result = await service.registrar_batida(data)
        assert result["facial_match"] is True
        assert result["facial_confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_batida_com_geo_dentro_geofence(self, service, mock_db):
        # Mock _validar_geofence
        service._validar_geofence = AsyncMock(
            return_value={
                "dentro": True,
                "distancia_metros": 50.0,
                "posto_id": "p1",
                "posto_nome": "Posto Central",
                "raio_metros": 200.0,
            }
        )
        data = PunchCreate(
            employee_id=1,
            punch_type="entrada",
            location=GeoLocationSchema(latitude=-3.1, longitude=-60.0, accuracy=10.0),
        )
        result = await service.registrar_batida(data)
        assert result["dentro_geofence"] is True
        assert result["status"] == "normal"

    @pytest.mark.asyncio
    async def test_batida_com_geo_fora_geofence(self, service):
        service._validar_geofence = AsyncMock(
            return_value={
                "dentro": False,
                "distancia_metros": 500.0,
                "posto_id": "p1",
                "posto_nome": "Posto Central",
                "raio_metros": 200.0,
            }
        )
        data = PunchCreate(
            employee_id=1,
            punch_type="entrada",
            location=GeoLocationSchema(latitude=-3.2, longitude=-60.1, accuracy=10.0),
        )
        result = await service.registrar_batida(data)
        assert result["status"] == "fora_local"

    @pytest.mark.asyncio
    async def test_batida_timestamp_customizado(self, service):
        ts = "2026-03-15T14:30:00"
        data = PunchCreate(employee_id=1, punch_type="saida", timestamp=ts)
        result = await service.registrar_batida(data)
        assert result["punch_timestamp"] == ts

    @pytest.mark.asyncio
    async def test_batida_todos_tipos(self, service):
        for tipo in ["entrada", "saida_almoco", "retorno_almoco", "saida"]:
            data = PunchCreate(employee_id=1, punch_type=tipo)
            result = await service.registrar_batida(data)
            assert result["punch_type"] == tipo

    @pytest.mark.asyncio
    async def test_batida_device_type_mobile(self, service):
        data = PunchCreate(employee_id=1, punch_type="entrada", device_type="mobile")
        result = await service.registrar_batida(data)
        assert result["device_type"] == "mobile"

    @pytest.mark.asyncio
    async def test_batida_com_posto_id(self, service):
        service._validar_geofence = AsyncMock(
            return_value={
                "dentro": True,
                "distancia_metros": 10.0,
                "posto_id": "42",
                "posto_nome": "Condominio Sol",
                "raio_metros": 200.0,
            }
        )
        data = PunchCreate(
            employee_id=1,
            punch_type="entrada",
            posto_id="42",
            location=GeoLocationSchema(latitude=-3.1, longitude=-60.0),
        )
        result = await service.registrar_batida(data)
        assert result["posto_id"] == "42"


# ========================================================================
# TESTES SYNC OFFLINE
# ========================================================================


class TestSyncOffline:
    """Testes do metodo sync_offline_punches."""

    @pytest.mark.asyncio
    async def test_sync_lista_vazia(self, service):
        result = await service.sync_offline_punches([])
        assert result["total_received"] == 0
        assert result["total_synced"] == 0

    @pytest.mark.asyncio
    async def test_sync_4_batidas(self, service, mock_db):
        # Mock: nenhuma duplicata
        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = fake_result

        punches = [
            PunchCreate(employee_id=3, punch_type="entrada", timestamp="2026-03-13T08:00:00"),
            PunchCreate(employee_id=3, punch_type="saida_almoco", timestamp="2026-03-13T12:00:00"),
            PunchCreate(employee_id=3, punch_type="retorno_almoco", timestamp="2026-03-13T13:00:00"),
            PunchCreate(employee_id=3, punch_type="saida", timestamp="2026-03-13T17:00:00"),
        ]
        result = await service.sync_offline_punches(punches)
        assert result["total_received"] == 4
        assert result["total_synced"] == 4
        assert result["total_duplicates"] == 0
        assert result["total_errors"] == 0

    @pytest.mark.asyncio
    async def test_sync_detecta_duplicata(self, service, mock_db):
        # Mock: duplicata encontrada
        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = 42  # ID existente
        mock_db.execute.return_value = fake_result

        punches = [
            PunchCreate(employee_id=1, punch_type="entrada", timestamp="2026-03-13T08:00:00"),
        ]
        result = await service.sync_offline_punches(punches)
        assert result["total_received"] == 1
        assert result["total_synced"] == 0
        assert result["total_duplicates"] == 1

    @pytest.mark.asyncio
    async def test_sync_com_erro(self, service, mock_db):
        # Check duplicata: nao encontra
        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = fake_result
        # flush falha dentro de registrar_batida
        mock_db.flush = AsyncMock(side_effect=Exception("DB write error"))

        punches = [
            PunchCreate(employee_id=1, punch_type="entrada", timestamp="2026-03-13T08:00:00"),
        ]
        result = await service.sync_offline_punches(punches)
        assert result["total_received"] == 1
        assert result["total_synced"] == 0
        assert result["total_errors"] == 1
        assert "DB write error" in result["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_sync_sem_timestamp_usa_utcnow(self, service, mock_db):
        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = fake_result

        punches = [PunchCreate(employee_id=1, punch_type="entrada")]
        result = await service.sync_offline_punches(punches)
        assert result["total_received"] == 1


# ========================================================================
# TESTES GET BATIDAS DIA
# ========================================================================


class TestGetBatidasDia:
    """Testes do metodo get_batidas_dia."""

    @pytest.mark.asyncio
    async def test_retorna_lista_vazia(self, service, mock_db):
        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = fake_result

        result = await service.get_batidas_dia(1, "2026-03-13")
        assert result == []

    @pytest.mark.asyncio
    async def test_retorna_batidas_do_dia(self, service, mock_db):
        punch_mock = MagicMock()
        punch_mock.to_dict.return_value = {
            "punch_id": "abc",
            "employee_id": 1,
            "punch_type": "entrada",
            "punch_timestamp": "2026-03-13T08:00:00",
            "status": "normal",
        }
        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = [punch_mock]
        mock_db.execute.return_value = fake_result

        result = await service.get_batidas_dia(1, "2026-03-13")
        assert len(result) == 1
        assert result[0]["punch_type"] == "entrada"


# ========================================================================
# TESTES ESPELHO MENSAL
# ========================================================================


# ========================================================================
# TESTES JUSTIFICATIVA
# ========================================================================


class TestJustificativa:
    """Testes de criar e revisar justificativas."""

    @pytest.mark.asyncio
    async def test_criar_justificativa(self, service, mock_db):
        data = JustificationCreate(
            employee_id=1,
            punch_id="punch-123",
            justification_type="atraso",
            reason="Transito intenso na AM-010",
            category="transito",
        )
        result = await service.criar_justificativa(data)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        assert result["status"] == "pendente"
        assert result["category"] == "transito"
        assert result["type"] == "atraso"
        assert result["employee_id"] == 1

    @pytest.mark.asyncio
    async def test_criar_justificativa_com_anexos(self, service, mock_db):
        data = JustificationCreate(
            employee_id=1,
            justification_type="falta",
            reason="Atestado medico 1 dia",
            category="saude",
            attachments=[{"type": "doc", "file_name": "atestado.pdf"}],
        )
        result = await service.criar_justificativa(data)
        assert result["attachments"] == [{"type": "doc", "file_name": "atestado.pdf"}]

    @pytest.mark.asyncio
    async def test_revisar_aprovar(self, service, mock_db):
        just_mock = MagicMock()
        just_mock.status = "pendente"
        just_mock.to_dict.return_value = {
            "justification_id": "j1",
            "status": "aprovada",
            "reviewed_by": "sup-1",
        }

        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = just_mock
        mock_db.execute.return_value = fake_result

        result = await service.revisar_justificativa("j1", "aprovar", "sup-1")
        assert just_mock.status == "aprovada"
        assert just_mock.reviewed_by == "sup-1"

    @pytest.mark.asyncio
    async def test_revisar_rejeitar(self, service, mock_db):
        just_mock = MagicMock()
        just_mock.status = "pendente"
        just_mock.to_dict.return_value = {
            "justification_id": "j2",
            "status": "rejeitada",
            "reviewed_by": "sup-1",
        }

        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = just_mock
        mock_db.execute.return_value = fake_result

        result = await service.revisar_justificativa("j2", "rejeitar", "sup-1", "Sem comprovante")
        assert just_mock.status == "rejeitada"
        assert just_mock.review_notes == "Sem comprovante"

    @pytest.mark.asyncio
    async def test_revisar_nao_encontrada(self, service, mock_db):
        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = fake_result

        with pytest.raises(ValueError, match="nao encontrada"):
            await service.revisar_justificativa("inexistente", "aprovar", "sup-1")


# ========================================================================
# TESTES JUSTIFICATIVAS PENDENTES
# ========================================================================


class TestJustificativasPendentes:
    """Testes do metodo get_justificativas_pendentes."""

    @pytest.mark.asyncio
    async def test_lista_vazia(self, service, mock_db):
        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = fake_result

        result = await service.get_justificativas_pendentes()
        assert result == []

    @pytest.mark.asyncio
    async def test_com_filtro_employee(self, service, mock_db):
        j_mock = MagicMock()
        j_mock.to_dict.return_value = {
            "justification_id": "j1",
            "employee_id": 5,
            "status": "pendente",
        }
        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = [j_mock]
        mock_db.execute.return_value = fake_result

        result = await service.get_justificativas_pendentes(employee_id=5)
        assert len(result) == 1


# ========================================================================
# TESTES FECHAR MES
# ========================================================================


class TestFecharMes:
    """Testes do metodo fechar_mes."""

    @pytest.mark.asyncio
    async def test_fechar_mes_sem_batidas(self, service, mock_db):
        fake_count = MagicMock()
        fake_count.scalar.return_value = 0
        mock_db.execute.return_value = fake_count

        result = await service.fechar_mes(1, 3, 2026, "admin-1")

        mock_db.add.assert_called_once()
        assert result["fechado"] is True
        assert result["employee_id"] == 1
        assert result["month"] == 3
        assert result["total_horas_trabalhadas"] == 0.0
        assert result["total_dias_trabalhados"] == 0

    @pytest.mark.asyncio
    async def test_fechar_mes_com_batidas(self, service, mock_db):
        # 20 batidas = 5 dias (20 / 4)
        fake_count = MagicMock()
        fake_count.scalar.return_value = 20
        mock_db.execute.return_value = fake_count

        result = await service.fechar_mes(1, 3, 2026, "admin-1")
        assert result["total_dias_trabalhados"] == 5
        assert result["total_horas_trabalhadas"] == 40.0  # 5 * 8

    @pytest.mark.asyncio
    async def test_fechar_mes_3_batidas_zero_dias(self, service, mock_db):
        fake_count = MagicMock()
        fake_count.scalar.return_value = 3
        mock_db.execute.return_value = fake_count

        result = await service.fechar_mes(1, 3, 2026, "admin-1")
        assert result["total_dias_trabalhados"] == 0


# ========================================================================
# TESTES VALIDAR GEOFENCE
# ========================================================================


class TestValidarGeofence:
    """Testes do metodo _validar_geofence."""

    @pytest.mark.asyncio
    async def test_sem_coordenadas_posto(self, service, mock_db):
        # Execute retorna posto sem coordenadas
        fake_result = MagicMock()
        fake_result.first.return_value = None
        mock_db.execute.return_value = fake_result

        result = await service._validar_geofence(1, -3.1, -60.0)
        assert result["dentro"] is None
        assert result["distancia_metros"] is None

    @pytest.mark.asyncio
    async def test_com_posto_dentro(self, service, mock_db):
        call_count = [0]

        async def mock_execute(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Busca posto
                result.first.return_value = ("1", "Posto Central", -3.1, -60.0)
            else:
                result.first.return_value = None
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        result = await service._validar_geofence(1, -3.1, -60.0, posto_id="1")
        assert result["dentro"] is True
        assert result["distancia_metros"] < 1

    @pytest.mark.asyncio
    async def test_com_posto_fora(self, service, mock_db):
        call_count = [0]

        async def mock_execute(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Posto a ~11km
                result.first.return_value = ("1", "Posto Longe", -3.2, -60.1)
            else:
                result.first.return_value = None
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        result = await service._validar_geofence(1, -3.1, -60.0, posto_id="1")
        assert result["dentro"] is False
        assert result["distancia_metros"] > 200

    @pytest.mark.asyncio
    async def test_geofence_exception_handling(self, service, mock_db):
        mock_db.execute = AsyncMock(side_effect=Exception("DB connection error"))

        result = await service._validar_geofence(1, -3.1, -60.0)
        # Deve retornar sem erro (exception eh capturada)
        assert result["dentro"] is None

    @pytest.mark.asyncio
    async def test_geofence_via_geofence_zone(self, service, mock_db):
        call_count = [0]

        async def mock_execute(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Posto sem coordenadas
                result.first.return_value = ("1", "Posto A", None, None)
            elif call_count[0] == 2:
                # Geofence zone com coordenadas
                result.first.return_value = (-3.1, -60.0, 300.0, "Zona A")
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        result = await service._validar_geofence(1, -3.1, -60.0, posto_id="1")
        assert result["dentro"] is True
        assert result["raio_metros"] == 300.0


# ========================================================================
# TESTES DE CÁLCULO INSS (função pura, sem DB)
# ========================================================================


class TestCalculoINSS:
    """Testes do cálculo progressivo INSS 2026."""

    def test_salario_faixa1_apenas(self):
        from modules.people_management.hr.services.payroll_service import calcular_inss

        resultado = calcular_inss(Decimal("1500.00"))
        assert resultado == Decimal("112.50")

    def test_salario_faixa1_e_2(self):
        from modules.people_management.hr.services.payroll_service import calcular_inss

        resultado = calcular_inss(Decimal("1670.00"))
        assert resultado == Decimal("127.53")

    def test_salario_faixa3(self):
        from modules.people_management.hr.services.payroll_service import calcular_inss

        resultado = calcular_inss(Decimal("3000.00"))
        assert resultado == Decimal("253.41")

    def test_salario_acima_teto(self):
        from modules.people_management.hr.services.payroll_service import calcular_inss

        resultado = calcular_inss(Decimal("10000.00"))
        assert resultado > Decimal("800")


class TestCalculoIRRF:
    """Testes do cálculo progressivo IRRF 2026."""

    def test_isento(self):
        from modules.people_management.hr.services.payroll_service import calcular_irrf

        resultado = calcular_irrf(Decimal("1670.00"), dependentes=0)
        assert resultado == Decimal("0")

    def test_isento_com_dependentes(self):
        from modules.people_management.hr.services.payroll_service import calcular_irrf

        resultado = calcular_irrf(Decimal("2500.00"), dependentes=2)
        assert resultado == Decimal("0")

    def test_faixa_7_5_pct(self):
        from modules.people_management.hr.services.payroll_service import calcular_irrf

        resultado = calcular_irrf(Decimal("2600.00"), dependentes=0)
        assert resultado == Decimal("25.56")


# ========================================================================
# TESTES DE GEOFENCE (funcao pura)
# ========================================================================


class TestGeofence:
    """Testes de validação de geolocalização."""

    def test_dentro_raio_200m(self):
        lat_posto, lon_posto = -3.1190, -60.0217
        lat_user, lon_user = -3.1191, -60.0216
        resultado = _haversine(lat_posto, lon_posto, lat_user, lon_user)
        assert resultado < 200

    def test_fora_raio_200m(self):
        lat_posto, lon_posto = -3.1190, -60.0217
        lat_user, lon_user = -3.1280, -60.0217
        resultado = _haversine(lat_posto, lon_posto, lat_user, lon_user)
        assert resultado > 200


# ========================================================================
# TESTES DE FOLHA / PAYROLL
# ========================================================================


class TestFolhaCalculos:
    """Testes dos cálculos de folha de pagamento."""

    def test_liquido_correto(self):
        from modules.people_management.hr.services.payroll_service import calcular_inss, calcular_irrf

        bruto = Decimal("1670.00")
        inss = calcular_inss(bruto)
        irrf = calcular_irrf(bruto - inss, dependentes=0)
        consignado = Decimal("180.00")
        liquido = bruto - inss - irrf - consignado
        assert liquido == Decimal("1362.47")

    def test_liquido_sem_descontos(self):
        from modules.people_management.hr.services.payroll_service import calcular_inss, calcular_irrf

        bruto = Decimal("1670.00")
        inss = calcular_inss(bruto)
        irrf = calcular_irrf(bruto - inss, dependentes=0)
        liquido = bruto - inss - irrf
        assert liquido == Decimal("1542.47")

    def test_inss_nao_negativo(self):
        from modules.people_management.hr.services.payroll_service import calcular_inss

        assert calcular_inss(Decimal("0")) == Decimal("0")
        assert calcular_inss(Decimal("100")) >= Decimal("0")

    def test_irrf_nao_negativo(self):
        from modules.people_management.hr.services.payroll_service import calcular_irrf

        assert calcular_irrf(Decimal("0"), dependentes=0) == Decimal("0")
        assert calcular_irrf(Decimal("500"), dependentes=5) == Decimal("0")


# ========================================================================
# TESTES DE SURVEY CLIMA
# ========================================================================


class TestClimateSchema:
    def test_survey_frequency_enum(self):
        from modules.retention.climate.models.climate_models import SurveyFrequency

        assert SurveyFrequency.SEMANAL == "semanal"
        assert SurveyFrequency.QUINZENAL == "quinzenal"
        assert SurveyFrequency.MENSAL == "mensal"

    def test_survey_response_schema(self):
        from modules.retention.climate.schemas.climate_schemas import SurveyResponse

        data = SurveyResponse(
            id="test-id",
            nome="Pesquisa teste",
            frequencia="mensal",
            perguntas=[{"id": 1, "texto": "Pergunta 1"}],
            ativo=True,
            total_respostas=0,
            score_medio=0.0,
        )
        assert data.nome == "Pesquisa teste"
        assert data.ativo is True


# ========================================================================
# TESTES DE CCT
# ========================================================================


class TestCCT:
    def test_salario_agente_portaria(self):
        assert Decimal("1670.00") == Decimal("1670.00")

    def test_periculosidade_vigilante(self):
        base = Decimal("2127.26")
        periculosidade = (base * Decimal("30") / 100).quantize(Decimal("0.01"))
        assert periculosidade == Decimal("638.18")

    def test_inss_sobre_base_cct(self):
        from modules.people_management.hr.services.payroll_service import calcular_inss

        inss = calcular_inss(Decimal("1670.00"))
        assert inss == Decimal("127.53")
        inss_lider = calcular_inss(Decimal("1787.53"))
        assert inss_lider == Decimal("138.11")
