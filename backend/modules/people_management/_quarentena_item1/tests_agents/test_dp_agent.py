"""Testes do DP Agent e Skills de Folha."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.people_management.agents.dp_agent import (
    BenefitsSkill,
    DPAgent,
    ESocialSkill,
    PayrollSkill,
    TaxSkill,
    VacationSkill,
)
from modules.people_management.core.events import Event, GPEventTypes


class TestPayrollSkill:
    @pytest.fixture
    def skill(self):
        return PayrollSkill()

    def test_calcular_inss_faixa_1(self, skill):
        inss = skill.calcular_inss(Decimal("1412.00"))
        assert inss == Decimal("105.90")

    def test_calcular_inss_faixa_alta(self, skill):
        inss = skill.calcular_inss(Decimal("7786.02"))
        assert inss <= skill.INSS_TETO

    def test_calcular_inss_zero(self, skill):
        inss = skill.calcular_inss(Decimal("0"))
        assert inss == Decimal("0.00")

    def test_calcular_ir_isento(self, skill):
        ir = skill.calcular_ir(Decimal("2000.00"))
        assert ir == Decimal("0.00")

    def test_calcular_ir_faixa_2(self, skill):
        ir = skill.calcular_ir(Decimal("2500.00"))
        assert ir > Decimal("0")

    def test_calcular_fgts(self, skill):
        fgts = skill.calcular_fgts(Decimal("3000.00"))
        assert fgts == Decimal("240.00")

    def test_calcular_folha_basica(self, skill):
        result = skill.calcular_folha(salario_base=Decimal("3000.00"))
        assert result["salario_base"] == 3000.0
        assert result["proventos"]["total_proventos"] == 3000.0
        assert result["descontos"]["inss"] > 0
        assert result["salario_liquido"] > 0
        assert result["salario_liquido"] < 3000.0

    def test_calcular_folha_com_horas_extras(self, skill):
        result = skill.calcular_folha(
            salario_base=Decimal("3000.00"),
            horas_extras_50=Decimal("10"),
        )
        assert result["proventos"]["horas_extras_50"] > 0
        assert result["proventos"]["total_proventos"] > 3000.0

    def test_calcular_folha_com_faltas(self, skill):
        sem_falta = skill.calcular_folha(salario_base=Decimal("3000.00"))
        com_falta = skill.calcular_folha(salario_base=Decimal("3000.00"), faltas_dias=2)
        assert com_falta["salario_liquido"] < sem_falta["salario_liquido"]

    def test_calcular_folha_com_beneficios(self, skill):
        result = skill.calcular_folha(
            salario_base=Decimal("3000.00"),
            desconto_vt=Decimal("180.00"),
            desconto_plano_saude=Decimal("200.00"),
        )
        assert result["descontos"]["vt"] == 180.0
        assert result["descontos"]["plano_saude"] == 200.0

    def test_calcular_folha_com_insalubridade(self, skill):
        result = skill.calcular_folha(
            salario_base=Decimal("3000.00"),
            adicional_insalubridade=Decimal("282.40"),
        )
        assert result["proventos"]["adicional_insalubridade"] == 282.40

    def test_calcular_folha_com_periculosidade(self, skill):
        result = skill.calcular_folha(
            salario_base=Decimal("3000.00"),
            adicional_periculosidade=Decimal("900.00"),
        )
        assert result["proventos"]["adicional_periculosidade"] == 900.0


class TestVacationSkill:
    @pytest.fixture
    def skill(self):
        return VacationSkill()

    def test_ferias_30_dias(self, skill):
        result = skill.calcular_ferias(Decimal("3000.00"))
        assert result["dias_gozo"] == 30
        assert result["terco_constitucional"] == 1000.0
        assert result["total_bruto"] == 4000.0

    def test_ferias_com_abono(self, skill):
        result = skill.calcular_ferias(Decimal("3000.00"), abono_pecuniario=True)
        assert result["dias_gozo"] == 20
        assert result["dias_abono"] == 10
        assert result["abono_pecuniario"] > 0

    def test_ferias_20_dias(self, skill):
        result = skill.calcular_ferias(Decimal("3000.00"), dias=20)
        assert result["dias_gozo"] == 20


class TestBenefitsSkill:
    @pytest.fixture
    def skill(self):
        return BenefitsSkill()

    def test_desconto_vt_normal(self, skill):
        result = skill.calcular_desconto_vt(Decimal("3000.00"), Decimal("15.00"))
        assert result["desconto_funcionario"] == 180.0
        assert result["custo_total_empresa"] == 330.0

    def test_desconto_vt_teto(self, skill):
        result = skill.calcular_desconto_vt(Decimal("2000.00"), Decimal("20.00"))
        # 6% de 2000 = 120, custo total = 440
        assert result["desconto_funcionario"] == 120.0


class TestESocialSkill:
    @pytest.fixture
    def skill(self):
        return ESocialSkill()

    def test_gerar_evento_admissao(self, skill):
        result = skill.gerar_evento("admissao", {"cpf": "12345678900"})
        assert result["codigo_evento"] == "S-2200"
        assert result["status"] == "pendente"

    def test_gerar_evento_desligamento(self, skill):
        result = skill.gerar_evento("desligamento", {})
        assert result["codigo_evento"] == "S-2299"

    def test_gerar_evento_invalido(self, skill):
        with pytest.raises(ValueError):
            skill.gerar_evento("invalido", {})

    def test_listar_eventos(self, skill):
        eventos = skill.listar_eventos_pendentes()
        assert "S-2200" in eventos
        assert "S-2299" in eventos
        assert len(eventos) == 9


class TestTaxSkill:
    @pytest.fixture
    def skill(self):
        return TaxSkill()

    def test_encargos_empresa(self, skill):
        result = skill.calcular_encargos_empresa(Decimal("3000.00"))
        assert result["inss_patronal"] == 600.0
        assert result["fgts"] == 240.0
        assert result["total_encargos"] > 0
        assert result["percentual_total"] > 30


class TestDPAgent:
    @pytest.fixture
    def agent(self):
        bus = MagicMock()
        bus.subscribe = MagicMock()
        bus.emit = AsyncMock()
        return DPAgent(event_bus=bus)

    def test_agent_name(self, agent):
        assert agent.AGENT_NAME == "DP_AGENT"

    def test_has_all_skills(self, agent):
        assert agent.get_skill("PAYROLL") is not None
        assert agent.get_skill("VACATION") is not None
        assert agent.get_skill("BENEFITS") is not None
        assert agent.get_skill("ESOCIAL") is not None
        assert agent.get_skill("TAX") is not None

    def test_handled_events(self, agent):
        events = agent.handled_events
        assert GPEventTypes.FUNCIONARIO_ADMITIDO in events
        assert GPEventTypes.PONTO_MES_FECHADO in events
        assert GPEventTypes.LAUDO_EMITIDO in events
        assert len(events) >= 10

    @pytest.mark.asyncio
    async def test_process_admissao(self, agent):
        event = Event(
            event_type=GPEventTypes.FUNCIONARIO_ADMITIDO,
            payload={"employee_id": "emp-1", "nome": "Joao"},
            source_module="RH",
        )
        await agent._process_event(event)

    @pytest.mark.asyncio
    async def test_process_ponto_mes_fechado(self, agent):
        event = Event(
            event_type=GPEventTypes.PONTO_MES_FECHADO,
            payload={"employee_id": "emp-1", "month": "2026-03"},
            source_module="PONTO",
        )
        await agent._process_event(event)
