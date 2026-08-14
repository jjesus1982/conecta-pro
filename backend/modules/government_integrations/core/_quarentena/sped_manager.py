"""
Module: SPEDManager
Description: Sistema Público de Escrituração Digital
             - EFD-ICMS/IPI (SPED Fiscal)
             - EFD-Contribuições (PIS/COFINS)
             - EFD-REINF (Retenções na Fonte)
Author: Conecta PRO
Date: 2026-01-17

Portal: https://www.gov.br/receitafederal/pt-br/assuntos/sped
Documentação: https://www.sped.fazenda.gov.br

SPED:
- EFD-ICMS/IPI: Escrituração fiscal estadual (entradas, saídas, apuração)
- EFD-Contribuições: Escrituração federal (PIS/COFINS)
- EFD-REINF: Retenções na fonte e informações da contribuição previdenciária
"""

import hashlib
import logging
import re
import ssl
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from io import StringIO
from typing import Any

import aiohttp
from lxml import etree
from signxml import XMLSigner, methods

logger = logging.getLogger(__name__)


# =============================================================================
# EFD-ICMS/IPI (SPED Fiscal)
# =============================================================================


class EFDICMSBloco(StrEnum):
    """Blocos do EFD-ICMS/IPI."""

    BLOCO_0 = "0"  # Abertura, Identificação e Referências
    BLOCO_C = "C"  # Documentos Fiscais I - Mercadorias
    BLOCO_D = "D"  # Documentos Fiscais II - Serviços
    BLOCO_E = "E"  # Apuração do ICMS e IPI
    BLOCO_G = "G"  # CIAP
    BLOCO_H = "H"  # Inventário Físico
    BLOCO_K = "K"  # Produção e Estoque
    BLOCO_1 = "1"  # Outras Informações
    BLOCO_9 = "9"  # Controle e Encerramento


@dataclass
class Registro0000:
    """Registro 0000 - Abertura do Arquivo Digital."""

    cod_ver: str = "018"  # Versão do leiaute
    cod_fin: str = "0"  # 0=Original, 1=Substituto
    dt_ini: date = None
    dt_fin: date = None
    nome: str = ""
    cnpj: str = ""
    cpf: str = ""
    uf: str = ""
    ie: str = ""
    cod_mun: str = ""
    im: str = ""
    suframa: str = ""
    ind_perfil: str = "A"  # Perfil A, B ou C
    ind_ativ: str = "1"  # 1=Industrial/Equiparado, 0=Outros

    def to_line(self) -> str:
        """Gera linha do registro."""
        dt_ini_str = self.dt_ini.strftime("%d%m%Y") if self.dt_ini else ""
        dt_fin_str = self.dt_fin.strftime("%d%m%Y") if self.dt_fin else ""
        cnpj = re.sub(r"[^\d]", "", self.cnpj)

        return f"|0000|{self.cod_ver}|{self.cod_fin}|{dt_ini_str}|{dt_fin_str}|{self.nome}|{cnpj}|{self.cpf}|{self.uf}|{self.ie}|{self.cod_mun}|{self.im}|{self.suframa}|{self.ind_perfil}|{self.ind_ativ}|"


@dataclass
class Registro0001:
    """Registro 0001 - Abertura do Bloco 0."""

    ind_mov: str = "0"  # 0=Com dados, 1=Sem dados

    def to_line(self) -> str:
        return f"|0001|{self.ind_mov}|"


@dataclass
class Registro0990:
    """Registro 0990 - Encerramento do Bloco 0."""

    qtd_lin_0: int = 0

    def to_line(self) -> str:
        return f"|0990|{self.qtd_lin_0}|"


@dataclass
class RegistroC001:
    """Registro C001 - Abertura do Bloco C."""

    ind_mov: str = "0"

    def to_line(self) -> str:
        return f"|C001|{self.ind_mov}|"


