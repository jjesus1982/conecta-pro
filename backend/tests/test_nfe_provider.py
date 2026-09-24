"""
Testes para NFeProvider - Integração NF-e com SEFAZ.

Testa a nova integração NF-e via PyNFe em substituição à simulação.
Execute com: python -m pytest tests/test_nfe_provider.py -v -s
"""

import asyncio
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# Adiciona backend ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.financial.integrations.nfe_provider import (
    NFeConfig,
    NFeError,
    NFeProvider,
    _calcular_dv_chave,
    create_nfe_provider,
)


class TestNFeProvider:
    """Testes para NFeProvider."""

    def setup_method(self):
        """Setup para cada teste."""
        self.config = NFeConfig(
            certificado_path="/opt/certs/test_cert.p12",
            certificado_senha="test_password",
            ambiente="2",  # Homologação
            uf="SP",
        )
        self.provider = NFeProvider(self.config)

    def test_config_validation(self):
        """Testa validação da configuração."""
        # Config válida
        config = NFeConfig(certificado_path="/cert.p12", certificado_senha="senha123", ambiente="2", uf="SP")
        assert config.certificado_path == "/cert.p12"
        assert config.ambiente == "2"
        assert config.timeout_seconds == 30  # Default

        # Config com timeout customizado
        config_timeout = NFeConfig(
            certificado_path="/cert.p12", certificado_senha="senha123", ambiente="1", uf="RJ", timeout_seconds=60
        )
        assert config_timeout.timeout_seconds == 60

    def test_create_nfe_provider_factory(self):
        """Testa factory function."""
        provider = create_nfe_provider(
            certificado_path="/cert.p12", certificado_senha="senha123", ambiente="1", uf="RJ"
        )

        assert isinstance(provider, NFeProvider)
        assert provider.config.certificado_path == "/cert.p12"
        assert provider.config.ambiente == "1"
        assert provider.config.uf == "RJ"

    @pytest.mark.asyncio
    async def test_emitir_nfe(self):
        """Testa emissão de NF-e (com mock do sync)."""
        nfe_data = {
            "destinatario": {"cnpj": "12345678000199", "razao_social": "Cliente Teste LTDA"},
            "items": [
                {
                    "codigo": "PROD001",
                    "descricao": "Produto Teste",
                    "quantidade": 1,
                    "valor_unitario": 100.00,
                    "valor_total": 100.00,
                }
            ],
        }

        fake_chave = "35260235710481000103550010000001231234567890"
        fake_result = {
            "status": "enviada",
            "chave_acesso": fake_chave,
            "protocolo": "",
            "mensagem": "[] Sem resposta SEFAZ",
            "xml_autorizado": None,
            "pdf_danfe": None,
            "codigo_status": "",
            "motivo": "Sem resposta SEFAZ",
            "data_autorizacao": datetime.now().isoformat(),
        }

        with patch.object(self.provider, "_emitir_sync", return_value=fake_result):
            resultado = await self.provider.emitir_nfe(
                nfe_data=nfe_data,
                nfe_id=uuid4(),
                numero=123,
                # A identidade do emitente vem da tabela `empresas` (DGX Z2): nada
                # chumbado no provider. Aqui basta um dicionário — `_emitir_sync`
                # está mockado e a conferência de campos mora dentro dele.
                emitente={"slug": "conecta_eletronica"},
            )

        # Verificar estrutura da resposta
        assert "status" in resultado
        assert "chave_acesso" in resultado
        assert "protocolo" in resultado
        assert "mensagem" in resultado

        # Verificar valores
        assert resultado["status"] == "enviada"
        assert len(resultado["chave_acesso"]) == 44
        assert resultado["chave_acesso"] == fake_chave

    @pytest.mark.asyncio
    async def test_cancelar_nfe(self):
        """Testa cancelamento de NF-e (com mock do sync)."""
        chave_acesso = "13202613123456000199550010000001231234567890"
        motivo = "Teste de cancelamento - erro de digitação"

        fake_result = {
            "status": "cancelada",
            "chave_acesso": chave_acesso,
            "protocolo": "135260000012345",
            "mensagem": "[135] Evento registrado e vinculado a NF-e",
            "data_cancelamento": datetime.now().isoformat(),
            "codigo_status": "135",
            "motivo_cancelamento": motivo,
        }

        with patch.object(self.provider, "_cancelar_sync", return_value=fake_result):
            resultado = await self.provider.cancelar_nfe(
                chave_acesso=chave_acesso,
                motivo=motivo,
                nfe_id=uuid4(),
                protocolo="135260000012345",
                cnpj_emitente="13123456000199",
            )

        # Verificar estrutura da resposta
        assert "status" in resultado
        assert "chave_acesso" in resultado
        assert "protocolo" in resultado
        assert "mensagem" in resultado
        assert "data_cancelamento" in resultado

        # Verificar valores
        assert resultado["status"] == "cancelada"
        assert resultado["chave_acesso"] == chave_acesso
        assert resultado["motivo_cancelamento"] == motivo

    @pytest.mark.asyncio
    async def test_cancelar_nfe_chave_invalida(self):
        """Testa cancelamento com chave inválida."""
        chave_invalida = "123"  # Muito curta
        motivo = "Teste cancelamento com motivo suficiente"

        with pytest.raises(NFeError) as exc_info:
            await self.provider.cancelar_nfe(
                chave_acesso=chave_invalida,
                motivo=motivo,
                nfe_id=uuid4(),
                protocolo="135260000012345",
                cnpj_emitente="13123456000199",
            )

        assert "44 dígitos" in str(exc_info.value)
        assert exc_info.value.code == "INVALID_KEY"

    @pytest.mark.asyncio
    async def test_cancelar_nfe_motivo_curto(self):
        """Testa cancelamento com motivo muito curto."""
        chave_acesso = "13202613123456000199550010000001231234567890"
        motivo_curto = "Erro"  # Menos de 15 caracteres

        with pytest.raises(NFeError) as exc_info:
            await self.provider.cancelar_nfe(
                chave_acesso=chave_acesso,
                motivo=motivo_curto,
                nfe_id=uuid4(),
                protocolo="135260000012345",
                cnpj_emitente="13123456000199",
            )

        assert "15 caracteres" in str(exc_info.value)
        assert exc_info.value.code == "INVALID_REASON"

    @pytest.mark.asyncio
    async def test_consultar_status(self):
        """Testa consulta de status (com mock do sync)."""
        chave_acesso = "13202613123456000199550010000001231234567890"

        fake_result = {
            "status": "autorizada",
            "chave_acesso": chave_acesso,
            "protocolo": "135260000012345",
            "data_autorizacao": datetime.now().isoformat(),
            "codigo_status": "100",
            "descricao_status": "Autorizado o uso da NF-e",
            "xml_disponivel": True,
            "situacao": "NORMAL",
        }

        with patch.object(self.provider, "_consultar_sync", return_value=fake_result):
            resultado = await self.provider.consultar_status(chave_acesso)

        # Verificar estrutura da resposta
        assert "status" in resultado
        assert "chave_acesso" in resultado
        assert "protocolo" in resultado
        assert "data_autorizacao" in resultado
        assert "codigo_status" in resultado

        # Verificar valores
        assert resultado["status"] == "autorizada"
        assert resultado["chave_acesso"] == chave_acesso
        assert resultado["codigo_status"] == "100"

    @pytest.mark.asyncio
    async def test_consultar_status_chave_invalida(self):
        """Testa consulta com chave inválida."""
        chave_invalida = "abc123"

        with pytest.raises(NFeError) as exc_info:
            await self.provider.consultar_status(chave_invalida)

        assert "44 dígitos" in str(exc_info.value)
        assert exc_info.value.code == "INVALID_KEY"

    @pytest.mark.asyncio
    async def test_test_connection(self):
        """Testa conexão com SEFAZ (com mock do sync)."""
        fake_result = {
            "conectado": True,
            "ambiente": "Homologação",
            "uf": "SP",
            "servico_ativo": True,
            "ultima_atualizacao": datetime.now().isoformat(),
            "versao_schema": "4.00",
            "codigo_status": "107",
            "motivo": "Servico em Operacao",
            "tempo_medio_resposta": "1",
        }

        with patch.object(self.provider, "_status_sync", return_value=fake_result):
            resultado = await self.provider.test_connection()

        # Verificar estrutura da resposta
        assert "conectado" in resultado
        assert "ambiente" in resultado
        assert "uf" in resultado
        assert "servico_ativo" in resultado

        # Verificar valores
        assert resultado["conectado"] is True
        assert resultado["ambiente"] == "Homologação"
        assert resultado["uf"] == "SP"

    def test_calcular_dv_chave(self):
        """Testa cálculo do dígito verificador da chave NF-e."""
        # Chave sem DV: 1320261312345600019955001000000123
        chave_sem_dv = "1320261312345600019955001000000123"
        dv = _calcular_dv_chave(chave_sem_dv)

        # DV deve ser um dígito string de 0 a 9
        assert isinstance(dv, str)
        assert len(dv) == 1
        assert dv in "0123456789"

    def test_nfe_error_structure(self):
        """Testa estrutura da exceção NFeError."""
        error = NFeError(message="Erro de teste", code="TEST_ERROR", details={"campo": "valor"})

        assert str(error) == "Erro de teste"
        assert error.code == "TEST_ERROR"
        assert error.details == {"campo": "valor"}


class TestNFeProviderIntegracao:
    """Testes de integração (quando PyNFe estiver configurado)."""

    @pytest.mark.skip(reason="PyNFe/certificado não configurado ainda")
    @pytest.mark.asyncio
    async def test_emissao_real_homologacao(self):
        """Teste de emissão real em homologação (quando implementado)."""
        pass

    @pytest.mark.skip(reason="PyNFe/certificado não configurado ainda")
    @pytest.mark.asyncio
    async def test_cancelamento_real_homologacao(self):
        """Teste de cancelamento real em homologação (quando implementado)."""
        pass


if __name__ == "__main__":
    # Execução direta para debug
    pytest.main([__file__, "-v", "-s"])
