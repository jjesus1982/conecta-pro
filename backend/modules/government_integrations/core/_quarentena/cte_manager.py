"""
Module: CTEManager
Description: Sistema de emissao de CT-e (Conhecimento de Transporte Eletronico)
             Modelo 57 - Transporte de cargas
             Versao 4.00 (sincrono)
Author: Conecta PRO
Date: 2026-01-17

Portal: https://www.cte.fazenda.gov.br
Documentacao: https://www.cte.fazenda.gov.br/portal/documentos.aspx

CT-e 4.00:
- Webservice sincrono (CTeRecepcaoSinc)
- XML versao 4.00
- Assinatura digital obrigatoria
"""

import logging
import re
import ssl
import time
import xml.etree.ElementTree as ET  # noqa: N817, S405
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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


# Endpoints CT-e por autorizador
CTE_ENDPOINTS = {
    # SVRS - Sefaz Virtual do RS (AM, AC, AL, BA, CE, DF, ES, GO, MA, PA, PB, PI, RJ, RN, RO, SC, SE, TO)
    "SVRS_PROD": {
        "CTeRecepcaoSinc": "https://cte.svrs.rs.gov.br/ws/CTeRecepcaoSincV4/CTeRecepcaoSincV4.asmx",
        "CTeRecepcaoGTVe": "https://cte.svrs.rs.gov.br/ws/CTeRecepcaoGTVeV4/CTeRecepcaoGTVeV4.asmx",
        "CTeRecepcaoOS": "https://cte.svrs.rs.gov.br/ws/CTeRecepcaoOSV4/CTeRecepcaoOSV4.asmx",
        "CTeConsulta": "https://cte.svrs.rs.gov.br/ws/CTeConsultaV4/CTeConsultaV4.asmx",
        "CTeStatusServico": "https://cte.svrs.rs.gov.br/ws/CTeStatusServicoV4/CTeStatusServicoV4.asmx",
        "CTeRecepcaoEvento": "https://cte.svrs.rs.gov.br/ws/CTeRecepcaoEventoV4/CTeRecepcaoEventoV4.asmx",
        "CTeDistribuicaoDFe": "https://cte.svrs.rs.gov.br/ws/CTeDistribuicaoDFeV4/CTeDistribuicaoDFeV4.asmx",
    },
    "SVRS_HOM": {
        "CTeRecepcaoSinc": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeRecepcaoSincV4/CTeRecepcaoSincV4.asmx",
        "CTeRecepcaoGTVe": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeRecepcaoGTVeV4/CTeRecepcaoGTVeV4.asmx",
        "CTeRecepcaoOS": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeRecepcaoOSV4/CTeRecepcaoOSV4.asmx",
        "CTeConsulta": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeConsultaV4/CTeConsultaV4.asmx",
        "CTeStatusServico": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeStatusServicoV4/CTeStatusServicoV4.asmx",
        "CTeRecepcaoEvento": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeRecepcaoEventoV4/CTeRecepcaoEventoV4.asmx",
        "CTeDistribuicaoDFe": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeDistribuicaoDFeV4/CTeDistribuicaoDFeV4.asmx",
    },
    # SVSP - Sefaz Virtual de SP (AP, PE, RR)
    "SVSP_PROD": {
        "CTeRecepcaoSinc": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRecepcaoSincV4.asmx",
        "CTeConsulta": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeConsultaV4.asmx",
        "CTeStatusServico": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeStatusServicoV4.asmx",
        "CTeRecepcaoEvento": "https://nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRecepcaoEventoV4.asmx",
    },
    "SVSP_HOM": {
        "CTeRecepcaoSinc": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRecepcaoSincV4.asmx",
        "CTeConsulta": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeConsultaV4.asmx",
        "CTeStatusServico": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeStatusServicoV4.asmx",
        "CTeRecepcaoEvento": "https://homologacao.nfe.fazenda.sp.gov.br/CTeWS/WS/CTeRecepcaoEventoV4.asmx",
    },
    # SVC-RS - Contingencia para estados SVSP, MT, MS, SP
    "SVC_RS_PROD": {
        "CTeRecepcaoSinc": "https://cte.svrs.rs.gov.br/ws/CTeRecepcaoSincSVCV4/CTeRecepcaoSincSVCV4.asmx",
    },
    "SVC_RS_HOM": {
        "CTeRecepcaoSinc": "https://cte-homologacao.svrs.rs.gov.br/ws/CTeRecepcaoSincSVCV4/CTeRecepcaoSincSVCV4.asmx",
    },
}

