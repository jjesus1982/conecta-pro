"""
Module: eSocialTransmitter
Description: Sistema de transmissao de eventos para eSocial (Sistema de Escrituracao
             Digital das Obrigacoes Fiscais, Previdenciarias e Trabalhistas).
Author: Claude AI + Human Developer
Date: 2026-01-10
Quality Score Target: 99+/100
Compliance: Decreto 8.373/2014 - eSocial
"""

import logging
import os
import re as re_module
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4
from xml.dom import minidom  # noqa: S408
from xml.etree.ElementTree import Element, SubElement  # noqa: S405

import defusedxml.ElementTree as ET  # noqa: N817
import requests as http_requests
from sqlalchemy import Column, Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base

# Importa gerenciador de certificados e assinador XML
from .certificate_manager import CertificateManager
from .xml_signer import ESocialXMLSigner

logger = logging.getLogger(__name__)

Base = declarative_base()


class EventType(StrEnum):
    """Tipos de eventos eSocial."""

    # Eventos de Tabelas (S-1000 a S-1080)
    S1000_EMPREGADOR = "S-1000"  # Informacoes do Empregador
    S1005_ESTABELECIMENTOS = "S-1005"  # Tabela de Estabelecimentos
    S1010_RUBRICAS = "S-1010"  # Tabela de Rubricas
    S1020_LOTACOES = "S-1020"  # Tabela de Lotacoes Tributarias
    S1030_CARGOS = "S-1030"  # Tabela de Cargos/Empregos
    S1035_CARREIRAS = "S-1035"  # Tabela de Carreiras Publicas
    S1040_FUNCOES = "S-1040"  # Tabela de Funcoes
    S1050_HORARIOS = "S-1050"  # Tabela de Horarios
    S1060_AMBIENTES = "S-1060"  # Tabela de Ambientes de Trabalho
    S1070_PROCESSOS = "S-1070"  # Tabela de Processos Administrativos

    # Eventos Nao Periodicos (S-2190 a S-2420)
    S2190_ADMISSAO_PRELIMINAR = "S-2190"  # Registro Preliminar de Admissao
    S2200_ADMISSAO = "S-2200"  # Cadastramento Inicial/Admissao
    S2205_ALTERACAO_DADOS = "S-2205"  # Alteracao de Dados Cadastrais
    S2206_ALTERACAO_CONTRATO = "S-2206"  # Alteracao de Contrato de Trabalho
    S2210_CAT = "S-2210"  # Comunicacao de Acidente de Trabalho
    S2220_MONITORAMENTO_SAUDE = "S-2220"  # Monitoramento da Saude do Trabalhador
    S2230_AFASTAMENTO = "S-2230"  # Afastamento Temporario
    S2240_EXPOSICAO_RISCOS = "S-2240"  # Condicoes Ambientais do Trabalho
    S2299_DESLIGAMENTO = "S-2299"  # Desligamento
    S2300_TSV_INICIO = "S-2300"  # Trabalhador Sem Vinculo - Inicio
    S2306_TSV_ALTERACAO = "S-2306"  # TSV - Alteracao Contratual
    S2399_TSV_TERMINO = "S-2399"  # TSV - Termino

    # Eventos Periodicos (S-1200 a S-1299)
    S1200_REMUNERACAO = "S-1200"  # Remuneracao do Trabalhador
    S1202_REMUNERACAO_RPPS = "S-1202"  # Remuneracao Servidor RPPS
    S1207_BENEFICIOS_PREVIDENCIARIOS = "S-1207"  # Beneficios Previdenciarios
    S1210_PAGAMENTOS = "S-1210"  # Pagamentos de Rendimentos
    S1260_COMERCIALIZACAO = "S-1260"  # Comercializacao Producao Rural
    S1270_AQUISICAO = "S-1270"  # Contratacao de Trabalhadores Avulsos
    S1280_INFO_DESONERADA = "S-1280"  # Informacoes Complementares Desonerada
    S1298_REABERTURA = "S-1298"  # Reabertura dos Eventos Periodicos
    S1299_FECHAMENTO = "S-1299"  # Fechamento dos Eventos Periodicos

    # Eventos de SST (S-2210 a S-2240 - ja listados acima)
    # Eventos Totalizadores
    S5001_BASES_IRRF = "S-5001"  # Bases de Calculo IRRF
    S5002_BASES_CS = "S-5002"  # Imposto de Renda Retido na Fonte
    S5003_BASES_FGTS = "S-5003"  # Bases de Calculo FGTS
    S5011_TOTAL_CONTRIB = "S-5011"  # Consolidacao de Contribuicoes
    S5012_TOTAL_IRRF = "S-5012"  # Consolidacao IRRF

    # Exclusao
    S3000_EXCLUSAO = "S-3000"  # Exclusao de Eventos


class TransmissionStatus(StrEnum):
    """Status de transmissao de evento."""

    PENDING = "pending"  # Aguardando envio
    VALIDATING = "validating"  # Em validacao
    TRANSMITTED = "transmitted"  # Transmitido
    PROCESSING = "processing"  # Em processamento no governo
    ACCEPTED = "accepted"  # Aceito
    REJECTED = "rejected"  # Rejeitado
    ERROR = "error"  # Erro na transmissao
    CANCELLED = "cancelled"  # Cancelado


class Environment(StrEnum):
    """Ambiente de transmissao."""

    PRODUCAO = "1"
    PRODUCAO_RESTRITA = "2"  # Homologacao


