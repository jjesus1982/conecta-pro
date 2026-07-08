"""
Client SOAP — Consulta aos Identificadores de Eventos + Download de Eventos (eSocial).

ESPELHO OFICIAL: estes dois webservices são READ-ONLY no governo — devolvem os
eventos JÁ TRANSMITIDOS do empregador (por qualquer transmissor: Portte,
MB Consultoria/INDEXMED, nós). Nenhuma transmissão acontece aqui.

Fatos do Manual de Orientação do Desenvolvedor (v1.15, seções 7.7 e 7.8):
- URL produção (AMBOS os serviços vivem no host de DOWNLOAD, path "dwlcirurgico"):
  https://webservices.download.esocial.gov.br/servicos/empregador/dwlcirurgico/
    WsConsultarIdentificadoresEventos.svc
    WsSolicitarDownloadEventos.svc
- SOAP 1.1 (BasicHttpBinding), document/literal, mTLS obrigatório.
- A mensagem interna <eSocial> DEVE ser ASSINADA (XMLDSig enveloped, URI="",
  SHA-256 — mesmo padrão da assinatura de evento; reuso do ESocialXMLSigner).
- RESTRIÇÕES DURAS (o serviço as impõe; nós as respeitamos ANTES de chamar):
  * Consultas/downloads BLOQUEADOS entre os dias 1 e 7 de cada mês (cd 403).
  * Máximo 10 ACESSOS/DIA somando os dois webservices (cd 405).
  * SEM paralelismo — uma solicitação por vez (cd 404).
  * dtFim até 1 hora antes da hora atual (cd 409); intervalo máx. 31 dias (cd 410).
  * Consulta identificadores retorna no máx. 50 itens; paginação via
    dhUltimoEvtRetornado → dtIni da próxima consulta.
  * Download aceita até 50 ids/recibos por chamada.

WSDLs reais baixados em produção com mTLS em 2026-07-08 (confirmam operações,
SOAPActions e wrappers) — ver relatório da Missão D.
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

import requests as http_requests
from defusedxml import ElementTree as DET

from .certificate_manager import CertificateManager
from .xml_signer import ESocialXMLSigner, SignatureType

logger = logging.getLogger(__name__)

# Limites oficiais (Manual do Desenvolvedor 7.7.7 / 7.8.7)
MAX_ACESSOS_DIA = 10
DIAS_BLOQUEADOS = range(1, 8)  # dias 1..7 de cada mês
MAX_ITENS_DOWNLOAD = 50
MAX_INTERVALO_DIAS = 31
PAUSA_ENTRE_CHAMADAS_S = 3.0  # sem paralelismo + cortesia de rate

# Namespaces das mensagens internas (Manual 7.7.13/7.7.16/7.8.12/7.8.13)
NS_CONSULTA_EMPREGADOR = "http://www.esocial.gov.br/schema/consulta/identificadores-eventos/empregador/v1_0_0"
NS_CONSULTA_TABELA = "http://www.esocial.gov.br/schema/consulta/identificadores-eventos/tabela/v1_0_0"
NS_CONSULTA_TRABALHADOR = "http://www.esocial.gov.br/schema/consulta/identificadores-eventos/trabalhador/v1_0_0"
NS_DOWNLOAD_POR_ID = "http://www.esocial.gov.br/schema/download/solicitacao/id/v1_0_0"
NS_DOWNLOAD_POR_RECIBO = "http://www.esocial.gov.br/schema/download/solicitacao/nrRecibo/v1_0_0"

# Namespaces dos wrappers SOAP (WSDL real, baixado em produção)
NS_SVC_CONSULTA = "http://www.esocial.gov.br/servicos/empregador/consulta/identificadores-eventos/v1_0_0"
NS_SVC_DOWNLOAD = "http://www.esocial.gov.br/servicos/empregador/download/solicitacao/v1_0_0"


class AmbienteEspelho(StrEnum):
    PRODUCAO = "producao"
    PRODUCAO_RESTRITA = "producaorestrita"


URLS = {
    AmbienteEspelho.PRODUCAO: {
        "consulta_identificadores": (
            "https://webservices.download.esocial.gov.br"
            "/servicos/empregador/dwlcirurgico/WsConsultarIdentificadoresEventos.svc"
        ),
        "download": (
            "https://webservices.download.esocial.gov.br"
            "/servicos/empregador/dwlcirurgico/WsSolicitarDownloadEventos.svc"
        ),
    },
    AmbienteEspelho.PRODUCAO_RESTRITA: {
        "consulta_identificadores": (
            "https://webservices.producaorestrita.esocial.gov.br"
            "/servicos/empregador/dwlcirurgico/WsConsultarIdentificadoresEventos.svc"
        ),
        "download": (
            "https://webservices.producaorestrita.esocial.gov.br"
            "/servicos/empregador/dwlcirurgico/WsSolicitarDownloadEventos.svc"
        ),
    },
}


class EspelhoClientError(Exception):
    """Erro de infraestrutura/protocolo na chamada ao webservice do espelho."""


@dataclass
class RespostaConsultaIdentificadores:
    cd_resposta: str
    desc_resposta: str
    qtde_total: int = 0
    dh_ultimo_evento: str | None = None
    itens: list[dict[str, str]] = field(default_factory=list)  # [{"id":..., "nr_recibo":...}]
    http_status: int = 0
    raw: str = ""

    @property
    def sucesso(self) -> bool:
        # 201 = sucesso; 203 = sucesso com truncamento (mais de 50)
        return self.cd_resposta in ("201", "203")

    @property
    def vazio(self) -> bool:
        return self.cd_resposta == "406"  # nenhum registro para o filtro


@dataclass
class RespostaDownload:
    cd_resposta: str
    desc_resposta: str
    arquivos: list[dict[str, Any]] = field(default_factory=list)
    # cada arquivo: {"cd": str, "desc": str, "xml": str|None, "id_evento": str|None}
    http_status: int = 0
    raw: str = ""

    @property
    def sucesso(self) -> bool:
        return self.cd_resposta == "201"


def resolve_ambiente_espelho(ambiente: str | None = None) -> AmbienteEspelho:
    """Mesma regra do transmitter: default SEGURO producaorestrita; produção explícita."""
    valor = (ambiente or os.getenv("ESOCIAL_AMBIENTE") or "producaorestrita").strip().lower()
    if valor in ("producao", "producao_real", "prod", "1"):
        return AmbienteEspelho.PRODUCAO
    return AmbienteEspelho.PRODUCAO_RESTRITA


def dia_bloqueado(agora: datetime | None = None) -> bool:
    """O governo bloqueia consultas/downloads entre os dias 1 e 7 de cada mês."""
    agora = agora or datetime.now()
    return agora.day in DIAS_BLOQUEADOS


class ESocialEventosClient:
    """Client SOAP+mTLS para consulta identificadores + download de eventos.

    Padrão do ESocialTransmitter: mesmo CertificateManager (A1 .pfx) e mesmo
    assinador XMLDSig. Todas as chamadas são de LEITURA no governo.
    """

    def __init__(
        self,
        ambiente: AmbienteEspelho | None = None,
        certificate_path: str | None = None,
        certificate_password: str | None = None,
    ):
        self.ambiente = ambiente or resolve_ambiente_espelho()
        self._cert_manager = CertificateManager(
            pfx_path=certificate_path
            or os.environ.get("CERTIFICATE_PATH", "/app/credentials/certificates/certificado.pfx"),
            password=certificate_password or os.environ.get("CERTIFICATE_PASSWORD", ""),
        )
        if not self._cert_manager.load():
            raise EspelhoClientError("Falha ao carregar certificado A1 para o espelho eSocial")
        self._signer = ESocialXMLSigner(self._cert_manager)
        self._ultima_chamada: float = 0.0
        logger.info("ESocialEventosClient inicializado (ambiente=%s)", self.ambiente.value)

    # ------------------------------------------------------------------ infra

    def _assinar(self, xml_interno: str) -> str:
        """Assina a mensagem interna <eSocial> (enveloped, URI='', SHA-256)."""
        assinado = self._signer.sign(xml_interno, signature_type=SignatureType.ESOCIAL, reference_uri="")
        # remover declaração <?xml?> para embutir no envelope SOAP
        if assinado.startswith("<?xml"):
            assinado = assinado[assinado.index("?>") + 2 :].strip()
        return assinado

    def _post(self, url: str, soap_action: str, envelope: str) -> tuple[int, str]:
        """POST SOAP 1.1 com mTLS. Respeita pausa mínima entre chamadas (sem paralelismo)."""
        espera = PAUSA_ENTRE_CHAMADAS_S - (time.monotonic() - self._ultima_chamada)
        if espera > 0:
            time.sleep(espera)

        cert_path, key_path = self._cert_manager.get_certificate_for_request()
        try:
            resp = http_requests.post(
                url,
                data=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": f'"{soap_action}"',
                },
                cert=(cert_path, key_path),
                timeout=120,
                verify=True,
            )
            return resp.status_code, resp.text
        except http_requests.exceptions.RequestException as e:
            raise EspelhoClientError(f"Falha HTTP no webservice do espelho: {e}") from e
        finally:
            self._ultima_chamada = time.monotonic()
            try:
                cert_dir = os.path.dirname(cert_path)
                for p in (cert_path, key_path):
                    if p and os.path.exists(p):
                        os.unlink(p)
                if os.path.isdir(cert_dir):
                    os.rmdir(cert_dir)
            except OSError:
                pass

    @staticmethod
    def _envelope(wrapper_ns: str, operacao: str, parametro: str, conteudo_assinado: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soap:Body>"
            f'<{operacao} xmlns="{wrapper_ns}">'
            f"<{parametro}>{conteudo_assinado}</{parametro}>"
            f"</{operacao}>"
            "</soap:Body>"
            "</soap:Envelope>"
        )

    @staticmethod
    def _nr_insc(cnpj: str) -> str:
        """eSocial usa a RAIZ do CNPJ (8 dígitos) como nrInsc do empregador."""
        digits = re.sub(r"\D", "", cnpj)
        return digits[:8]

    # ------------------------------------------------ consulta identificadores

    def _consultar(self, xml_interno: str) -> RespostaConsultaIdentificadores:
        operacao_por_ns = {
            NS_CONSULTA_EMPREGADOR: ("ConsultarIdentificadoresEventosEmpregador", "consultaEventosEmpregador"),
            NS_CONSULTA_TABELA: ("ConsultarIdentificadoresEventosTabela", "consultaEventosTabela"),
            NS_CONSULTA_TRABALHADOR: ("ConsultarIdentificadoresEventosTrabalhador", "consultaEventosTrabalhador"),
        }
        ns_interno = next(ns for ns in operacao_por_ns if ns in xml_interno)
        operacao, parametro = operacao_por_ns[ns_interno]
        soap_action = f"{NS_SVC_CONSULTA}/ServicoConsultarIdentificadoresEventos/{operacao}"
        envelope = self._envelope(NS_SVC_CONSULTA, operacao, parametro, self._assinar(xml_interno))

        url = URLS[self.ambiente]["consulta_identificadores"]
        status, texto = self._post(url, soap_action, envelope)
        logger.info("Consulta identificadores (%s): HTTP %d (%d bytes)", operacao, status, len(texto))

        resposta = self._parse_retorno_consulta(texto)
        resposta.http_status = status
        if status != 200 and not resposta.cd_resposta:
            raise EspelhoClientError(f"HTTP {status} na consulta de identificadores: {texto[:400]}")
        return resposta

    def consultar_identificadores_trabalhador(
        self, employer_cnpj: str, cpf: str, dt_ini: str, dt_fim: str
    ) -> RespostaConsultaIdentificadores:
        """Todos os eventos NÃO PERIÓDICOS do trabalhador recebidos no intervalo.

        dt_ini/dt_fim: 'AAAA-MM-DDTHH:MM:SS' — data de RECEPÇÃO do evento no
        eSocial (não a data-fato). Intervalo máx. 31 dias; dt_fim <= agora-1h.
        """
        xml = (
            f'<eSocial xmlns="{NS_CONSULTA_TRABALHADOR}">'
            "<consultaIdentificadoresEvts>"
            f"<ideEmpregador><tpInsc>1</tpInsc><nrInsc>{self._nr_insc(employer_cnpj)}</nrInsc></ideEmpregador>"
            "<consultaEvtsTrabalhador>"
            f"<cpfTrab>{re.sub(r'[^0-9]', '', cpf)}</cpfTrab>"
            f"<dtIni>{dt_ini}</dtIni>"
            f"<dtFim>{dt_fim}</dtFim>"
            "</consultaEvtsTrabalhador>"
            "</consultaIdentificadoresEvts>"
            "</eSocial>"
        )
        return self._consultar(xml)

    def consultar_identificadores_empregador(
        self, employer_cnpj: str, tp_evt: str, per_apur: str
    ) -> RespostaConsultaIdentificadores:
        """Eventos do EMPREGADOR fora das categorias tabela/trabalhador (ex.: S-1299).

        per_apur: 'AAAA-MM' ou 'AAAA'.
        """
        xml = (
            f'<eSocial xmlns="{NS_CONSULTA_EMPREGADOR}">'
            "<consultaIdentificadoresEvts>"
            f"<ideEmpregador><tpInsc>1</tpInsc><nrInsc>{self._nr_insc(employer_cnpj)}</nrInsc></ideEmpregador>"
            "<consultaEvtsEmpregador>"
            f"<tpEvt>{tp_evt}</tpEvt>"
            f"<perApur>{per_apur}</perApur>"
            "</consultaEvtsEmpregador>"
            "</consultaIdentificadoresEvts>"
            "</eSocial>"
        )
        return self._consultar(xml)

    def consultar_identificadores_tabela(
        self,
        employer_cnpj: str,
        tp_evt: str,
        ch_evt: str | None = None,
        dt_ini: str | None = None,
        dt_fim: str | None = None,
    ) -> RespostaConsultaIdentificadores:
        """Eventos de TABELA do empregador (S-1000..S-1080)."""
        filtros = f"<tpEvt>{tp_evt}</tpEvt>"
        if ch_evt:
            filtros += f"<chEvt>{ch_evt}</chEvt>"
        if dt_ini:
            filtros += f"<dtIni>{dt_ini}</dtIni>"
        if dt_fim:
            filtros += f"<dtFim>{dt_fim}</dtFim>"
        xml = (
            f'<eSocial xmlns="{NS_CONSULTA_TABELA}">'
            "<consultaIdentificadoresEvts>"
            f"<ideEmpregador><tpInsc>1</tpInsc><nrInsc>{self._nr_insc(employer_cnpj)}</nrInsc></ideEmpregador>"
            f"<consultaEvtsTabela>{filtros}</consultaEvtsTabela>"
            "</consultaIdentificadoresEvts>"
            "</eSocial>"
        )
        return self._consultar(xml)

    def _parse_retorno_consulta(self, texto: str) -> RespostaConsultaIdentificadores:
        resposta = RespostaConsultaIdentificadores(cd_resposta="", desc_resposta="", raw=texto[:8000])
        try:
            root = DET.fromstring(texto.encode())
        except Exception:  # noqa: BLE001 — resposta não-XML: reporta honesto
            resposta.desc_resposta = f"Resposta não-XML do governo: {texto[:300]}"
            return resposta

        status = root.find(".//{*}retornoConsultaIdentificadoresEvts/{*}status")
        if status is None:
            status = root.find(".//{*}status")
        if status is not None:
            resposta.cd_resposta = (status.findtext("{*}cdResposta") or "").strip()
            resposta.desc_resposta = (status.findtext("{*}descResposta") or "").strip()

        ret = root.find(".//{*}retornoIdentificadoresEvts")
        if ret is not None:
            qtde = ret.findtext("{*}qtdeTotEvtsConsulta")
            resposta.qtde_total = int(qtde) if qtde and qtde.isdigit() else 0
            resposta.dh_ultimo_evento = ret.findtext("{*}dhUltimoEvtRetornado")

        for item in root.iter():
            if item.tag.endswith("identificadorEvt"):
                resposta.itens.append(
                    {
                        "id": (item.findtext("{*}id") or "").strip(),
                        "nr_recibo": (item.findtext("{*}nrRec") or "").strip(),
                    }
                )
        return resposta

    # ------------------------------------------------------------- download

    def solicitar_download_por_id(self, employer_cnpj: str, ids: list[str]) -> RespostaDownload:
        """Baixa até 50 eventos (XML completo + recibo) pelos Ids."""
        if not ids:
            raise ValueError("Nenhum id informado para download")
        if len(ids) > MAX_ITENS_DOWNLOAD:
            raise ValueError(f"Máximo {MAX_ITENS_DOWNLOAD} ids por solicitação (recebi {len(ids)})")
        corpo = "".join(f"<id>{i}</id>" for i in ids)
        xml = (
            f'<eSocial xmlns="{NS_DOWNLOAD_POR_ID}">'
            "<download>"
            f"<ideEmpregador><tpInsc>1</tpInsc><nrInsc>{self._nr_insc(employer_cnpj)}</nrInsc></ideEmpregador>"
            f"<solicDownloadEvtsPorId>{corpo}</solicDownloadEvtsPorId>"
            "</download>"
            "</eSocial>"
        )
        return self._download("SolicitarDownloadEventosPorId", xml)

    def solicitar_download_por_recibo(self, employer_cnpj: str, recibos: list[str]) -> RespostaDownload:
        """Baixa até 50 eventos (XML completo + recibo) pelos números de recibo."""
        if not recibos:
            raise ValueError("Nenhum recibo informado para download")
        if len(recibos) > MAX_ITENS_DOWNLOAD:
            raise ValueError(f"Máximo {MAX_ITENS_DOWNLOAD} recibos por solicitação (recebi {len(recibos)})")
        corpo = "".join(f"<nrRec>{r}</nrRec>" for r in recibos)
        # ATENÇÃO: o manual (7.8.13) diz "solicDownloadEvtsPorNrRecibo", mas o XSD
        # REAL do governo (erro 417 em produção, 2026-07-08) exige
        # "solicDownloadEventosPorNrRecibo".
        xml = (
            f'<eSocial xmlns="{NS_DOWNLOAD_POR_RECIBO}">'
            "<download>"
            f"<ideEmpregador><tpInsc>1</tpInsc><nrInsc>{self._nr_insc(employer_cnpj)}</nrInsc></ideEmpregador>"
            f"<solicDownloadEventosPorNrRecibo>{corpo}</solicDownloadEventosPorNrRecibo>"
            "</download>"
            "</eSocial>"
        )
        return self._download("SolicitarDownloadEventosPorNrRecibo", xml)

    def _download(self, operacao: str, xml_interno: str) -> RespostaDownload:
        soap_action = f"{NS_SVC_DOWNLOAD}/ServicoSolicitarDownloadEventos/{operacao}"
        envelope = self._envelope(NS_SVC_DOWNLOAD, operacao, "solicitacao", self._assinar(xml_interno))
        url = URLS[self.ambiente]["download"]
        status, texto = self._post(url, soap_action, envelope)
        logger.info("Download eventos (%s): HTTP %d (%d bytes)", operacao, status, len(texto))

        resposta = self._parse_retorno_download(texto)
        resposta.http_status = status
        if status != 200 and not resposta.cd_resposta:
            raise EspelhoClientError(f"HTTP {status} no download de eventos: {texto[:400]}")
        return resposta

    def _parse_retorno_download(self, texto: str) -> RespostaDownload:
        import xml.etree.ElementTree as ET  # noqa: S405 — serialização de subárvore confiável (já parseada por defusedxml)

        resposta = RespostaDownload(cd_resposta="", desc_resposta="", raw=texto[:4000])
        try:
            root = DET.fromstring(texto.encode())
        except Exception:  # noqa: BLE001
            resposta.desc_resposta = f"Resposta não-XML do governo: {texto[:300]}"
            return resposta

        download = None
        for el in root.iter():
            if el.tag.endswith("}download") or el.tag == "download":
                download = el
                break
        if download is not None:
            st = download.find("{*}status")
            if st is not None:
                resposta.cd_resposta = (st.findtext("{*}cdResposta") or "").strip()
                resposta.desc_resposta = (st.findtext("{*}descResposta") or "").strip()

        for arq in root.iter():
            if not arq.tag.endswith("arquivo"):
                continue
            st = arq.find("{*}status")
            cd = (st.findtext("{*}cdResposta") or "").strip() if st is not None else ""
            desc = (st.findtext("{*}descResposta") or "").strip() if st is not None else ""
            xml_evt: str | None = None
            id_evt: str | None = None
            evt = arq.find("{*}evt")
            if evt is not None:
                id_evt = evt.get("Id") or evt.get("id")
                # conteúdo: o XML completo do evento (elemento <eSocial> interno)
                filhos = list(evt)
                if filhos:
                    xml_evt = "".join(ET.tostring(f, encoding="unicode") for f in filhos)
                elif (evt.text or "").strip():
                    xml_evt = evt.text.strip()  # alguns retornos embutem como texto/CDATA
            resposta.arquivos.append({"cd": cd, "desc": desc, "xml": xml_evt, "id_evento": id_evt})

        # Observado em produção (2026-07-08): quando há arquivos, o retorno NÃO
        # traz <status> geral sob <download> — só o status POR ARQUIVO. Nesse
        # caso o sucesso é implícito.
        if not resposta.cd_resposta and resposta.arquivos:
            resposta.cd_resposta = "201"
            resposta.desc_resposta = "(sem status geral no retorno; arquivos presentes)"
        return resposta
