"""
Module: ESocialManager
Description: Integração com eSocial - Sistema de Escrituração Digital
             das Obrigações Fiscais, Previdenciárias e Trabalhistas
Author: Conecta PRO
Date: 2026-01-17

Portal: https://www.gov.br/esocial
Documentacao: https://www.gov.br/esocial/pt-br/documentacao-tecnica

eSocial:
- Obrigatório para todas as empresas com empregados
- Eventos de admissão, demissão, folha, etc.
- Webservice REST com XML assinado
- Certificado digital ICP-Brasil obrigatório
"""

import logging
import re
import xml.etree.ElementTree as ET  # noqa: S405
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4
from xml.dom import minidom  # noqa: S408
from xml.etree.ElementTree import Element  # noqa: S405

logger = logging.getLogger(__name__)


# Endpoints eSocial
ESOCIAL_ENDPOINTS = {
    "producao": {
        "envio_lote": "https://webservices.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc",
        "consulta_lote": "https://webservices.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc",
    },
    "producao_restrita": {
        "envio_lote": "https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc",
        "consulta_lote": "https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc",
    },
}


class GrupoEvento(StrEnum):
    """Grupos de eventos do eSocial."""

    TABELAS = "1"  # Eventos de Tabelas (S-1000 a S-1080)
    NAO_PERIODICOS = "2"  # Eventos Não Periódicos (S-2190 a S-2420)
    PERIODICOS = "3"  # Eventos Periódicos (S-1200 a S-1299)


class TipoEvento(StrEnum):
    """Tipos de eventos do eSocial."""

    # Tabelas
    S1000 = "S-1000"  # Informações do Empregador
    S1005 = "S-1005"  # Tabela de Estabelecimentos
    S1010 = "S-1010"  # Tabela de Rubricas
    S1020 = "S-1020"  # Tabela de Lotações Tributárias
    S1070 = "S-1070"  # Tabela de Processos Administrativos/Judiciais

    # Não Periódicos
    S2190 = "S-2190"  # Registro Preliminar de Trabalhador
    S2200 = "S-2200"  # Cadastramento Inicial / Admissão
    S2205 = "S-2205"  # Alteração de Dados Cadastrais
    S2206 = "S-2206"  # Alteração de Contrato de Trabalho
    S2210 = "S-2210"  # CAT - Comunicação de Acidente de Trabalho
    S2220 = "S-2220"  # Monitoramento da Saúde do Trabalhador
    S2230 = "S-2230"  # Afastamento Temporário
    S2240 = "S-2240"  # Condições Ambientais do Trabalho
    S2298 = "S-2298"  # Reintegração
    S2299 = "S-2299"  # Desligamento
    S2300 = "S-2300"  # Trabalhador Sem Vínculo (início)
    S2306 = "S-2306"  # Trabalhador Sem Vínculo (alteração)
    S2399 = "S-2399"  # Trabalhador Sem Vínculo (término)

    # Periódicos
    S1200 = "S-1200"  # Remuneração do Trabalhador
    S1202 = "S-1202"  # Remuneração de Servidor Público
    S1207 = "S-1207"  # Benefícios Previdenciários
    S1210 = "S-1210"  # Pagamentos de Rendimentos
    S1260 = "S-1260"  # Comercialização da Produção Rural
    S1270 = "S-1270"  # Contratação de Trabalhadores Avulsos
    S1280 = "S-1280"  # Informações Complementares aos Eventos Periódicos
    S1298 = "S-1298"  # Reabertura dos Eventos Periódicos
    S1299 = "S-1299"  # Fechamento dos Eventos Periódicos


class TipoInscricao(StrEnum):
    """Tipo de inscrição."""

    CNPJ = "1"
    CPF = "2"
    CAEPF = "3"
    CNO = "4"


class NaturezaJuridica(StrEnum):
    """Natureza jurídica simplificada."""

    PESSOA_JURIDICA = "1"
    PESSOA_FISICA = "2"
    ORGAO_PUBLICO = "3"


