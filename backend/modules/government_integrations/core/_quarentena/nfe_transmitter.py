"""
Transmissor de NF-e para SEFAZ.

Implementa transmissão real de NF-e usando SOAP 1.2 com mTLS.
Resolve erro 215 (Falha no Schema XML) com envelope correto.

Author: Claude AI + Human Developer
Date: 2026-01-17
"""

import logging
import re
import ssl
from dataclasses import dataclass
from datetime import datetime

import aiohttp
from lxml import etree

from .contingency import ENDPOINTS_CENTRALIZADOS, MatrizContingencia
from .credentials.file_credential_provider import get_file_credential_provider

logger = logging.getLogger(__name__)


# Namespaces
NS_SOAP12 = "http://www.w3.org/2003/05/soap-envelope"
NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_NFE_WSDL = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4"


@dataclass
class ResultadoTransmissao:
    """Resultado da transmissão para SEFAZ."""

    sucesso: bool
    status_code: str
    motivo: str
    protocolo: str | None = None
    chave_acesso: str | None = None
    data_recebimento: datetime | None = None
    xml_retorno: str | None = None
    tempo_resposta: float = 0.0
    erro_tecnico: str | None = None


class NFETransmitter:
    """
    Transmissor de NF-e para SEFAZ.

    Implementa:
    - Montagem de envelope SOAP 1.2 correto
    - Transmissão com certificado mTLS
    - Processamento de resposta
    - Suporte a modo síncrono e assíncrono
    """

    TIMEOUT = 60  # Segundos
    VERSION = "4.00"

    def __init__(
        self,
        uf: str = "AM",
        ambiente: str = "2",  # 1=Produção, 2=Homologação
    ):
        """
        Inicializa transmissor.

        Args:
            uf: UF do emitente
            ambiente: 1=Produção, 2=Homologação
        """
        self.uf = uf.upper()
        self.ambiente = ambiente
        self._session: aiohttp.ClientSession | None = None
        self._ssl_context: ssl.SSLContext | None = None
        self._lote_counter = int(datetime.utcnow().strftime("%y%m%d%H%M%S"))

        logger.info(
            f"NFETransmitter inicializado: UF={self.uf}, Ambiente={'Produção' if ambiente == '1' else 'Homologação'}"
        )

    def _get_next_lote_id(self) -> str:
        """Gera próximo ID de lote (15 dígitos)."""
        self._lote_counter += 1
        return str(self._lote_counter).zfill(15)[-15:]

    def _get_endpoint_url(self, servico: str = "NfeAutorizacao") -> str:
        """
        Obtém URL do endpoint do serviço.

        Args:
            servico: Nome do serviço (NfeAutorizacao, NfeRetAutorizacao, etc.)
        """
        config = MatrizContingencia.obter_config_nfe(self.uf)
        endpoint_key = config.principal.url

        # Tratar UFs com endpoints separados por ambiente (ex: AM)
        # AM_PROD -> AM_HOM para homologação
        if endpoint_key.endswith("_PROD") and self.ambiente == "2":
            endpoint_key = endpoint_key.replace("_PROD", "_HOM")

        # Se é referência para endpoints centralizados
        if endpoint_key in ENDPOINTS_CENTRALIZADOS:
            endpoints = ENDPOINTS_CENTRALIZADOS[endpoint_key]
            url = endpoints.get(servico, "")
            logger.debug(f"Endpoint {servico} para {self.uf}: {url}")
            return url

        # URL direta - construir path do serviço
        base_url = config.principal.url.rstrip("/")

        # Mapeamento de serviços para paths conhecidos
        service_paths = {
            "NfeAutorizacao": "NFeAutorizacao4",
            "NfeRetAutorizacao": "NFeRetAutorizacao4",
            "NfeConsultaProtocolo": "NFeConsulta4",
            "NfeStatusServico": "NFeStatusServico4",
            "RecepcaoEvento": "NFeRecepcaoEvento4",
        }

        path = service_paths.get(servico, servico)
        return f"{base_url}/{path}"

    def _criar_envelope_autorizacao(self, xml_nfe_assinado: str, sincrono: bool = True) -> str:
        """
        Cria envelope SOAP 1.2 para autorização de NF-e.

        Args:
            xml_nfe_assinado: XML da NFe assinada
            sincrono: Se True, transmissão síncrona

        Returns:
            Envelope SOAP completo
        """
        id_lote = self._get_next_lote_id()
        ind_sinc = "1" if sincrono else "0"

        # Remover declaração XML da NFe assinada (será incluída no envelope)
        xml_nfe_limpo = re.sub(r"<\?xml[^?]*\?>\s*", "", xml_nfe_assinado)

        # Garantir namespace correto na NFe
        if 'xmlns="http://www.portalfiscal.inf.br/nfe"' not in xml_nfe_limpo:
            # Adicionar namespace se não existir
            xml_nfe_limpo = xml_nfe_limpo.replace("<NFe", '<NFe xmlns="http://www.portalfiscal.inf.br/nfe"', 1)

        # Envelope SOAP 1.2 - formato bare (sem wrapper)
        # nfeDadosMsg vai direto no Body com namespace do WSDL
        envelope = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<soap12:Envelope xmlns:soap12="{NS_SOAP12}" xmlns:nfea="{NS_NFE_WSDL}">'
            f"<soap12:Header/>"
            f"<soap12:Body>"
            f"<nfea:nfeDadosMsg>"
            f'<enviNFe xmlns="{NS_NFE}" versao="{self.VERSION}">'
            f"<idLote>{id_lote}</idLote>"
            f"<indSinc>{ind_sinc}</indSinc>"
            f"{xml_nfe_limpo}"
            f"</enviNFe>"
            f"</nfea:nfeDadosMsg>"
            f"</soap12:Body>"
            f"</soap12:Envelope>"
        )

        return envelope

    def _criar_envelope_consulta_recibo(self, recibo: str) -> str:
        """Cria envelope para consultar recibo (modo assíncrono)."""
        wsdl_ns = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRetAutorizacao4"

        # Envelope SOAP 1.2 - formato bare (sem wrapper)
        envelope = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<soap12:Envelope xmlns:soap12="{NS_SOAP12}" xmlns:nfer="{wsdl_ns}">'
            f"<soap12:Header/>"
            f"<soap12:Body>"
            f"<nfer:nfeDadosMsg>"
            f'<consReciNFe xmlns="{NS_NFE}" versao="{self.VERSION}">'
            f"<tpAmb>{self.ambiente}</tpAmb>"
            f"<nRec>{recibo}</nRec>"
            f"</consReciNFe>"
            f"</nfer:nfeDadosMsg>"
            f"</soap12:Body>"
            f"</soap12:Envelope>"
        )

        return envelope

    def _criar_envelope_status_servico(self) -> str:
        """Cria envelope para consultar status do serviço."""
        # Código UF
        uf_codes = {
            "AC": "12",
            "AL": "27",
            "AM": "13",
            "AP": "16",
            "BA": "29",
            "CE": "23",
            "DF": "53",
            "ES": "32",
            "GO": "52",
            "MA": "21",
            "MG": "31",
            "MS": "50",
            "MT": "51",
            "PA": "15",
            "PB": "25",
            "PE": "26",
            "PI": "22",
            "PR": "41",
            "RJ": "33",
            "RN": "24",
            "RO": "11",
            "RR": "14",
            "RS": "43",
            "SC": "42",
            "SE": "28",
            "SP": "35",
            "TO": "17",
        }
        cod_uf = uf_codes.get(self.uf, "35")

        # Namespace do WSDL - NF-e usa document/literal bare
        # nfeDadosMsg vai direto no Body, sem wrapper
        wsdl_ns = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4"

        # Envelope SOAP 1.2 - formato bare (sem wrapper)
        envelope = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<soap12:Envelope xmlns:soap12="{NS_SOAP12}" xmlns:nfes="{wsdl_ns}">'
            f"<soap12:Header/>"
            f"<soap12:Body>"
            f"<nfes:nfeDadosMsg>"
            f'<consStatServ xmlns="{NS_NFE}" versao="{self.VERSION}">'
            f"<tpAmb>{self.ambiente}</tpAmb>"
            f"<cUF>{cod_uf}</cUF>"
            f"<xServ>STATUS</xServ>"
            f"</consStatServ>"
            f"</nfes:nfeDadosMsg>"
            f"</soap12:Body>"
            f"</soap12:Envelope>"
        )

        return envelope

    async def _get_ssl_context(self) -> ssl.SSLContext:
        """Obtém contexto SSL com certificado."""
        if self._ssl_context is None:
            provider = get_file_credential_provider()
            self._ssl_context = provider.get_ssl_context()
        return self._ssl_context

    async def _get_session(self) -> aiohttp.ClientSession:
        """Obtém sessão HTTP configurada."""
        if self._session is None or self._session.closed:
            ssl_context = await self._get_ssl_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=self.TIMEOUT),
            )

        return self._session

    async def _fazer_requisicao(self, url: str, envelope: str, soap_action: str) -> tuple[int, str]:
        """
        Faz requisição SOAP para SEFAZ.

        Args:
            url: URL do webservice
            envelope: Envelope SOAP
            soap_action: SOAP Action

        Returns:
            Tupla (status_http, resposta_texto)
        """
        headers = {
            "Content-Type": f'application/soap+xml; charset=utf-8; action="{soap_action}"',
            "Accept": "application/soap+xml",
        }

        session = await self._get_session()

        logger.debug(f"Requisição SOAP para: {url}")
        logger.debug(f"SOAP Action: {soap_action}")

        async with session.post(url, data=envelope.encode("utf-8"), headers=headers) as response:
            texto = await response.text()
            return response.status, texto

    def _processar_resposta_autorizacao(self, xml_resposta: str) -> ResultadoTransmissao:
        """
        Processa resposta de autorização.

        Args:
            xml_resposta: XML de resposta da SEFAZ

        Returns:
            ResultadoTransmissao
        """
        resultado = ResultadoTransmissao(
            sucesso=False,
            status_code="",
            motivo="",
            xml_retorno=xml_resposta,
        )

        try:
            # Parse XML
            root = etree.fromstring(xml_resposta.encode("utf-8"))

            # Buscar retEnviNFe
            ret_envi = root.find(f".//{{{NS_NFE}}}retEnviNFe")
            if ret_envi is None:
                # Tentar sem namespace
                ret_envi = root.find(".//retEnviNFe")

            if ret_envi is not None:
                resultado.status_code = ret_envi.findtext(f"{{{NS_NFE}}}cStat") or ret_envi.findtext("cStat") or ""
                resultado.motivo = ret_envi.findtext(f"{{{NS_NFE}}}xMotivo") or ret_envi.findtext("xMotivo") or ""

                # Resposta síncrona - buscar protNFe
                prot = ret_envi.find(f".//{{{NS_NFE}}}protNFe")
                if prot is None:
                    prot = ret_envi.find(".//protNFe")

                if prot is not None:
                    inf_prot = prot.find(f"{{{NS_NFE}}}infProt") or prot.find("infProt")
                    if inf_prot is not None:
                        prot_status = inf_prot.findtext(f"{{{NS_NFE}}}cStat") or inf_prot.findtext("cStat") or ""

                        # 100 = Autorizada, 150 = Autorizada fora do prazo
                        if prot_status in ["100", "150"]:
                            resultado.sucesso = True
                            resultado.protocolo = inf_prot.findtext(f"{{{NS_NFE}}}nProt") or inf_prot.findtext("nProt")
                            resultado.chave_acesso = inf_prot.findtext(f"{{{NS_NFE}}}chNFe") or inf_prot.findtext(
                                "chNFe"
                            )

                            dh_recbto = inf_prot.findtext(f"{{{NS_NFE}}}dhRecbto") or inf_prot.findtext("dhRecbto")
                            if dh_recbto:
                                try:
                                    resultado.data_recebimento = datetime.fromisoformat(
                                        dh_recbto.replace("Z", "+00:00")
                                    )
                                except Exception as e:
                                    logger.debug(f"Erro ao processar data de recebimento: {e}")

                        resultado.status_code = prot_status
                        resultado.motivo = (
                            inf_prot.findtext(f"{{{NS_NFE}}}xMotivo")
                            or inf_prot.findtext("xMotivo")
                            or resultado.motivo
                        )

                # Resposta assíncrona - pode ter apenas recibo
                recibo = ret_envi.findtext(f".//{{{NS_NFE}}}nRec") or ret_envi.findtext(".//nRec")
                if recibo and resultado.status_code == "103":  # Lote recebido
                    resultado.protocolo = recibo  # Neste caso, é o número do recibo
                    resultado.motivo = f"Lote recebido. Recibo: {recibo}"

            else:
                # Verificar se é erro SOAP
                fault = root.find(f".//{{{NS_SOAP12}}}Fault")
                if fault is not None:
                    reason = fault.find(f"{{{NS_SOAP12}}}Reason")
                    if reason is not None:
                        text = reason.find(f"{{{NS_SOAP12}}}Text")
                        resultado.motivo = text.text if text is not None else "Erro SOAP não identificado"
                    resultado.status_code = "SOAP_FAULT"
                else:
                    resultado.motivo = "Resposta não reconhecida"
                    resultado.status_code = "PARSE_ERROR"

        except Exception as e:
            logger.error(f"Erro ao processar resposta: {e}")
            resultado.erro_tecnico = str(e)
            resultado.motivo = f"Erro ao processar resposta: {e}"

        return resultado

    async def consultar_status_servico(self) -> ResultadoTransmissao:
        """
        Consulta status do serviço SEFAZ.

        Returns:
            ResultadoTransmissao
        """
        url = self._get_endpoint_url("NfeStatusServico")
        envelope = self._criar_envelope_status_servico()
        soap_action = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4/nfeStatusServicoNF"

        inicio = datetime.utcnow()

        try:
            status_http, resposta = await self._fazer_requisicao(url, envelope, soap_action)

            resultado = ResultadoTransmissao(
                sucesso=False,
                status_code="",
                motivo="",
                xml_retorno=resposta,
                tempo_resposta=(datetime.utcnow() - inicio).total_seconds(),
            )

            if status_http != 200:
                resultado.motivo = f"HTTP {status_http}"
                resultado.erro_tecnico = resposta[:500]
                return resultado

            # Parse resposta
            root = etree.fromstring(resposta.encode("utf-8"))
            ret = root.find(f".//{{{NS_NFE}}}retConsStatServ")
            if ret is None:
                ret = root.find(".//retConsStatServ")

            if ret is not None:
                resultado.status_code = ret.findtext(f"{{{NS_NFE}}}cStat") or ret.findtext("cStat") or ""
                resultado.motivo = ret.findtext(f"{{{NS_NFE}}}xMotivo") or ret.findtext("xMotivo") or ""

                # 107 = Serviço em operação
                resultado.sucesso = resultado.status_code == "107"

            return resultado

        except Exception as e:
            logger.error(f"Erro ao consultar status: {e}")
            return ResultadoTransmissao(
                sucesso=False,
                status_code="ERROR",
                motivo=str(e),
                erro_tecnico=str(e),
                tempo_resposta=(datetime.utcnow() - inicio).total_seconds(),
            )

    async def transmitir(self, xml_nfe_assinado: str, sincrono: bool = True) -> ResultadoTransmissao:
        """
        Transmite NF-e para SEFAZ.

        Args:
            xml_nfe_assinado: XML da NFe já assinada
            sincrono: Se True, aguarda resposta imediata

        Returns:
            ResultadoTransmissao
        """
        url = self._get_endpoint_url("NfeAutorizacao")
        envelope = self._criar_envelope_autorizacao(xml_nfe_assinado, sincrono)
        soap_action = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4/nfeAutorizacaoLote"

        logger.info(f"Transmitindo NF-e para: {url}")

        inicio = datetime.utcnow()

        try:
            status_http, resposta = await self._fazer_requisicao(url, envelope, soap_action)

            tempo_resposta = (datetime.utcnow() - inicio).total_seconds()

            if status_http != 200:
                return ResultadoTransmissao(
                    sucesso=False,
                    status_code=str(status_http),
                    motivo=f"Erro HTTP {status_http}",
                    xml_retorno=resposta,
                    tempo_resposta=tempo_resposta,
                    erro_tecnico=resposta[:1000],
                )

            resultado = self._processar_resposta_autorizacao(resposta)
            resultado.tempo_resposta = tempo_resposta

            if resultado.sucesso:
                logger.info(f"NF-e autorizada: chave={resultado.chave_acesso}, protocolo={resultado.protocolo}")
            else:
                logger.warning(f"NF-e não autorizada: status={resultado.status_code}, motivo={resultado.motivo}")

            return resultado

        except Exception as e:
            logger.error(f"Erro na transmissão: {e}")
            return ResultadoTransmissao(
                sucesso=False,
                status_code="ERROR",
                motivo=str(e),
                erro_tecnico=str(e),
                tempo_resposta=(datetime.utcnow() - inicio).total_seconds(),
            )

    async def consultar_recibo(self, recibo: str) -> ResultadoTransmissao:
        """
        Consulta resultado de lote assíncrono.

        Args:
            recibo: Número do recibo retornado na transmissão

        Returns:
            ResultadoTransmissao
        """
        url = self._get_endpoint_url("NfeRetAutorizacao")
        envelope = self._criar_envelope_consulta_recibo(recibo)
        soap_action = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRetAutorizacao4/nfeRetAutorizacaoLote"

        inicio = datetime.utcnow()

        try:
            status_http, resposta = await self._fazer_requisicao(url, envelope, soap_action)

            if status_http != 200:
                return ResultadoTransmissao(
                    sucesso=False,
                    status_code=str(status_http),
                    motivo=f"Erro HTTP {status_http}",
                    tempo_resposta=(datetime.utcnow() - inicio).total_seconds(),
                )

            resultado = self._processar_resposta_autorizacao(resposta)
            resultado.tempo_resposta = (datetime.utcnow() - inicio).total_seconds()

            return resultado

        except Exception as e:
            logger.error(f"Erro ao consultar recibo: {e}")
            return ResultadoTransmissao(
                sucesso=False,
                status_code="ERROR",
                motivo=str(e),
                erro_tecnico=str(e),
                tempo_resposta=(datetime.utcnow() - inicio).total_seconds(),
            )

    async def close(self):
        """Fecha recursos."""
        if self._session and not self._session.closed:
            await self._session.close()


# Singleton
_nfe_transmitter: NFETransmitter | None = None


def get_nfe_transmitter(uf: str = "AM", ambiente: str = "2") -> NFETransmitter:
    """Obtém instância do transmissor de NF-e."""
    global _nfe_transmitter
    if _nfe_transmitter is None:
        _nfe_transmitter = NFETransmitter(uf=uf, ambiente=ambiente)
    return _nfe_transmitter


def init_nfe_transmitter(uf: str = "AM", ambiente: str = "2") -> NFETransmitter:
    """Inicializa transmissor de NF-e."""
    global _nfe_transmitter
    _nfe_transmitter = NFETransmitter(uf=uf, ambiente=ambiente)
    return _nfe_transmitter
