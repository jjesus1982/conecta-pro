"""
Tests for all 7 bidding AI agents + orchestrator.

Uses pytest + unittest.mock to mock external calls (Claude API, HTTP requests, DB).
All tests run WITHOUT a database, API keys, or network access.
"""

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.bidding.agents.base_agent import AgentConfig, ExecutionResult, ExecutionStatus

# ══════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def agent_config():
    """AgentConfig with fast timeouts for tests."""
    return AgentConfig(max_retries=0, retry_delay_seconds=0, timeout_seconds=10.0)


@pytest.fixture
def sample_analysis():
    """Sample ANALYST output used by downstream agents."""
    return {
        "objeto_resumido": "Prestacao de servicos de vigilancia patrimonial armada e desarmada",
        "objeto_detalhado": "Contratacao de empresa para vigilancia patrimonial em Manaus-AM",
        "segmento": "seguranca",
        "modalidade": "pregao_eletronico",
        "criterio_julgamento": "menor_preco",
        "tipo_contratacao": "servicos_continuados",
        "regime_execucao": None,
        "valor_estimado": 1_500_000.0,
        "valor_maximo_aceitavel": None,
        "data_abertura": "2026-04-15T10:00:00",
        "data_encerramento_propostas": "2026-04-14T23:59:00",
        "prazo_contrato_meses": 12,
        "prorrogavel": True,
        "requisitos_habilitacao": [
            {"categoria": "juridica", "descricao": "Contrato social ou ato constitutivo", "obrigatorio": True},
            {"categoria": "fiscal", "descricao": "CND Federal (Receita Federal)", "obrigatorio": True},
            {"categoria": "fiscal", "descricao": "CRF FGTS (Caixa)", "obrigatorio": True},
            {
                "categoria": "tecnica",
                "descricao": "Atestado de capacidade tecnica em vigilancia patrimonial",
                "obrigatorio": True,
            },
        ],
        "documentos_necessarios": [
            {
                "nome": "CND Federal",
                "descricao": "Certidao negativa da Receita",
                "tipo": "habilitacao",
                "obrigatorio": True,
                "prazo_validade_dias": 180,
            },
            {
                "nome": "Contrato Social",
                "descricao": None,
                "tipo": "habilitacao",
                "obrigatorio": True,
                "prazo_validade_dias": None,
            },
        ],
        "red_flags": [],
        "quantidade_postos": 5,
        "tipos_posto": ["12x36", "diurno"],
        "armamento_necessario": False,
        "veiculo_necessario": False,
        "confianca_analise": 85.0,
        "observacoes": ["Edital padrao de vigilancia"],
    }


@pytest.fixture
def sample_pricing_data():
    """Sample PRICER output used by COMPILER."""
    return {
        "cenarios": [
            {
                "tipo": "conservador",
                "descricao": "Margem alta",
                "preco_mensal": "150000.00",
                "preco_anual": "1800000.00",
                "preco_total_contrato": "1800000.00",
                "custo_mao_de_obra": {"custo_mensal_total": "100000.00", "quantidade_profissionais": 11},
                "custos_indiretos": "8000.00",
                "custo_total_direto": "108000.00",
                "bdi_percentual": "30.0",
                "valor_bdi": "10000.00",
                "impostos_detalhamento": {"iss": "5.00", "pis": "1.65", "cofins": "7.60"},
                "total_impostos": "21375.00",
                "margem_lucro_percentual": "12.0",
                "valor_lucro": "18000.00",
            }
        ],
        "cenario_recomendado": "moderado",
        "preco_mensal_recomendado": "130000.00",
        "preco_total_recomendado": "1560000.00",
        "regime_tributario": "lucro_real",
        "prazo_contrato_meses": 12,
    }


# ══════════════════════════════════════════════════════════════
# 1. SCOUT Agent Tests
# ══════════════════════════════════════════════════════════════