class CategoriaTabalhador(StrEnum):
    """Categoria do trabalhador."""

    EMPREGADO = "101"
    EMPREGADO_RURAL = "102"
    EMPREGADO_APRENDIZ = "103"
    EMPREGADO_DOMESTICO = "104"
    TRABALHADOR_TEMPORARIO = "106"
    DIRETOR_NAO_EMPREGADO = "721"
    CONTRIBUINTE_INDIVIDUAL = "701"
    ESTAGIARIO = "901"
    MEI = "741"


@dataclass
class Empregador:
    """Dados do empregador."""

    tipo_inscricao: TipoInscricao
    numero_inscricao: str  # CNPJ ou CPF
    razao_social: str
    natureza_juridica: str  # Código tabela IBGE
    classificacao_tributaria: str
    ind_coop: str = "0"  # 0=Não é cooperativa
    ind_constr: str = "0"  # 0=Não é construtora
    ind_opt_reg_eletron: str = "0"  # Opção pelo registro eletrônico
    cnae_preponderante: str | None = None
    endereco_logradouro: str = ""
    endereco_numero: str = ""
    endereco_bairro: str = ""
    endereco_cep: str = ""
    endereco_municipio: str = ""
    endereco_uf: str = ""
    telefone: str | None = None
    email: str | None = None


@dataclass
class Trabalhador:
    """Dados do trabalhador."""

    cpf: str
    nome: str
    data_nascimento: date
    sexo: str  # M ou F
    raca_cor: str  # 1=Branca, 2=Preta, 3=Parda, 4=Amarela, 5=Indígena, 6=Não informado
    estado_civil: str  # 1=Solteiro, 2=Casado, 3=Divorciado, 4=Separado, 5=Viúvo
    grau_instrucao: str  # 01 a 12 (tabela)
    nome_social: str | None = None
    nacionalidade: str = "105"  # Brasil
    pis_pasep: str | None = None
    ctps_numero: str | None = None
    ctps_serie: str | None = None
    ctps_uf: str | None = None
    rg_numero: str | None = None
    rg_orgao: str | None = None
    rg_uf: str | None = None
    endereco_logradouro: str = ""
    endereco_numero: str = ""
    endereco_bairro: str = ""
    endereco_cep: str = ""
    endereco_municipio: str = ""
    endereco_uf: str = ""
    telefone: str | None = None
    email: str | None = None

    # Dados bancários
    banco: str | None = None
    agencia: str | None = None
    conta: str | None = None
    tipo_conta: str | None = None  # 1=Conta corrente, 2=Conta poupança


@dataclass
class Contrato:
    """Dados do contrato de trabalho."""

    matricula: str
    categoria: CategoriaTabalhador
    data_admissao: date
    tipo_regime_trabalhista: str  # 1=CLT, 2=Estatutário
    tipo_regime_previdenciario: str  # 1=RGPS, 2=RPPS
    tipo_contrato: str  # 1=Prazo indeterminado, 2=Prazo determinado
    cargo: str
    cargo_cbo: str  # Código CBO
    salario: Decimal
    unidade_salario: (
        str  # 1=Por hora, 2=Por dia, 3=Por semana, 4=Por quinzena, 5=Por mês, 6=Por tarefa, 7=Não aplicável
    )
    jornada_semanal: int  # Horas semanais
    tipo_jornada: str  # 1=Integral, 2=Parcial
    data_termino: date | None = None  # Se prazo determinado
    local_trabalho_tipo: str = "1"  # 1=Estabelecimento do empregador
    local_trabalho_cnpj: str | None = None
    desc_salario_variavel: str | None = None