@dataclass
class RegistroC100:
    """Registro C100 - Documento Fiscal (NF-e, NF)."""

    ind_oper: str = ""  # 0=Entrada, 1=Saída
    ind_emit: str = ""  # 0=Própria, 1=Terceiros
    cod_part: str = ""  # Código participante
    cod_mod: str = "55"  # Modelo (55=NF-e)
    cod_sit: str = "00"  # Situação (00=Regular)
    ser: str = ""
    num_doc: str = ""
    chv_nfe: str = ""
    dt_doc: date = None
    dt_e_s: date = None  # Data entrada/saída
    vl_doc: Decimal = Decimal("0")
    ind_pgto: str = "0"
    vl_desc: Decimal = Decimal("0")
    vl_abat_nt: Decimal = Decimal("0")
    vl_merc: Decimal = Decimal("0")
    ind_frt: str = "9"
    vl_frt: Decimal = Decimal("0")
    vl_seg: Decimal = Decimal("0")
    vl_out_da: Decimal = Decimal("0")
    vl_bc_icms: Decimal = Decimal("0")
    vl_icms: Decimal = Decimal("0")
    vl_bc_icms_st: Decimal = Decimal("0")
    vl_icms_st: Decimal = Decimal("0")
    vl_ipi: Decimal = Decimal("0")
    vl_pis: Decimal = Decimal("0")
    vl_cofins: Decimal = Decimal("0")
    vl_pis_st: Decimal = Decimal("0")
    vl_cofins_st: Decimal = Decimal("0")

    def to_line(self) -> str:
        dt_doc_str = self.dt_doc.strftime("%d%m%Y") if self.dt_doc else ""
        dt_e_s_str = self.dt_e_s.strftime("%d%m%Y") if self.dt_e_s else ""

        return (
            f"|C100|{self.ind_oper}|{self.ind_emit}|{self.cod_part}|{self.cod_mod}|"
            f"{self.cod_sit}|{self.ser}|{self.num_doc}|{self.chv_nfe}|{dt_doc_str}|"
            f"{dt_e_s_str}|{self.vl_doc:.2f}|{self.ind_pgto}|{self.vl_desc:.2f}|"
            f"{self.vl_abat_nt:.2f}|{self.vl_merc:.2f}|{self.ind_frt}|{self.vl_frt:.2f}|"
            f"{self.vl_seg:.2f}|{self.vl_out_da:.2f}|{self.vl_bc_icms:.2f}|{self.vl_icms:.2f}|"
            f"{self.vl_bc_icms_st:.2f}|{self.vl_icms_st:.2f}|{self.vl_ipi:.2f}|"
            f"{self.vl_pis:.2f}|{self.vl_cofins:.2f}|{self.vl_pis_st:.2f}|{self.vl_cofins_st:.2f}|"
        )


@dataclass
class RegistroC990:
    """Registro C990 - Encerramento do Bloco C."""

    qtd_lin_c: int = 0

    def to_line(self) -> str:
        return f"|C990|{self.qtd_lin_c}|"


@dataclass
class Registro9001:
    """Registro 9001 - Abertura do Bloco 9."""

    ind_mov: str = "0"

    def to_line(self) -> str:
        return f"|9001|{self.ind_mov}|"


@dataclass
class Registro9900:
    """Registro 9900 - Registros do arquivo."""

    reg_blc: str = ""
    qtd_reg_blc: int = 0

    def to_line(self) -> str:
        return f"|9900|{self.reg_blc}|{self.qtd_reg_blc}|"


@dataclass
class Registro9990:
    """Registro 9990 - Encerramento do Bloco 9."""

    qtd_lin_9: int = 0

    def to_line(self) -> str:
        return f"|9990|{self.qtd_lin_9}|"


@dataclass
class Registro9999:
    """Registro 9999 - Encerramento do arquivo."""

    qtd_lin: int = 0

    def to_line(self) -> str:
        return f"|9999|{self.qtd_lin}|"


class EFDICMSIPIBuilder:
    """Builder de arquivo EFD-ICMS/IPI."""

    def __init__(self):
        self.registros: list[Any] = []
        self.contadores: dict[str, int] = {}

    def add_registro(self, registro: Any):
        """Adiciona registro ao arquivo."""
        self.registros.append(registro)
        reg_type = type(registro).__name__
        self.contadores[reg_type] = self.contadores.get(reg_type, 0) + 1

    def build(self) -> str:
        """Gera arquivo EFD-ICMS/IPI."""
        output = StringIO()

        for registro in self.registros:
            output.write(registro.to_line() + "\n")

        return output.getvalue()


