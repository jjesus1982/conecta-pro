"""
Testes para NFETransmitter.

Testa transmissão real de NF-e para SEFAZ.
Execute com: python -m pytest tests/test_nfe_transmitter.py -v -s
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

# Adiciona backend ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from modules.government_integrations.core.certificate_manager import CertificateManager
from modules.government_integrations.core.nfe_transmitter import (
    NFETransmitter,
    ResultadoTransmissao,
    init_nfe_transmitter,
)
from modules.government_integrations.core.sefaz_manager import (
    Destinatario,
    DocumentStatus,
    DocumentType,
    Emitente,
    Endereco,
    NFEXMLBuilder,
    NotaFiscal,
    OperationType,
    Pagamento,
    PaymentType,
    Produto,
)
from modules.government_integrations.core.xml_signer import NFEXMLSigner

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# Fixtures
@pytest.fixture
def emitente():
    """Emitente para testes."""
    endereco = Endereco(
        logradouro="Rua Teste",
        numero="100",
        bairro="Centro",
        cidade="Manaus",
        uf="AM",
        cep="69000-000",
        codigo_municipio="1302603",  # Manaus
    )

    return Emitente(
        cnpj="35.710.481/0001-03",
        razao_social="CONECTAMAIS ELETRONICA LTDA",
        nome_fantasia="Conecta PRO",
        inscricao_estadual="123456789",  # Substituir por IE válida
        endereco=endereco,
        regime_tributario="1",  # Simples Nacional
    )


@pytest.fixture
def destinatario():
    """Destinatário para testes."""
    endereco = Endereco(
        logradouro="Av Teste",
        numero="200",
        bairro="Centro",
        cidade="Manaus",
        uf="AM",
        cep="69000-000",
        codigo_municipio="1302603",
    )

    return Destinatario(
        cpf_cnpj="123.456.789-00",  # CPF de teste (homologação)
        nome="NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
        endereco=endereco,
        indicador_ie="9",  # Não contribuinte
    )


@pytest.fixture
def produto():
    """Produto para testes."""
    return Produto(
        codigo="PROD001",
        descricao="NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
        ncm="84713012",
        cfop="5102",
        unidade="UN",
        quantidade=Decimal("1"),
        valor_unitario=Decimal("10.00"),
        origem="0",
        cst_icms="41",  # Não tributado
    )


@pytest.fixture
def pagamento():
    """Pagamento para testes."""
    return Pagamento(
        tipo=PaymentType.DINHEIRO,
        valor=Decimal("10.00"),
    )


@pytest.fixture
def transmitter():
    """Transmissor configurado para homologação."""
    return NFETransmitter(uf="AM", ambiente="2")  # Homologação


class TestNFETransmitter:
    """Testes do transmissor de NF-e."""

    @pytest.mark.asyncio
    async def test_consultar_status_servico(self, transmitter):
        """Testa consulta de status do serviço SEFAZ."""
        resultado = await transmitter.consultar_status_servico()

        logger.info(f"Status: {resultado.status_code}")
        logger.info(f"Motivo: {resultado.motivo}")
        logger.info(f"Tempo: {resultado.tempo_resposta:.2f}s")

        # Status 107 = Serviço em operação
        assert resultado.status_code in ["107", "108", "109"], f"Status inesperado: {resultado.status_code}"

        await transmitter.close()

    @pytest.mark.asyncio
    async def test_criar_envelope_autorizacao(self, transmitter):
        """Testa criação do envelope SOAP."""
        xml_nfe = """<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
            <infNFe Id="NFe35260112345678000195550010000000011234567890" versao="4.00">
                <ide><cUF>35</cUF></ide>
            </infNFe>
        </NFe>"""

        envelope = transmitter._criar_envelope_autorizacao(xml_nfe, sincrono=True)

        # Verificar estrutura do envelope
        assert "soap12:Envelope" in envelope
        assert "NFeAutorizacao4" in envelope
        assert "enviNFe" in envelope
        assert "idLote" in envelope
        assert "indSinc" in envelope
        assert "<indSinc>1</indSinc>" in envelope  # Síncrono

        logger.info("Envelope criado com sucesso")
        logger.debug(envelope[:500])


class TestTransmissaoReal:
    """
    Testes de transmissão real para SEFAZ.

    ATENÇÃO: Estes testes fazem requisições reais à SEFAZ.
    Execute apenas em ambiente de homologação.
    """

    @pytest.fixture
    def cert_manager(self):
        """Carrega certificado do arquivo."""
        cert_path = "/opt/conecta-pro/credentials/certificates/certificado.pfx"
        cert_password = "Conecta123"

        manager = CertificateManager(
            pfx_path=cert_path,
            password=cert_password,
        )
        manager.load()
        return manager

    @pytest.fixture
    def xml_signer(self, cert_manager):
        """Assinador XML."""
        return NFEXMLSigner(cert_manager)

    @pytest.mark.asyncio
    async def test_transmitir_nfe_homologacao(
        self,
        transmitter,
        emitente,
        destinatario,
        produto,
        pagamento,
        xml_signer,
    ):
        """
        Testa transmissão de NF-e para homologação.

        NOTA: Este teste requer:
        - Certificado válido em /opt/conecta-pro/credentials/certificates/
        - Conexão com internet
        - SEFAZ AM disponível
        """
        # Criar NotaFiscal
        nf = NotaFiscal(
            id=uuid4(),
            tipo=DocumentType.NFE,
            status=DocumentStatus.DRAFT,
            emitente=emitente,
            destinatario=destinatario,
            produtos=[produto],
            pagamentos=[pagamento],
            operacao=OperationType.SAIDA,
            natureza_operacao="VENDA",
            numero=1,
            serie=1,
            data_emissao=datetime.utcnow(),
        )

        # Gerar chave de acesso
        nf.generate_chave_acesso()
        logger.info(f"Chave de acesso: {nf.chave_acesso}")

        # Gerar XML
        builder = NFEXMLBuilder()
        xml_content = builder.build_nfe(nf)
        logger.debug(f"XML gerado:\n{xml_content[:500]}")

        # Assinar XML
        xml_assinado = xml_signer.sign_nfe(xml_content, f"NFe{nf.chave_acesso}")
        logger.debug(f"XML assinado:\n{xml_assinado[:500]}")

        # Transmitir
        resultado = await transmitter.transmitir(xml_assinado, sincrono=True)

        logger.info(f"Sucesso: {resultado.sucesso}")
        logger.info(f"Status: {resultado.status_code}")
        logger.info(f"Motivo: {resultado.motivo}")
        logger.info(f"Protocolo: {resultado.protocolo}")
        logger.info(f"Tempo: {resultado.tempo_resposta:.2f}s")

        if resultado.xml_retorno:
            logger.debug(f"XML Retorno:\n{resultado.xml_retorno[:1000]}")

        # Em homologação, esperamos rejeição por dados de teste
        # Status comuns: 215 (schema), 227 (IE não cadastrada), etc.
        assert resultado.status_code is not None
        assert resultado.motivo is not None

        await transmitter.close()


# Script de teste standalone
async def test_status_servico_standalone():
    """Testa status do serviço como script standalone."""
    print("\n" + "=" * 60)
    print("TESTE DE STATUS DO SERVIÇO SEFAZ")
    print("=" * 60)

    transmitter = NFETransmitter(uf="AM", ambiente="2")  # Homologação

    resultado = await transmitter.consultar_status_servico()

    print("\nResultado:")
    print(f"  Sucesso: {resultado.sucesso}")
    print(f"  Status: {resultado.status_code}")
    print(f"  Motivo: {resultado.motivo}")
    print(f"  Tempo resposta: {resultado.tempo_resposta:.2f}s")

    if resultado.erro_tecnico:
        print(f"  Erro técnico: {resultado.erro_tecnico[:200]}")

    await transmitter.close()

    return resultado


if __name__ == "__main__":
    # Executar teste standalone
    resultado = asyncio.run(test_status_servico_standalone())

    if resultado.sucesso:
        print("\n✅ SEFAZ respondendo normalmente")
    else:
        print(f"\n❌ Problema com SEFAZ: {resultado.motivo}")