@dataclass
class EventoeSocial:
    """Evento do eSocial."""

    id: UUID = field(default_factory=uuid4)
    tipo: TipoEvento = TipoEvento.S1000
    grupo: GrupoEvento = GrupoEvento.TABELAS
    empregador: Empregador = None
    trabalhador: Trabalhador | None = None
    contrato: Contrato | None = None
    data_evento: datetime = None
    periodo_apuracao: str | None = None  # AAAA-MM
    numero_recibo: str | None = None  # Retorno após envio
    protocolo: str | None = None
    status: str = "pendente"

    def __post_init__(self):
        if self.data_evento is None:
            self.data_evento = datetime.now()


class ESocialXMLBuilder:
    """Builder de XML para eventos do eSocial."""

    NAMESPACE = "http://www.esocial.gov.br/schema/evt"
    VERSION = "S-1.2"  # Versão simplificada do eSocial

    def build_evento(self, evento: EventoeSocial, ambiente: str = "2") -> str:
        """
        Constrói XML do evento eSocial.

        Args:
            evento: Dados do evento
            ambiente: 1=Produção, 2=Produção Restrita

        Returns:
            XML do evento
        """
        # ID do evento: formato específico do eSocial
        # ID + tipo_insc(1) + nr_insc(14) + AAAAMMDDHHMMSS(14) + seq(5) = 36 chars
        nr_insc = re.sub(r"[^\d]", "", evento.empregador.numero_inscricao).zfill(14)
        timestamp = evento.data_evento.strftime("%Y%m%d%H%M%S")
        seq = "00001"
        evento_id = f"ID{evento.empregador.tipo_inscricao.value}{nr_insc}{timestamp}{seq}"

        # Criar estrutura base
        root = ET.Element("eSocial", xmlns=self.NAMESPACE)

        if evento.tipo == TipoEvento.S2200:
            return self._build_s2200(root, evento, evento_id, ambiente)
        elif evento.tipo == TipoEvento.S2299:
            return self._build_s2299(root, evento, evento_id, ambiente)
        elif evento.tipo == TipoEvento.S1200:
            return self._build_s1200(root, evento, evento_id, ambiente)
        elif evento.tipo == TipoEvento.S1000:
            return self._build_s1000(root, evento, evento_id, ambiente)
        else:
            # Evento genérico (placeholder)
            return self._build_generico(root, evento, evento_id, ambiente)

    def _build_s1000(self, root: Element, evento: EventoeSocial, evento_id: str, ambiente: str) -> str:
        """Constrói S-1000 - Informações do Empregador."""
        evt = ET.SubElement(root, "evtInfoEmpregador", Id=evento_id)

        ide = ET.SubElement(evt, "ideEvento")
        ET.SubElement(ide, "tpAmb").text = ambiente
        ET.SubElement(ide, "procEmi").text = "1"  # Aplicativo do empregador
        ET.SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        ide_empregador = ET.SubElement(evt, "ideEmpregador")
        ET.SubElement(ide_empregador, "tpInsc").text = evento.empregador.tipo_inscricao.value
        ET.SubElement(ide_empregador, "nrInsc").text = re.sub(r"[^\d]", "", evento.empregador.numero_inscricao)[:8]

        info = ET.SubElement(evt, "infoEmpregador")
        inclusao = ET.SubElement(info, "inclusao")
        ide_periodo = ET.SubElement(inclusao, "idePeriodo")
        ET.SubElement(ide_periodo, "iniValid").text = datetime.now().strftime("%Y-%m")

        info_cad = ET.SubElement(inclusao, "infoCadastro")
        ET.SubElement(info_cad, "classTrib").text = evento.empregador.classificacao_tributaria
        ET.SubElement(info_cad, "indCoop").text = evento.empregador.ind_coop
        ET.SubElement(info_cad, "indConstr").text = evento.empregador.ind_constr
        ET.SubElement(info_cad, "indOptRegEletron").text = evento.empregador.ind_opt_reg_eletron
        ET.SubElement(info_cad, "nmRazao").text = evento.empregador.razao_social
        ET.SubElement(info_cad, "natJurid").text = evento.empregador.natureza_juridica

        return self._prettify(root)

    def _build_s2200(self, root: Element, evento: EventoeSocial, evento_id: str, ambiente: str) -> str:
        """Constrói S-2200 - Admissão de Trabalhador."""
        evt = ET.SubElement(root, "evtAdmissao", Id=evento_id)

        # ideEvento
        ide = ET.SubElement(evt, "ideEvento")
        ET.SubElement(ide, "indRetif").text = "1"  # Original
        ET.SubElement(ide, "tpAmb").text = ambiente
        ET.SubElement(ide, "procEmi").text = "1"
        ET.SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        # ideEmpregador
        ide_empregador = ET.SubElement(evt, "ideEmpregador")
        ET.SubElement(ide_empregador, "tpInsc").text = evento.empregador.tipo_inscricao.value
        ET.SubElement(ide_empregador, "nrInsc").text = re.sub(r"[^\d]", "", evento.empregador.numero_inscricao)[:8]

        # trabalhador
        trab = evento.trabalhador
        if trab:
            trabalhador = ET.SubElement(evt, "trabalhador")
            ET.SubElement(trabalhador, "cpfTrab").text = re.sub(r"[^\d]", "", trab.cpf)
            ET.SubElement(trabalhador, "nmTrab").text = trab.nome
            ET.SubElement(trabalhador, "sexo").text = trab.sexo
            ET.SubElement(trabalhador, "racaCor").text = trab.raca_cor
            ET.SubElement(trabalhador, "estCiv").text = trab.estado_civil
            ET.SubElement(trabalhador, "grauInstr").text = trab.grau_instrucao

            nascimento = ET.SubElement(trabalhador, "nascimento")
            ET.SubElement(nascimento, "dtNascto").text = trab.data_nascimento.strftime("%Y-%m-%d")
            ET.SubElement(nascimento, "paisNascto").text = trab.nacionalidade
            ET.SubElement(nascimento, "paisNac").text = trab.nacionalidade

            # Documentos
            docs = ET.SubElement(trabalhador, "documentos")
            if trab.ctps_numero:
                ctps = ET.SubElement(docs, "CTPS")
                ET.SubElement(ctps, "nrCtps").text = trab.ctps_numero
                ET.SubElement(ctps, "serieCtps").text = trab.ctps_serie or ""
                ET.SubElement(ctps, "ufCtps").text = trab.ctps_uf or ""

            # Endereço
            endereco = ET.SubElement(trabalhador, "endereco")
            brasil = ET.SubElement(endereco, "brasil")
            ET.SubElement(brasil, "tpLograd").text = "R"  # Rua
            ET.SubElement(brasil, "dscLograd").text = trab.endereco_logradouro
            ET.SubElement(brasil, "nrLograd").text = trab.endereco_numero
            ET.SubElement(brasil, "bairro").text = trab.endereco_bairro
            ET.SubElement(brasil, "cep").text = re.sub(r"[^\d]", "", trab.endereco_cep)
            ET.SubElement(brasil, "codMunic").text = trab.endereco_municipio
            ET.SubElement(brasil, "uf").text = trab.endereco_uf

        # vínculo
        contrato = evento.contrato
        if contrato:
            vinculo = ET.SubElement(evt, "vinculo")
            ET.SubElement(vinculo, "matricula").text = contrato.matricula
            ET.SubElement(vinculo, "tpRegTrab").text = contrato.tipo_regime_trabalhista
            ET.SubElement(vinculo, "tpRegPrev").text = contrato.tipo_regime_previdenciario
            ET.SubElement(vinculo, "cadIni").text = "S"  # Cadastramento inicial
            ET.SubElement(vinculo, "dtAdm").text = contrato.data_admissao.strftime("%Y-%m-%d")
            ET.SubElement(vinculo, "tpAdmissao").text = "1"  # Normal

            info_contrato = ET.SubElement(vinculo, "infoContrato")
            ET.SubElement(info_contrato, "nmCargo").text = contrato.cargo
            ET.SubElement(info_contrato, "CBOCargo").text = contrato.cargo_cbo
            ET.SubElement(info_contrato, "dtIngrCargo").text = contrato.data_admissao.strftime("%Y-%m-%d")

            remuneracao = ET.SubElement(info_contrato, "remuneracao")
            ET.SubElement(remuneracao, "vrSalFx").text = f"{contrato.salario:.2f}"
            ET.SubElement(remuneracao, "undSalFixo").text = contrato.unidade_salario

            duracao = ET.SubElement(info_contrato, "duracao")
            ET.SubElement(duracao, "tpContr").text = contrato.tipo_contrato
            if contrato.data_termino:
                ET.SubElement(duracao, "dtTerm").text = contrato.data_termino.strftime("%Y-%m-%d")

        return self._prettify(root)

    def _build_s2299(self, root: Element, evento: EventoeSocial, evento_id: str, ambiente: str) -> str:
        """Constrói S-2299 - Desligamento."""
        evt = ET.SubElement(root, "evtDeslig", Id=evento_id)

        ide = ET.SubElement(evt, "ideEvento")
        ET.SubElement(ide, "indRetif").text = "1"
        ET.SubElement(ide, "tpAmb").text = ambiente
        ET.SubElement(ide, "procEmi").text = "1"
        ET.SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        ide_empregador = ET.SubElement(evt, "ideEmpregador")
        ET.SubElement(ide_empregador, "tpInsc").text = evento.empregador.tipo_inscricao.value
        ET.SubElement(ide_empregador, "nrInsc").text = re.sub(r"[^\d]", "", evento.empregador.numero_inscricao)[:8]

        if evento.trabalhador:
            ide_vinculo = ET.SubElement(evt, "ideVinculo")
            ET.SubElement(ide_vinculo, "cpfTrab").text = re.sub(r"[^\d]", "", evento.trabalhador.cpf)
            ET.SubElement(ide_vinculo, "matricula").text = evento.contrato.matricula if evento.contrato else ""

        return self._prettify(root)

    def _build_s1200(self, root: Element, evento: EventoeSocial, evento_id: str, ambiente: str) -> str:
        """Constrói S-1200 - Remuneração do Trabalhador."""
        evt = ET.SubElement(root, "evtRemun", Id=evento_id)

        ide = ET.SubElement(evt, "ideEvento")
        ET.SubElement(ide, "indRetif").text = "1"
        ET.SubElement(ide, "perApur").text = evento.periodo_apuracao or datetime.now().strftime("%Y-%m")
        ET.SubElement(ide, "tpAmb").text = ambiente
        ET.SubElement(ide, "procEmi").text = "1"
        ET.SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        ide_empregador = ET.SubElement(evt, "ideEmpregador")
        ET.SubElement(ide_empregador, "tpInsc").text = evento.empregador.tipo_inscricao.value
        ET.SubElement(ide_empregador, "nrInsc").text = re.sub(r"[^\d]", "", evento.empregador.numero_inscricao)[:8]

        if evento.trabalhador:
            ide_trab = ET.SubElement(evt, "ideTrabalhador")
            ET.SubElement(ide_trab, "cpfTrab").text = re.sub(r"[^\d]", "", evento.trabalhador.cpf)

        return self._prettify(root)

    def _build_generico(self, root: Element, evento: EventoeSocial, evento_id: str, ambiente: str) -> str:
        """Constrói evento genérico (placeholder)."""
        evt = ET.SubElement(root, f"evt{evento.tipo.value.replace('-', '')}", Id=evento_id)

        ide = ET.SubElement(evt, "ideEvento")
        ET.SubElement(ide, "tpAmb").text = ambiente
        ET.SubElement(ide, "procEmi").text = "1"
        ET.SubElement(ide, "verProc").text = "CONECTA_PRO_1.0"

        ide_empregador = ET.SubElement(evt, "ideEmpregador")
        ET.SubElement(ide_empregador, "tpInsc").text = evento.empregador.tipo_inscricao.value
        ET.SubElement(ide_empregador, "nrInsc").text = re.sub(r"[^\d]", "", evento.empregador.numero_inscricao)[:8]

        return self._prettify(root)

    def _prettify(self, elem: Element) -> str:
        """Formata XML."""
        rough_string = ET.tostring(elem, encoding="unicode")
        reparsed = minidom.parseString(rough_string)  # noqa: S318 - Apenas formata XML gerado internamente
        return reparsed.toprettyxml(indent="  ")