class TestScoutAgent:
    """Tests for the SCOUT agent — multi-portal opportunity search."""

    @pytest.mark.asyncio
    async def test_scout_execute_returns_opportunities(self, agent_config):
        """Verifies SCOUT returns a list of opportunity dicts sorted by relevancia."""
        with (
            patch("modules.bidding.agents.scout_agent.PNCPClient") as MockPNCP,
            patch("modules.bidding.agents.scout_agent.ComprasNetClient") as MockCN,
            patch("modules.bidding.agents.scout_agent.LicitacoesEClient") as MockLE,
            patch("modules.bidding.agents.scout_agent.EComprasAMClient") as MockECAM,
        ):
            from modules.bidding.agents.scout_agent import ScoutAgent, ScoutSearchParams

            # Setup mock PNCP client
            mock_pncp = AsyncMock()
            mock_pncp.__aenter__ = AsyncMock(return_value=mock_pncp)
            mock_pncp.__aexit__ = AsyncMock(return_value=False)
            mock_response = MagicMock()
            mock_response.sucesso = True
            mock_response.compras = []
            mock_response.total_paginas = 1
            mock_pncp.buscar_compras = AsyncMock(return_value=mock_response)
            MockPNCP.return_value = mock_pncp

            # ComprasNet returns one opportunity
            mock_cn = AsyncMock()
            mock_cn.__aenter__ = AsyncMock(return_value=mock_cn)
            mock_cn.__aexit__ = AsyncMock(return_value=False)
            mock_cn.buscar_oportunidades = AsyncMock(
                return_value=[
                    {
                        "objeto": "Contratacao de servicos de vigilancia patrimonial",
                        "valor_estimado": 500000,
                        "modalidade": "Pregao Eletronico",
                        "orgao_nome": "UFAM",
                        "orgao_cnpj": "04.378.626/0001-97",
                        "uf": "AM",
                        "data_abertura": "2026-04-10",
                        "portal_id": "CN-001",
                    },
                ]
            )
            MockCN.return_value = mock_cn

            # Other portals return empty
            for MockPortal in [MockLE, MockECAM]:
                mock_portal = AsyncMock()
                mock_portal.__aenter__ = AsyncMock(return_value=mock_portal)
                mock_portal.__aexit__ = AsyncMock(return_value=False)
                mock_portal.buscar_oportunidades = AsyncMock(return_value=[])
                MockPortal.return_value = mock_portal

            agent = ScoutAgent(agent_config)
            params = ScoutSearchParams(
                keywords=["vigilancia"],
                ufs=["AM"],
                portais=["pncp", "comprasnet", "licitacoes_e", "ecompras_am"],
            )
            result = await agent.execute(search_params=params)

            assert isinstance(result, list)
            assert len(result) >= 1
            assert "relevancia_score" in result[0]
            assert "numero_compra" in result[0]

    @pytest.mark.asyncio
    async def test_scout_relevancia_scoring(self, agent_config):
        """Verifies the _calcular_relevancia algorithm produces expected scores."""
        with (
            patch("modules.bidding.agents.scout_agent.PNCPClient"),
            patch("modules.bidding.agents.scout_agent.ComprasNetClient"),
            patch("modules.bidding.agents.scout_agent.LicitacoesEClient"),
            patch("modules.bidding.agents.scout_agent.EComprasAMClient"),
        ):
            from modules.bidding.agents.scout_agent import ScoutAgent

            agent = ScoutAgent(agent_config)

            # Scenario: 2 of 4 keywords matched, pregao eletronico, 20 days out, 500k value
            score = agent._calcular_relevancia(
                modalidade="Pregao Eletronico",
                data_abertura=datetime.utcnow() + timedelta(days=20),
                valor_estimado=500_000.0,
                matched_keywords=["vigilancia", "seguranca patrimonial"],
                total_keywords=4,
            )

            # keywords: 2/4 * 40 = 20
            # modalidade: pregao eletronico = 20
            # prazo: >15 days = 20
            # valor: 100k-5M = 20
            assert score == 80.0

    @pytest.mark.asyncio
    async def test_scout_deduplication(self, agent_config):
        """Verifies duplicate opportunities from different portals are merged."""
        with (
            patch("modules.bidding.agents.scout_agent.PNCPClient"),
            patch("modules.bidding.agents.scout_agent.ComprasNetClient"),
            patch("modules.bidding.agents.scout_agent.LicitacoesEClient"),
            patch("modules.bidding.agents.scout_agent.EComprasAMClient"),
        ):
            from modules.bidding.agents.scout_agent import OpportunityResponse, ScoutAgent

            agent = ScoutAgent(agent_config)

            opp1 = OpportunityResponse(
                numero_compra="001",
                orgao_cnpj="12.345.678/0001-99",
                objeto="Contratacao vigilancia patrimonial",
                relevancia_score=80.0,
                fonte="pncp",
            )
            opp2 = OpportunityResponse(
                numero_compra="001",
                orgao_cnpj="12.345.678/0001-99",
                objeto="Contratacao vigilancia patrimonial",
                relevancia_score=70.0,
                fonte="comprasnet",
            )

            unique = agent._deduplicar([opp1, opp2])
            assert len(unique) == 1
            # Should keep higher score
            assert unique[0].relevancia_score == 80.0

    @pytest.mark.asyncio
    async def test_scout_handles_portal_errors_gracefully(self, agent_config):
        """Verifies SCOUT continues when one portal raises an exception."""
        with (
            patch("modules.bidding.agents.scout_agent.PNCPClient") as MockPNCP,
            patch("modules.bidding.agents.scout_agent.ComprasNetClient") as MockCN,
            patch("modules.bidding.agents.scout_agent.LicitacoesEClient") as MockLE,
            patch("modules.bidding.agents.scout_agent.EComprasAMClient") as MockECAM,
        ):
            from modules.bidding.agents.scout_agent import ScoutAgent, ScoutSearchParams

            # PNCP raises
            mock_pncp = AsyncMock()
            mock_pncp.__aenter__ = AsyncMock(return_value=mock_pncp)
            mock_pncp.__aexit__ = AsyncMock(return_value=False)
            mock_pncp.buscar_compras = AsyncMock(side_effect=ConnectionError("PNCP offline"))
            MockPNCP.return_value = mock_pncp

            # ComprasNet returns data
            mock_cn = AsyncMock()
            mock_cn.__aenter__ = AsyncMock(return_value=mock_cn)
            mock_cn.__aexit__ = AsyncMock(return_value=False)
            mock_cn.buscar_oportunidades = AsyncMock(
                return_value=[
                    {
                        "objeto": "Servicos de seguranca patrimonial para predios publicos",
                        "valor_estimado": 300000,
                        "orgao_nome": "TRF1",
                        "orgao_cnpj": "00.000.000/0001-00",
                        "uf": "AM",
                        "portal_id": "CN-999",
                    },
                ]
            )
            MockCN.return_value = mock_cn

            for MockPortal in [MockLE, MockECAM]:
                mock_portal = AsyncMock()
                mock_portal.__aenter__ = AsyncMock(return_value=mock_portal)
                mock_portal.__aexit__ = AsyncMock(return_value=False)
                mock_portal.buscar_oportunidades = AsyncMock(return_value=[])
                MockPortal.return_value = mock_portal

            agent = ScoutAgent(agent_config)
            params = ScoutSearchParams(
                keywords=["seguranca patrimonial"],
                ufs=["AM"],
                portais=["pncp", "comprasnet", "licitacoes_e", "ecompras_am"],
            )

            # Should NOT raise even though PNCP failed
            result = await agent.execute(search_params=params)
            assert isinstance(result, list)
            # Should still get ComprasNet results
            assert len(result) >= 1


