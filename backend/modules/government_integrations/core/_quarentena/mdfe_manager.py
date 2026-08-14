"""
Module: MDFeManager
Description: Sistema de emissao de MDF-e (Manifesto Eletronico de Documentos Fiscais)
             Modelo 58 - Acompanhamento de transporte de cargas
             Versao 3.00
Author: Conecta PRO
Date: 2026-01-17

Portal: https://www.mdfe.fazenda.gov.br
Documentacao: https://www.mdfe.fazenda.gov.br/portal/documentos.aspx

MDF-e:
- Obrigatorio para transportadores com CT-e
- Obrigatorio para emitentes de NF-e com transporte proprio
- Vincula NF-e/CT-e ao veiculo/condutor
"""

import logging
import re
import ssl
import time
import xml.etree.ElementTree as ET  # noqa: N817, S405
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4
from xml.dom import minidom  # noqa: S408
from xml.etree.ElementTree import Element  # noqa: S405

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


# Endpoints MDF-e (SVRS atende todos os estados)
MDFE_ENDPOINTS = {
    "SVRS_PROD": {
        "MDFeRecepcaoSinc": "https://mdfe.svrs.rs.gov.br/ws/MDFeRecepcaoSinc/MDFeRecepcaoSinc.asmx",
        "MDFeConsulta": "https://mdfe.svrs.rs.gov.br/ws/MDFeConsulta/MDFeConsulta.asmx",
        "MDFeStatusServico": "https://mdfe.svrs.rs.gov.br/ws/MDFeStatusServico/MDFeStatusServico.asmx",
        "MDFeRecepcaoEvento": "https://mdfe.svrs.rs.gov.br/ws/MDFeRecepcaoEvento/MDFeRecepcaoEvento.asmx",
        "MDFeConsNaoEnc": "https://mdfe.svrs.rs.gov.br/ws/MDFeConsNaoEnc/MDFeConsNaoEnc.asmx",
        "MDFeDistribuicaoDFe": "https://mdfe.svrs.rs.gov.br/ws/MDFeDistribuicaoDFe/MDFeDistribuicaoDFe.asmx",
    },
    "SVRS_HOM": {
        "MDFeRecepcaoSinc": "https://mdfe-homologacao.svrs.rs.gov.br/ws/MDFeRecepcaoSinc/MDFeRecepcaoSinc.asmx",
        "MDFeConsulta": "https://mdfe-homologacao.svrs.rs.gov.br/ws/MDFeConsulta/MDFeConsulta.asmx",
        "MDFeStatusServico": "https://mdfe-homologacao.svrs.rs.gov.br/ws/MDFeStatusServico/MDFeStatusServico.asmx",
        "MDFeRecepcaoEvento": "https://mdfe-homologacao.svrs.rs.gov.br/ws/MDFeRecepcaoEvento/MDFeRecepcaoEvento.asmx",
        "MDFeConsNaoEnc": "https://mdfe-homologacao.svrs.rs.gov.br/ws/MDFeConsNaoEnc/MDFeConsNaoEnc.asmx",
        "MDFeDistribuicaoDFe": "https://mdfe-homologacao.svrs.rs.gov.br/ws/MDFeDistribuicaoDFe/MDFeDistribuicaoDFe.asmx",
    },
}