@dataclass
class ESocialResult:
    """Resultado de operação com eSocial."""

    sucesso: bool
    mensagem: str
    protocolo: str | None = None
    numero_recibo: str | None = None
    codigo_retorno: str | None = None
    xml_retorno: str | None = None
    tempo_resposta: float = 0.0


class ESocialManager:
    """
    Gerenciador de eventos do eSocial.

    Coordena criação, validação e envio de eventos
    do eSocial para o governo.
    """

    def __init__(
        self,
        ambiente: str = "2",
        cert_path: str | None = None,
        cert_password: str | None = None,
    ):
        """
        Inicializa o gerenciador eSocial.

        Args:
            ambiente: 1=Produção, 2=Produção Restrita
            cert_path: Caminho do certificado
            cert_password: Senha do certificado
        """
        self.ambiente = ambiente
        self.cert_path = cert_path
        self.cert_password = cert_password

        env_key = "producao" if ambiente == "1" else "producao_restrita"
        self.endpoints = ESOCIAL_ENDPOINTS[env_key]
        self.xml_builder = ESocialXMLBuilder()

        logger.info(f"ESocialManager inicializado: Ambiente={'Produção' if ambiente == '1' else 'Produção Restrita'}")

    def criar_evento_admissao(
        self, empregador: Empregador, trabalhador: Trabalhador, contrato: Contrato
    ) -> EventoeSocial:
        """Cria evento S-2200 - Admissão."""
        return EventoeSocial(
            tipo=TipoEvento.S2200,
            grupo=GrupoEvento.NAO_PERIODICOS,
            empregador=empregador,
            trabalhador=trabalhador,
            contrato=contrato,
        )

    def criar_evento_desligamento(
        self, empregador: Empregador, trabalhador: Trabalhador, contrato: Contrato, data_desligamento: date, motivo: str
    ) -> EventoeSocial:
        """Cria evento S-2299 - Desligamento."""
        return EventoeSocial(
            tipo=TipoEvento.S2299,
            grupo=GrupoEvento.NAO_PERIODICOS,
            empregador=empregador,
            trabalhador=trabalhador,
            contrato=contrato,
        )

    def criar_evento_remuneracao(
        self,
        empregador: Empregador,
        trabalhador: Trabalhador,
        periodo: str,  # AAAA-MM
    ) -> EventoeSocial:
        """Cria evento S-1200 - Remuneração."""
        return EventoeSocial(
            tipo=TipoEvento.S1200,
            grupo=GrupoEvento.PERIODICOS,
            empregador=empregador,
            trabalhador=trabalhador,
            periodo_apuracao=periodo,
        )

    def gerar_xml(self, evento: EventoeSocial) -> str:
        """Gera XML do evento."""
        return self.xml_builder.build_evento(evento, self.ambiente)

    def gerar_lote(self, eventos: list, grupo: GrupoEvento) -> str:
        """
        Gera lote de eventos para envio.

        Args:
            eventos: Lista de XMLs de eventos assinados
            grupo: Grupo do lote (1=Tabelas, 2=Não Periódicos, 3=Periódicos)

        Returns:
            XML do lote
        """
        from datetime import datetime

        # ID do lote: ID + tp inscrição + nr inscrição + timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        f"ID1{self._nr_insc[:14]}{timestamp}"

        # Montar eventos - cada evento precisa de Id
        eventos_xml = ""
        for idx, evt in enumerate(eventos):
            # Extrair Id do evento do XML
            id_match = re.search(r'Id="([^"]+)"', evt)
            evt_id = id_match.group(1) if id_match else f"ID{idx + 1:010d}"
            eventos_xml += f'<evento Id="{evt_id}">{evt}</evento>'

        lote = f'''<eSocial xmlns="http://www.esocial.gov.br/schema/lote/eventos/envio/v1_1_1">
<envioLoteEventos grupo="{grupo.value}">
<ideEmpregador>
<tpInsc>1</tpInsc>
<nrInsc>{self._nr_insc[:8]}</nrInsc>
</ideEmpregador>
<ideTransmissor>
<tpInsc>1</tpInsc>
<nrInsc>{self._nr_insc}</nrInsc>
</ideTransmissor>
<eventos>{eventos_xml}</eventos>
</envioLoteEventos>
</eSocial>'''

        return lote

    async def enviar_evento(self, evento: EventoeSocial) -> ESocialResult:
        """
        Envia evento para o eSocial.

        Args:
            evento: Evento a ser enviado

        Returns:
            Resultado do envio
        """
        return await self.enviar_lote([evento])

    async def enviar_lote(self, eventos: list) -> ESocialResult:
        """
        Envia lote de eventos para o eSocial.

        Args:
            eventos: Lista de EventoeSocial

        Returns:
            Resultado do envio
        """
        import ssl
        import tempfile
        import time

        import httpx

        start_time = time.time()

        try:
            if not self.cert_path:
                return ESocialResult(sucesso=False, mensagem="Certificado digital não configurado")

            # Importar dependências
            from .certificate_manager import CertificateManager
            from .xml_signer import SignatureType, XMLSigner

            # Carregar certificado
            cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
            cert_manager.load()

            signer = XMLSigner(cert_manager)

            # Gerar e assinar cada evento
            eventos_assinados = []
            primeiro_evento = eventos[0] if eventos else None
            grupo = primeiro_evento.grupo if primeiro_evento else GrupoEvento.NAO_PERIODICOS

            # Guardar nr_insc para o lote
            if primeiro_evento and primeiro_evento.empregador:
                self._nr_insc = re.sub(r"[^\d]", "", primeiro_evento.empregador.numero_inscricao)
            else:
                self._nr_insc = "00000000000000"

            for evento in eventos:
                xml = self.gerar_xml(evento)

                # Extrair ID do evento para assinatura
                id_match = re.search(r'Id="([^"]+)"', xml)
                if id_match:
                    ref_uri = f"#{id_match.group(1)}"
                    xml_assinado = signer.sign(xml, SignatureType.ESOCIAL, ref_uri)
                    # Remover declaração XML
                    xml_assinado = re.sub(r"<\?xml[^>]+\?>\s*", "", xml_assinado)
                    eventos_assinados.append(xml_assinado)
                else:
                    eventos_assinados.append(xml)

            # Montar lote
            lote_xml = self.gerar_lote(eventos_assinados, grupo)

            # Configurar SSL
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
                f.write(cert_manager.get_certificate_pem())
                cert_pem = f.name

            with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
                f.write(cert_manager.get_private_key_pem())
                key_pem = f.name

            ssl_context.load_cert_chain(cert_pem, key_pem)

            # Montar envelope SOAP 1.1
            url = self.endpoints["envio_lote"]
            wsdl_ns = "http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/v1_1_0"
            soap_action = f"{wsdl_ns}/ServicoEnviarLoteEventos/EnviarLoteEventos"

            envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