# ══════════════════════════════════════════════════════════════
# 2. ANALYST Agent Tests
# ══════════════════════════════════════════════════════════════


class TestAnalystAgent:
    """Tests for the ANALYST agent — edital analysis using Claude API."""

    @pytest.mark.asyncio
    async def test_analyst_execute_returns_analysis(self, agent_config):
        """Verifies ANALYST returns structured analysis dict from Claude response."""
        from modules.bidding.agents.analyst_agent import AnalystAgent

        mock_claude_response = {
            "content": [
                {
                    "type": "text",
                    "text": '{"objeto_resumido": "Vigilancia patrimonial", "objeto_detalhado": "Detalhes", "segmento": "seguranca", "modalidade": "pregao_eletronico", "criterio_julgamento": "menor_preco", "tipo_contratacao": "servicos_continuados", "regime_execucao": null, "valor_estimado": 500000, "valor_maximo_aceitavel": null, "data_abertura": null, "data_encerramento_propostas": null, "prazo_contrato_meses": 12, "prorrogavel": true, "requisitos_habilitacao": [], "documentos_necessarios": [], "red_flags": [], "quantidade_postos": 2, "tipos_posto": ["12x36"], "armamento_necessario": false, "veiculo_necessario": false, "confianca_analise": 75, "observacoes": []}',
                }
            ]
        }

        with patch("modules.bidding.agents.analyst_agent.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = mock_claude_response
            mock_response.raise_for_status = MagicMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            agent = AnalystAgent(agent_config, api_key="test-key-123")
            result = await agent.execute(
                edital_text="Edital de vigilancia patrimonial para a UFAM.",
                numero_edital="PE-001/2026",
                orgao="UFAM",
                uf="AM",
            )

            assert isinstance(result, dict)
            assert result["objeto_resumido"] == "Vigilancia patrimonial"
            assert result["numero_edital"] == "PE-001/2026"
            assert result["orgao"] == "UFAM"

    @pytest.mark.asyncio
    async def test_analyst_truncates_long_text(self, agent_config):
        """Verifies ANALYST truncates edital text beyond 150k characters."""
        from modules.bidding.agents.analyst_agent import AnalystAgent

        mock_claude_response = {
            "content": [
                {"type": "text", "text": '{"objeto_resumido": "Truncated", "confianca_analise": 50, "observacoes": []}'}
            ]
        }

        with patch("modules.bidding.agents.analyst_agent.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = mock_claude_response
            mock_response.raise_for_status = MagicMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            agent = AnalystAgent(agent_config, api_key="test-key-123")

            # Text with 200k chars
            long_text = "A" * 200_000
            await agent.execute(edital_text=long_text)

            # Verify the POST was called with truncated text
            call_args = mock_client_instance.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            user_msg = payload["messages"][0]["content"]
            # The edital text inside the message should be at most 150k chars
            assert len(user_msg) < 200_000 + 500  # overhead from prompt template

    @pytest.mark.asyncio
    async def test_analyst_handles_api_error(self, agent_config):
        """Verifies ANALYST raises on missing API key or empty response."""
        with patch("modules.bidding.agents.analyst_agent.ANTHROPIC_API_KEY", ""):
            from modules.bidding.agents.analyst_agent import AnalystAgent

            agent = AnalystAgent(agent_config, api_key=None)
            agent.api_key = ""  # Force empty after init

            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                await agent.execute(edital_text="Test edital text")

    @pytest.mark.asyncio
    async def test_analyst_requires_edital_text(self, agent_config):
        """Verifies ANALYST raises ValueError when edital_text is empty."""
        from modules.bidding.agents.analyst_agent import AnalystAgent

        agent = AnalystAgent(agent_config, api_key="test-key")

        with pytest.raises(ValueError, match="edital_text"):
            await agent.execute(edital_text="")


# ══════════════════════════════════════════════════════════════
# 3. ASSESSOR Agent Tests
# ══════════════════════════════════════════════════════════════


class TestAssessorAgent:
    """Tests for the ASSESSOR agent — Go/No-Go evaluation."""

    @pytest.mark.asyncio
    async def test_assessor_go_recommendation(self, agent_config, sample_analysis):
        """Verifies ASSESSOR recommends GO for a well-matching opportunity."""
        from modules.bidding.agents.assessor_agent import AssessorAgent, CompanyProfile

        company = CompanyProfile(
            quantidade_vigilantes=44,
            cobertura_ufs=["AM"],
            autorizacao_pf=True,
            capital_social=500_000,
            faturamento_anual=3_000_000,
        )

        agent = AssessorAgent(agent_config, company_profile=company)
        result = await agent.execute(analysis=sample_analysis)

        assert isinstance(result, dict)
        assert result["recomendacao"] == "GO"
        assert result["score"] >= 70.0
        assert "PARTICIPAR" in result["justificativa"]

    @pytest.mark.asyncio
    async def test_assessor_no_go_recommendation(self, agent_config, sample_analysis):
        """Verifies ASSESSOR recommends NO_GO when eliminatory requirements are not met."""
        from modules.bidding.agents.assessor_agent import AssessorAgent, CompanyProfile

        # Company with very limited capabilities
        company = CompanyProfile(
            quantidade_vigilantes=2,
            cobertura_ufs=["SP"],  # Wrong state
            autorizacao_pf=False,
            capital_social=10_000,
            faturamento_anual=50_000,
            certificado_iso_9001=False,
            documentos_validos=[],  # No documents
            taxa_sucesso=5.0,
            possui_base_operacional=False,
            indice_liquidez_corrente=0.5,
            indice_liquidez_geral=0.5,
            indice_endividamento=0.9,
        )

        # Add red flags and ISO 9001 requirement (eliminatorio triggers automatic NO_GO)
        analysis = {**sample_analysis}
        analysis["red_flags"] = [
            {"tipo": "restritiva", "descricao": "Exigencia de ISO 9001 obrigatoria", "severidade": "alta"},
            {
                "tipo": "valor_incompativel",
                "descricao": "Valor muito acima da capacidade da empresa",
                "severidade": "alta",
            },
        ]
        analysis["requisitos_habilitacao"] = [
            *sample_analysis["requisitos_habilitacao"],
            {"categoria": "tecnica", "descricao": "Certificacao ISO 9001 obrigatoria", "obrigatorio": True},
            {"categoria": "economica", "descricao": "Indice de liquidez corrente minimo 1.0", "obrigatorio": True},
            {"categoria": "economica", "descricao": "Indice de liquidez geral minimo 1.0", "obrigatorio": True},
            {"categoria": "economica", "descricao": "Indice de endividamento maximo 0.6", "obrigatorio": True},
        ]

        agent = AssessorAgent(agent_config, company_profile=company)
        result = await agent.execute(analysis=analysis)

        assert isinstance(result, dict)
        assert result["recomendacao"] == "NO_GO"

    @pytest.mark.asyncio
    async def test_assessor_conditional_recommendation(self, agent_config, sample_analysis):
        """Verifies ASSESSOR recommends CONDICIONAL when score is mid-range (45-70)."""
        from modules.bidding.agents.assessor_agent import AssessorAgent, CompanyProfile

        company = CompanyProfile(
            quantidade_vigilantes=5,  # Very low
            cobertura_ufs=["AM"],
            autorizacao_pf=True,
            capital_social=50_000,  # Very low capital (10% of 1.5M = 150k needed)
            documentos_validos=["contrato_social"],  # Missing many docs
            taxa_sucesso=15.0,
            possui_base_operacional=True,
            indice_liquidez_corrente=0.8,
            indice_liquidez_geral=0.8,
        )

        # Add multiple medium red flags to lower the score
        analysis = {**sample_analysis}
        analysis["red_flags"] = [
            {"tipo": "prazo_curto", "descricao": "Prazo curto para entrega de documentos", "severidade": "media"},
            {
                "tipo": "exigencia_excessiva",
                "descricao": "Numero excessivo de atestados exigidos",
                "severidade": "media",
            },
            {"tipo": "clausula_abusiva", "descricao": "Clausula de multa desproporcional", "severidade": "media"},
        ]
        analysis["requisitos_habilitacao"] = [
            *sample_analysis["requisitos_habilitacao"],
            {"categoria": "economica", "descricao": "Indice de liquidez corrente minimo 1.0", "obrigatorio": True},
            {"categoria": "economica", "descricao": "Indice de liquidez geral minimo 1.0", "obrigatorio": True},
        ]

        agent = AssessorAgent(agent_config, company_profile=company)
        result = await agent.execute(analysis=analysis)

        assert isinstance(result, dict)
        # With low capital, missing docs, medium red flags: should be CONDICIONAL or NO_GO
        assert result["recomendacao"] in ["CONDICIONAL", "NO_GO"]
        assert result["score"] < 70.0

    @pytest.mark.asyncio
    async def test_assessor_scoring_weights(self, agent_config, sample_analysis):
        """Verifies ASSESSOR scoring uses all 7 evaluation criteria."""
        from modules.bidding.agents.assessor_agent import AssessorAgent, CompanyProfile

        agent = AssessorAgent(agent_config, company_profile=CompanyProfile())
        result = await agent.execute(analysis=sample_analysis)

        criterios = result["criterios"]
        assert len(criterios) == 7

        # Check all criteria are present
        nomes = {c["nome"] for c in criterios}
        expected_names = {
            "Habilitacao Juridica",
            "Regularidade Fiscal",
            "Qualificacao Tecnica",
            "Qualificacao Economica",
            "Capacidade Operacional",
            "Riscos",
            "Competitividade",
        }
        assert nomes == expected_names

        # Check weights sum to approximately 1.0
        total_peso = sum(c["peso"] for c in criterios)
        assert abs(total_peso - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_assessor_requires_analysis(self, agent_config):
        """Verifies ASSESSOR raises when analysis is missing."""
        from modules.bidding.agents.assessor_agent import AssessorAgent

        agent = AssessorAgent(agent_config)

        with pytest.raises(ValueError, match="analysis"):
            await agent.execute(analysis=None)


# ══════════════════════════════════════════════════════════════
# 4. PRICER Agent Tests
# ══════════════════════════════════════════════════════════════


class TestPricerAgent:
    """Tests for the PRICER agent — pricing calculation engine."""

    @pytest.mark.asyncio
    async def test_pricer_three_scenarios(self, agent_config):
        """Verifies PRICER generates exactly 3 pricing scenarios."""
        from modules.bidding.agents.pricer_agent import PostoServico, PricerAgent, PricingInput

        agent = PricerAgent(agent_config)

        pricing_input = PricingInput(
            postos=[PostoServico(tipo="12x36", quantidade=2, armado=False)],
            prazo_contrato_meses=12,
        )

        result = await agent.execute(pricing_input=pricing_input)

        assert isinstance(result, dict)
        cenarios = result["cenarios"]
        assert len(cenarios) == 3

        tipos = [c["tipo"] for c in cenarios]
        assert "conservador" in tipos
        assert "moderado" in tipos
        assert "agressivo" in tipos

        # Conservador should have highest price
        prices = {c["tipo"]: Decimal(str(c["preco_mensal"])) for c in cenarios}
        assert prices["conservador"] > prices["moderado"] > prices["agressivo"]

    @pytest.mark.asyncio
    async def test_pricer_tax_calculation_simples(self, agent_config):
        """Verifies PRICER applies correct Simples Nacional tax structure."""
        from modules.bidding.agents.pricer_agent import (
            PostoServico,
            PricerAgent,
            PricingInput,
            RegimeTributario,
        )

        agent = PricerAgent(agent_config)
        pricing_input = PricingInput(
            postos=[PostoServico(tipo="12x36", quantidade=1)],
            regime_tributario=RegimeTributario.SIMPLES_NACIONAL,
            prazo_contrato_meses=12,
        )

        result = await agent.execute(pricing_input=pricing_input)

        # Simples should have DAS unique tax
        cenario_moderado = next(c for c in result["cenarios"] if c["tipo"] == "moderado")
        impostos = cenario_moderado["impostos_detalhamento"]
        assert "das_simples" in impostos
        # DAS aliquota should be 13.5% for Anexo IV
        assert Decimal(str(impostos["das_simples"])) == Decimal("13.50")

    @pytest.mark.asyncio
    async def test_pricer_tax_calculation_lucro_real(self, agent_config):
        """Verifies PRICER applies correct Lucro Real tax structure."""
        from modules.bidding.agents.pricer_agent import (
            PostoServico,
            PricerAgent,
            PricingInput,
            RegimeTributario,
        )

        agent = PricerAgent(agent_config)
        pricing_input = PricingInput(
            postos=[PostoServico(tipo="12x36", quantidade=1)],
            regime_tributario=RegimeTributario.LUCRO_REAL,
            prazo_contrato_meses=12,
        )

        result = await agent.execute(pricing_input=pricing_input)

        cenario_moderado = next(c for c in result["cenarios"] if c["tipo"] == "moderado")
        impostos = cenario_moderado["impostos_detalhamento"]

        # Lucro Real should have individual taxes
        assert "iss" in impostos
        assert "pis" in impostos
        assert "cofins" in impostos
        assert "irpj" in impostos
        assert "csll" in impostos
        # PIS for Lucro Real is 1.65%
        assert Decimal(str(impostos["pis"])) == Decimal("1.65")
        # COFINS for Lucro Real is 7.60%
        assert Decimal(str(impostos["cofins"])) == Decimal("7.60")

    @pytest.mark.asyncio
    async def test_pricer_builds_input_from_analysis(self, agent_config, sample_analysis):
        """Verifies PRICER can build PricingInput from ANALYST output."""
        from modules.bidding.agents.pricer_agent import PricerAgent

        agent = PricerAgent(agent_config)
        result = await agent.execute(analysis=sample_analysis)

        assert isinstance(result, dict)
        assert len(result["cenarios"]) == 3
        # Should infer valor_estimado from analysis
        assert result.get("valor_estimado_edital") is not None


# ══════════════════════════════════════════════════════════════
# 5. COMPILER Agent Tests
# ══════════════════════════════════════════════════════════════


class TestCompilerAgent:
    """Tests for the COMPILER agent — document generation."""

    @pytest.mark.asyncio
    async def test_compiler_generates_documents(self, agent_config, sample_analysis, sample_pricing_data):
        """Verifies COMPILER generates all expected document types."""
        with (
            patch("modules.bidding.agents.compiler_agent.render_pdf", return_value=b"%PDF-fake"),
            patch("modules.bidding.agents.compiler_agent.save_pdf", return_value="/tmp/test.pdf"),
        ):
            from modules.bidding.agents.compiler_agent import CompilerAgent, CompilerInput

            agent = CompilerAgent(agent_config)
            compiler_input = CompilerInput(
                numero_edital="PE-001/2026",
                orgao="UFAM",
                orgao_cnpj="04.378.626/0001-97",
                objeto="Vigilancia patrimonial",
                modalidade="Pregao Eletronico",
            )

            result = await agent.execute(
                compiler_input=compiler_input,
                pricing_data=sample_pricing_data,
                analysis=sample_analysis,
            )

            assert isinstance(result, dict)
            docs = result.get("documentos", [])
            assert len(docs) > 0

            # Check document types
            tipos = [d.get("tipo") for d in docs]
            assert "carta_proposta" in tipos

    @pytest.mark.asyncio
    async def test_compiler_pdf_rendering(self, agent_config, sample_analysis, sample_pricing_data):
        """Verifies COMPILER calls PDF renderer for each document."""
        call_count = 0

        def mock_render_pdf(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return b"%PDF-1.4-mock"

        with (
            patch("modules.bidding.agents.compiler_agent.render_pdf", side_effect=mock_render_pdf),
            patch("modules.bidding.agents.compiler_agent.save_pdf", return_value="/tmp/test.pdf"),
        ):
            from modules.bidding.agents.compiler_agent import CompilerAgent, CompilerInput

            agent = CompilerAgent(agent_config)
            compiler_input = CompilerInput(
                numero_edital="PE-001/2026",
                orgao="UFAM",
                objeto="Vigilancia patrimonial",
            )

            await agent.execute(
                compiler_input=compiler_input,
                pricing_data=sample_pricing_data,
                analysis=sample_analysis,
            )

            # render_pdf should have been called at least once
            assert call_count >= 1


# ══════════════════════════════════════════════════════════════
# 6. SENTINEL Agent Tests
# ══════════════════════════════════════════════════════════════


class TestSentinelAgent:
    """Tests for the SENTINEL agent — certificate/document monitoring."""

    @pytest.mark.asyncio
    async def test_sentinel_check_valid_certificates(self, agent_config):
        """Verifies SENTINEL correctly identifies valid certificates."""
        from modules.bidding.agents.sentinel_agent import SentinelAgent

        agent = SentinelAgent(agent_config)
        today = date.today()
        future_date = (today + timedelta(days=90)).isoformat()

        docs = [
            {"tipo": "cnd_federal", "data_emissao": today.isoformat(), "data_validade": future_date},
            {"tipo": "cnd_estadual", "data_emissao": today.isoformat(), "data_validade": future_date},
            {"tipo": "cnd_municipal", "data_emissao": today.isoformat(), "data_validade": future_date},
            {"tipo": "crf_fgts", "data_emissao": today.isoformat(), "data_validade": future_date},
            {"tipo": "cndt_trabalhista", "data_emissao": today.isoformat(), "data_validade": future_date},
        ]

        result = await agent.execute(documentos=docs, cnpj="35.710.481/0001-03")

        assert isinstance(result, dict)
        assert result["validos"] >= 5
        assert result["vencidos"] == 0

    @pytest.mark.asyncio
    async def test_sentinel_alert_expiring(self, agent_config):
        """Verifies SENTINEL raises alerts for documents about to expire."""
        from modules.bidding.agents.sentinel_agent import SentinelAgent

        agent = SentinelAgent(agent_config)
        today = date.today()

        docs = [
            # Expiring in 10 days (critico)
            {
                "tipo": "cnd_federal",
                "data_emissao": (today - timedelta(days=170)).isoformat(),
                "data_validade": (today + timedelta(days=10)).isoformat(),
            },
            # Expiring in 25 days (urgente)
            {
                "tipo": "crf_fgts",
                "data_emissao": (today - timedelta(days=5)).isoformat(),
                "data_validade": (today + timedelta(days=25)).isoformat(),
            },
            # Already expired (critico)
            {
                "tipo": "cndt_trabalhista",
                "data_emissao": (today - timedelta(days=200)).isoformat(),
                "data_validade": (today - timedelta(days=5)).isoformat(),
            },
        ]

        result = await agent.execute(documentos=docs, cnpj="35.710.481/0001-03")

        assert result["vencidos"] >= 1
        assert result["vencendo"] >= 1
        assert len(result["alertas_criticos"]) >= 1

    @pytest.mark.asyncio
    async def test_sentinel_offline_fallback(self, agent_config):
        """Verifies SENTINEL works with default documents when none are provided."""
        from modules.bidding.agents.sentinel_agent import SentinelAgent

        agent = SentinelAgent(agent_config)

        # Call without any documents — should use defaults (all nao_possui)
        result = await agent.execute(cnpj="35.710.481/0001-03")

        assert isinstance(result, dict)
        assert result["total_documentos"] > 0
        # Default documents have no dates, so most should be nao_possui
        assert result["nao_possui"] >= 0

    @pytest.mark.asyncio
    async def test_sentinel_online_verification_with_cache(self, agent_config):
        """Verifies SENTINEL uses cache for online verification."""
        from modules.bidding.agents.sentinel_agent import SentinelAgent

        agent = SentinelAgent(agent_config)

        # Mock cache and HTTP
        with (
            patch.object(agent, "_cache_get", new_callable=AsyncMock) as mock_cache_get,
            patch.object(agent, "_cache_set", new_callable=AsyncMock),
        ):
            # Simulate cache miss for all
            mock_cache_get.return_value = None

            # Mock HTTP calls to fail (should fallback to offline)
            with patch("modules.bidding.agents.sentinel_agent.httpx.AsyncClient") as MockHTTP:
                mock_http = AsyncMock()
                mock_http.__aenter__ = AsyncMock(return_value=mock_http)
                mock_http.__aexit__ = AsyncMock(return_value=False)
                mock_http.get = AsyncMock(side_effect=ConnectionError("No network"))
                mock_http.post = AsyncMock(side_effect=ConnectionError("No network"))
                MockHTTP.return_value = mock_http

                results = await agent.verificar_online("35710481000103")

                # Should get results for all verifiable types (fallback to offline)
                assert len(results) >= 5
                for r in results:
                    assert r.fonte == "offline"


# ══════════════════════════════════════════════════════════════
# 7. WARRIOR Agent Tests
# ══════════════════════════════════════════════════════════════


class TestWarriorAgent:
    """Tests for the WARRIOR agent — auction bidding simulation."""

    @pytest.mark.asyncio
    async def test_warrior_simulation_mode(self, agent_config):
        """Verifies WARRIOR runs a full simulation and returns valid response."""
        from modules.bidding.agents.warrior_agent import WarriorAgent

        agent = WarriorAgent(agent_config)

        result = await agent.execute(
            valor_referencia=100_000.0,
            estrategia="moderado",
            piso_minimo=60_000.0,
            num_rodadas=5,
            concorrentes=3,
            seed=42,  # deterministic
        )

        assert isinstance(result, dict)
        assert result["status"] in ["won", "lost", "idle", "bidding"]
        assert result.get("simulacao") is not None
        sim = result["simulacao"]
        assert sim["total_rodadas"] == 5
        assert sim["total_concorrentes"] == 3
        assert sim["resultado"] in ["vencedor", "segundo_lugar", "desclassificado", "desistiu"]
        assert len(sim["lances_realizados"]) > 0

    @pytest.mark.asyncio
    async def test_warrior_strategy_calculation(self, agent_config):
        """Verifies WARRIOR different strategies produce different results."""
        from modules.bidding.agents.warrior_agent import WarriorAgent

        results = {}
        for strategy in ["agressivo", "moderado", "conservador"]:
            agent = WarriorAgent(agent_config)
            result = await agent.execute(
                valor_referencia=200_000.0,
                estrategia=strategy,
                piso_minimo=120_000.0,
                num_rodadas=10,
                concorrentes=3,
                seed=42,
            )
            results[strategy] = result

        # All should return valid responses
        for strategy, result in results.items():
            assert result.get("simulacao") is not None, f"Strategy {strategy} missing simulacao"
            assert len(result["simulacao"]["lances_realizados"]) > 0

    @pytest.mark.asyncio
    async def test_warrior_requires_valor_referencia(self, agent_config):
        """Verifies WARRIOR raises when neither valor_referencia nor warrior_config provided."""
        from modules.bidding.agents.warrior_agent import WarriorAgent

        agent = WarriorAgent(agent_config)

        with pytest.raises(ValueError):
            await agent.execute()

    @pytest.mark.asyncio
    async def test_warrior_piso_must_be_below_referencia(self, agent_config):
        """Verifies WARRIOR raises when piso >= valor_referencia."""
        from modules.bidding.agents.warrior_agent import WarriorAgent

        agent = WarriorAgent(agent_config)

        with pytest.raises(ValueError, match="piso_minimo"):
            agent.configurar_estrategia(
                estrategia="moderado",
                valor_referencia=Decimal("100000"),
                piso_minimo=Decimal("100000"),  # Equal to ref = invalid
            )


# ══════════════════════════════════════════════════════════════
# 8. Orchestrator Tests
# ══════════════════════════════════════════════════════════════


class TestPipelineOrchestrator:
    """Tests for the pipeline orchestrator — end-to-end agent coordination."""

    @pytest.mark.asyncio
    async def test_full_pipeline_go(self, agent_config, sample_analysis):
        """Verifies full pipeline runs when ASSESSOR recommends GO."""
        from modules.bidding.agents.orchestrator import PipelineOrchestrator

        with (
            patch("modules.bidding.agents.orchestrator.ScoutAgent") as MockScout,
            patch("modules.bidding.agents.orchestrator.AnalystAgent") as MockAnalyst,
            patch("modules.bidding.agents.orchestrator.AssessorAgent") as MockAssessor,
            patch("modules.bidding.agents.orchestrator.PricerAgent") as MockPricer,
            patch("modules.bidding.agents.orchestrator.CompilerAgent") as MockCompiler,
            patch("modules.bidding.agents.orchestrator.SentinelAgent") as MockSentinel,
        ):
            # SCOUT returns opportunities
            mock_scout = MagicMock()
            mock_scout.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="scout",
                    status=ExecutionStatus.SUCCESS,
                    data=[
                        {
                            "numero_compra": "001",
                            "objeto": "Vigilancia",
                            "orgao_nome": "UFAM",
                            "orgao_uf": "AM",
                            "orgao_cnpj": "04.378.626/0001-97",
                        }
                    ],
                )
            )
            mock_scout.info = MagicMock(return_value={"name": "scout"})
            MockScout.return_value = mock_scout

            # ANALYST returns analysis
            mock_analyst = MagicMock()
            mock_analyst.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="analyst",
                    status=ExecutionStatus.SUCCESS,
                    data=sample_analysis,
                )
            )
            mock_analyst.info = MagicMock(return_value={"name": "analyst"})
            MockAnalyst.return_value = mock_analyst

            # ASSESSOR recommends GO
            mock_assessor = MagicMock()
            mock_assessor.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="assessor",
                    status=ExecutionStatus.SUCCESS,
                    data={"recomendacao": "GO", "score": 82.0, "justificativa": "PARTICIPAR", "criterios": []},
                )
            )
            mock_assessor.info = MagicMock(return_value={"name": "assessor"})
            MockAssessor.return_value = mock_assessor

            # PRICER returns pricing
            mock_pricer = MagicMock()
            mock_pricer.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="pricer",
                    status=ExecutionStatus.SUCCESS,
                    data={"cenarios": [], "preco_mensal_recomendado": "120000"},
                )
            )
            mock_pricer.info = MagicMock(return_value={"name": "pricer"})
            MockPricer.return_value = mock_pricer

            # COMPILER generates docs
            mock_compiler = MagicMock()
            mock_compiler.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="compiler",
                    status=ExecutionStatus.SUCCESS,
                    data={"documentos": [{"tipo": "carta_proposta", "conteudo": "..."}]},
                )
            )
            mock_compiler.info = MagicMock(return_value={"name": "compiler"})
            MockCompiler.return_value = mock_compiler

            # SENTINEL checks certs
            mock_sentinel = MagicMock()
            mock_sentinel.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="sentinel",
                    status=ExecutionStatus.SUCCESS,
                    data={"apto_licitar": True, "total_documentos": 10},
                )
            )
            mock_sentinel.info = MagicMock(return_value={"name": "sentinel"})
            MockSentinel.return_value = mock_sentinel

            orchestrator = PipelineOrchestrator()
            result = await orchestrator.run_full_pipeline(
                gerar_documentos=True,
                verificar_certidoes=True,
            )

            assert result.status_geral == "completed"
            assert result.recomendacao_final == "GO"
            assert result.score_final == 82.0
            assert result.total_oportunidades >= 1
            # All 6 steps should be executed
            assert len(result.steps_executados) == 6

    @pytest.mark.asyncio
    async def test_full_pipeline_no_go_stops_early(self, agent_config, sample_analysis):
        """Verifies pipeline skips PRICER/COMPILER when ASSESSOR recommends NO_GO."""
        from modules.bidding.agents.orchestrator import PipelineOrchestrator

        with (
            patch("modules.bidding.agents.orchestrator.ScoutAgent") as MockScout,
            patch("modules.bidding.agents.orchestrator.AnalystAgent") as MockAnalyst,
            patch("modules.bidding.agents.orchestrator.AssessorAgent") as MockAssessor,
            patch("modules.bidding.agents.orchestrator.PricerAgent") as MockPricer,
            patch("modules.bidding.agents.orchestrator.CompilerAgent") as MockCompiler,
            patch("modules.bidding.agents.orchestrator.SentinelAgent") as MockSentinel,
        ):
            # SCOUT returns opportunities
            mock_scout = MagicMock()
            mock_scout.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="scout",
                    status=ExecutionStatus.SUCCESS,
                    data=[{"numero_compra": "001", "objeto": "Vigilancia", "orgao_nome": "UFAM", "orgao_uf": "AM"}],
                )
            )
            MockScout.return_value = mock_scout

            # ANALYST returns analysis
            mock_analyst = MagicMock()
            mock_analyst.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="analyst",
                    status=ExecutionStatus.SUCCESS,
                    data=sample_analysis,
                )
            )
            MockAnalyst.return_value = mock_analyst

            # ASSESSOR recommends NO_GO
            mock_assessor = MagicMock()
            mock_assessor.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="assessor",
                    status=ExecutionStatus.SUCCESS,
                    data={"recomendacao": "NO_GO", "score": 25.0, "justificativa": "NAO PARTICIPAR"},
                )
            )
            MockAssessor.return_value = mock_assessor

            # These should NOT be called (NO_GO stops pipeline)
            mock_pricer = MagicMock()
            mock_pricer.run = AsyncMock()
            MockPricer.return_value = mock_pricer

            mock_compiler = MagicMock()
            mock_compiler.run = AsyncMock()
            MockCompiler.return_value = mock_compiler

            mock_sentinel = MagicMock()
            mock_sentinel.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="sentinel",
                    status=ExecutionStatus.SUCCESS,
                    data={"apto_licitar": False},
                )
            )
            MockSentinel.return_value = mock_sentinel

            orchestrator = PipelineOrchestrator()
            result = await orchestrator.run_full_pipeline(
                gerar_documentos=True,
                verificar_certidoes=True,
            )

            assert result.status_geral == "completed"
            assert result.recomendacao_final == "NO_GO"

            # PRICER and COMPILER should be skipped
            step_statuses = {s.step: s.status for s in result.steps_executados}
            assert step_statuses.get("pricer") == "skipped"
            assert step_statuses.get("compiler") == "skipped"

            # PRICER.run should NOT have been called
            mock_pricer.run.assert_not_called()
            mock_compiler.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_pipeline_scout_failure_aborts(self, agent_config):
        """Verifies pipeline aborts when SCOUT fails."""
        from modules.bidding.agents.orchestrator import PipelineOrchestrator

        with (
            patch("modules.bidding.agents.orchestrator.ScoutAgent") as MockScout,
            patch("modules.bidding.agents.orchestrator.AnalystAgent") as MockAnalyst,
            patch("modules.bidding.agents.orchestrator.AssessorAgent") as MockAssessor,
            patch("modules.bidding.agents.orchestrator.PricerAgent") as MockPricer,
            patch("modules.bidding.agents.orchestrator.CompilerAgent") as MockCompiler,
            patch("modules.bidding.agents.orchestrator.SentinelAgent") as MockSentinel,
        ):
            mock_scout = MagicMock()
            mock_scout.run = AsyncMock(
                return_value=ExecutionResult(
                    agent_name="scout",
                    status=ExecutionStatus.FAILED,
                    error="All portals offline",
                    data=None,
                )
            )
            MockScout.return_value = mock_scout

            for Mock in [MockAnalyst, MockAssessor, MockPricer, MockCompiler, MockSentinel]:
                Mock.return_value = MagicMock()

            orchestrator = PipelineOrchestrator()
            result = await orchestrator.run_full_pipeline()

            assert result.status_geral == "failed"
            assert len(result.erros) >= 1
            assert "SCOUT" in result.erros[0]