def resolve_environment(ambiente: str | None = None) -> "Environment":
    """Resolve o ambiente eSocial a partir de parâmetro explícito ou da env ESOCIAL_AMBIENTE.

    Valores aceitos: "producao" (ou "prod"/"1") => PRODUCAO;
    qualquer outro valor (inclui "producaorestrita", "homologacao", "2", vazio)
    => PRODUCAO_RESTRITA.

    REGRA DE SEGURANÇA: o default é SEMPRE producaorestrita — NUNCA produção
    por omissão. A virada para produção é explícita: ESOCIAL_AMBIENTE=producao.
    """
    valor = (ambiente or os.getenv("ESOCIAL_AMBIENTE") or "producaorestrita").strip().lower()
    if valor in ("producao", "producao_real", "prod", "1"):
        return Environment.PRODUCAO
    return Environment.PRODUCAO_RESTRITA


class ESocialError(Exception):
    """Erro em operacao eSocial."""

    def __init__(self, message: str, event_id: str | None = None, code: str | None = None):
        self.message = message
        self.event_id = event_id
        self.code = code
        super().__init__(self.message)


class ValidationError(ESocialError):
    """Erro de validacao de evento."""

    pass


class TransmissionError(ESocialError):
    """Erro de transmissao."""

    pass


@dataclass
class CertificateInfo:
    """Informacoes do certificado digital."""

    serial_number: str
    subject_cn: str
    issuer_cn: str
    valid_from: datetime
    valid_until: datetime
    type: str  # A1, A3

    def is_valid(self) -> bool:
        """Verifica se certificado esta valido."""
        now = datetime.utcnow()
        return self.valid_from <= now <= self.valid_until

    def days_until_expiry(self) -> int:
        """Dias ate vencimento."""
        return (self.valid_until - datetime.utcnow()).days


@dataclass
class ESocialEvent:
    """Evento eSocial."""

    id: UUID
    event_type: EventType
    status: TransmissionStatus
    employer_cnpj: str
    employee_cpf: str | None = None
    xml_content: str | None = None
    xml_signed: str | None = None
    protocol: str | None = None
    receipt_number: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    transmitted_at: datetime | None = None
    processed_at: datetime | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    reference_id: str | None = None  # ID de referencia no sistema
    reference_date: date | None = None  # Data de referencia do evento
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "event_type": self.event_type.value,
            "status": self.status.value,
            "employer_cnpj": self.employer_cnpj,
            "employee_cpf": self.employee_cpf,
            "protocol": self.protocol,
            "receipt_number": self.receipt_number,
            "created_at": self.created_at.isoformat(),
            "transmitted_at": self.transmitted_at.isoformat() if self.transmitted_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# SQLAlchemy Model