# =============================================================================
# EFD-Contribuições (PIS/COFINS)
# =============================================================================


@dataclass
class EFDContrib0000:
    """Registro 0000 - Abertura do Arquivo EFD-Contribuições."""

    cod_ver: str = "006"  # Versão do leiaute
    tipo_escrit: str = "0"  # 0=Original
    ind_sit_esp: str = ""
    num_rec_anterior: str = ""
    dt_ini: date = None
    dt_fin: date = None
    nome: str = ""
    cnpj: str = ""
    uf: str = ""
    cod_mun: str = ""
    suframa: str = ""
    ind_nat_pj: str = "00"
    ind_ativ: str = "0"

    def to_line(self) -> str:
        dt_ini_str = self.dt_ini.strftime("%d%m%Y") if self.dt_ini else ""
        dt_fin_str = self.dt_fin.strftime("%d%m%Y") if self.dt_fin else ""
        cnpj = re.sub(r"[^\d]", "", self.cnpj)

        return f"|0000|{self.cod_ver}|{self.tipo_escrit}|{self.ind_sit_esp}|{self.num_rec_anterior}|{dt_ini_str}|{dt_fin_str}|{self.nome}|{cnpj}|{self.uf}|{self.cod_mun}|{self.suframa}|{self.ind_nat_pj}|{self.ind_ativ}|"


class EFDContribuicoesBuilder:
    """Builder de arquivo EFD-Contribuições."""

    def __init__(self):
        self.registros: list[Any] = []

    def add_registro(self, registro: Any):
        """Adiciona registro ao arquivo."""
        self.registros.append(registro)

    def build(self) -> str:
        """Gera arquivo EFD-Contribuições."""
        output = StringIO()

        for registro in self.registros:
            if hasattr(registro, "to_line"):
                output.write(registro.to_line() + "\n")

        return output.getvalue()


# =============================================================================
# EFD-REINF (Retenções na Fonte)
# =============================================================================

REINF_ENDPOINTS = {
    "producao": {
        "envio": "https://reinf.receita.economia.gov.br/recepcao/lotes",
        "consulta": "https://reinf.receita.economia.gov.br/consulta/lotes",
    },
    "producao_restrita": {
        "envio": "https://pre-reinf.receita.economia.gov.br/recepcao/lotes",
        "consulta": "https://pre-reinf.receita.economia.gov.br/consulta/lotes",
    },
}


class TipoEventoREINF(StrEnum):
    """Tipos de eventos REINF."""

    R1000 = "R-1000"  # Informações do Contribuinte
    R1050 = "R-1050"  # Tabela de Entidades Ligadas
    R1070 = "R-1070"  # Tabela de Processos Administrativos/Judiciais
    R2010 = "R-2010"  # Retenção - Serviços Tomados
    R2020 = "R-2020"  # Retenção - Serviços Prestados
    R2030 = "R-2030"  # Recursos Recebidos por Associação Desportiva
    R2040 = "R-2040"  # Recursos Repassados para Associação Desportiva
    R2050 = "R-2050"  # Comercialização Produção Rural PF
    R2055 = "R-2055"  # Aquisição Produção Rural
    R2060 = "R-2060"  # Contribuição Previdenciária sobre Receita Bruta (CPRB)
    R2098 = "R-2098"  # Reabertura dos Eventos Periódicos
    R2099 = "R-2099"  # Fechamento dos Eventos Periódicos
    R3010 = "R-3010"  # Receita de Espetáculos Desportivos
    R4010 = "R-4010"  # Pagamentos/Créditos a Beneficiário PF
    R4020 = "R-4020"  # Pagamentos/Créditos a Beneficiário PJ
    R4040 = "R-4040"  # Pagamentos/Créditos a Beneficiário Não Identificado
    R4080 = "R-4080"  # Retenção no Recebimento
    R4099 = "R-4099"  # Fechamento/Reabertura dos Eventos Série R-4000
    R9000 = "R-9000"  # Exclusão de Eventos