# Codigo IBGE UFs
UF_CODIGO_IBGE = {
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


class TipoEmitente(StrEnum):
    """Tipo de emitente do MDF-e."""

    PRESTADOR_SERVICO_TRANSPORTE = "1"  # Transportador
    TRANSPORTADOR_CARGA_PROPRIA = "2"  # Emitente NF-e transportando


class ModalTransporte(StrEnum):
    """Modal de transporte."""

    RODOVIARIO = "1"
    AEREO = "2"
    AQUAVIARIO = "3"
    FERROVIARIO = "4"


class TipoTransportador(StrEnum):
    """Tipo de transportador."""

    ETC = "1"  # Empresa de Transporte de Carga
    TAC = "2"  # Transportador Autonomo de Carga
    CTC = "3"  # Cooperativa de Transporte de Carga


class TipoCarroceria(StrEnum):
    """Tipo de carroceria."""

    NAO_APLICAVEL = "00"
    ABERTA = "01"
    FECHADA = "02"
    GRANELEIRA = "03"
    PORTA_CONTAINER = "04"
    SIDER = "05"


class TipoRodado(StrEnum):
    """Tipo de rodado."""

    TRUCK = "01"
    TOCO = "02"
    CAVALO_MECANICO = "03"
    VAN = "04"
    UTILITARIO = "05"
    OUTROS = "06"


@dataclass
class Endereco:
    """Endereco."""

    logradouro: str
    numero: str
    bairro: str
    cidade: str
    uf: str
    cep: str
    codigo_municipio: str
    complemento: str | None = None


@dataclass
class Emitente:
    """Dados do emitente do MDF-e."""

    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    inscricao_estadual: str
    endereco: Endereco


@dataclass
class Veiculo:
    """Dados do veiculo."""

    placa: str
    renavam: str | None = None
    tara: int = 0  # Peso do veiculo vazio em KG
    capacidade_kg: int = 0
    capacidade_m3: int = 0
    tipo_rodado: TipoRodado = TipoRodado.TRUCK
    tipo_carroceria: TipoCarroceria = TipoCarroceria.FECHADA
    uf_licenciamento: str = ""


@dataclass
class Condutor:
    """Dados do condutor."""

    cpf: str
    nome: str


@dataclass
class DocumentoVinculado:
    """Documento fiscal vinculado ao MDF-e (NF-e ou CT-e)."""

    chave_acesso: str
    tipo: str = "NFe"  # NFe ou CTe
    segundo_codigo_barras: str | None = None


@dataclass
class Municipio:
    """Municipio de carregamento/descarregamento."""

    codigo_ibge: str
    nome: str


@dataclass
class MDFe:
    """Manifesto Eletronico de Documentos Fiscais."""

    id: UUID = field(default_factory=uuid4)
    numero: int = 0
    serie: int = 1
    modal: ModalTransporte = ModalTransporte.RODOVIARIO
    tipo_emitente: TipoEmitente = TipoEmitente.PRESTADOR_SERVICO_TRANSPORTE
    tipo_transportador: TipoTransportador = TipoTransportador.ETC

    emitente: Emitente = None
    veiculo_tracao: Veiculo = None
    veiculos_reboque: list[Veiculo] = field(default_factory=list)
    condutores: list[Condutor] = field(default_factory=list)

    # Percurso
    uf_inicio: str = ""
    uf_fim: str = ""
    municipios_carregamento: list[Municipio] = field(default_factory=list)
    municipios_descarregamento: list[Municipio] = field(default_factory=list)
    ufs_percurso: list[str] = field(default_factory=list)  # UFs intermediarias

    # Documentos
    documentos: list[DocumentoVinculado] = field(default_factory=list)

    # Totais
    quantidade_cte: int = 0
    quantidade_nfe: int = 0
    valor_total_carga: Decimal = Decimal("0")
    peso_total_carga: Decimal = Decimal("0")  # KG
    unidade_peso: str = "KG"

    # Datas
    data_emissao: datetime = None
    data_inicio_viagem: datetime = None

    # Chave e protocolo
    chave_acesso: str | None = None
    protocolo: str | None = None
    status: str = "draft"

    # RNTRC
    rntrc: str | None = None  # Registro Nacional Transportadores Rodoviarios

    def __post_init__(self):
        if self.data_emissao is None:
            self.data_emissao = datetime.now(UTC)
        if self.data_inicio_viagem is None:
            self.data_inicio_viagem = self.data_emissao

    def generate_chave_acesso(self) -> str:
        """Gera a chave de acesso do MDF-e (44 digitos)."""
        uf_code = UF_CODIGO_IBGE.get(self.emitente.endereco.uf, "13")
        aamm = self.data_emissao.strftime("%y%m")
        cnpj = re.sub(r"[^\d]", "", self.emitente.cnpj).zfill(14)
        modelo = "58"
        serie = str(self.serie).zfill(3)
        numero = str(self.numero).zfill(9)
        tp_emis = "1"
        c_mdf = str(hash(f"{self.id}") % 100000000).zfill(8)

        chave_sem_dv = f"{uf_code}{aamm}{cnpj}{modelo}{serie}{numero}{tp_emis}{c_mdf}"

        # Modulo 11
        peso = 2
        soma = 0
        for digito in reversed(chave_sem_dv):
            soma += int(digito) * peso
            peso = peso + 1 if peso < 9 else 2
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto

        self.chave_acesso = f"{chave_sem_dv}{dv}"
        return self.chave_acesso

    def add_documento(self, chave: str, tipo: str = "NFe"):
        """Adiciona documento vinculado."""
        self.documentos.append(DocumentoVinculado(chave_acesso=chave, tipo=tipo))
        if tipo == "NFe":
            self.quantidade_nfe += 1
        else:
            self.quantidade_cte += 1


class MDFeXMLBuilder:
    """Builder de XML para MDF-e versao 3.00."""

    NAMESPACE = "http://www.portalfiscal.inf.br/mdfe"
    VERSION = "3.00"

    def build_mdfe(self, mdfe: MDFe, ambiente: str = "2") -> str:
        """Constroi XML do MDF-e."""
        if not mdfe.chave_acesso:
            mdfe.generate_chave_acesso()

        root = ET.Element("MDFe", xmlns=self.NAMESPACE)
        inf = ET.SubElement(root, "infMDFe", Id=f"MDFe{mdfe.chave_acesso}", versao=self.VERSION)

        # ide - Identificacao
        ide = ET.SubElement(inf, "ide")
        uf_code = UF_CODIGO_IBGE.get(mdfe.emitente.endereco.uf, "13")
        ET.SubElement(ide, "cUF").text = uf_code
        ET.SubElement(ide, "tpAmb").text = ambiente
        ET.SubElement(ide, "tpEmit").text = mdfe.tipo_emitente.value
        ET.SubElement(ide, "tpTransp").text = (
            mdfe.tipo_transportador.value if mdfe.modal == ModalTransporte.RODOVIARIO else None
        )
        ET.SubElement(ide, "mod").text = "58"
        ET.SubElement(ide, "serie").text = str(mdfe.serie)
        ET.SubElement(ide, "nMDF").text = str(mdfe.numero)
        ET.SubElement(ide, "cMDF").text = mdfe.chave_acesso[35:43]

        # Data/hora emissao
        tz_offset = -4 if mdfe.emitente.endereco.uf == "AM" else -3
        tz_str = f"{tz_offset:+03d}:00"
        data_emissao = mdfe.data_emissao
        if data_emissao.tzinfo is None:
            data_emissao = data_emissao + timedelta(hours=tz_offset)
        ET.SubElement(ide, "dhEmi").text = data_emissao.strftime(f"%Y-%m-%dT%H:%M:%S{tz_str}")

        ET.SubElement(ide, "tpEmis").text = "1"
        ET.SubElement(ide, "procEmi").text = "0"
        ET.SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"
        ET.SubElement(ide, "UFIni").text = mdfe.uf_inicio
        ET.SubElement(ide, "UFFim").text = mdfe.uf_fim
        ET.SubElement(ide, "cDV").text = mdfe.chave_acesso[-1]
        ET.SubElement(ide, "modal").text = mdfe.modal.value

        # Data inicio viagem
        data_viagem = mdfe.data_inicio_viagem
        if data_viagem.tzinfo is None:
            data_viagem = data_viagem + timedelta(hours=tz_offset)
        ET.SubElement(ide, "dhIniViagem").text = data_viagem.strftime(f"%Y-%m-%dT%H:%M:%S{tz_str}")

        # Municipios carregamento
        for mun in mdfe.municipios_carregamento:
            inf_mun = ET.SubElement(ide, "infMunCarrega")
            ET.SubElement(inf_mun, "cMunCarrega").text = mun.codigo_ibge
            ET.SubElement(inf_mun, "xMunCarrega").text = mun.nome

        # UFs percurso
        for uf in mdfe.ufs_percurso:
            inf_percurso = ET.SubElement(ide, "infPercurso")
            ET.SubElement(inf_percurso, "UFPer").text = uf

        # emit - Emitente
        emit = ET.SubElement(inf, "emit")
        ET.SubElement(emit, "CNPJ").text = re.sub(r"[^\d]", "", mdfe.emitente.cnpj)
        ET.SubElement(emit, "IE").text = mdfe.emitente.inscricao_estadual
        if ambiente == "2":
            ET.SubElement(emit, "xNome").text = "MDF-E EMITIDO EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
        else:
            ET.SubElement(emit, "xNome").text = mdfe.emitente.razao_social
        if mdfe.emitente.nome_fantasia:
            ET.SubElement(emit, "xFant").text = mdfe.emitente.nome_fantasia
        self._add_endereco(emit, "enderEmit", mdfe.emitente.endereco)

        # infModal - Modal rodoviario
        inf_modal = ET.SubElement(inf, "infModal", versaoModal=self.VERSION)
        if mdfe.modal == ModalTransporte.RODOVIARIO:
            rodo = ET.SubElement(inf_modal, "rodo")

            # RNTRC
            inf_antt = ET.SubElement(rodo, "infANTT")
            ET.SubElement(inf_antt, "RNTRC").text = mdfe.rntrc or "00000000"

            # Veiculo tracao
            if mdfe.veiculo_tracao:
                vt = ET.SubElement(rodo, "veicTracao")
                ET.SubElement(vt, "placa").text = mdfe.veiculo_tracao.placa
                if mdfe.veiculo_tracao.renavam:
                    ET.SubElement(vt, "RENAVAM").text = mdfe.veiculo_tracao.renavam
                ET.SubElement(vt, "tara").text = str(mdfe.veiculo_tracao.tara)
                ET.SubElement(vt, "capKG").text = str(mdfe.veiculo_tracao.capacidade_kg)
                ET.SubElement(vt, "capM3").text = str(mdfe.veiculo_tracao.capacidade_m3)
                ET.SubElement(vt, "tpRod").text = mdfe.veiculo_tracao.tipo_rodado.value
                ET.SubElement(vt, "tpCar").text = mdfe.veiculo_tracao.tipo_carroceria.value
                ET.SubElement(vt, "UF").text = mdfe.veiculo_tracao.uf_licenciamento or mdfe.emitente.endereco.uf

                # Condutores
                for condutor in mdfe.condutores:
                    cond = ET.SubElement(vt, "condutor")
                    ET.SubElement(cond, "xNome").text = condutor.nome
                    ET.SubElement(cond, "CPF").text = re.sub(r"[^\d]", "", condutor.cpf)

            # Veiculos reboque
            for reboque in mdfe.veiculos_reboque:
                vr = ET.SubElement(rodo, "veicReboque")
                ET.SubElement(vr, "placa").text = reboque.placa
                ET.SubElement(vr, "tara").text = str(reboque.tara)
                ET.SubElement(vr, "capKG").text = str(reboque.capacidade_kg)
                ET.SubElement(vr, "capM3").text = str(reboque.capacidade_m3)
                ET.SubElement(vr, "tpCar").text = reboque.tipo_carroceria.value

        # infDoc - Documentos por municipio descarregamento
        inf_doc = ET.SubElement(inf, "infDoc")
        for mun_desc in mdfe.municipios_descarregamento:
            inf_mun_desc = ET.SubElement(inf_doc, "infMunDescarga")
            ET.SubElement(inf_mun_desc, "cMunDescarga").text = mun_desc.codigo_ibge
            ET.SubElement(inf_mun_desc, "xMunDescarga").text = mun_desc.nome

            # Documentos deste municipio
            for doc in mdfe.documentos:
                if doc.tipo == "NFe":
                    inf_nfe = ET.SubElement(inf_mun_desc, "infNFe")
                    ET.SubElement(inf_nfe, "chNFe").text = doc.chave_acesso
                else:
                    inf_cte = ET.SubElement(inf_mun_desc, "infCTe")
                    ET.SubElement(inf_cte, "chCTe").text = doc.chave_acesso

        # seg - Seguro (opcional)
        seg = ET.SubElement(inf, "seg")
        inf_resp = ET.SubElement(seg, "infResp")
        ET.SubElement(inf_resp, "respSeg").text = "1"  # Emitente

        # prodPred - Produto predominante
        prod_pred = ET.SubElement(inf, "prodPred")
        ET.SubElement(prod_pred, "tpCarga").text = "05"  # Carga geral
        ET.SubElement(prod_pred, "xProd").text = "CARGA DIVERSA"

        # tot - Totais
        tot = ET.SubElement(inf, "tot")
        ET.SubElement(tot, "qCTe").text = str(mdfe.quantidade_cte)
        ET.SubElement(tot, "qNFe").text = str(mdfe.quantidade_nfe)
        ET.SubElement(tot, "vCarga").text = f"{mdfe.valor_total_carga:.2f}"
        ET.SubElement(tot, "cUnid").text = "01"  # KG
        ET.SubElement(tot, "qCarga").text = f"{mdfe.peso_total_carga:.4f}"

        # infRespTec
        inf_resp_tec = ET.SubElement(inf, "infRespTec")
        ET.SubElement(inf_resp_tec, "CNPJ").text = re.sub(r"[^\d]", "", mdfe.emitente.cnpj)
        ET.SubElement(inf_resp_tec, "xContato").text = "Suporte Tecnico"
        ET.SubElement(inf_resp_tec, "email").text = "suporte@conectapro.com.br"
        ET.SubElement(inf_resp_tec, "fone").text = "92999999999"

        return self._prettify(root)

    def _add_endereco(self, parent: Element, tag: str, endereco: Endereco) -> None:
        """Adiciona endereco ao XML."""
        end = ET.SubElement(parent, tag)
        ET.SubElement(end, "xLgr").text = endereco.logradouro
        ET.SubElement(end, "nro").text = endereco.numero
        if endereco.complemento:
            ET.SubElement(end, "xCpl").text = endereco.complemento
        ET.SubElement(end, "xBairro").text = endereco.bairro
        ET.SubElement(end, "cMun").text = endereco.codigo_municipio
        ET.SubElement(end, "xMun").text = endereco.cidade
        ET.SubElement(end, "CEP").text = re.sub(r"[^\d]", "", endereco.cep)
        ET.SubElement(end, "UF").text = endereco.uf

    def _prettify(self, elem: Element) -> str:
        """Formata XML."""
        rough_string = ET.tostring(elem, encoding="unicode")
        reparsed = minidom.parseString(rough_string)  # noqa: S318 - Apenas formata XML gerado internamente
        return reparsed.toprettyxml(indent="  ")


@dataclass
class MDFeResult:
    """Resultado de operacao com MDF-e."""

    sucesso: bool
    mensagem: str
    status_code: str | None = None
    protocolo: str | None = None
    chave_acesso: str | None = None
    xml_retorno: str | None = None
    tempo_resposta: float = 0.0


class MDFeTransmitter:
    """Transmissor de MDF-e para SEFAZ."""

    NS_SOAP12 = "http://www.w3.org/2003/05/soap-envelope"
    NS_MDFE = "http://www.portalfiscal.inf.br/mdfe"
    VERSION = "3.00"

    def __init__(
        self,
        uf: str,
        ambiente: str = "2",
        cert_path: str | None = None,
        cert_password: str | None = None,
    ):
        """Inicializa o transmissor de MDF-e."""
        self.uf = uf
        self.ambiente = ambiente
        self.cert_path = cert_path
        self.cert_password = cert_password

        # MDF-e usa SVRS para todos os estados
        env_suffix = "PROD" if ambiente == "1" else "HOM"
        self.endpoints = MDFE_ENDPOINTS.get(f"SVRS_{env_suffix}")
        self.xml_builder = MDFeXMLBuilder()

        self._client = None
        self._cert_pem_path = None
        self._key_pem_path = None

        logger.info(
            f"MDFeTransmitter inicializado: UF={uf}, Ambiente={'Producao' if ambiente == '1' else 'Homologacao'}"
        )

    async def status_servico(self) -> MDFeResult:
        """Consulta status do servico."""
        start_time = time.time()

        try:
            url = self.endpoints.get("MDFeStatusServico")
            if not url:
                return MDFeResult(sucesso=False, mensagem="Endpoint nao configurado")

            UF_CODIGO_IBGE.get(self.uf, "13")
            wsdl_ns = "http://www.portalfiscal.inf.br/mdfe/wsdl/MDFeStatusServico"

            envelope = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<soap12:Envelope xmlns:soap12="{self.NS_SOAP12}">'
                f"<soap12:Body>"
                f'<mdfeDadosMsg xmlns="{wsdl_ns}">'
                f'<consStatServMDFe xmlns="{self.NS_MDFE}" versao="{self.VERSION}">'
                f"<tpAmb>{self.ambiente}</tpAmb>"
                f"<xServ>STATUS</xServ>"
                f"</consStatServMDFe>"
                f"</mdfeDadosMsg>"
                f"</soap12:Body>"
                f"</soap12:Envelope>"
            )

            client = await self._get_client()
            response = await client.post(
                url,
                content=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "application/soap+xml; charset=utf-8",
                    "SOAPAction": f"{wsdl_ns}/mdfeStatusServico",
                },
            )

            tempo = time.time() - start_time

            if response.status_code == 200:
                xml_retorno = response.text
                cstat_match = re.search(r"<cStat>(\d+)</cStat>", xml_retorno)
                xmotivo_match = re.search(r"<xMotivo>([^<]+)</xMotivo>", xml_retorno)

                cstat = cstat_match.group(1) if cstat_match else "0"
                xmotivo = xmotivo_match.group(1) if xmotivo_match else "Resposta invalida"

                return MDFeResult(
                    sucesso=cstat == "107",
                    mensagem=xmotivo,
                    status_code=cstat,
                    xml_retorno=xml_retorno,
                    tempo_resposta=tempo,
                )
            else:
                return MDFeResult(sucesso=False, mensagem=f"Erro HTTP {response.status_code}", tempo_resposta=tempo)

        except Exception as e:
            logger.error(f"Erro ao consultar status: {e}")
            return MDFeResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)

    async def transmitir(self, xml_assinado: str) -> MDFeResult:
        """Transmite MDF-e assinado para SEFAZ."""
        start_time = time.time()

        try:
            url = self.endpoints.get("MDFeRecepcaoSinc")
            if not url:
                return MDFeResult(sucesso=False, mensagem="Endpoint nao configurado")

            wsdl_ns = "http://www.portalfiscal.inf.br/mdfe/wsdl/MDFeRecepcaoSinc"
            xml_mdfe = re.sub(r"<\?xml[^>]+\?>\s*", "", xml_assinado)

            envelope = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<soap12:Envelope xmlns:soap12="{self.NS_SOAP12}">'
                f"<soap12:Body>"
                f'<mdfeDadosMsg xmlns="{wsdl_ns}">'
                f"{xml_mdfe}"
                f"</mdfeDadosMsg>"
                f"</soap12:Body>"
                f"</soap12:Envelope>"
            )

            client = await self._get_client()
            response = await client.post(
                url,
                content=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "application/soap+xml; charset=utf-8",
                    "SOAPAction": f"{wsdl_ns}/mdfeRecepcaoSinc",
                },
            )

            tempo = time.time() - start_time

            if response.status_code == 200:
                xml_retorno = response.text

                cstat_match = re.search(r"<cStat>(\d+)</cStat>", xml_retorno)
                xmotivo_match = re.search(r"<xMotivo>([^<]+)</xMotivo>", xml_retorno)
                nprot_match = re.search(r"<nProt>(\d+)</nProt>", xml_retorno)
                chave_match = re.search(r"<chMDFe>(\d{44})</chMDFe>", xml_retorno)

                cstat = cstat_match.group(1) if cstat_match else "0"
                xmotivo = xmotivo_match.group(1) if xmotivo_match else "Resposta invalida"
                protocolo = nprot_match.group(1) if nprot_match else None
                chave = chave_match.group(1) if chave_match else None

                return MDFeResult(
                    sucesso=cstat == "100",
                    mensagem=xmotivo,
                    status_code=cstat,
                    protocolo=protocolo,
                    chave_acesso=chave,
                    xml_retorno=xml_retorno,
                    tempo_resposta=tempo,
                )
            else:
                return MDFeResult(sucesso=False, mensagem=f"Erro HTTP {response.status_code}", tempo_resposta=tempo)

        except Exception as e:
            logger.error(f"Erro ao transmitir MDF-e: {e}")
            return MDFeResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)

    async def encerrar(self, chave_acesso: str, protocolo: str, codigo_municipio: str, uf: str) -> MDFeResult:
        """Registra evento de encerramento do MDF-e."""
        start_time = time.time()

        try:
            url = self.endpoints.get("MDFeRecepcaoEvento")
            if not url:
                return MDFeResult(sucesso=False, mensagem="Endpoint nao configurado")

            # Montar evento de encerramento
            wsdl_ns = "http://www.portalfiscal.inf.br/mdfe/wsdl/MDFeRecepcaoEvento"

            tz_offset = -4 if uf == "AM" else -3
            tz_str = f"{tz_offset:+03d}:00"
            dh_evento = datetime.now(timezone(timedelta(hours=tz_offset))).strftime(f"%Y-%m-%dT%H:%M:%S{tz_str}")

            evento_xml = (
                f'<eventoMDFe xmlns="{self.NS_MDFE}" versao="{self.VERSION}">'
                f'<infEvento Id="ID110111{chave_acesso}01">'
                f"<cOrgao>{UF_CODIGO_IBGE.get(uf, '13')}</cOrgao>"
                f"<tpAmb>{self.ambiente}</tpAmb>"
                f"<CNPJ>{chave_acesso[6:20]}</CNPJ>"
                f"<chMDFe>{chave_acesso}</chMDFe>"
                f"<dhEvento>{dh_evento}</dhEvento>"
                f"<tpEvento>110111</tpEvento>"
                f"<nSeqEvento>1</nSeqEvento>"
                f'<detEvento versaoEvento="{self.VERSION}">'
                f"<evEncMDFe>"
                f"<descEvento>Encerramento</descEvento>"
                f"<nProt>{protocolo}</nProt>"
                f"<dtEnc>{datetime.now().strftime('%Y-%m-%d')}</dtEnc>"
                f"<cUF>{UF_CODIGO_IBGE.get(uf, '13')}</cUF>"
                f"<cMun>{codigo_municipio}</cMun>"
                f"</evEncMDFe>"
                f"</detEvento>"
                f"</infEvento>"
                f"</eventoMDFe>"
            )

            envelope = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<soap12:Envelope xmlns:soap12="{self.NS_SOAP12}">'
                f"<soap12:Body>"
                f'<mdfeDadosMsg xmlns="{wsdl_ns}">'
                f"{evento_xml}"
                f"</mdfeDadosMsg>"
                f"</soap12:Body>"
                f"</soap12:Envelope>"
            )

            client = await self._get_client()
            response = await client.post(
                url, content=envelope.encode("utf-8"), headers={"Content-Type": "application/soap+xml; charset=utf-8"}
            )

            tempo = time.time() - start_time

            if response.status_code == 200:
                xml_retorno = response.text
                cstat_match = re.search(r"<cStat>(\d+)</cStat>", xml_retorno)
                xmotivo_match = re.search(r"<xMotivo>([^<]+)</xMotivo>", xml_retorno)

                cstat = cstat_match.group(1) if cstat_match else "0"
                xmotivo = xmotivo_match.group(1) if xmotivo_match else "Resposta invalida"

                return MDFeResult(
                    sucesso=cstat in ["135", "136"],  # Evento registrado
                    mensagem=xmotivo,
                    status_code=cstat,
                    chave_acesso=chave_acesso,
                    xml_retorno=xml_retorno,
                    tempo_resposta=tempo,
                )
            else:
                return MDFeResult(sucesso=False, mensagem=f"Erro HTTP {response.status_code}", tempo_resposta=tempo)

        except Exception as e:
            return MDFeResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)

    async def _get_client(self):
        """Obtem cliente HTTP com certificado mTLS."""
        if self._client is None:
            import tempfile

            ssl_context = ssl.create_default_context()
            # Desabilitar verificação do servidor (necessário para SEFAZ sem cadeia ICP-Brasil local)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            if self.cert_path:
                from .certificate_manager import CertificateManager

                cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
                cert_manager.load()

                with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
                    f.write(cert_manager.get_certificate_pem())
                    self._cert_pem_path = f.name

                with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
                    f.write(cert_manager.get_private_key_pem())
                    self._key_pem_path = f.name

                ssl_context.load_cert_chain(self._cert_pem_path, self._key_pem_path)

            self._client = httpx.AsyncClient(verify=ssl_context, timeout=60.0)

        return self._client

    async def close(self):
        """Fecha cliente e limpa arquivos temporarios."""
        if self._client:
            await self._client.aclose()
            self._client = None

        import os

        if self._cert_pem_path and os.path.exists(self._cert_pem_path):
            os.unlink(self._cert_pem_path)
        if self._key_pem_path and os.path.exists(self._key_pem_path):
            os.unlink(self._key_pem_path)


logger.info("Modulo MDFeManager carregado")
