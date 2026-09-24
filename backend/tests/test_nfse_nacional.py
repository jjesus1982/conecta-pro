"""
Testes para API NFS-e Padrao Nacional - Sprint 36.

Testes completos para o modulo de NFS-e Padrao Nacional,
incluindo emissao, consulta, cancelamento e informacoes de migracao.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Cria app isolado para testes (evita carregar todo o main.py)
from modules.government_integrations.controllers.nfse_nacional_controller import router as nfse_router

app = FastAPI()
app.include_router(nfse_router, prefix="/api/v1/government")


@pytest.fixture
def auth_headers():
    """Headers de autenticacao para testes."""
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def tomador_valido():
    """Dados de tomador valido."""
    return {
        "cpf_cnpj": "12345678901234",
        "razao_social": "Empresa Cliente LTDA",
        "logradouro": "Av. Eduardo Ribeiro",
        "numero": "1000",
        "complemento": "Sala 101",
        "bairro": "Centro",
        "codigo_municipio": "1302603",
        "uf": "AM",
        "cep": "69010001",
        "email": "contato@empresa.com.br",
        "telefone": "9232001234",
    }


@pytest.fixture
def servico_valido():
    """Dados de servico valido."""
    return {
        "codigo_tributacao_nacional": "1.1701.10.00",
        "descricao": "Servicos de vigilancia patrimonial armada conforme contrato 001/2026, periodo janeiro/2026",
        "valor_servico": "15000.00",
        "valor_deducao": "0",
        "valor_desconto_incondicionado": "0",
        "codigo_cnae": "8011101",
        "aliquota_iss": "0.05",
        "iss_retido": False,
    }


@pytest.fixture
def prestador_valido():
    """Dados de prestador valido."""
    return {
        "cnpj": "35710481000103",
        "inscricao_municipal": "123456",
        "codigo_municipio": "1302603",
        "razao_social": "Conecta Plus Servicos LTDA",
        "nome_fantasia": "Conecta Plus",
        "regime_especial": "6",
        "optante_simples": True,
    }


class TestEmitirDPS:
    """Testes para endpoint de emissao de DPS."""

    @pytest.mark.asyncio
    async def test_emitir_dps_sucesso(self, auth_headers, tomador_valido, servico_valido):
        """Testa emissao de DPS com dados validos."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/government/nfse-nacional/emitir",
                headers=auth_headers,
                json={
                    "tomador": tomador_valido,
                    "servico": servico_valido,
                    "competencia": "2026-01",
                    "tipo_tributacao": "1",
                },
            )

        # Pode ser 202 (aceito) ou 401/403 (auth)
        assert response.status_code in [202, 401, 403]

        if response.status_code == 202:
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert data["data"]["status"] == "preparacao"

    @pytest.mark.asyncio
    async def test_emitir_dps_com_prestador(self, auth_headers, tomador_valido, servico_valido, prestador_valido):
        """Testa emissao de DPS com dados de prestador customizado."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/government/nfse-nacional/emitir",
                headers=auth_headers,
                json={
                    "prestador": prestador_valido,
                    "tomador": tomador_valido,
                    "servico": servico_valido,
                    "competencia": "2026-01",
                    "tipo_tributacao": "1",
                },
            )

        assert response.status_code in [202, 401, 403]

    @pytest.mark.asyncio
    async def test_emitir_dps_tomador_invalido(self, auth_headers, servico_valido):
        """Testa emissao de DPS com tomador invalido."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/government/nfse-nacional/emitir",
                headers=auth_headers,
                json={
                    "tomador": {
                        "cpf_cnpj": "123",  # CPF/CNPJ invalido
                        "razao_social": "Teste",
                        "logradouro": "Rua",
                        "bairro": "Bairro",
                        "cep": "69000000",
                    },
                    "servico": servico_valido,
                },
            )

        # Deve retornar erro de validacao
        assert response.status_code in [400, 422, 401, 403]

    @pytest.mark.asyncio
    async def test_emitir_dps_servico_invalido(self, auth_headers, tomador_valido):
        """Testa emissao de DPS com servico invalido."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/government/nfse-nacional/emitir",
                headers=auth_headers,
                json={
                    "tomador": tomador_valido,
                    "servico": {
                        "descricao": "Curta",  # Descricao muito curta
                        "valor_servico": "-100",  # Valor negativo
                    },
                },
            )

        assert response.status_code in [400, 422, 401, 403]


class TestConsultarDPS:
    """Testes para endpoint de consulta de DPS."""

    @pytest.mark.asyncio
    async def test_consultar_dps_por_id(self, auth_headers):
        """Testa consulta de DPS por ID."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/government/nfse-nacional/consultar/dps/DPS-2026-000001",
                headers=auth_headers,
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            assert data["data"]["status"] == "preparacao"