class ESocialEventModel(Base):
    """Modelo de banco para eventos eSocial."""

    __tablename__ = "gov_esocial_events"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_type = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    employer_cnpj = Column(String(18), nullable=False, index=True)
    employee_cpf = Column(String(14), nullable=True, index=True)
    xml_content = Column(Text, nullable=True)
    xml_signed = Column(Text, nullable=True)
    protocol = Column(String(100), nullable=True, index=True)
    receipt_number = Column(String(100), nullable=True, unique=True)
    reference_id = Column(String(100), nullable=True, index=True)
    reference_date = Column(Date, nullable=True, index=True)
    errors = Column(JSONB, default=[])
    warnings = Column(JSONB, default=[])
    extra_metadata = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    transmitted_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class XMLBuilder:
    """Construtor de XML para eventos eSocial."""

    NAMESPACE = "http://www.esocial.gov.br/schema/evt"
    VERSION = "S_1.1.0"  # Versao do layout

    def __init__(self, environment: Environment = Environment.PRODUCAO_RESTRITA):
        self.environment = environment

    def build_event_id(self, event_type: str, employer_cnpj: str) -> str:
        """Gera ID unico do evento (exatamente 36 chars conforme XSD eSocial).

        Formato: ID(2) + tpInsc(1) + nrInsc(14, raiz CNPJ padded) + AAAAMMDDHHMMSS(14) + seq(5) = 36
        IMPORTANTE: nrInsc usa raiz CNPJ (8 dígitos) padded com zeros até 14.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        seq = uuid4().int % 100000  # noqa: S311
        seq_str = f"{seq:05d}"
        cnpj_clean = employer_cnpj.replace(".", "").replace("/", "").replace("-", "")
        # Raiz do CNPJ (8 primeiros dígitos) padded com zeros até 14
        cnpj_raiz = cnpj_clean[:8].ljust(14, "0")
        return f"ID1{cnpj_raiz}{timestamp}{seq_str}"

    def build_s2200_admissao(self, data: dict[str, Any]) -> str:
        """Constroi XML do evento S-2200 (Admissao)."""
        event_id = self.build_event_id("S-2200", data["employer_cnpj"])

        root = Element("eSocial", xmlns=self.NAMESPACE)
        evt = SubElement(root, "evtAdmissao", Id=event_id)

        # ideEvento
        ide = SubElement(evt, "ideEvento")
        SubElement(ide, "indRetif").text = str(data.get("indRetif", 1))
        SubElement(ide, "tpAmb").text = self.environment.value
        SubElement(ide, "procEmi").text = "1"
        SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        # ideEmpregador
        emp = SubElement(evt, "ideEmpregador")
        SubElement(emp, "tpInsc").text = "1"
        SubElement(emp, "nrInsc").text = data["employer_cnpj"][:8]

        # trabalhador
        trab = SubElement(evt, "trabalhador")
        SubElement(trab, "cpfTrab").text = data["cpf"]
        SubElement(trab, "nmTrab").text = data["nome"]
        SubElement(trab, "sexo").text = data["sexo"]
        SubElement(trab, "racaCor").text = str(data.get("racaCor", 6))
        SubElement(trab, "estCiv").text = str(data.get("estCiv", 1))
        SubElement(trab, "grauInstr").text = str(data.get("grauInstr", "07"))

        # nascimento
        nasc = SubElement(trab, "nascimento")
        SubElement(nasc, "dtNascto").text = data["dtNascimento"]
        SubElement(nasc, "paisNascto").text = data.get("paisNascto", "105")
        if data.get("paisNascto", "105") == "105":
            SubElement(nasc, "paisNac").text = "105"

        # vinculo
        vinc = SubElement(evt, "vinculo")
        SubElement(vinc, "matricula").text = data["matricula"]
        SubElement(vinc, "tpRegTrab").text = str(data.get("tpRegTrab", 1))
        SubElement(vinc, "tpRegPrev").text = str(data.get("tpRegPrev", 1))
        SubElement(vinc, "cadIni").text = "S" if data.get("cadIni", True) else "N"

        # infoRegimeTrab
        reg = SubElement(vinc, "infoRegimeTrab")
        clt = SubElement(reg, "infoCeletista")
        SubElement(clt, "dtAdm").text = data["dtAdmissao"]
        SubElement(clt, "tpAdmissao").text = str(data.get("tpAdmissao", 1))
        SubElement(clt, "indAdmissao").text = str(data.get("indAdmissao", 1))
        SubElement(clt, "tpRegJor").text = str(data.get("tpRegJor", 1))
        SubElement(clt, "natAtividade").text = str(data.get("natAtividade", 1))
        SubElement(clt, "dtBase").text = str(data.get("dtBase", 1))
        SubElement(clt, "cnpjSindCategProf").text = data.get("cnpjSindicato", "")

        # infoContrato
        cont = SubElement(vinc, "infoContrato")
        SubElement(cont, "nmCargo").text = data.get("cargo", "")
        SubElement(cont, "CBOCargo").text = data.get("cbo", "")

        # remuneracao
        rem = SubElement(cont, "remuneracao")
        SubElement(rem, "vrSalFx").text = str(data["salario"])
        SubElement(rem, "undSalFixo").text = str(data.get("undSalFixo", 5))

        return self._prettify(root)

    def build_s2299_desligamento(self, data: dict[str, Any]) -> str:
        """Constroi XML do evento S-2299 (Desligamento)."""
        event_id = self.build_event_id("S-2299", data["employer_cnpj"])

        root = Element("eSocial", xmlns=self.NAMESPACE)
        evt = SubElement(root, "evtDeslig", Id=event_id)

        # ideEvento
        ide = SubElement(evt, "ideEvento")
        SubElement(ide, "indRetif").text = str(data.get("indRetif", 1))
        SubElement(ide, "tpAmb").text = self.environment.value
        SubElement(ide, "procEmi").text = "1"
        SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        # ideEmpregador
        emp = SubElement(evt, "ideEmpregador")
        SubElement(emp, "tpInsc").text = "1"
        SubElement(emp, "nrInsc").text = data["employer_cnpj"][:8]

        # ideVinculo
        vinc = SubElement(evt, "ideVinculo")
        SubElement(vinc, "cpfTrab").text = data["cpf"]
        SubElement(vinc, "matricula").text = data["matricula"]

        # infoDeslig
        desl = SubElement(evt, "infoDeslig")
        SubElement(desl, "mtvDeslig").text = data["mtvDeslig"]
        SubElement(desl, "dtDeslig").text = data["dtDesligamento"]
        SubElement(desl, "indPagtoAPI").text = "S" if data.get("indPagtoAPI", True) else "N"
        SubElement(desl, "dtProjFimAPI").text = data.get("dtProjFimAPI", data["dtDesligamento"])
        SubElement(desl, "pensAlim").text = str(data.get("pensAlim", 0))
        SubElement(desl, "percAliment").text = str(data.get("percAliment", 0))
        SubElement(desl, "vrAlim").text = str(data.get("vrAlim", 0))

        return self._prettify(root)

    def build_s2220_monitoramento_saude(self, data: dict[str, Any]) -> str:
        """Constroi XML do evento S-2220 (Monitoramento da Saude)."""
        event_id = self.build_event_id("S-2220", data["employer_cnpj"])

        root = Element("eSocial", xmlns=self.NAMESPACE)
        evt = SubElement(root, "evtMonit", Id=event_id)

        # ideEvento
        ide = SubElement(evt, "ideEvento")
        SubElement(ide, "indRetif").text = str(data.get("indRetif", 1))
        SubElement(ide, "tpAmb").text = self.environment.value
        SubElement(ide, "procEmi").text = "1"
        SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        # ideEmpregador
        emp = SubElement(evt, "ideEmpregador")
        SubElement(emp, "tpInsc").text = "1"
        SubElement(emp, "nrInsc").text = data["employer_cnpj"][:8]

        # ideVinculo
        vinc = SubElement(evt, "ideVinculo")
        SubElement(vinc, "cpfTrab").text = data["cpf"]
        SubElement(vinc, "matricula").text = data["matricula"]

        # exMedOcup
        exmed = SubElement(evt, "exMedOcup")
        SubElement(exmed, "tpExameOcup").text = str(data["tpExameOcup"])

        # aso
        aso = SubElement(exmed, "aso")
        SubElement(aso, "dtAso").text = data["dtAso"]
        SubElement(aso, "resAso").text = str(data["resAso"])

        # exame
        for exame in data.get("exames", []):
            exam = SubElement(aso, "exame")
            SubElement(exam, "dtExm").text = exame["dtExm"]
            SubElement(exam, "procRealizado").text = exame["procRealizado"]
            SubElement(exam, "obsProc").text = exame.get("obsProc", "")

        # medico
        med = SubElement(aso, "medico")
        SubElement(med, "nmMed").text = data["nmMed"]
        SubElement(med, "nrCRM").text = data["nrCRM"]
        SubElement(med, "ufCRM").text = data["ufCRM"]

        return self._prettify(root)

    def build_s1000_empregador(self, data: dict[str, Any]) -> str:
        """Constroi XML do evento S-1000 conforme XSD v_S_01_03_00 (eSocial Simplificado).

        IMPORTANTE: No schema S_01_02_00, o S-1000 NÃO tem:
        - indRetif no ideEvento
        - nmRazao (razão social vem da RFB)
        - natJurid (vem da RFB)
        - contato (removido)

        Ordem dos campos em infoCadastro:
        classTrib, indCoop?, indConstr?, indDesFolha, indOpcCP?, indPorte?,
        indOptRegEletron, cnpjEFR?, dtTrans11096?, indTribFolhaPisCofins?,
        dadosIsencao?, infoOrgInternacional?
        """
        event_id = self.build_event_id("S-1000", data["employer_cnpj"])

        root = Element("eSocial", xmlns="http://www.esocial.gov.br/schema/evt/evtInfoEmpregador/v_S_01_03_00")
        evt = SubElement(root, "evtInfoEmpregador", Id=event_id)

        # ideEvento — S-1000 usa T_ideEvento_exclusao: SEM indRetif
        ide = SubElement(evt, "ideEvento")
        SubElement(ide, "tpAmb").text = self.environment.value
        SubElement(ide, "procEmi").text = "1"  # 1=Aplicativo do empregador
        SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        # ideEmpregador
        cnpj_clean = data["employer_cnpj"].replace(".", "").replace("/", "").replace("-", "")
        emp = SubElement(evt, "ideEmpregador")
        SubElement(emp, "tpInsc").text = "1"  # CNPJ
        SubElement(emp, "nrInsc").text = cnpj_clean[:8]  # Raiz do CNPJ

        # infoEmpregador
        info = SubElement(evt, "infoEmpregador")
        inclusao = SubElement(info, "inclusao")

        # idePeriodo
        ide_periodo = SubElement(inclusao, "idePeriodo")
        SubElement(ide_periodo, "iniValid").text = data.get("iniValid", datetime.utcnow().strftime("%Y-%m"))

        # infoCadastro — ordem EXATA do XSD v_S_01_03_00
        # classTrib, indCoop, indConstr, indDesFolha, indOpcCP?, indPorte?,
        # indOptRegEletron, cnpjEFR?, dtTrans11096?, indTribFolhaPisCofins?
        cad = SubElement(inclusao, "infoCadastro")
        SubElement(cad, "classTrib").text = data.get("classTrib", "02")  # 02=Empresa geral
        SubElement(cad, "indCoop").text = data.get("indCoop", "0")  # 0=Não cooperativa
        SubElement(cad, "indConstr").text = data.get("indConstr", "0")  # 0=Não construtora
        SubElement(cad, "indDesFolha").text = data.get("indDesFolha", "0")  # 0=Não desonerada
        SubElement(cad, "indOptRegEletron").text = data.get("indOptRegEletron", "0")  # 0=Não optou

        return self._prettify(root), event_id

    def _prettify(self, elem: Element) -> str:
        """Formata XML com identacao."""
        rough_string = ET.tostring(elem, encoding="unicode")
        reparsed = minidom.parseString(rough_string)  # noqa: S318 # nosec B318
        return reparsed.toprettyxml(indent="  ")


class ESocialTransmitter:
    """
    Transmissor de eventos eSocial.

    Coordena geracao, validacao, assinatura e transmissao
    de eventos para o eSocial.

    Example:
        >>> transmitter = ESocialTransmitter(config)
        >>> event = await transmitter.create_event(
        ...     EventType.S2200_ADMISSAO,
        ...     employer_cnpj="12.345.678/0001-90",
        ...     data=admissao_data
        ... )
        >>> result = await transmitter.transmit(event.id)
    """

    # URLs oficiais dos webservices eSocial.
    # PRODUÇÃO usa hosts distintos por serviço (envio/consulta/download);
    # PRODUÇÃO RESTRITA (ambiente de testes do governo, dados reais) usa host único.
    WEBSERVICE_URLS = {
        Environment.PRODUCAO: {
            "envio": "https://webservices.envio.esocial.gov.br",
            "consulta": "https://webservices.consulta.esocial.gov.br",
            "download": "https://webservices.download.esocial.gov.br",
        },
        Environment.PRODUCAO_RESTRITA: {
            "envio": "https://webservices.producaorestrita.esocial.gov.br",
            "consulta": "https://webservices.producaorestrita.esocial.gov.br",
            "download": "https://webservices.producaorestrita.esocial.gov.br",
        },
    }

    def __init__(
        self,
        environment: Environment | None = None,
        certificate_path: str | None = None,
        certificate_password: str | None = None,
        certificate_data: bytes | None = None,
    ):
        """
        Inicializa o transmissor.

        Args:
            environment: Ambiente de transmissao. Se None, resolve via env
                ESOCIAL_AMBIENTE (default seguro: producaorestrita).
            certificate_path: Caminho do certificado A1 (.pfx/.p12).
            certificate_password: Senha do certificado.
            certificate_data: Dados do certificado em bytes (alternativa ao path).
        """
        if environment is None:
            environment = resolve_environment()
        self.environment = environment
        self.certificate_path = certificate_path
        self.certificate_password = certificate_password
        self.certificate_data = certificate_data
        self._events: dict[UUID, ESocialEvent] = {}
        self._xml_builder = XMLBuilder(environment)
        self._certificate_info: CertificateInfo | None = None
        self._certificate_manager: CertificateManager | None = None
        self._xml_signer: ESocialXMLSigner | None = None
        logger.info("ESocialTransmitter inicializado (ambiente: %s)", environment.value)

    async def load_certificate(self) -> CertificateInfo:
        """
        Carrega e valida certificado digital A1.

        Returns:
            CertificateInfo: Informacoes do certificado.

        Raises:
            ESocialError: Se certificado invalido ou nao encontrado.
        """
        if not self.certificate_path and not self.certificate_data:
            raise ESocialError("Certificado digital nao configurado")

        try:
            # Carrega certificado usando CertificateManager
            self._certificate_manager = CertificateManager(
                pfx_path=self.certificate_path, pfx_data=self.certificate_data, password=self.certificate_password
            )

            if not self._certificate_manager.load():
                raise ESocialError("Falha ao carregar certificado digital")

            # Valida certificado
            is_valid, validation_msg = self._certificate_manager.validate()
            if not is_valid:
                raise ESocialError(f"Certificado invalido: {validation_msg}")

            # Extrai informacoes
            cert_info = self._certificate_manager.info

            self._certificate_info = CertificateInfo(
                serial_number=cert_info.serial_number,
                subject_cn=cert_info.subject_cn,
                issuer_cn=cert_info.issuer_cn,
                valid_from=cert_info.valid_from,
                valid_until=cert_info.valid_until,
                type="A1",
            )

            # Inicializa assinador XML com certificado
            self._xml_signer = ESocialXMLSigner(self._certificate_manager)

            logger.info(
                "Certificado A1 carregado: %s (CPF/CNPJ: %s, valido ate %s)",
                self._certificate_info.subject_cn,
                cert_info.cpf_cnpj or "N/A",
                self._certificate_info.valid_until.date(),
            )

            return self._certificate_info

        except ESocialError:
            raise
        except Exception as e:
            logger.error("Erro ao carregar certificado: %s", str(e))
            raise ESocialError(f"Erro ao carregar certificado: {str(e)}")

    async def create_event(
        self,
        event_type: EventType,
        employer_cnpj: str,
        data: dict[str, Any],
        employee_cpf: str | None = None,
        reference_id: str | None = None,
        reference_date: date | None = None,
    ) -> ESocialEvent:
        """
        Cria evento eSocial.

        Args:
            event_type: Tipo do evento.
            employer_cnpj: CNPJ do empregador.
            data: Dados do evento.
            employee_cpf: CPF do trabalhador (se aplicavel).
            reference_id: ID de referencia no sistema.
            reference_date: Data de referencia.

        Returns:
            ESocialEvent: Evento criado.
        """
        # Gera XML baseado no tipo
        xml_content = await self._build_xml(event_type, employer_cnpj, data)

        event = ESocialEvent(
            id=uuid4(),
            event_type=event_type,
            status=TransmissionStatus.PENDING,
            employer_cnpj=employer_cnpj,
            employee_cpf=employee_cpf,
            xml_content=xml_content,
            reference_id=reference_id,
            reference_date=reference_date,
            metadata={"original_data": data},
        )

        self._events[event.id] = event

        logger.info("Evento criado: id=%s, type=%s, cnpj=%s", event.id, event_type.value, employer_cnpj)

        return event

    async def create_event_from_xml(
        self,
        event_type: EventType,
        employer_cnpj: str,
        xml_content: str,
        employee_cpf: str | None = None,
        reference_id: str | None = None,
        reference_date: date | None = None,
    ) -> ESocialEvent:
        """
        Cria evento eSocial a partir de XML JÁ CONSTRUÍDO externamente.

        Usado pelos geradores de eventos SST (S-2210/S-2220/S-2230/S-2240) do
        módulo people_management, que constroem o XML conforme o leiaute e o
        entregam pronto para assinatura+transmissão. O XML DEVE conter o
        atributo Id="..." no elemento do evento (exigido pela assinatura).

        Raises:
            ESocialError: Se o XML não parseia ou não contém Id.
        """
        try:
            ET.fromstring(xml_content)
        except Exception as e:  # noqa: BLE001
            raise ESocialError(f"XML inválido para {event_type.value}: {e}")

        if 'Id="' not in xml_content:
            raise ESocialError(f"XML de {event_type.value} sem atributo Id — assinatura impossível")

        event = ESocialEvent(
            id=uuid4(),
            event_type=event_type,
            status=TransmissionStatus.PENDING,
            employer_cnpj=employer_cnpj,
            employee_cpf=employee_cpf,
            xml_content=xml_content,
            reference_id=reference_id,
            reference_date=reference_date,
            metadata={"xml_origin": "external_builder"},
        )
        self._events[event.id] = event
        logger.info(
            "Evento (XML externo) criado: id=%s, type=%s, cnpj=%s", event.id, event_type.value, employer_cnpj
        )
        return event

    async def _build_xml(self, event_type: EventType, employer_cnpj: str, data: dict[str, Any]) -> str:
        """Constroi XML do evento."""
        data["employer_cnpj"] = employer_cnpj

        if event_type == EventType.S1000_EMPREGADOR:
            xml, event_id = self._xml_builder.build_s1000_empregador(data)
            # Armazena event_id para uso na assinatura
            data["_event_xml_id"] = event_id
            return xml
        elif event_type == EventType.S2200_ADMISSAO:
            return self._xml_builder.build_s2200_admissao(data)
        elif event_type == EventType.S2299_DESLIGAMENTO:
            return self._xml_builder.build_s2299_desligamento(data)
        elif event_type == EventType.S2220_MONITORAMENTO_SAUDE:
            return self._xml_builder.build_s2220_monitoramento_saude(data)
        else:
            raise ESocialError(f"Tipo de evento nao implementado: {event_type.value}")

    async def validate_event(self, event_id: UUID) -> dict[str, Any]:
        """
        Valida evento antes da transmissao.

        Args:
            event_id: ID do evento.

        Returns:
            Dict: Resultado da validacao.
        """
        event = self._events.get(event_id)
        if not event:
            raise ESocialError("Evento nao encontrado", str(event_id))

        event.status = TransmissionStatus.VALIDATING
        errors = []
        warnings = []

        # Valida XML
        try:
            ET.fromstring(event.xml_content)
        except ET.ParseError as e:
            errors.append({"code": "XML_INVALID", "message": str(e)})

        # Valida campos obrigatorios
        if not event.employer_cnpj:
            errors.append({"code": "CNPJ_REQUIRED", "message": "CNPJ do empregador obrigatorio"})

        # Valida certificado
        if self._certificate_info:
            days_until = self._certificate_info.days_until_expiry()
            if days_until < 30:
                warnings.append({"code": "CERTIFICATE_EXPIRING", "message": f"Certificado vence em {days_until} dias"})

        event.errors = errors
        event.warnings = warnings

        if errors:
            event.status = TransmissionStatus.ERROR
            raise ValidationError(f"Validacao falhou: {len(errors)} erro(s)")

        event.status = TransmissionStatus.PENDING

        return {
            "valid": True,
            "errors": errors,
            "warnings": warnings,
        }

    async def sign_event(self, event_id: UUID) -> str:
        """
        Assina evento com certificado digital A1 usando XMLDSig.

        Args:
            event_id: ID do evento.

        Returns:
            str: XML assinado com assinatura digital valida.

        Raises:
            ESocialError: Se falha na assinatura.
        """
        event = self._events.get(event_id)
        if not event:
            raise ESocialError("Evento nao encontrado", str(event_id))

        # Carrega certificado se necessario
        if not self._xml_signer:
            await self.load_certificate()

        if not self._xml_signer:
            raise ESocialError("Assinador XML nao inicializado")

        try:
            # Extrai ID do evento do XML para referencia
            import re

            id_match = re.search(r'Id="([^"]+)"', event.xml_content)
            if not id_match:
                raise ESocialError("ID do evento nao encontrado no XML")

            event_xml_id = id_match.group(1)

            # Assina XML usando assinatura digital real
            signed_xml = self._xml_signer.sign_event(xml_content=event.xml_content, event_id=event_xml_id)

            event.xml_signed = signed_xml

            logger.info("Evento assinado com certificado A1: id=%s, event_xml_id=%s", event_id, event_xml_id)

            return signed_xml

        except Exception as e:
            logger.error("Erro ao assinar evento %s: %s", event_id, str(e))
            raise ESocialError(f"Falha na assinatura digital: {str(e)}", str(event_id))

    def _build_soap_envelope(self, signed_xml: str, grupo: int = 1) -> str:
        """
        Monta envelope SOAP para o webservice EnviarLoteEventos.

        Args:
            signed_xml: XML do evento já assinado
            grupo: Grupo do evento (1=tabelas, 2=não-periódicos, 3=periódicos)
        """
        # Remover declaração <?xml?>
        xml_clean = signed_xml
        if xml_clean.startswith("<?xml"):
            xml_clean = xml_clean[xml_clean.index("?>") + 2 :].strip()

        # XSD EnvioLoteEventos-v1_1_1: <evento> contém xs:any processContents="skip"
        # O XML completo do evento (com <eSocial> wrapper) vai DENTRO de <evento>.
        xml_evento_inner = xml_clean

        # Extrair o Id do evento do XML
        id_match = re_module.search(r'Id="([^"]+)"', xml_evento_inner)
        lote_id = (
            id_match.group(1) if id_match else f"ID135710481000103{datetime.utcnow().strftime('%Y%m%d%H%M%S')}00001"
        )

        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <EnviarLoteEventos xmlns="http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/v1_1_1">
      <loteEventos>
        <eSocial xmlns="http://www.esocial.gov.br/schema/lote/eventos/envio/v1_1_1">
          <envioLoteEventos grupo="{grupo}">
            <ideEmpregador>
              <tpInsc>1</tpInsc>
              <nrInsc>35710481</nrInsc>
            </ideEmpregador>
            <ideTransmissor>
              <tpInsc>1</tpInsc>
              <nrInsc>35710481000103</nrInsc>
            </ideTransmissor>
            <eventos>
              <evento Id="{lote_id}">
{xml_evento_inner}
              </evento>
            </eventos>
          </envioLoteEventos>
        </eSocial>
      </loteEventos>
    </EnviarLoteEventos>
  </soap:Body>
</soap:Envelope>"""
        return envelope

    def _build_consulta_soap(self, protocolo: str) -> str:
        """Monta envelope SOAP para ConsultarLoteEventos."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ConsultarLoteEventos xmlns="http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/consulta/retornoProcessamento/v1_0_0">
      <consulta>
        <eSocial xmlns="http://www.esocial.gov.br/schema/consulta/retornoProcessamento/v1_0_0">
          <consultaLoteEventos>
            <protocoloEnvio>{protocolo}</protocoloEnvio>
          </consultaLoteEventos>
        </eSocial>
      </consulta>
    </ConsultarLoteEventos>
  </soap:Body>
</soap:Envelope>"""

    def _get_cert_files(self) -> tuple[str, str]:
        """Retorna caminhos dos arquivos PEM do certificado para mTLS."""
        if not self._certificate_manager:
            raise ESocialError("Certificado não carregado")
        return self._certificate_manager.get_certificate_for_request()

    async def transmit(self, event_id: UUID) -> ESocialEvent:
        """
        Transmite evento para o eSocial via SOAP com mTLS.

        Faz chamada real ao webservice do governo usando certificado A1.
        """
        event = self._events.get(event_id)
        if not event:
            raise ESocialError("Evento nao encontrado", str(event_id))

        # Valida
        await self.validate_event(event_id)

        # Assina com certificado A1
        if not event.xml_signed:
            await self.sign_event(event_id)

        event.status = TransmissionStatus.TRANSMITTED
        event.transmitted_at = datetime.utcnow()

        # Determinar grupo do evento
        grupo = 1  # Tabelas (S-1000 a S-1080)
        if event.event_type.value.startswith("S-2"):
            grupo = 2  # Não-periódicos
        elif event.event_type.value.startswith("S-12"):
            grupo = 3  # Periódicos

        # Montar envelope SOAP
        soap_envelope = self._build_soap_envelope(event.xml_signed, grupo)

        # URL do webservice (host de ENVIO do ambiente corrente)
        base_url = self.WEBSERVICE_URLS[self.environment]["envio"]
        url = f"{base_url}/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc"

        logger.info(
            "Transmitindo evento %s (%s) para %s",
            event.event_type.value,
            event_id,
            url,
        )

        # Obter certificado para mTLS
        cert_path, key_path = self._get_cert_files()

        try:
            response = http_requests.post(
                url,
                data=soap_envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/v1_1_0/ServicoEnviarLoteEventos/EnviarLoteEventos",
                },
                cert=(cert_path, key_path),
                timeout=60,
                verify=True,
            )

            logger.info(
                "Resposta eSocial: HTTP %d (%d bytes)",
                response.status_code,
                len(response.content),
            )

            # Parsear resposta SOAP
            event.metadata["http_status"] = response.status_code
            event.metadata["response_raw"] = response.text[:5000]

            if response.status_code == 200:
                # Extrair protocolo da resposta
                protocolo = self._extract_protocol(response.text)
                if protocolo:
                    event.protocol = protocolo
                    event.status = TransmissionStatus.PROCESSING
                    logger.info("Evento aceito: protocolo=%s", protocolo)
                else:
                    # Pode ser erro de validação do governo
                    erro = self._extract_error(response.text)
                    event.status = TransmissionStatus.REJECTED
                    event.errors.append({"code": "GOV_REJECT", "message": erro})
                    logger.warning("Evento rejeitado pelo governo: %s", erro)
            else:
                event.status = TransmissionStatus.ERROR
                event.errors.append(
                    {
                        "code": f"HTTP_{response.status_code}",
                        "message": response.text[:500],
                    }
                )
                logger.error("Erro HTTP %d na transmissão", response.status_code)

        except http_requests.exceptions.SSLError as e:
            event.status = TransmissionStatus.ERROR
            event.errors.append({"code": "SSL_ERROR", "message": str(e)[:300]})
            logger.error("Erro SSL/mTLS: %s", str(e)[:200])
        except http_requests.exceptions.ConnectionError as e:
            event.status = TransmissionStatus.ERROR
            event.errors.append({"code": "CONNECTION_ERROR", "message": str(e)[:300]})
            logger.error("Erro de conexão: %s", str(e)[:200])
        except http_requests.exceptions.Timeout:
            event.status = TransmissionStatus.ERROR
            event.errors.append({"code": "TIMEOUT", "message": "Timeout na conexão com webservice"})
            logger.error("Timeout na transmissão")
        except Exception as e:
            event.status = TransmissionStatus.ERROR
            event.errors.append({"code": "UNKNOWN", "message": str(e)[:300]})
            logger.error("Erro inesperado: %s", str(e))
        finally:
            # Limpar arquivos temporários do certificado
            try:
                if cert_path and os.path.exists(cert_path):
                    cert_dir = os.path.dirname(cert_path)
                    os.unlink(cert_path)
                    if key_path and os.path.exists(key_path):
                        os.unlink(key_path)
                    if os.path.isdir(cert_dir):
                        os.rmdir(cert_dir)
            except OSError:
                pass

        return event

    def _extract_protocol(self, response_xml: str) -> str | None:
        """Extrai protocolo de envio da resposta SOAP do eSocial."""
        try:
            # Tentar extrair com regex (mais robusto contra namespaces)
            match = re_module.search(r"<protocoloEnvio>([^<]+)</protocoloEnvio>", response_xml)
            if match:
                return match.group(1).strip()

            # Fallback: tentar com nrProt
            match = re_module.search(r"<nrProt>([^<]+)</nrProt>", response_xml)
            if match:
                return match.group(1).strip()

            # Fallback: protocolo em atributo
            match = re_module.search(r"protocolo[\"=]([^\"<>\s]+)", response_xml, re_module.IGNORECASE)
            if match:
                return match.group(1).strip()

        except Exception as e:
            logger.error("Erro extraindo protocolo: %s", e)

        return None

    def _extract_error(self, response_xml: str) -> str:
        """Extrai mensagem de erro da resposta SOAP."""
        try:
            # Buscar descricao de erro
            for tag in ["descricao", "descResposta", "faultstring", "dsOcorrencia", "mensagem"]:
                match = re_module.search(rf"<{tag}>([^<]+)</{tag}>", response_xml, re_module.IGNORECASE)
                if match:
                    return match.group(1).strip()

            # Se não encontrou tag específica, retornar trecho do XML
            return response_xml[:300]
        except Exception:
            return "Erro desconhecido na resposta"

    async def check_status(self, event_id: UUID) -> ESocialEvent:
        """
        Consulta status de processamento do evento via SOAP.
        """
        event = self._events.get(event_id)
        if not event:
            raise ESocialError("Evento nao encontrado", str(event_id))

        if event.status not in [TransmissionStatus.TRANSMITTED, TransmissionStatus.PROCESSING]:
            return event

        if not event.protocol:
            raise ESocialError("Evento sem protocolo para consulta")

        # URL do webservice de consulta (host de CONSULTA do ambiente corrente)
        base_url = self.WEBSERVICE_URLS[self.environment]["consulta"]
        url = f"{base_url}/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc"

        soap_consulta = self._build_consulta_soap(event.protocol)

        cert_path, key_path = self._get_cert_files()

        try:
            response = http_requests.post(
                url,
                data=soap_consulta.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/consulta/retornoProcessamento/v1_0_0/ServicoConsultarLoteEventos/ConsultarLoteEventos",
                },
                cert=(cert_path, key_path),
                timeout=60,
                verify=True,
            )

            logger.info("Consulta status: HTTP %d", response.status_code)

            if response.status_code == 200:
                # Verificar se foi processado
                if "cdResposta>201" in response.text or "processado" in response.text.lower():
                    event.status = TransmissionStatus.ACCEPTED
                    event.processed_at = datetime.utcnow()
                    # Extrair recibo
                    match = re_module.search(r"<nrRecibo>([^<]+)</nrRecibo>", response.text)
                    if match:
                        event.receipt_number = match.group(1).strip()
                elif "cdResposta>501" in response.text:
                    # Ainda em processamento
                    event.status = TransmissionStatus.PROCESSING
                else:
                    # Verificar rejeição
                    erro = self._extract_error(response.text)
                    event.status = TransmissionStatus.REJECTED
                    event.errors.append({"code": "GOV_REJECT", "message": erro})

            event.metadata["status_response"] = response.text[:1000]

        except Exception as e:
            logger.error("Erro consultando status: %s", e)
            event.errors.append({"code": "STATUS_ERROR", "message": str(e)[:300]})
        finally:
            try:
                if cert_path and os.path.exists(cert_path):
                    cert_dir = os.path.dirname(cert_path)
                    os.unlink(cert_path)
                    if key_path and os.path.exists(key_path):
                        os.unlink(key_path)
                    if os.path.isdir(cert_dir):
                        os.rmdir(cert_dir)
            except OSError:
                pass

        return event

    async def get_event(self, event_id: UUID) -> ESocialEvent | None:
        """Recupera evento por ID."""
        return self._events.get(event_id)

    async def list_events(
        self,
        status: TransmissionStatus | None = None,
        event_type: EventType | None = None,
        employer_cnpj: str | None = None,
    ) -> list[ESocialEvent]:
        """Lista eventos com filtros."""
        events = list(self._events.values())

        if status:
            events = [e for e in events if e.status == status]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if employer_cnpj:
            events = [e for e in events if e.employer_cnpj == employer_cnpj]

        return sorted(events, key=lambda x: x.created_at, reverse=True)

    async def get_pending_events(self) -> list[ESocialEvent]:
        """Lista eventos pendentes de transmissao."""
        return await self.list_events(status=TransmissionStatus.PENDING)

    async def batch_transmit(self, event_ids: list[UUID]) -> dict[str, Any]:
        """
        Transmite lote de eventos.

        Args:
            event_ids: Lista de IDs de eventos.

        Returns:
            Dict: Resultado do lote.
        """
        results = {
            "total": len(event_ids),
            "success": 0,
            "failed": 0,
            "events": [],
        }

        for event_id in event_ids:
            try:
                event = await self.transmit(event_id)
                results["success"] += 1
                results["events"].append(
                    {
                        "id": str(event_id),
                        "status": event.status.value,
                        "protocol": event.protocol,
                    }
                )
            except ESocialError as e:
                results["failed"] += 1
                results["events"].append(
                    {
                        "id": str(event_id),
                        "status": "error",
                        "error": str(e),
                    }
                )

        logger.info("Lote transmitido: %d/%d sucesso", results["success"], results["total"])

        return results

    async def get_transmission_summary(self) -> dict[str, Any]:
        """Gera resumo de transmissoes."""
        events = list(self._events.values())

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "total_events": len(events),
            "by_status": {status.value: sum(1 for e in events if e.status == status) for status in TransmissionStatus},
            "by_type": {},
            "pending_count": len(await self.get_pending_events()),
        }


# Singleton
_esocial_transmitter: ESocialTransmitter | None = None


def get_esocial_transmitter() -> ESocialTransmitter:
    """Retorna instancia singleton do ESocialTransmitter."""
    global _esocial_transmitter
    if _esocial_transmitter is None:
        _esocial_transmitter = ESocialTransmitter()
    return _esocial_transmitter


def init_esocial_transmitter(
    environment: Environment | None = None,
    certificate_path: str | None = None,
    certificate_password: str | None = None,
    certificate_data: bytes | None = None,
) -> ESocialTransmitter:
    """
    Inicializa o ESocialTransmitter singleton.

    Args:
        environment: Ambiente (producao ou homologacao).
        certificate_path: Caminho do arquivo .pfx/.p12.
        certificate_password: Senha do certificado.
        certificate_data: Dados do certificado em bytes.

    Returns:
        ESocialTransmitter: Instancia configurada.
    """
    global _esocial_transmitter
    _esocial_transmitter = ESocialTransmitter(
        environment=environment,
        certificate_path=certificate_path,
        certificate_password=certificate_password,
        certificate_data=certificate_data,
    )
    return _esocial_transmitter