@dataclass
class ContribuinteREINF:
    """Dados do contribuinte REINF."""

    tipo_inscricao: str  # 1=CNPJ, 2=CPF
    numero_inscricao: str
    razao_social: str
    natureza_juridica: str
    classificacao_tributaria: str
    ind_escrituracao: str = "1"  # 1=Empresa não obrigada a ECD
    ind_desoneracaco: str = "0"  # 0=Não aplicável
    ind_acordo_isenção_multa: str = "0"
    situacao_pj: str = "0"  # 0=Normal


@dataclass
class ServicoTomadoREINF:
    """Serviço tomado com retenção (R-2010)."""

    tipo_inscricao_prestador: str
    numero_inscricao_prestador: str
    razao_social_prestador: str
    valor_bruto: Decimal
    valor_retencao_previdenciaria: Decimal
    valor_servicos_15: Decimal = Decimal("0")
    valor_servicos_20: Decimal = Decimal("0")
    valor_servicos_25: Decimal = Decimal("0")
    valor_adicional_retencao: Decimal = Decimal("0")
    valor_nao_retido: Decimal = Decimal("0")


@dataclass
class EventoREINF:
    """Evento REINF."""

    tipo: TipoEventoREINF
    contribuinte: ContribuinteREINF
    periodo_apuracao: str  # AAAA-MM
    dados_especificos: dict[str, Any] = field(default_factory=dict)
    protocolo: str | None = None
    numero_recibo: str | None = None


class REINFXMLBuilder:
    """Builder de XML para eventos REINF."""

    NAMESPACE = "http://www.reinf.esocial.gov.br/schemas/evt"
    VERSION = "2.01.02"

    def build_r1000(self, contribuinte: ContribuinteREINF, ambiente: str = "2") -> str:
        """Constrói R-1000 - Informações do Contribuinte."""
        import xml.etree.ElementTree as ET  # noqa: S405
        from xml.dom import minidom  # noqa: S408

        root = ET.Element("Reinf", xmlns=self.NAMESPACE)
        evt = ET.SubElement(root, "evtInfoContri")

        ide = ET.SubElement(evt, "ideEvento")
        ET.SubElement(ide, "tpAmb").text = ambiente
        ET.SubElement(ide, "procEmi").text = "1"
        ET.SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        ide_contrib = ET.SubElement(evt, "ideContri")
        ET.SubElement(ide_contrib, "tpInsc").text = contribuinte.tipo_inscricao
        ET.SubElement(ide_contrib, "nrInsc").text = re.sub(r"[^\d]", "", contribuinte.numero_inscricao)[:8]

        info = ET.SubElement(evt, "infoContri")
        inclusao = ET.SubElement(info, "inclusao")

        ide_periodo = ET.SubElement(inclusao, "idePeriodo")
        ET.SubElement(ide_periodo, "iniValid").text = datetime.now().strftime("%Y-%m")

        info_cad = ET.SubElement(inclusao, "infoCadastro")
        ET.SubElement(info_cad, "classTrib").text = contribuinte.classificacao_tributaria
        ET.SubElement(info_cad, "indEscrituracao").text = contribuinte.ind_escrituracao
        ET.SubElement(info_cad, "indDesoneracao").text = contribuinte.ind_desoneracaco
        ET.SubElement(info_cad, "indAcordoIsenMulta").text = contribuinte.ind_acordo_isenção_multa
        ET.SubElement(info_cad, "indSitPJ").text = contribuinte.situacao_pj

        rough = ET.tostring(root, encoding="unicode")
        return minidom.parseString(rough).toprettyxml(indent="  ")  # noqa: S318 - Apenas formata XML gerado internamente

    def build_r2010(
        self, contribuinte: ContribuinteREINF, servico: ServicoTomadoREINF, periodo: str, ambiente: str = "2"
    ) -> str:
        """Constrói R-2010 - Retenção Serviços Tomados."""
        import xml.etree.ElementTree as ET  # noqa: S405
        from xml.dom import minidom  # noqa: S408

        root = ET.Element("Reinf", xmlns=self.NAMESPACE)
        evt = ET.SubElement(root, "evtServTom")

        ide = ET.SubElement(evt, "ideEvento")
        ET.SubElement(ide, "indRetif").text = "1"
        ET.SubElement(ide, "perApur").text = periodo
        ET.SubElement(ide, "tpAmb").text = ambiente
        ET.SubElement(ide, "procEmi").text = "1"
        ET.SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        ide_contrib = ET.SubElement(evt, "ideContri")
        ET.SubElement(ide_contrib, "tpInsc").text = contribuinte.tipo_inscricao
        ET.SubElement(ide_contrib, "nrInsc").text = re.sub(r"[^\d]", "", contribuinte.numero_inscricao)[:8]

        info_serv = ET.SubElement(evt, "infoServTom")
        ide_estab = ET.SubElement(info_serv, "ideEstabObra")
        ET.SubElement(ide_estab, "tpInscEstab").text = "1"
        ET.SubElement(ide_estab, "nrInscEstab").text = re.sub(r"[^\d]", "", contribuinte.numero_inscricao)

        ide_prest = ET.SubElement(ide_estab, "idePrestServ")
        ET.SubElement(ide_prest, "cnpjPrestador").text = re.sub(r"[^\d]", "", servico.numero_inscricao_prestador)
        ET.SubElement(ide_prest, "vlrTotalBruto").text = f"{servico.valor_bruto:.2f}"
        ET.SubElement(ide_prest, "vlrTotalBaseRet").text = f"{servico.valor_bruto:.2f}"
        ET.SubElement(ide_prest, "vlrTotalRetPrinc").text = f"{servico.valor_retencao_previdenciaria:.2f}"
        ET.SubElement(ide_prest, "vlrTotalRetAdworking").text = f"{servico.valor_adicional_retencao:.2f}"
        ET.SubElement(ide_prest, "vlrTotalNRetPrinc").text = f"{servico.valor_nao_retido:.2f}"
        ET.SubElement(ide_prest, "vlrTotalNRetAdworking").text = "0.00"

        rough = ET.tostring(root, encoding="unicode")
        return minidom.parseString(rough).toprettyxml(indent="  ")  # noqa: S318 - Apenas formata XML gerado internamente


