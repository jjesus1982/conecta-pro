"""Testes dos Agents: GED, OPS, RH, SST, PORTAL e seus Skills."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from modules.people_management.agents.ged_agent import (
    DriveSkill,
    ExportSkill,
    GEDAgent,
    KitBuilderSkill,
    StorageSkill,
)
from modules.people_management.agents.ops_agent import (
    AllocatorSkill,
    DisciplineSkill,
    OPSAgent,
    SchedulerSkill,
)
from modules.people_management.agents.portal_agent import (
    NotificationType,
    NotifierSkill,
    PortalAgent,
    RequestSkill,
    ViewerSkill,
)
from modules.people_management.agents.rh_agent import (
    EvaluatorSkill,
    RecruiterSkill,
    RHAgent,
    TrainerSkill,
)
from modules.people_management.agents.sst_agent import (
    AccidentSkill,
    HealthSkill,
    RiskSkill,
    SafetySkill,
    SSTAgent,
)
from modules.people_management.core.events import Event, GPEventTypes

# ==========================================
# GED
# ==========================================


class TestStorageSkill:
    @pytest.fixture
    def skill(self):
        return StorageSkill()

    def test_document_count_70(self, skill):
        assert skill.get_document_count() == 70

    def test_get_by_category(self, skill):
        sst = skill.get_document_types("sst")
        assert len(sst) == 14

    def test_get_categories(self, skill):
        cats = skill.get_categories()
        assert "admissional" in cats
        assert "mensal" in cats
        assert "sst" in cats
        assert "rescisao" in cats

    def test_mandatory_admissional(self, skill):
        mandatory = skill.get_mandatory_documents("admissional")
        assert "ficha_registro" in mandatory
        assert "contrato_trabalho" in mandatory

    def test_certidoes_all_mandatory(self, skill):
        mandatory = skill.get_mandatory_documents("certidao")
        assert len(mandatory) == 5


class TestKitBuilderSkill:
    @pytest.fixture
    def skill(self):
        return KitBuilderSkill()

    def test_build_kit(self, skill):
        kit = skill.build_kit("client-1", 3, 2026, ["e1", "e2", "e3"])
        assert kit["client_id"] == "client-1"
        assert kit["reference"] == "2026-03"
        assert kit["employee_count"] == 3
        assert kit["expected_documents"] == 24  # 3 employees * 8 doc types
        assert kit["status"] == "montando"

    def test_build_kit_custom_docs(self, skill):
        kit = skill.build_kit("c1", 1, 2026, ["e1"], document_types=["contracheque"])
        assert kit["expected_documents"] == 1


class TestExportSkill:
    @pytest.fixture
    def skill(self):
        return ExportSkill()

    def test_prepare_export_pdf(self, skill):
        result = skill.prepare_export("kit-1", "pdf")
        assert result["format"] == "pdf"
        assert result["status"] == "preparando"

    def test_prepare_export_invalid(self, skill):
        with pytest.raises(ValueError):
            skill.prepare_export("kit-1", "doc")

    def test_supported_formats(self, skill):
        assert "pdf" in skill.SUPPORTED_FORMATS
        assert "zip" in skill.SUPPORTED_FORMATS
        assert "xlsx" in skill.SUPPORTED_FORMATS


class TestDriveSkill:
    def test_prepare_upload(self):
        skill = DriveSkill()
        result = skill.prepare_upload("kit.pdf", 1024000, "/kits/2026-03")
        assert result["file_name"] == "kit.pdf"
        assert result["status"] == "pending"


class TestGEDAgent:
    @pytest.fixture
    def agent(self):
        bus = MagicMock()
        bus.subscribe = MagicMock()
        bus.emit = AsyncMock()
        return GEDAgent(event_bus=bus)

    def test_agent_name(self, agent):
        assert agent.AGENT_NAME == "GED_AGENT"

    def test_has_skills(self, agent):
        assert agent.get_skill("STORAGE") is not None
        assert agent.get_skill("KIT_BUILDER") is not None
        assert agent.get_skill("EXPORT") is not None
        assert agent.get_skill("DRIVE") is not None

    def test_handled_events(self, agent):
        events = agent.handled_events
        assert GPEventTypes.DOCUMENTO_CRIADO in events
        assert GPEventTypes.FOLHA_FECHADA in events
        assert GPEventTypes.FUNCIONARIO_ADMITIDO in events
        assert len(events) >= 10

    @pytest.mark.asyncio
    async def test_on_documento_criado(self, agent):
        event = Event(event_type=GPEventTypes.DOCUMENTO_CRIADO, payload={"tipo": "contracheque"}, source_module="DP")
        await agent._process_event(event)

    @pytest.mark.asyncio
    async def test_on_folha_fechada(self, agent):
        event = Event(event_type=GPEventTypes.FOLHA_FECHADA, payload={"month": "2026-03"}, source_module="DP")
        await agent._process_event(event)


# ==========================================
# OPS
# ==========================================


class TestSchedulerSkill:
    @pytest.fixture
    def skill(self):
        return SchedulerSkill()

    def test_criar_escala_12x36(self, skill):
        result = skill.criar_escala("12x36", "posto-1", ["e1", "e2"], "2026-03-01", "2026-03-31")
        assert result["tipo"] == "12x36"
        assert result["status"] == "rascunho"

    def test_criar_escala_invalida(self, skill):
        with pytest.raises(ValueError):
            skill.criar_escala("invalida", "posto-1", ["e1"], "2026-03-01", "2026-03-31")

    def test_calcular_cobertura(self, skill):
        postos = [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]
        alocacoes = [{"posto_id": "p1"}, {"posto_id": "p3"}]
        result = skill.calcular_cobertura(postos, alocacoes)
        assert result["percentual_cobertura"] == 66.7
        assert result["postos_descobertos"] == 1

    def test_calcular_cobertura_vazio(self, skill):
        result = skill.calcular_cobertura([], [])
        assert result["percentual_cobertura"] == 0


class TestAllocatorSkill:
    @pytest.fixture
    def skill(self):
        return AllocatorSkill()

    def test_alocar(self, skill):
        result = skill.alocar("e1", "p1", "diurno", "2026-03-01")
        assert result["status"] == "ativa"
        assert result["employee_id"] == "e1"

    def test_desalocar(self, skill):
        result = skill.desalocar("aloc-1", "rescisao")
        assert result["status"] == "encerrada"
        assert result["motivo"] == "rescisao"


class TestDisciplineSkill:
    @pytest.fixture
    def skill(self):
        return DisciplineSkill()

    def test_advertencia_verbal(self, skill):
        result = skill.aplicar_medida("e1", "advertencia_verbal", "Atraso", "sup-1")
        assert result["pontos"] == 1
        assert result["dias_suspensao"] == 0

    def test_suspensao_3_dias(self, skill):
        result = skill.aplicar_medida("e1", "suspensao_3_dias", "Falta grave", "sup-1")
        assert result["pontos"] == 5
        assert result["dias_suspensao"] == 3

    def test_tipo_invalido(self, skill):
        with pytest.raises(ValueError):
            skill.aplicar_medida("e1", "nao_existe", "X", "sup-1")


class TestOPSAgent:
    @pytest.fixture
    def agent(self):
        bus = MagicMock()
        bus.subscribe = MagicMock()
        bus.emit = AsyncMock()
        return OPSAgent(event_bus=bus)

    def test_agent_name(self, agent):
        assert agent.AGENT_NAME == "OPS_AGENT"

    def test_has_skills(self, agent):
        assert agent.get_skill("SCHEDULER") is not None
        assert agent.get_skill("ALLOCATOR") is not None
        assert agent.get_skill("DISCIPLINE") is not None

    @pytest.mark.asyncio
    async def test_on_cat(self, agent):
        event = Event(event_type=GPEventTypes.CAT_ABERTA, payload={"employee_id": "e1"}, source_module="SST")
        await agent._process_event(event)


# ==========================================
# RH
# ==========================================


class TestRecruiterSkill:
    @pytest.fixture
    def skill(self):
        return RecruiterSkill()

    def test_criar_vaga(self, skill):
        result = skill.criar_vaga("Vigilante", "Operacoes", {"min": 1800, "max": 2500}, ["NR-10"])
        assert result["status"] == "aberta"
        assert len(result["etapas"]) == 7

    def test_avancar_etapa(self, skill):
        result = skill.avancar_etapa("c1", "triagem_curriculo")
        assert result["pode_avancar"] is True
        assert result["etapa_nova"] == "entrevista_rh"

    def test_avancar_ultima_etapa(self, skill):
        result = skill.avancar_etapa("c1", "aprovado")
        assert result["pode_avancar"] is False


class TestTrainerSkill:
    @pytest.fixture
    def skill(self):
        return TrainerSkill()

    def test_criar_treinamento(self, skill):
        result = skill.criar_treinamento("NR-10", "nr", 40, obrigatorio=True)
        assert result["status"] == "agendado"
        assert result["obrigatorio"] is True

    def test_emitir_certificado(self, skill):
        result = skill.emitir_certificado("t1", "e1", nota=9.5)
        assert result["status"] == "valido"
        assert result["nota"] == 9.5

    def test_verificar_nrs_pendentes(self, skill):
        pendentes = skill.verificar_nrs_pendentes(["NR-05", "NR-06"])
        assert "NR-10" in pendentes
        assert "NR-35" in pendentes
        assert "NR-05" not in pendentes


class TestEvaluatorSkill:
    @pytest.fixture
    def skill(self):
        return EvaluatorSkill()

    def test_criar_avaliacao(self, skill):
        result = skill.criar_avaliacao("e1", "sup-1", "2026-Q1")
        assert result["status"] == "pendente"
        assert len(result["dimensoes"]) == 6

    def test_calcular_media(self, skill):
        notas = {"competencia_tecnica": 8.0, "trabalho_equipe": 9.0, "pontualidade": 7.0}
        media = skill.calcular_media(notas)
        assert media == 8.0

    def test_calcular_media_vazia(self, skill):
        assert skill.calcular_media({}) == 0.0


class TestRHAgent:
    @pytest.fixture
    def agent(self):
        bus = MagicMock()
        bus.subscribe = MagicMock()
        bus.emit = AsyncMock()
        return RHAgent(event_bus=bus)

    def test_agent_name(self, agent):
        assert agent.AGENT_NAME == "RH_AGENT"

    def test_has_skills(self, agent):
        assert agent.get_skill("RECRUITER") is not None
        assert agent.get_skill("TRAINER") is not None
        assert agent.get_skill("EVALUATOR") is not None

    @pytest.mark.asyncio
    async def test_on_admitido(self, agent):
        event = Event(event_type=GPEventTypes.FUNCIONARIO_ADMITIDO, payload={"employee_id": "e1"}, source_module="DP")
        await agent._process_event(event)

    @pytest.mark.asyncio
    async def test_on_treinamento_realizado(self, agent):
        event = Event(
            event_type=GPEventTypes.TREINAMENTO_REALIZADO,
            payload={"treinamento_id": "t1", "employee_id": "e1"},
            source_module="RH",
        )
        await agent._process_event(event)


# ==========================================
# SST
# ==========================================


class TestHealthSkill:
    @pytest.fixture
    def skill(self):
        return HealthSkill()

    def test_agendar_aso_admissional(self, skill):
        result = skill.agendar_aso("e1", "admissional", "2026-03-20")
        assert result["status"] == "agendado"
        assert result["tipo"] == "admissional"

    def test_agendar_aso_invalido(self, skill):
        with pytest.raises(ValueError):
            skill.agendar_aso("e1", "invalido", "2026-03-20")

    def test_registrar_resultado(self, skill):
        result = skill.registrar_resultado("aso-1", True, ["Nao operar maquinas"])
        assert result["apto"] is True
        assert len(result["restricoes"]) == 1

    def test_verificar_vencimentos(self, skill):
        asos = [
            {
                "aso_id": "a1",
                "employee_id": "e1",
                "tipo": "periodico",
                "realizado_em": (datetime.utcnow() - timedelta(days=340)).isoformat(),
            }
        ]
        vencendo = skill.verificar_vencimentos(asos, dias_antecedencia=30)
        assert len(vencendo) == 1
        assert vencendo[0]["dias_restantes"] <= 30


class TestSafetySkill:
    @pytest.fixture
    def skill(self):
        return SafetySkill()

    def test_registrar_entrega_epi(self, skill):
        result = skill.registrar_entrega_epi("e1", "Coturno")
        assert result["epi"] == "Coturno"
        assert result["status"] == "entregue"
        assert result["nr"] == "NR-6"

    def test_registrar_epi_desconhecido(self, skill):
        result = skill.registrar_entrega_epi("e1", "EPI Generico")
        assert result["status"] == "entregue"

    def test_epis_count(self, skill):
        assert len(skill.EPIS_VIGILANCIA) == 5


class TestAccidentSkill:
    @pytest.fixture
    def skill(self):
        return AccidentSkill()

    def test_abrir_cat(self, skill):
        result = skill.abrir_cat("e1", "tipico", "Queda", "2026-03-13", "Posto Alpha")
        assert result["status"] == "aberta"
        assert result["tipo"] == "tipico"
        assert result["gravidade"] == "leve"

    def test_abrir_cat_grave(self, skill):
        result = skill.abrir_cat("e1", "tipico", "Queda", "2026-03-13", "Posto A", gravidade="grave")
        assert result["gravidade"] == "grave"


class TestRiskSkill:
    @pytest.fixture
    def skill(self):
        return RiskSkill()

    def test_mapear_risco(self, skill):
        result = skill.mapear_risco("p1", "fisico", "Ruido acima de 85dB", "alto")
        assert result["categoria"] == "fisico"
        assert result["nivel"] == "alto"

    def test_mapear_risco_invalido(self, skill):
        with pytest.raises(ValueError):
            skill.mapear_risco("p1", "invalido", "X")

    def test_categorias_risco(self, skill):
        assert len(skill.CATEGORIAS_RISCO) == 5


class TestSSTAgent:
    @pytest.fixture
    def agent(self):
        bus = MagicMock()
        bus.subscribe = MagicMock()
        bus.emit = AsyncMock()
        return SSTAgent(event_bus=bus)

    def test_agent_name(self, agent):
        assert agent.AGENT_NAME == "SST_AGENT"

    def test_has_skills(self, agent):
        assert agent.get_skill("HEALTH") is not None
        assert agent.get_skill("SAFETY") is not None
        assert agent.get_skill("ACCIDENT") is not None
        assert agent.get_skill("RISK") is not None

    @pytest.mark.asyncio
    async def test_on_admitido(self, agent):
        event = Event(event_type=GPEventTypes.FUNCIONARIO_ADMITIDO, payload={"employee_id": "e1"}, source_module="DP")
        await agent._process_event(event)

    @pytest.mark.asyncio
    async def test_on_ocorrencia_acidente(self, agent):
        event = Event(
            event_type=GPEventTypes.OCORRENCIA_REGISTRADA,
            payload={"employee_id": "e1", "tipo": "acidente_trabalho", "descricao": "Queda", "local": "Posto A"},
            source_module="OPS",
        )
        await agent._process_event(event)


# ==========================================
# PORTAL
# ==========================================


class TestNotifierSkill:
    @pytest.fixture
    def skill(self):
        return NotifierSkill()

    def test_criar_notificacao(self, skill):
        result = skill.criar_notificacao("e1", "Contracheque", "Disponivel")
        assert result["employee_id"] == "e1"
        assert result["lida"] is False

    def test_criar_em_massa(self, skill):
        result = skill.criar_notificacao_em_massa(["e1", "e2", "e3"], "Aviso", "Texto")
        assert len(result) == 3

    def test_criar_urgent(self, skill):
        result = skill.criar_notificacao("e1", "Alerta", "Urgente", NotificationType.URGENT)
        assert result["tipo"] == "urgent"


class TestViewerSkill:
    @pytest.fixture
    def skill(self):
        return ViewerSkill()

    def test_acesso_contracheque(self, skill):
        assert skill.verificar_acesso("e1", "contracheque") is True

    def test_acesso_negado(self, skill):
        assert skill.verificar_acesso("e1", "ppra_pgr") is False

    def test_listar_disponiveis(self, skill):
        docs = skill.listar_documentos_disponiveis()
        assert "contracheque" in docs
        assert len(docs) >= 10


class TestRequestSkill:
    @pytest.fixture
    def skill(self):
        return RequestSkill()

    def test_criar_solicitacao_ferias(self, skill):
        result = skill.criar_solicitacao("e1", "ferias", "Ferias janeiro")
        assert result["tipo"] == "ferias"
        assert result["status"] == "pendente"

    def test_criar_solicitacao_invalida(self, skill):
        with pytest.raises(ValueError):
            skill.criar_solicitacao("e1", "invalido", "X")

    def test_tipos_disponiveis(self, skill):
        assert len(skill.TIPOS_SOLICITACAO) == 8


class TestPortalAgent:
    @pytest.fixture
    def agent(self):
        bus = MagicMock()
        bus.subscribe = MagicMock()
        bus.emit = AsyncMock()
        return PortalAgent(event_bus=bus)

    def test_agent_name(self, agent):
        assert agent.AGENT_NAME == "PORTAL_AGENT"

    def test_has_skills(self, agent):
        assert agent.get_skill("NOTIFIER") is not None
        assert agent.get_skill("VIEWER") is not None
        assert agent.get_skill("REQUEST") is not None

    def test_notification_map_has_entries(self, agent):
        assert len(agent.EVENT_NOTIFICATION_MAP) >= 10

    @pytest.mark.asyncio
    async def test_process_folha_fechada(self, agent):
        event = Event(
            event_type=GPEventTypes.FOLHA_FECHADA,
            payload={"employee_id": "e1"},
            source_module="DP",
        )
        await agent._process_event(event)

    @pytest.mark.asyncio
    async def test_process_without_employee_id(self, agent):
        event = Event(
            event_type=GPEventTypes.FOLHA_FECHADA,
            payload={},
            source_module="DP",
        )
        # Should not raise
        await agent._process_event(event)