class TestConsultarNFSe:
    """Testes para endpoint de consulta de NFS-e."""

    @pytest.mark.asyncio
    async def test_consultar_nfse_por_numero(self, auth_headers):
        """Testa consulta de NFS-e por numero nacional."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/government/nfse-nacional/consultar/nfse/NFSe-NAC-123456789",
                headers=auth_headers,
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            assert data["data"]["status"] == "preparacao"


class TestCancelarNFSe:
    """Testes para endpoint de cancelamento de NFS-e."""

    @pytest.mark.asyncio
    async def test_cancelar_nfse(self, auth_headers):
        """Testa cancelamento de NFS-e."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/government/nfse-nacional/cancelar",
                headers=auth_headers,
                json={
                    "numero_nfse": "NFSe-NAC-123456789",
                    "motivo_cancelamento": "1",
                    "justificativa": "Erro no valor do servico",
                },
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            assert data["data"]["status"] == "preparacao"

    @pytest.mark.asyncio
    async def test_cancelar_nfse_sem_justificativa(self, auth_headers):
        """Testa cancelamento de NFS-e sem justificativa."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/government/nfse-nacional/cancelar",
                headers=auth_headers,
                json={
                    "numero_nfse": "NFSe-NAC-123456789",
                    "motivo_cancelamento": "2",
                },
            )

        assert response.status_code in [200, 401, 403]


class TestSubstituirNFSe:
    """Testes para endpoint de substituicao de NFS-e."""

    @pytest.mark.asyncio
    async def test_substituir_nfse(self, auth_headers, tomador_valido, servico_valido):
        """Testa substituicao de NFS-e."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/government/nfse-nacional/substituir",
                headers=auth_headers,
                json={
                    "numero_nfse_substituida": "NFSe-NAC-123456789",
                    "tomador": tomador_valido,
                    "servico": servico_valido,
                },
            )

        assert response.status_code in [202, 401, 403]


class TestEventos:
    """Testes para endpoint de eventos de NFS-e."""

    @pytest.mark.asyncio
    async def test_consultar_eventos(self, auth_headers):
        """Testa consulta de eventos de NFS-e."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/government/nfse-nacional/eventos/NFSe-NAC-123456789",
                headers=auth_headers,
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            assert "eventos" in data["data"]


class TestStatus:
    """Testes para endpoints de status."""

    @pytest.mark.asyncio
    async def test_validar_conexao(self, auth_headers):
        """Testa validacao de conexao e status."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/government/nfse-nacional/status",
                headers=auth_headers,
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert "ambiente" in data["data"]
            assert "status_api" in data["data"]
            # dgx aa4 (24/09/2026): era `is False` — a régua estava errada, não o código.
            # Manaus ADERIU ao Padrão Nacional: `nfse_emitidas_nacional` tem 115 notas reais
            # desta casa com chave começando em 1302603 (IBGE de Manaus), e a frente Z7
            # emitiu pelos dois CNPJs em homologação. Afirmar indisponibilidade era fixar
            # uma crença falsa com um teste verde.
            assert data["data"]["migracao_disponivel"] is True