# Mapeamento UF -> Autorizador
UF_AUTORIZADOR_CTE = {
    "AC": "SVRS",
    "AL": "SVRS",
    "AM": "SVRS",
    "AP": "SVSP",
    "BA": "SVRS",
    "CE": "SVRS",
    "DF": "SVRS",
    "ES": "SVRS",
    "GO": "SVRS",
    "MA": "SVRS",
    "MG": "MG",
    "MS": "MS",
    "MT": "MT",
    "PA": "SVRS",
    "PB": "SVRS",
    "PE": "SVSP",
    "PI": "SVRS",
    "PR": "PR",
    "RJ": "SVRS",
    "RN": "SVRS",
    "RO": "SVRS",
    "RR": "SVSP",
    "RS": "RS",
    "SC": "SVRS",
    "SE": "SVRS",
    "SP": "SP",
    "TO": "SVRS",
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


class TipoCTe(StrEnum):
    """Tipo de CT-e."""

    NORMAL = "0"  # Normal
    COMPLEMENTO_VALORES = "1"  # CT-e de Complemento de Valores
    ANULACAO = "2"  # CT-e de Anulacao
    SUBSTITUTO = "3"  # CT-e Substituto


class ModalTransporte(StrEnum):
    """Modal de transporte."""

    RODOVIARIO = "01"
    AEREO = "02"
    AQUAVIARIO = "03"
    FERROVIARIO = "04"
    DUTOVIARIO = "05"
    MULTIMODAL = "06"


class TipoServico(StrEnum):
    """Tipo de servico de transporte."""

    NORMAL = "0"
    SUBCONTRATACAO = "1"
    REDESPACHO = "2"
    REDESPACHO_INTERMEDIARIO = "3"
    VINCULADO_MULTIMODAL = "4"


class TomadorServico(StrEnum):
    """Tomador do servico."""

    REMETENTE = "0"
    EXPEDIDOR = "1"
    RECEBEDOR = "2"
    DESTINATARIO = "3"
    OUTROS = "4"


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
    pais: str = "Brasil"
    codigo_pais: str = "1058"


@dataclass
class Emitente:
    """Dados do emitente do CT-e."""

    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    inscricao_estadual: str
    endereco: Endereco
    rntrc: str | None = None  # Registro Nacional de Transportadores Rodoviarios


@dataclass
class Remetente:
    """Dados do remetente (quem envia a carga)."""

    cpf_cnpj: str
    razao_social: str
    endereco: Endereco
    inscricao_estadual: str | None = None
    email: str | None = None
    telefone: str | None = None

    @property
    def is_cpf(self) -> bool:
        return len(re.sub(r"[^\d]", "", self.cpf_cnpj)) == 11


@dataclass
class Destinatario:
    """Dados do destinatario (quem recebe a carga)."""

    cpf_cnpj: str
    razao_social: str
    endereco: Endereco
    inscricao_estadual: str | None = None
    email: str | None = None
    telefone: str | None = None

    @property
    def is_cpf(self) -> bool:
        return len(re.sub(r"[^\d]", "", self.cpf_cnpj)) == 11


@dataclass
class Carga:
    """Dados da carga transportada."""

    valor_carga: Decimal
    produto_predominante: str
    quantidade: Decimal = Decimal("1")
    unidade: str = "UN"
    peso_bruto: Decimal | None = None
    peso_liquido: Decimal | None = None
    cubagem: Decimal | None = None  # m3
    caracteristica_adicional: str | None = None


@dataclass
class ComponenteValor:
    """Componente do valor do frete."""

    nome: str  # Ex: "FRETE PESO", "GRIS", "PEDÁGIO"
    valor: Decimal


@dataclass
class CTe:
    """Conhecimento de Transporte Eletronico."""

    id: UUID = field(default_factory=uuid4)
    numero: int = 0
    serie: int = 1
    tipo: TipoCTe = TipoCTe.NORMAL
    modal: ModalTransporte = ModalTransporte.RODOVIARIO
    tipo_servico: TipoServico = TipoServico.NORMAL
    tomador: TomadorServico = TomadorServico.REMETENTE

    emitente: Emitente = None
    remetente: Remetente = None
    destinatario: Destinatario = None

    carga: Carga = None
    componentes_frete: list[ComponenteValor] = field(default_factory=list)

    # Locais
    municipio_inicio: str = ""  # Codigo IBGE
    municipio_fim: str = ""  # Codigo IBGE
    uf_inicio: str = ""
    uf_fim: str = ""

    # Valores
    valor_total_servico: Decimal = Decimal("0")
    valor_receber: Decimal = Decimal("0")
    valor_icms: Decimal = Decimal("0")
    base_calculo_icms: Decimal = Decimal("0")
    aliquota_icms: Decimal = Decimal("0")

    # Datas
    data_emissao: datetime = None
    data_previsao_entrega: datetime | None = None

    # Chave de acesso
    chave_acesso: str | None = None

    # Protocolo
    protocolo: str | None = None
    status: str = "draft"

    def __post_init__(self):
        if self.data_emissao is None:
            self.data_emissao = datetime.now(UTC)

    def generate_chave_acesso(self) -> str:
        """Gera a chave de acesso do CT-e (44 digitos)."""
        # Formato: UF(2) + AAMM(4) + CNPJ(14) + Modelo(2) + Serie(3) + Numero(9) + tpEmis(1) + cCT(8) + DV(1)
        uf_code = UF_CODIGO_IBGE.get(self.emitente.endereco.uf, "13")
        aamm = self.data_emissao.strftime("%y%m")
        cnpj = re.sub(r"[^\d]", "", self.emitente.cnpj).zfill(14)
        modelo = "57"
        serie = str(self.serie).zfill(3)
        numero = str(self.numero).zfill(9)
        tp_emis = "1"  # Normal
        c_ct = str(hash(f"{self.id}") % 100000000).zfill(8)

        chave_sem_dv = f"{uf_code}{aamm}{cnpj}{modelo}{serie}{numero}{tp_emis}{c_ct}"

        # Calculo do digito verificador (modulo 11)
        peso = 2
        soma = 0
        for digito in reversed(chave_sem_dv):
            soma += int(digito) * peso
            peso = peso + 1 if peso < 9 else 2
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto

        self.chave_acesso = f"{chave_sem_dv}{dv}"
        return self.chave_acesso


class CTeXMLBuilder:
    """Builder de XML para CT-e versao 4.00."""

    NAMESPACE = "http://www.portalfiscal.inf.br/cte"
    VERSION = "4.00"

    def build_cte(self, cte: CTe, ambiente: str = "2") -> str:
        """
        Constroi XML do CT-e.

        Args:
            cte: Dados do CT-e
            ambiente: 1=Producao, 2=Homologacao

        Returns:
            XML do CT-e
        """
        if not cte.chave_acesso:
            cte.generate_chave_acesso()

        root = ET.Element("CTe", xmlns=self.NAMESPACE)
        inf = ET.SubElement(root, "infCte", Id=f"CTe{cte.chave_acesso}", versao=self.VERSION)

        # ide - Identificacao
        ide = ET.SubElement(inf, "ide")
        uf_code = UF_CODIGO_IBGE.get(cte.emitente.endereco.uf, "13")
        ET.SubElement(ide, "cUF").text = uf_code
        ET.SubElement(ide, "cCT").text = cte.chave_acesso[35:43]
        ET.SubElement(ide, "CFOP").text = "6352"  # Transporte interestadual
        ET.SubElement(ide, "natOp").text = "PRESTACAO DE SERVICO DE TRANSPORTE"
        ET.SubElement(ide, "mod").text = "57"
        ET.SubElement(ide, "serie").text = str(cte.serie)
        ET.SubElement(ide, "nCT").text = str(cte.numero)

        # Data/hora emissao
        tz_offset = -4 if cte.emitente.endereco.uf == "AM" else -3
        tz_str = f"{tz_offset:+03d}:00"
        data_emissao = cte.data_emissao
        if data_emissao.tzinfo is None:
            data_emissao = data_emissao + timedelta(hours=tz_offset)
        ET.SubElement(ide, "dhEmi").text = data_emissao.strftime(f"%Y-%m-%dT%H:%M:%S{tz_str}")

        ET.SubElement(ide, "tpImp").text = "1"  # Retrato
        ET.SubElement(ide, "tpEmis").text = "1"  # Normal
        ET.SubElement(ide, "cDV").text = cte.chave_acesso[-1]
        ET.SubElement(ide, "tpAmb").text = ambiente
        ET.SubElement(ide, "tpCTe").text = cte.tipo.value
        ET.SubElement(ide, "procEmi").text = "0"
        ET.SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"
        ET.SubElement(ide, "cMunEnv").text = cte.emitente.endereco.codigo_municipio
        ET.SubElement(ide, "xMunEnv").text = cte.emitente.endereco.cidade
        ET.SubElement(ide, "UFEnv").text = cte.emitente.endereco.uf
        ET.SubElement(ide, "modal").text = cte.modal.value
        ET.SubElement(ide, "tpServ").text = cte.tipo_servico.value
        ET.SubElement(ide, "cMunIni").text = cte.municipio_inicio
        ET.SubElement(ide, "xMunIni").text = "MUNICIPIO ORIGEM"
        ET.SubElement(ide, "UFIni").text = cte.uf_inicio
        ET.SubElement(ide, "cMunFim").text = cte.municipio_fim
        ET.SubElement(ide, "xMunFim").text = "MUNICIPIO DESTINO"
        ET.SubElement(ide, "UFFim").text = cte.uf_fim
        ET.SubElement(ide, "retira").text = "0"
        ET.SubElement(ide, "indIEToma").text = "1"  # Contribuinte ICMS
        ET.SubElement(ide, "toma3")
        toma3 = ide.find("toma3")
        ET.SubElement(toma3, "toma").text = cte.tomador.value

        # compl - Complemento (opcional)
        compl = ET.SubElement(inf, "compl")
        ET.SubElement(compl, "xObs").text = "CT-e emitido pelo sistema Conecta PRO"

        # emit - Emitente
        emit = ET.SubElement(inf, "emit")
        ET.SubElement(emit, "CNPJ").text = re.sub(r"[^\d]", "", cte.emitente.cnpj)
        ET.SubElement(emit, "IE").text = cte.emitente.inscricao_estadual
        if ambiente == "2":
            ET.SubElement(emit, "xNome").text = "CT-E EMITIDO EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
        else:
            ET.SubElement(emit, "xNome").text = cte.emitente.razao_social
        if cte.emitente.nome_fantasia:
            ET.SubElement(emit, "xFant").text = cte.emitente.nome_fantasia
        self._add_endereco(emit, "enderEmit", cte.emitente.endereco)

        # rem - Remetente
        if cte.remetente:
            rem = ET.SubElement(inf, "rem")
            doc = re.sub(r"[^\d]", "", cte.remetente.cpf_cnpj)
            if cte.remetente.is_cpf:
                ET.SubElement(rem, "CPF").text = doc
            else:
                ET.SubElement(rem, "CNPJ").text = doc
            if cte.remetente.inscricao_estadual:
                ET.SubElement(rem, "IE").text = cte.remetente.inscricao_estadual
            ET.SubElement(rem, "xNome").text = cte.remetente.razao_social
            self._add_endereco(rem, "enderReme", cte.remetente.endereco)

        # dest - Destinatario
        if cte.destinatario:
            dest = ET.SubElement(inf, "dest")
            doc = re.sub(r"[^\d]", "", cte.destinatario.cpf_cnpj)
            if cte.destinatario.is_cpf:
                ET.SubElement(dest, "CPF").text = doc
            else:
                ET.SubElement(dest, "CNPJ").text = doc
            if cte.destinatario.inscricao_estadual:
                ET.SubElement(dest, "IE").text = cte.destinatario.inscricao_estadual
            ET.SubElement(dest, "xNome").text = cte.destinatario.razao_social
            self._add_endereco(dest, "enderDest", cte.destinatario.endereco)

        # vPrest - Valores da prestacao
        v_prest = ET.SubElement(inf, "vPrest")
        ET.SubElement(v_prest, "vTPrest").text = f"{cte.valor_total_servico:.2f}"
        ET.SubElement(v_prest, "vRec").text = f"{cte.valor_receber:.2f}"
        for comp in cte.componentes_frete:
            comp_elem = ET.SubElement(v_prest, "Comp")
            ET.SubElement(comp_elem, "xNome").text = comp.nome
            ET.SubElement(comp_elem, "vComp").text = f"{comp.valor:.2f}"

        # imp - Impostos
        imp = ET.SubElement(inf, "imp")
        icms = ET.SubElement(imp, "ICMS")
        icms00 = ET.SubElement(icms, "ICMS00")
        ET.SubElement(icms00, "CST").text = "00"
        ET.SubElement(icms00, "vBC").text = f"{cte.base_calculo_icms:.2f}"
        ET.SubElement(icms00, "pICMS").text = f"{cte.aliquota_icms:.2f}"
        ET.SubElement(icms00, "vICMS").text = f"{cte.valor_icms:.2f}"

        # infCTeNorm - Informacoes do CT-e Normal
        inf_cte_norm = ET.SubElement(inf, "infCTeNorm")

        # infCarga - Dados da carga
        if cte.carga:
            inf_carga = ET.SubElement(inf_cte_norm, "infCarga")
            ET.SubElement(inf_carga, "vCarga").text = f"{cte.carga.valor_carga:.2f}"
            ET.SubElement(inf_carga, "proPred").text = cte.carga.produto_predominante
            if cte.carga.caracteristica_adicional:
                ET.SubElement(inf_carga, "xOutCat").text = cte.carga.caracteristica_adicional
            inf_q = ET.SubElement(inf_carga, "infQ")
            ET.SubElement(inf_q, "cUnid").text = "01"  # KG
            ET.SubElement(inf_q, "tpMed").text = "PESO BRUTO"
            ET.SubElement(inf_q, "qCarga").text = f"{cte.carga.peso_bruto or cte.carga.quantidade:.4f}"

        # infModal - Dados do modal
        inf_modal = ET.SubElement(inf_cte_norm, "infModal", versaoModal=self.VERSION)
        if cte.modal == ModalTransporte.RODOVIARIO:
            rodo = ET.SubElement(inf_modal, "rodo")
            ET.SubElement(rodo, "RNTRC").text = cte.emitente.rntrc or "00000000"

        # infRespTec - Responsavel tecnico
        inf_resp = ET.SubElement(inf, "infRespTec")
        ET.SubElement(inf_resp, "CNPJ").text = re.sub(r"[^\d]", "", cte.emitente.cnpj)
        ET.SubElement(inf_resp, "xContato").text = "Suporte Tecnico"
        ET.SubElement(inf_resp, "email").text = "suporte@conectapro.com.br"
        ET.SubElement(inf_resp, "fone").text = "92999999999"

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
class CTeResult:
    """Resultado de operacao com CT-e."""

    sucesso: bool
    mensagem: str
    status_code: str | None = None
    protocolo: str | None = None
    chave_acesso: str | None = None
    xml_retorno: str | None = None
    tempo_resposta: float = 0.0


class CTeTransmitter:
    """Transmissor de CT-e para SEFAZ."""

    NS_SOAP12 = "http://www.w3.org/2003/05/soap-envelope"
    NS_CTE = "http://www.portalfiscal.inf.br/cte"
    VERSION = "4.00"

    def __init__(
        self,
        uf: str,
        ambiente: str = "2",
        cert_path: str | None = None,
        cert_password: str | None = None,
    ):
        """
        Inicializa o transmissor de CT-e.

        Args:
            uf: UF do emitente
            ambiente: 1=Producao, 2=Homologacao
            cert_path: Caminho do certificado PFX
            cert_password: Senha do certificado
        """
        self.uf = uf
        self.ambiente = ambiente
        self.cert_path = cert_path
        self.cert_password = cert_password

        # Determinar autorizador
        autorizador = UF_AUTORIZADOR_CTE.get(uf, "SVRS")
        env_suffix = "PROD" if ambiente == "1" else "HOM"
        endpoint_key = f"{autorizador}_{env_suffix}"

        # Para autorizadores proprios, usar SVRS como fallback
        if endpoint_key not in CTE_ENDPOINTS:
            endpoint_key = f"SVRS_{env_suffix}"

        self.endpoints = CTE_ENDPOINTS.get(endpoint_key, CTE_ENDPOINTS[f"SVRS_{env_suffix}"])
        self.xml_builder = CTeXMLBuilder()

        self._client = None
        self._cert_pem_path = None
        self._key_pem_path = None

        logger.info(
            f"CTeTransmitter inicializado: UF={uf}, Autorizador={autorizador}, Ambiente={'Producao' if ambiente == '1' else 'Homologacao'}"
        )

    def get_endpoint(self, service: str) -> str:
        """Retorna endpoint do servico."""
        return self.endpoints.get(service, "")

    async def status_servico(self) -> CTeResult:
        """Consulta status do servico."""
        start_time = time.time()

        try:
            url = self.get_endpoint("CTeStatusServico")
            if not url:
                return CTeResult(sucesso=False, mensagem="Endpoint nao configurado")

            cod_uf = UF_CODIGO_IBGE.get(self.uf, "13")
            wsdl_ns = "http://www.portalfiscal.inf.br/cte/wsdl/CTeStatusServicoV4"

            envelope = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<soap12:Envelope xmlns:soap12="{self.NS_SOAP12}">'
                f"<soap12:Body>"
                f'<cteDadosMsg xmlns="{wsdl_ns}">'
                f'<consStatServCTe xmlns="{self.NS_CTE}" versao="{self.VERSION}">'
                f"<tpAmb>{self.ambiente}</tpAmb>"
                f"<cUF>{cod_uf}</cUF>"
                f"<xServ>STATUS</xServ>"
                f"</consStatServCTe>"
                f"</cteDadosMsg>"
                f"</soap12:Body>"
                f"</soap12:Envelope>"
            )

            client = await self._get_client()
            response = await client.post(
                url,
                content=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "application/soap+xml; charset=utf-8",
                    "SOAPAction": f"{wsdl_ns}/cteStatusServicoCT",
                },
            )

            tempo = time.time() - start_time

            if response.status_code == 200:
                # Parse response
                xml_retorno = response.text
                # Extrair cStat e xMotivo
                import re

                cstat_match = re.search(r"<cStat>(\d+)</cStat>", xml_retorno)
                xmotivo_match = re.search(r"<xMotivo>([^<]+)</xMotivo>", xml_retorno)

                cstat = cstat_match.group(1) if cstat_match else "0"
                xmotivo = xmotivo_match.group(1) if xmotivo_match else "Resposta invalida"

                return CTeResult(
                    sucesso=cstat == "107",
                    mensagem=xmotivo,
                    status_code=cstat,
                    xml_retorno=xml_retorno,
                    tempo_resposta=tempo,
                )
            else:
                return CTeResult(sucesso=False, mensagem=f"Erro HTTP {response.status_code}", tempo_resposta=tempo)

        except Exception as e:
            logger.error(f"Erro ao consultar status: {e}")
            return CTeResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)

    async def transmitir(self, xml_assinado: str) -> CTeResult:
        """
        Transmite CT-e assinado para SEFAZ.

        Args:
            xml_assinado: XML do CT-e assinado

        Returns:
            Resultado da transmissao
        """
        start_time = time.time()

        try:
            url = self.get_endpoint("CTeRecepcaoSinc")
            if not url:
                return CTeResult(sucesso=False, mensagem="Endpoint nao configurado")

            wsdl_ns = "http://www.portalfiscal.inf.br/cte/wsdl/CTeRecepcaoSincV4"

            # Extrair apenas o conteudo do CT-e (sem declaracao XML)
            xml_cte = re.sub(r"<\?xml[^>]+\?>\s*", "", xml_assinado)

            envelope = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<soap12:Envelope xmlns:soap12="{self.NS_SOAP12}">'
                f"<soap12:Body>"
                f'<cteDadosMsg xmlns="{wsdl_ns}">'
                f"{xml_cte}"
                f"</cteDadosMsg>"
                f"</soap12:Body>"
                f"</soap12:Envelope>"
            )

            client = await self._get_client()
            response = await client.post(
                url,
                content=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "application/soap+xml; charset=utf-8",
                    "SOAPAction": f"{wsdl_ns}/cteRecepcaoSinc",
                },
            )

            tempo = time.time() - start_time

            if response.status_code == 200:
                xml_retorno = response.text

                # Parse resultado
                cstat_match = re.search(r"<cStat>(\d+)</cStat>", xml_retorno)
                xmotivo_match = re.search(r"<xMotivo>([^<]+)</xMotivo>", xml_retorno)
                nprot_match = re.search(r"<nProt>(\d+)</nProt>", xml_retorno)
                chave_match = re.search(r"<chCTe>(\d{44})</chCTe>", xml_retorno)

                cstat = cstat_match.group(1) if cstat_match else "0"
                xmotivo = xmotivo_match.group(1) if xmotivo_match else "Resposta invalida"
                protocolo = nprot_match.group(1) if nprot_match else None
                chave = chave_match.group(1) if chave_match else None

                sucesso = cstat == "100"  # Autorizado

                return CTeResult(
                    sucesso=sucesso,
                    mensagem=xmotivo,
                    status_code=cstat,
                    protocolo=protocolo,
                    chave_acesso=chave,
                    xml_retorno=xml_retorno,
                    tempo_resposta=tempo,
                )
            else:
                return CTeResult(sucesso=False, mensagem=f"Erro HTTP {response.status_code}", tempo_resposta=tempo)

        except Exception as e:
            logger.error(f"Erro ao transmitir CT-e: {e}")
            return CTeResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)

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


logger.info("Modulo CTEManager carregado")