@dataclass
class SPEDResult:
    """Resultado de operação SPED."""

    sucesso: bool
    mensagem: str
    arquivo: str | None = None
    xml: str | None = None
    protocolo: str | None = None
    numero_recibo: str | None = None


class SPEDManager:
    """
    Gerenciador unificado do SPED.

    Coordena geração de arquivos e envio para:
    - EFD-ICMS/IPI
    - EFD-Contribuições
    - EFD-REINF
    """

    def __init__(
        self,
        ambiente: str = "2",
        cert_path: str | None = None,
        cert_password: str | None = None,
    ):
        """Inicializa o gerenciador SPED."""
        self.ambiente = ambiente
        self.cert_path = cert_path
        self.cert_password = cert_password

        self.efd_icms_builder = EFDICMSIPIBuilder()
        self.efd_contrib_builder = EFDContribuicoesBuilder()
        self.reinf_builder = REINFXMLBuilder()

        logger.info(f"SPEDManager inicializado: Ambiente={'Produção' if ambiente == '1' else 'Homologação'}")

    # -------------------------------------------------------------------------
    # EFD-ICMS/IPI
    # -------------------------------------------------------------------------

    def criar_efd_icms(
        self,
        empresa_nome: str,
        empresa_cnpj: str,
        empresa_uf: str,
        empresa_ie: str,
        empresa_municipio: str,
        data_inicio: date,
        data_fim: date,
    ) -> EFDICMSIPIBuilder:
        """Cria builder de EFD-ICMS/IPI com registros iniciais."""
        builder = EFDICMSIPIBuilder()

        # Registro 0000 - Abertura
        builder.add_registro(
            Registro0000(
                dt_ini=data_inicio,
                dt_fin=data_fim,
                nome=empresa_nome,
                cnpj=empresa_cnpj,
                uf=empresa_uf,
                ie=empresa_ie,
                cod_mun=empresa_municipio,
            )
        )

        # Registro 0001 - Abertura Bloco 0
        builder.add_registro(Registro0001(ind_mov="0"))

        return builder

    def adicionar_nfe_efd(
        self,
        builder: EFDICMSIPIBuilder,
        tipo_operacao: str,  # 0=Entrada, 1=Saída
        chave_nfe: str,
        data_documento: date,
        valor_total: Decimal,
        valor_icms: Decimal,
    ):
        """Adiciona NF-e ao EFD-ICMS/IPI."""
        builder.add_registro(
            RegistroC100(
                ind_oper=tipo_operacao,
                ind_emit="0" if tipo_operacao == "1" else "1",
                cod_mod="55",
                chv_nfe=chave_nfe,
                num_doc=chave_nfe[25:34],
                ser=chave_nfe[22:25],
                dt_doc=data_documento,
                dt_e_s=data_documento,
                vl_doc=valor_total,
                vl_merc=valor_total,
                vl_bc_icms=valor_total,
                vl_icms=valor_icms,
            )
        )

    def finalizar_efd_icms(self, builder: EFDICMSIPIBuilder) -> str:
        """Finaliza e gera arquivo EFD-ICMS/IPI."""
        # Encerrar blocos
        builder.add_registro(Registro0990(qtd_lin_0=builder.contadores.get("Registro0000", 0) + 2))
        builder.add_registro(RegistroC001(ind_mov="0"))
        builder.add_registro(RegistroC990(qtd_lin_c=builder.contadores.get("RegistroC100", 0) + 2))
        builder.add_registro(Registro9001(ind_mov="0"))
        builder.add_registro(Registro9990(qtd_lin_9=3))
        builder.add_registro(Registro9999(qtd_lin=len(builder.registros) + 1))

        return builder.build()

    # -------------------------------------------------------------------------
    # EFD-REINF
    # -------------------------------------------------------------------------

    def criar_evento_reinf_r1000(self, contribuinte: ContribuinteREINF) -> str:
        """Cria evento R-1000 - Informações do Contribuinte."""
        return self.reinf_builder.build_r1000(contribuinte, self.ambiente)

    def criar_evento_reinf_r2010(
        self, contribuinte: ContribuinteREINF, servico: ServicoTomadoREINF, periodo: str
    ) -> str:
        """Cria evento R-2010 - Retenção Serviços Tomados."""
        return self.reinf_builder.build_r2010(contribuinte, servico, periodo, self.ambiente)

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Cria SSL context com certificado para mTLS."""
        ssl_context = ssl.create_default_context()

        if self.cert_path and self.cert_password:
            try:
                from .certificate_manager import CertificateManager

                cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
                cert_manager.load()

                # Escreve certificado e chave em arquivos temporários
                cert_pem = cert_manager.get_certificate_pem()
                key_pem = cert_manager.get_private_key_pem()

                with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as cert_file:
                    cert_file.write(cert_pem)
                    cert_file_path = cert_file.name

                with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as key_file:
                    key_file.write(key_pem)
                    key_file_path = key_file.name

                ssl_context.load_cert_chain(cert_file_path, key_file_path)

                # Cleanup
                import os

                os.unlink(cert_file_path)
                os.unlink(key_file_path)

                logger.info("SSL context configurado com certificado digital")

            except Exception as e:
                logger.warning(f"Erro ao carregar certificado: {e}. Usando SSL sem certificado cliente.")

        # Desabilita verificação de servidor em homologação
        if self.ambiente == "2":
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        return ssl_context

    def _assinar_evento_reinf(self, xml_evento: str) -> str:
        """Assina evento REINF com XMLDSig."""
        if not self.cert_path or not self.cert_password:
            raise ValueError("Certificado não configurado para assinatura")

        from .certificate_manager import CertificateManager

        cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
        cert_manager.load()

        # Parse XML
        xml_bytes = xml_evento.encode("utf-8") if isinstance(xml_evento, str) else xml_evento
        # Remove XML declaration se presente
        xml_str = xml_bytes.decode("utf-8")
        if xml_str.startswith("<?xml"):
            xml_str = xml_str.split("?>", 1)[1].strip()
        xml_bytes = xml_str.encode("utf-8")

        root = etree.fromstring(xml_bytes)

        # Encontra elemento a assinar (primeiro elemento filho de Reinf)
        root.nsmap.get(None, "http://www.reinf.esocial.gov.br/schemas/evt")

        # Procura elemento de evento
        for child in root:
            if "evt" in child.tag.lower():
                # Adiciona Id se não existir
                if child.get("id") is None:
                    id_evento = f"ID{hashlib.sha256(etree.tostring(child)).hexdigest()[:32].upper()}"
                    child.set("id", id_evento)
                break

        # Assina
        signer = XMLSigner(
            method=methods.enveloped,
            signature_algorithm="rsa-sha256",
            digest_algorithm="sha256",
            c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
        )

        signed_root = signer.sign(
            root,
            key=cert_manager._private_key_crypto,
            cert=[cert_manager._x509_cert],  # signxml espera lista de certificados
        )

        return etree.tostring(signed_root, encoding="unicode", pretty_print=False)

    def _criar_lote_reinf(self, eventos_assinados: list[str]) -> str:
        """Cria lote de eventos REINF para envio."""
        # Namespace REINF
        ns = "http://www.reinf.esocial.gov.br/schemas/envioLoteEventosAssincrono/v1_00_00"
        nsmap = {None: ns}

        root = etree.Element(f"{{{ns}}}Reinf", nsmap=nsmap)

        lote_eventos = etree.SubElement(root, f"{{{ns}}}envioLoteEventos")

        # ideContribuinte ao invés de ideTransmissor
        ide_contrib = etree.SubElement(lote_eventos, f"{{{ns}}}ideContribuinte")
        etree.SubElement(ide_contrib, f"{{{ns}}}tpInsc").text = "1"  # CNPJ
        etree.SubElement(ide_contrib, f"{{{ns}}}nrInsc").text = "35710481"  # Primeiros 8 dígitos do CNPJ

        eventos = etree.SubElement(lote_eventos, f"{{{ns}}}eventos")

        for idx, evt_xml in enumerate(eventos_assinados):
            evento = etree.SubElement(eventos, f"{{{ns}}}evento")
            # ID conforme padrão: ID + tipo inscrição + nr inscrição + sequencial
            evento.set("Id", f"ID1357104810001{idx + 1:05d}")

            # Parse evento e adiciona como subelemento
            evt_root = etree.fromstring(evt_xml.encode("utf-8"))
            evento.append(evt_root)

        xml_str = etree.tostring(root, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_str}'

    async def enviar_lote_reinf(self, eventos: list[str], assinar: bool = True) -> SPEDResult:
        """
        Envia lote de eventos REINF.

        Args:
            eventos: Lista de XMLs de eventos REINF
            assinar: Se True, assina eventos antes de enviar

        Returns:
            SPEDResult com resultado da transmissão
        """
        try:
            # Assina eventos se necessário
            eventos_para_envio = []
            for evt in eventos:
                if assinar:
                    evt_assinado = self._assinar_evento_reinf(evt)
                    eventos_para_envio.append(evt_assinado)
                else:
                    eventos_para_envio.append(evt)

            # Cria lote
            lote_xml = self._criar_lote_reinf(eventos_para_envio)

            # Determina endpoint
            ambiente_key = "producao" if self.ambiente == "1" else "producao_restrita"
            endpoint = REINF_ENDPOINTS[ambiente_key]["envio"]

            logger.info(f"Enviando lote REINF para {endpoint}")
            logger.debug(f"Lote XML: {lote_xml[:500]}...")

            # Configura SSL
            ssl_context = self._get_ssl_context()

            # Headers
            headers = {"Content-Type": "application/xml", "Accept": "application/xml"}

            # Envia requisição
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with (
                aiohttp.ClientSession(connector=connector) as session,
                session.post(
                    endpoint, data=lote_xml.encode("utf-8"), headers=headers, timeout=aiohttp.ClientTimeout(total=60)
                ) as response,
            ):
                response_text = await response.text()

                logger.info(f"Resposta REINF: HTTP {response.status}")
                logger.debug(f"Resposta body: {response_text[:500]}...")

                if response.status in (200, 201, 202):
                    # Parse resposta
                    resultado = self._parse_resposta_reinf(response_text)
                    return resultado
                else:
                    return SPEDResult(
                        sucesso=False, mensagem=f"Erro HTTP {response.status}: {response_text}", xml=lote_xml
                    )

        except Exception as e:
            logger.error(f"Erro ao enviar lote REINF: {e}", exc_info=True)
            return SPEDResult(
                sucesso=False, mensagem=f"Erro ao enviar: {str(e)}", xml=lote_xml if "lote_xml" in locals() else None
            )

    def _parse_resposta_reinf(self, response_xml: str) -> SPEDResult:
        """Parse da resposta do webservice REINF."""
        try:
            root = etree.fromstring(response_xml.encode("utf-8"))

            # Busca elementos de resposta
            # Namespace pode variar
            for ns in [
                "http://www.reinf.esocial.gov.br/schemas/retornoLoteEventosAssincrono/v1_00_00",
                "http://www.reinf.esocial.gov.br/schemas/retornoLoteEventos/v1_00_00",
            ]:
                # Tenta encontrar status
                status = root.find(f".//{{{ns}}}cdStatus")
                desc_status = root.find(f".//{{{ns}}}descStatus")
                protocolo = root.find(f".//{{{ns}}}protocoloEnvio") or root.find(f".//{{{ns}}}nrProtEnvio")

                if status is not None:
                    cod_status = status.text
                    mensagem = desc_status.text if desc_status is not None else "Sem descrição"
                    prot = protocolo.text if protocolo is not None else None

                    # Status 1 = Sucesso
                    sucesso = cod_status == "1"

                    return SPEDResult(
                        sucesso=sucesso, mensagem=f"Status {cod_status}: {mensagem}", protocolo=prot, xml=response_xml
                    )

            # Tenta parse genérico
            return SPEDResult(sucesso=True, mensagem="Resposta recebida (parse parcial)", xml=response_xml)

        except Exception as e:
            return SPEDResult(sucesso=False, mensagem=f"Erro ao processar resposta: {e}", xml=response_xml)

    async def consultar_lote_reinf(self, protocolo: str) -> SPEDResult:
        """
        Consulta resultado de lote REINF pelo protocolo.

        Args:
            protocolo: Número do protocolo de envio

        Returns:
            SPEDResult com resultado da consulta
        """
        try:
            # Determina endpoint
            ambiente_key = "producao" if self.ambiente == "1" else "producao_restrita"
            endpoint = REINF_ENDPOINTS[ambiente_key]["consulta"]

            # Monta XML de consulta
            nsmap = {None: "http://www.reinf.esocial.gov.br/schemas/consultaLoteEventos/v1_00_00"}

            root = etree.Element(
                "{http://www.reinf.esocial.gov.br/schemas/consultaLoteEventos/v1_00_00}Reinf", nsmap=nsmap
            )
            consulta = etree.SubElement(root, "consultaLoteEventos")
            etree.SubElement(consulta, "protocoloEnvio").text = protocolo

            consulta_str = etree.tostring(root, encoding="unicode")
            consulta_xml = f'<?xml version="1.0" encoding="UTF-8"?>{consulta_str}'

            logger.info(f"Consultando lote REINF protocolo {protocolo}")

            # Configura SSL
            ssl_context = self._get_ssl_context()

            headers = {"Content-Type": "application/xml", "Accept": "application/xml"}

            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with (
                aiohttp.ClientSession(connector=connector) as session,
                session.post(
                    endpoint,
                    data=consulta_xml.encode("utf-8"),
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response,
            ):
                response_text = await response.text()

                logger.info(f"Resposta consulta REINF: HTTP {response.status}")

                if response.status == 200:
                    return self._parse_resposta_reinf(response_text)
                else:
                    return SPEDResult(sucesso=False, mensagem=f"Erro HTTP {response.status}: {response_text}")

        except Exception as e:
            logger.error(f"Erro ao consultar lote REINF: {e}", exc_info=True)
            return SPEDResult(sucesso=False, mensagem=f"Erro na consulta: {str(e)}")

    async def enviar_reinf(self, xml_evento: str) -> SPEDResult:
        """
        Envia evento REINF individual.

        Wrapper para enviar_lote_reinf com um único evento.
        """
        return await self.enviar_lote_reinf([xml_evento], assinar=True)


logger.info("Módulo SPEDManager carregado")
