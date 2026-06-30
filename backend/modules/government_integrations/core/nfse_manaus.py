"""
NFS-e Manaus - Integração com Prefeitura de Manaus.

Portal: https://nfse.manaus.am.gov.br/
WebService: ABRASF 2.04

Funções:
- Emissão de NFS-e
- Consulta de NFS-e
- Cancelamento de NFS-e
- Substituição de NFS-e
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from xml.etree.ElementTree import Element, SubElement  # noqa: S405

import defusedxml.ElementTree as ET  # noqa: N817

from .certificate_manager import CertificateManager
from .xml_signer import XMLSigner

logger = logging.getLogger(__name__)


class NFSeStatus(StrEnum):
    """Status da NFS-e."""

    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    AUTORIZADA = "autorizada"
    CANCELADA = "cancelada"
    SUBSTITUIDA = "substituida"
    ERRO = "erro"


class TipoTributacao(StrEnum):
    """Tipo de tributação do ISS."""

    NORMAL = "1"  # Tributação no município
    RETIDO = "2"  # ISS retido pelo tomador
    IMUNE = "3"  # Imune
    ISENTO = "4"  # Isento
    EXIGIBILIDADE_SUSPENSA = "5"  # Exigibilidade suspensa por decisão judicial
    EXIGIBILIDADE_SUSPENSA_ADM = "6"  # Exigibilidade suspensa por processo administrativo


class NaturezaOperacao(StrEnum):
    """Natureza da operação."""

    TRIBUTACAO_MUNICIPIO = "1"
    TRIBUTACAO_FORA_MUNICIPIO = "2"
    ISENCAO = "3"
    IMUNE = "4"
    EXIGIBILIDADE_SUSPENSA_JUDICIAL = "5"
    EXIGIBILIDADE_SUSPENSA_ADM = "6"
    EXPORTACAO = "7"


@dataclass
class Tomador:
    """Dados do tomador do serviço."""

    cpf_cnpj: str
    razao_social: str
    endereco: str
    numero: str
    bairro: str
    cidade: str
    uf: str
    cep: str
    email: str | None = None
    telefone: str | None = None
    inscricao_municipal: str | None = None
    complemento: str | None = None


@dataclass
class Servico:
    """Dados do serviço prestado."""

    codigo_servico: str  # Código do serviço (Lista de Serviços LC 116)
    discriminacao: str  # Descrição do serviço
    valor_servicos: Decimal
    valor_deducoes: Decimal = Decimal("0")
    valor_pis: Decimal = Decimal("0")
    valor_cofins: Decimal = Decimal("0")
    valor_inss: Decimal = Decimal("0")
    valor_ir: Decimal = Decimal("0")
    valor_csll: Decimal = Decimal("0")
    valor_iss: Decimal = Decimal("0")
    aliquota_iss: Decimal = Decimal("0.05")  # 5% padrão Manaus
    iss_retido: bool = False
    codigo_cnae: str | None = None
    codigo_tributacao_municipio: str | None = None

    @property
    def base_calculo(self) -> Decimal:
        """Calcula base de cálculo do ISS."""
        return self.valor_servicos - self.valor_deducoes

    @property
    def valor_liquido(self) -> Decimal:
        """Calcula valor líquido da nota."""
        return (
            self.valor_servicos
            - self.valor_deducoes
            - self.valor_pis
            - self.valor_cofins
            - self.valor_inss
            - self.valor_ir
            - self.valor_csll
            - (self.valor_iss if self.iss_retido else Decimal("0"))
        )


@dataclass
class NFSeManaus:
    """Representação de uma NFS-e de Manaus."""

    # Identificação
    numero: str | None = None
    codigo_verificacao: str | None = None

    # Prestador (dados da empresa)
    prestador_cnpj: str = ""
    prestador_inscricao_municipal: str = ""

    # Tomador
    tomador: Tomador | None = None

    # Serviço
    servico: Servico | None = None

    # Datas
    data_emissao: datetime = field(default_factory=datetime.now)
    competencia: date = field(default_factory=date.today)

    # Tributação
    natureza_operacao: NaturezaOperacao = NaturezaOperacao.TRIBUTACAO_MUNICIPIO
    regime_especial_tributacao: str | None = None
    optante_simples: bool = True
    incentivador_cultural: bool = False

    # Status
    status: NFSeStatus = NFSeStatus.PENDENTE
    mensagem_retorno: str | None = None

    # XML
    xml_envio: str | None = None
    xml_retorno: str | None = None


class NFSeManausManager:
    """
    Gerenciador de NFS-e para Prefeitura de Manaus.

    Implementa padrão ABRASF 2.04.
    Provider: Abaco/GIF
    Testado em: Janeiro 2026

    Endpoints testados e funcionais:
    - RecepcionarLoteRps
    - ConsultarSituacaoLoteRps
    - ConsultarNfsePorRps
    - ConsultarLoteRps
    """

    # URLs dos WebServices (Abaco/GIF - Testado Janeiro 2026)
    URL_BASE_PRODUCAO = "https://nfse-prd.manaus.am.gov.br/nfse/servlet"
    URL_BASE_HOMOLOGACAO = "https://nfse-hml.manaus.am.gov.br/nfse/servlet"

    # Endpoints específicos
    ENDPOINTS = {
        "RecepcionarLoteRps": "/arecepcionarloterps",
        "ConsultarSituacaoLoteRps": "/aconsultarsituacaoloterps",
        "ConsultarNfsePorRps": "/aconsultarnfseporrps",
        "ConsultarLoteRps": "/aconsultarloterps",
        "ConsultarNfse": "/aconsultarnfse",
        "CancelarNfse": "/acancelarnfse",
        "SubstituirNfse": "/asubstituirnfse",
        "ConsultarNfseServicoPrestado": "/aconsultarnfseservicoprestado",
        "ConsultarNfseServicoTomado": "/aconsultarnfseservicotomado",
    }

    # WSDLs para Zeep (se necessário)
    WSDL_PRODUCAO = "https://nfse-prd.manaus.am.gov.br/nfse/servlet/arecepcionarloterps?wsdl"
    WSDL_HOMOLOGACAO = "https://nfse-hml.manaus.am.gov.br/nfse/servlet/arecepcionarloterps?wsdl"

    # Código do município de Manaus (IBGE)
    CODIGO_MUNICIPIO = "1302603"

    # Namespace ABRASF
    NS_TIPOS = "http://www.abrasf.org.br/nfse.xsd"

    # Namespace do WebService (Abaco/GIF)
    NS_WS = "http://www.e-nfs.com.br"

    def __init__(
        self,
        certificate_manager: CertificateManager,
        ambiente: str = "producao",
        inscricao_municipal: str = "",
        cnpj: str = "",
        usuario: str = "",
        senha: str = "",
    ):
        """
        Inicializa o gerenciador.

        Args:
            certificate_manager: Gerenciador de certificados
            ambiente: 'producao' ou 'homologacao'
            inscricao_municipal: Inscrição municipal do prestador
            cnpj: CNPJ do prestador
            usuario: Usuário para autenticação (geralmente o CNPJ)
            senha: Senha para autenticação
        """
        self.cert_manager = certificate_manager
        self.ambiente = ambiente
        self.inscricao_municipal = inscricao_municipal
        self.cnpj = cnpj
        self.usuario = usuario or cnpj
        self.senha = senha

        # XMLSigner é opcional (só necessário para operações que exigem assinatura)
        self.xml_signer = None
        if certificate_manager is not None:
            self.xml_signer = XMLSigner(certificate_manager)

        # URLs
        self.url_base = self.URL_BASE_PRODUCAO if ambiente == "producao" else self.URL_BASE_HOMOLOGACAO
        self.wsdl_url = self.WSDL_PRODUCAO if ambiente == "producao" else self.WSDL_HOMOLOGACAO

    def gerar_rps(self, nfse: NFSeManaus) -> str:
        """
        Gera XML do RPS (Recibo Provisório de Serviço).

        Args:
            nfse: Dados da NFS-e

        Returns:
            XML do RPS
        """
        # Namespace

        # Root
        rps = Element("Rps")

        # InfDeclaracaoPrestacaoServico
        inf_rps = SubElement(rps, "InfDeclaracaoPrestacaoServico")

        # Rps (identificação)
        rps_id = SubElement(inf_rps, "Rps")
        ident_rps = SubElement(rps_id, "IdentificacaoRps")
        SubElement(ident_rps, "Numero").text = str(int(datetime.now().timestamp()))
        SubElement(ident_rps, "Serie").text = "RPS"
        SubElement(ident_rps, "Tipo").text = "1"  # RPS
        SubElement(rps_id, "DataEmissao").text = nfse.data_emissao.strftime("%Y-%m-%d")
        SubElement(rps_id, "Status").text = "1"  # Normal

        # Competência
        SubElement(inf_rps, "Competencia").text = nfse.competencia.strftime("%Y-%m-%d")

        # Serviço
        servico = SubElement(inf_rps, "Servico")
        valores = SubElement(servico, "Valores")
        SubElement(valores, "ValorServicos").text = str(nfse.servico.valor_servicos)
        SubElement(valores, "ValorDeducoes").text = str(nfse.servico.valor_deducoes)
        SubElement(valores, "ValorPis").text = str(nfse.servico.valor_pis)
        SubElement(valores, "ValorCofins").text = str(nfse.servico.valor_cofins)
        SubElement(valores, "ValorInss").text = str(nfse.servico.valor_inss)
        SubElement(valores, "ValorIr").text = str(nfse.servico.valor_ir)
        SubElement(valores, "ValorCsll").text = str(nfse.servico.valor_csll)
        SubElement(valores, "IssRetido").text = "1" if nfse.servico.iss_retido else "2"
        SubElement(valores, "ValorIss").text = str(nfse.servico.valor_iss)
        SubElement(valores, "BaseCalculo").text = str(nfse.servico.base_calculo)
        SubElement(valores, "Aliquota").text = str(nfse.servico.aliquota_iss)
        SubElement(valores, "ValorLiquidoNfse").text = str(nfse.servico.valor_liquido)

        SubElement(servico, "ItemListaServico").text = nfse.servico.codigo_servico
        if nfse.servico.codigo_cnae:
            SubElement(servico, "CodigoCnae").text = nfse.servico.codigo_cnae
        SubElement(servico, "Discriminacao").text = nfse.servico.discriminacao
        SubElement(servico, "CodigoMunicipio").text = self.CODIGO_MUNICIPIO

        # Prestador
        prestador = SubElement(inf_rps, "Prestador")
        cpf_cnpj_prest = SubElement(prestador, "CpfCnpj")
        SubElement(cpf_cnpj_prest, "Cnpj").text = self.cnpj
        SubElement(prestador, "InscricaoMunicipal").text = self.inscricao_municipal

        # Tomador
        if nfse.tomador:
            tomador = SubElement(inf_rps, "Tomador")
            ident_tomador = SubElement(tomador, "IdentificacaoTomador")
            cpf_cnpj_tom = SubElement(ident_tomador, "CpfCnpj")

            doc = nfse.tomador.cpf_cnpj.replace(".", "").replace("-", "").replace("/", "")
            if len(doc) == 11:
                SubElement(cpf_cnpj_tom, "Cpf").text = doc
            else:
                SubElement(cpf_cnpj_tom, "Cnpj").text = doc

            if nfse.tomador.inscricao_municipal:
                SubElement(ident_tomador, "InscricaoMunicipal").text = nfse.tomador.inscricao_municipal

            SubElement(tomador, "RazaoSocial").text = nfse.tomador.razao_social

            endereco = SubElement(tomador, "Endereco")
            SubElement(endereco, "Endereco").text = nfse.tomador.endereco
            SubElement(endereco, "Numero").text = nfse.tomador.numero
            if nfse.tomador.complemento:
                SubElement(endereco, "Complemento").text = nfse.tomador.complemento
            SubElement(endereco, "Bairro").text = nfse.tomador.bairro
            SubElement(endereco, "CodigoMunicipio").text = self.CODIGO_MUNICIPIO
            SubElement(endereco, "Uf").text = nfse.tomador.uf
            SubElement(endereco, "Cep").text = nfse.tomador.cep.replace("-", "")

            if nfse.tomador.email or nfse.tomador.telefone:
                contato = SubElement(tomador, "Contato")
                if nfse.tomador.telefone:
                    SubElement(contato, "Telefone").text = nfse.tomador.telefone
                if nfse.tomador.email:
                    SubElement(contato, "Email").text = nfse.tomador.email

        # Regime especial
        SubElement(inf_rps, "OptanteSimplesNacional").text = "1" if nfse.optante_simples else "2"
        SubElement(inf_rps, "IncentivoFiscal").text = "1" if nfse.incentivador_cultural else "2"

        return ET.tostring(rps, encoding="unicode")

    def enviar_lote_rps(self, lista_nfse: list[NFSeManaus]) -> dict[str, Any]:
        """
        Envia lote de RPS para geração de NFS-e.

        Args:
            lista_nfse: Lista de NFS-e a serem enviadas

        Returns:
            Resultado do envio
        """
        # Monta lote
        lote = Element("EnviarLoteRpsSincronoEnvio", xmlns=self.NS_TIPOS)

        lote_rps = SubElement(lote, "LoteRps")
        SubElement(lote_rps, "NumeroLote").text = str(int(datetime.now().timestamp()))

        cpf_cnpj = SubElement(lote_rps, "CpfCnpj")
        SubElement(cpf_cnpj, "Cnpj").text = self.cnpj
        SubElement(lote_rps, "InscricaoMunicipal").text = self.inscricao_municipal
        SubElement(lote_rps, "QuantidadeRps").text = str(len(lista_nfse))

        lista_rps = SubElement(lote_rps, "ListaRps")

        for nfse in lista_nfse:
            rps_xml = self.gerar_rps(nfse)
            rps_element = ET.fromstring(rps_xml)
            lista_rps.append(rps_element)

        # Assina o lote se certificado configurado
        xml_str = ET.tostring(lote, encoding="unicode")
        if self.xml_signer:
            xml_assinado = self.xml_signer.sign(xml_str, reference_uri="")
        else:
            xml_assinado = xml_str

        logger.info(f"Enviando lote com {len(lista_nfse)} RPS")

        return {"xml_envio": xml_assinado, "quantidade": len(lista_nfse), "status": "pendente"}

    def consultar_nfse_por_rps(self, numero_rps: str, serie: str = "RPS", tipo: str = "1") -> dict[str, Any]:
        """
        Consulta NFS-e pelo número do RPS.

        Args:
            numero_rps: Número do RPS
            serie: Série do RPS
            tipo: Tipo do RPS

        Returns:
            Dados da NFS-e
        """
        consulta = Element("ConsultarNfseRpsEnvio", xmlns=self.NS_TIPOS)

        ident_rps = SubElement(consulta, "IdentificacaoRps")
        SubElement(ident_rps, "Numero").text = numero_rps
        SubElement(ident_rps, "Serie").text = serie
        SubElement(ident_rps, "Tipo").text = tipo

        prestador = SubElement(consulta, "Prestador")
        cpf_cnpj = SubElement(prestador, "CpfCnpj")
        SubElement(cpf_cnpj, "Cnpj").text = self.cnpj
        SubElement(prestador, "InscricaoMunicipal").text = self.inscricao_municipal

        xml_str = ET.tostring(consulta, encoding="unicode")

        return {"xml_consulta": xml_str, "numero_rps": numero_rps}

    def consultar_nfse_por_numero(self, numero_nfse: str) -> dict[str, Any]:
        """
        Consulta NFS-e pelo número da nota.

        Args:
            numero_nfse: Número da NFS-e

        Returns:
            Dados da NFS-e
        """
        consulta = Element("ConsultarNfseEnvio", xmlns=self.NS_TIPOS)

        prestador = SubElement(consulta, "Prestador")
        cpf_cnpj = SubElement(prestador, "CpfCnpj")
        SubElement(cpf_cnpj, "Cnpj").text = self.cnpj
        SubElement(prestador, "InscricaoMunicipal").text = self.inscricao_municipal

        SubElement(consulta, "NumeroNfse").text = numero_nfse

        xml_str = ET.tostring(consulta, encoding="unicode")

        return {"xml_consulta": xml_str, "numero_nfse": numero_nfse}

    def cancelar_nfse(self, numero_nfse: str, codigo_cancelamento: str = "1") -> dict[str, Any]:
        """
        Cancela uma NFS-e.

        Args:
            numero_nfse: Número da NFS-e
            codigo_cancelamento: Código do motivo (1=Erro emissão, 2=Serviço não prestado, etc.)

        Returns:
            Resultado do cancelamento
        """
        cancelamento = Element("CancelarNfseEnvio", xmlns=self.NS_TIPOS)

        pedido = SubElement(cancelamento, "Pedido")
        inf_pedido = SubElement(pedido, "InfPedidoCancelamento")

        ident_nfse = SubElement(inf_pedido, "IdentificacaoNfse")
        SubElement(ident_nfse, "Numero").text = numero_nfse
        cpf_cnpj = SubElement(ident_nfse, "CpfCnpj")
        SubElement(cpf_cnpj, "Cnpj").text = self.cnpj
        SubElement(ident_nfse, "InscricaoMunicipal").text = self.inscricao_municipal
        SubElement(ident_nfse, "CodigoMunicipio").text = self.CODIGO_MUNICIPIO

        SubElement(inf_pedido, "CodigoCancelamento").text = codigo_cancelamento

        xml_str = ET.tostring(cancelamento, encoding="unicode")
        if self.xml_signer:
            xml_assinado = self.xml_signer.sign(xml_str, reference_uri="")
        else:
            xml_assinado = xml_str

        logger.info(f"Cancelando NFS-e {numero_nfse}")

        return {
            "xml_cancelamento": xml_assinado,
            "numero_nfse": numero_nfse,
            "codigo_cancelamento": codigo_cancelamento,
        }

    def substituir_nfse(self, numero_nfse_substituida: str, nova_nfse: NFSeManaus) -> dict[str, Any]:
        """
        Substitui uma NFS-e por outra.

        Args:
            numero_nfse_substituida: Número da NFS-e a ser substituída
            nova_nfse: Dados da nova NFS-e

        Returns:
            Resultado da substituição
        """
        substituicao = Element("SubstituirNfseEnvio", xmlns=self.NS_TIPOS)

        # Pedido de substituição
        pedido = SubElement(substituicao, "SubstituicaoNfse")

        # NFS-e a ser substituída
        SubElement(pedido, "NfseSubstituida").text = numero_nfse_substituida

        # Nova NFS-e (RPS)
        rps_xml = self.gerar_rps(nova_nfse)
        rps_element = ET.fromstring(rps_xml)
        pedido.append(rps_element)

        xml_str = ET.tostring(substituicao, encoding="unicode")
        if self.xml_signer:
            xml_assinado = self.xml_signer.sign(xml_str, reference_uri="")
        else:
            xml_assinado = xml_str

        logger.info(f"Substituindo NFS-e {numero_nfse_substituida}")

        return {"xml_substituicao": xml_assinado, "numero_substituida": numero_nfse_substituida}

    def _montar_envelope_soap(self, operacao: str, xml_cabecalho: str, xml_dados: str) -> str:
        """
        Monta envelope SOAP para comunicação com WebService.

        Args:
            operacao: Nome da operação (ex: RecepcionarLoteRps)
            xml_cabecalho: XML do cabeçalho ABRASF
            xml_dados: XML dos dados da requisição

        Returns:
            Envelope SOAP completo
        """
        from xml.sax.saxutils import escape as _esc

        cab = _esc(xml_cabecalho)
        dad = _esc(xml_dados)
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:enf="{self.NS_WS}">
  <soap:Body>
    <enf:{operacao}.Execute>
      <enf:Nfsecabecmsg>{cab}</enf:Nfsecabecmsg>
      <enf:Nfsedadosmsg>{dad}</enf:Nfsedadosmsg>
    </enf:{operacao}.Execute>
  </soap:Body>
</soap:Envelope>'''

    def _gerar_cabecalho(self) -> str:
        """Gera cabeçalho ABRASF 2.04."""
        return f'''<cabecalho xmlns="{self.NS_TIPOS}" versao="2.04"><versaoDados>2.04</versaoDados></cabecalho>'''

    def _get_url(self, operacao: str) -> str:
        """Retorna URL completa para operação."""
        endpoint = self.ENDPOINTS.get(operacao, "")
        return f"{self.url_base}{endpoint}"

    def _get_soap_action(self, operacao: str) -> str:
        """Retorna SOAPAction para operação."""
        endpoint = self.ENDPOINTS.get(operacao, "").upper()
        return f"http://www.e-nfs.com.braction{endpoint}.Execute"

    def enviar_requisicao(self, operacao: str, xml_dados: str, timeout: int = 30) -> dict[str, Any]:
        """
        Envia requisição SOAP para o WebService.

        Args:
            operacao: Nome da operação
            xml_dados: XML dos dados
            timeout: Timeout em segundos

        Returns:
            Resultado da requisição
        """
        import requests

        url = self._get_url(operacao)
        cabecalho = self._gerar_cabecalho()
        envelope = self._montar_envelope_soap(operacao, cabecalho, xml_dados)

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": self._get_soap_action(operacao),
        }

        logger.info(f"Enviando requisição {operacao} para {url}")

        try:
            response = requests.post(
                url,
                data=envelope.encode("utf-8"),
                headers=headers,
                timeout=timeout,
                cert=self.cert_manager.get_certificate_for_request() if self.cert_manager else None,
            )

            resultado = {
                "status_code": response.status_code,
                "operacao": operacao,
                "url": url,
                "resposta_raw": response.text,
            }

            # Parseia resposta
            if response.status_code == 200:
                if "Outputxml" in response.text:
                    match = re.search(r"<Outputxml>(.*?)</Outputxml>", response.text, re.DOTALL)
                    if match:
                        resultado["outputxml"] = match.group(1)
                        resultado["sucesso"] = True
                elif "Fault" in response.text:
                    match = re.search(r"<faultstring>(.*?)</faultstring>", response.text, re.DOTALL)
                    if match:
                        resultado["erro"] = match.group(1)
                        resultado["sucesso"] = False

            return resultado

        except requests.RequestException as e:
            logger.error(f"Erro na requisição {operacao}: {e}")
            return {"sucesso": False, "erro": str(e), "operacao": operacao}


# Códigos de serviço comuns para vigilância/segurança
CODIGOS_SERVICO_VIGILANCIA = {
    "11.02": "Vigilância, segurança ou monitoramento de bens, pessoas e semoventes",
    "11.03": "Escolta, inclusive de veículos e cargas",
    "11.04": "Armazenamento, depósito, carga, descarga, arrumação e guarda de bens",
    "11.05": "Serviços de transporte de valores",
}