class TestMigracao:
    """Testes para endpoints de migracao."""

    @pytest.mark.asyncio
    async def test_status_migracao(self, auth_headers):
        """Testa consulta de status de migracao."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/government/nfse-nacional/migracao/status",
                headers=auth_headers,
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert data["data"]["municipio"] == "Manaus"
            assert data["data"]["codigo_ibge"] == "1302603"
            assert data["data"]["padrao_atual"] == "ABRASF 2.04"
            assert "migracao_prevista" in data["data"]

    @pytest.mark.asyncio
    async def test_comparar_padroes(self, auth_headers):
        """Testa comparacao entre padroes."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/government/nfse-nacional/migracao/comparar-padroes",
                headers=auth_headers,
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert "abrasf_204" in data["data"]
            assert "padrao_nacional" in data["data"]
            assert "recomendacao" in data["data"]

    @pytest.mark.asyncio
    async def test_mapeamento_servicos(self, auth_headers):
        """Testa mapeamento de codigos de servico."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/government/nfse-nacional/migracao/mapeamento-servicos",
                headers=auth_headers,
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert "mapeamentos" in data["data"]
            mapeamentos = data["data"]["mapeamentos"]
            assert isinstance(mapeamentos, list)
            if len(mapeamentos) > 0:
                assert "codigo_abrasf" in mapeamentos[0]
                assert "codigo_nbs" in mapeamentos[0]


class TestCodigosServico:
    """Testes para endpoint de codigos de servico."""

    @pytest.mark.asyncio
    async def test_listar_codigos_servico(self, auth_headers):
        """Testa listagem de codigos de servico NBS."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/government/nfse-nacional/codigos-servico",
                headers=auth_headers,
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert "codigos" in data["data"]
            codigos = data["data"]["codigos"]
            assert isinstance(codigos, list)
            assert len(codigos) > 0
            # Verifica estrutura do codigo
            assert "codigo_nbs" in codigos[0]
            assert "codigo_lc116" in codigos[0]
            assert "descricao" in codigos[0]