<soap:Body>
<EnviarLoteEventos xmlns="{wsdl_ns}">
<loteEventos>{lote_xml}</loteEventos>
</EnviarLoteEventos>
</soap:Body>
</soap:Envelope>'''

            # Enviar
            async with httpx.AsyncClient(verify=ssl_context, timeout=60.0) as client:
                response = await client.post(
                    url,
                    content=envelope.encode("utf-8"),
                    headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": soap_action},
                )

            tempo = time.time() - start_time

            # Limpar arquivos temporários
            import os

            os.unlink(cert_pem)
            os.unlink(key_pem)

            # Processar resposta
            if response.status_code == 200:
                xml_retorno = response.text

                # Extrair informações
                protocolo_match = re.search(r"<protocoloEnvio>([^<]+)</protocoloEnvio>", xml_retorno)
                status_match = re.search(r"<cdResposta>(\d+)</cdResposta>", xml_retorno)
                msg_match = re.search(r"<descResposta>([^<]+)</descResposta>", xml_retorno)

                protocolo = protocolo_match.group(1) if protocolo_match else None
                codigo = status_match.group(1) if status_match else None
                mensagem = msg_match.group(1) if msg_match else "Resposta processada"

                # Código 201 = Lote recebido com sucesso
                sucesso = codigo in ["201", "202"]

                return ESocialResult(
                    sucesso=sucesso,
                    mensagem=mensagem,
                    protocolo=protocolo,
                    codigo_retorno=codigo,
                    xml_retorno=xml_retorno,
                    tempo_resposta=tempo,
                )
            else:
                return ESocialResult(
                    sucesso=False,
                    mensagem=f"Erro HTTP {response.status_code}",
                    xml_retorno=response.text,
                    tempo_resposta=tempo,
                )

        except Exception as e:
            logger.error(f"Erro ao enviar lote eSocial: {e}")
            return ESocialResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)

    async def consultar_lote(self, protocolo: str) -> ESocialResult:
        """
        Consulta resultado do processamento de um lote.

        Args:
            protocolo: Protocolo de envio retornado

        Returns:
            Resultado da consulta
        """
        import ssl
        import tempfile
        import time

        import httpx

        start_time = time.time()

        try:
            if not self.cert_path:
                return ESocialResult(sucesso=False, mensagem="Certificado digital não configurado")

            from .certificate_manager import CertificateManager

            cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
            cert_manager.load()

            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
                f.write(cert_manager.get_certificate_pem())
                cert_pem = f.name

            with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
                f.write(cert_manager.get_private_key_pem())
                key_pem = f.name

            ssl_context.load_cert_chain(cert_pem, key_pem)

            url = self.endpoints["consulta_lote"]
            wsdl_ns = (
                "http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/consulta/retornoProcessamento/v1_1_0"
            )

            envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
<soap:Header/>
<soap:Body>
<ConsultarLoteEventos xmlns="{wsdl_ns}">
<consulta>
<protocoloEnvio>{protocolo}</protocoloEnvio>
</consulta>
</ConsultarLoteEventos>
</soap:Body>
</soap:Envelope>'''

            async with httpx.AsyncClient(verify=ssl_context, timeout=60.0) as client:
                response = await client.post(
                    url,
                    content=envelope.encode("utf-8"),
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": f"{wsdl_ns}/ConsultarLoteEventos",
                    },
                )

            tempo = time.time() - start_time

            import os

            os.unlink(cert_pem)
            os.unlink(key_pem)

            if response.status_code == 200:
                xml_retorno = response.text

                # Extrair recibos
                recibos = re.findall(r"<nrRecibo>([^<]+)</nrRecibo>", xml_retorno)

                return ESocialResult(
                    sucesso=True,
                    mensagem=f"Consulta realizada. {len(recibos)} recibo(s) encontrado(s).",
                    protocolo=protocolo,
                    numero_recibo=recibos[0] if recibos else None,
                    xml_retorno=xml_retorno,
                    tempo_resposta=tempo,
                )
            else:
                return ESocialResult(sucesso=False, mensagem=f"Erro HTTP {response.status_code}", tempo_resposta=tempo)

        except Exception as e:
            logger.error(f"Erro ao consultar lote eSocial: {e}")
            return ESocialResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)


logger.info("Módulo ESocialManager carregado")