class TestInfoPadraoNacional:
    """Testes para endpoint de informacoes do Padrao Nacional."""

    @pytest.mark.asyncio
    async def test_info_padrao_nacional(self, auth_headers):
        """Testa obtencao de informacoes do Padrao Nacional."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/government/nfse-nacional/info",
                headers=auth_headers,
            )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            info = data["data"]
            assert info["nome"] == "Padrao Nacional de NFS-e"
            assert "portal" in info
            assert "caracteristicas" in info
            assert "beneficios" in info
            assert "status_manaus" in info


class TestNFSeNacionalService:
    """Testes unitarios para o service."""

    def test_service_singleton(self):
        """Testa que o service e singleton."""
        from modules.government_integrations.services.nfse_nacional_service import (
            get_nfse_nacional_service,
        )

        service1 = get_nfse_nacional_service()
        service2 = get_nfse_nacional_service()
        assert service1 is service2

    def test_service_emitir_dps(self):
        """Testa emissao de DPS via service."""
        from modules.government_integrations.services.nfse_nacional_service import (
            NFSeNacionalService,
        )

        service = NFSeNacionalService()

        tomador = {
            "cpf_cnpj": "12345678901234",
            "razao_social": "Empresa Teste",
            "logradouro": "Rua Teste",
            "numero": "100",
            "bairro": "Centro",
            "cep": "69000000",
        }

        servico = {
            "codigo_tributacao_nacional": "1.1701.10.00",
            "descricao": "Servicos de vigilancia - contrato teste",
            "valor_servico": "10000.00",
            "aliquota_iss": "0.05",
        }

        resultado = service.emitir_dps(
            tomador_data=tomador,
            servico_data=servico,
            competencia="2026-01",
        )

        assert resultado is not None
        assert resultado["status"] == "preparacao"
        assert "id_dps" in resultado
        assert "payload_previsto" in resultado

    def test_service_status_migracao(self):
        """Testa consulta de status de migracao."""
        from modules.government_integrations.services.nfse_nacional_service import (
            NFSeNacionalService,
        )

        service = NFSeNacionalService()
        resultado = service.consultar_status_migracao()

        assert resultado is not None
        assert resultado["municipio"] == "Manaus"
        assert resultado["codigo_ibge"] == "1302603"
        assert "migracao_prevista" in resultado

    def test_service_comparar_padroes(self):
        """Testa comparacao entre padroes."""
        from modules.government_integrations.services.nfse_nacional_service import (
            NFSeNacionalService,
        )

        service = NFSeNacionalService()
        resultado = service.comparar_padroes()

        assert resultado is not None
        assert "abrasf_204" in resultado
        assert "padrao_nacional" in resultado
        assert "recomendacao" in resultado

    def test_service_mapeamento_servicos(self):
        """Testa obtencao de mapeamento de servicos."""
        from modules.government_integrations.services.nfse_nacional_service import (
            NFSeNacionalService,
        )

        service = NFSeNacionalService()
        mapeamentos = service.obter_mapeamento_servicos()

        assert mapeamentos is not None
        assert isinstance(mapeamentos, list)
        assert len(mapeamentos) > 0

    def test_service_validar_conexao(self):
        """Testa validacao de conexao."""
        from modules.government_integrations.services.nfse_nacional_service import (
            NFSeNacionalService,
        )

        service = NFSeNacionalService()
        resultado = service.validar_conexao()

        assert resultado is not None
        assert "ambiente" in resultado
        assert "status_api" in resultado
        # dgx aa4 (24/09/2026): ver comentário em TestNFSeNacionalEndpoints.
        assert resultado["migracao_disponivel"] is True


class TestNFSeNacionalSchemas:
    """Testes para schemas Pydantic."""

    def test_tomador_request_cpf_valido(self):
        """Testa validacao de CPF no schema de tomador."""
        from modules.government_integrations.schemas.nfse_nacional import (
            TomadorNacionalRequest,
        )

        tomador = TomadorNacionalRequest(
            cpf_cnpj="123.456.789-01",  # Com formatacao
            razao_social="Pessoa Fisica",
            logradouro="Rua Teste",
            bairro="Centro",
            cep="69000-000",  # Com hifen
        )

        assert tomador.cpf_cnpj == "12345678901"
        assert tomador.cep == "69000000"

    def test_tomador_request_cnpj_valido(self):
        """Testa validacao de CNPJ no schema de tomador."""
        from modules.government_integrations.schemas.nfse_nacional import (
            TomadorNacionalRequest,
        )

        tomador = TomadorNacionalRequest(
            cpf_cnpj="12.345.678/0001-34",  # Com formatacao
            razao_social="Empresa LTDA",
            logradouro="Av. Teste",
            bairro="Centro",
            cep="69010001",
        )

        assert tomador.cpf_cnpj == "12345678000134"

    def test_tomador_request_documento_invalido(self):
        """Testa rejeicao de documento invalido."""
        from modules.government_integrations.schemas.nfse_nacional import (
            TomadorNacionalRequest,
        )

        with pytest.raises(ValueError):
            TomadorNacionalRequest(
                cpf_cnpj="123",  # Muito curto
                razao_social="Teste",
                logradouro="Rua",
                bairro="Bairro",
                cep="69000000",
            )

    def test_servico_request_valores(self):
        """Testa validacao de valores no schema de servico."""
        from modules.government_integrations.schemas.nfse_nacional import (
            ServicoNacionalRequest,
        )

        servico = ServicoNacionalRequest(
            descricao="Servicos de vigilancia conforme contrato",
            valor_servico=Decimal("10000.00"),
            aliquota_iss=Decimal("0.05"),
        )

        assert servico.valor_servico == Decimal("10000.00")
        assert servico.aliquota_iss == Decimal("0.05")
        assert servico.iss_retido is False

    def test_servico_request_valor_negativo(self):
        """Testa rejeicao de valor negativo."""
        from modules.government_integrations.schemas.nfse_nacional import (
            ServicoNacionalRequest,
        )

        with pytest.raises(ValueError):
            ServicoNacionalRequest(
                descricao="Servicos de vigilancia conforme contrato",
                valor_servico=Decimal("-100.00"),  # Valor negativo
            )

    def test_emitir_dps_request_completo(self):
        """Testa schema completo de emissao de DPS."""
        from modules.government_integrations.schemas.nfse_nacional import (
            EmitirDPSRequest,
            ServicoNacionalRequest,
            TomadorNacionalRequest,
        )

        request = EmitirDPSRequest(
            tomador=TomadorNacionalRequest(
                cpf_cnpj="12345678901234",
                razao_social="Empresa Cliente",
                logradouro="Av. Principal",
                numero="100",
                bairro="Centro",
                cep="69010001",
            ),
            servico=ServicoNacionalRequest(
                codigo_tributacao_nacional="1.1701.10.00",
                descricao="Servicos de vigilancia patrimonial armada",
                valor_servico=Decimal("15000.00"),
            ),
            competencia="2026-01",
            tipo_tributacao="1",
        )

        assert request.tomador.cpf_cnpj == "12345678901234"
        assert request.servico.valor_servico == Decimal("15000.00")
        assert request.competencia == "2026-01"
