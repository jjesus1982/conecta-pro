"""
SPED Fiscal - EFD ICMS/IPI (Escrituração Fiscal Digital).

Portal: https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/sped-sistema-publico-de-escrituracao-digital/efd-icms-ipi
Documentação: Guia Prático EFD ICMS/IPI

A EFD ICMS/IPI é obrigatória para contribuintes do ICMS e IPI.
Empresas do Simples Nacional estão dispensadas.

Blocos do arquivo:
- Bloco 0: Abertura, Identificação e Referências
- Bloco C: Documentos Fiscais I (Mercadorias - NF-e, etc)
- Bloco D: Documentos Fiscais II (Serviços de Transporte - CT-e)
- Bloco E: Apuração do ICMS e do IPI
- Bloco G: Controle do Crédito de ICMS do Ativo Permanente - CIAP
- Bloco H: Inventário Físico
- Bloco K: Controle da Produção e do Estoque
- Bloco 1: Outras Informações
- Bloco 9: Controle e Encerramento do Arquivo
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class FinalidadeArquivo(StrEnum):
    """Finalidade do arquivo SPED."""

    ORIGINAL = "0"
    SUBSTITUTO = "1"


class PerfilArquivo(StrEnum):
    """Perfil de apresentação do arquivo."""

    PERFIL_A = "A"  # Completo
    PERFIL_B = "B"  # Intermediário
    PERFIL_C = "C"  # Simplificado


class TipoAtividade(StrEnum):
    """Indicador de tipo de atividade."""

    INDUSTRIAL = "0"
    OUTROS = "1"


class IndicadorMovimento(StrEnum):
    """Indicador de movimento."""

    COM_DADOS = "0"
    SEM_DADOS = "1"


@dataclass
class Participante:
    """Participante (fornecedor/cliente)."""

    codigo: str
    nome: str
    cnpj_cpf: str
    inscricao_estadual: str | None = None
    codigo_municipio: str | None = None
    uf: str | None = None
    endereco: str | None = None
    cep: str | None = None


def _d(v) -> Decimal:
    """Decimal tolerante — campo nulo do banco vira zero, não explode o arquivo."""
    try:
        return Decimal(str(v if v is not None else 0))
    except (ArithmeticError, ValueError):
        return Decimal("0")


def _n(v) -> str:
    return str(_d(v))


@dataclass
class Produto:
    """Produto/Item."""

    codigo: str
    descricao: str
    codigo_barras: str | None = None
    unidade: str = "UN"
    tipo_item: str = "00"  # 00=Mercadoria, 01=Matéria-prima, etc
    ncm: str | None = None
    cest: str | None = None
    aliquota_icms: Decimal = Decimal("0")


@dataclass
class DocumentoFiscal:
    """Documento fiscal (NF-e, CT-e, etc)."""

    tipo: str  # 55=NF-e, 57=CT-e, 65=NFC-e
    chave: str
    numero: str
    serie: str
    data_emissao: date
    data_entrada_saida: date
    participante: Participante
    valor_total: Decimal
    valor_icms: Decimal = Decimal("0")
    valor_ipi: Decimal = Decimal("0")
    valor_pis: Decimal = Decimal("0")
    valor_cofins: Decimal = Decimal("0")
    cfop: str = ""
    itens: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ApuracaoICMS:
    """Apuração de ICMS do período."""

    periodo: str  # YYYY-MM
    valor_debitos: Decimal = Decimal("0")
    valor_creditos: Decimal = Decimal("0")
    valor_estorno_debitos: Decimal = Decimal("0")
    valor_estorno_creditos: Decimal = Decimal("0")
    valor_saldo_credor_anterior: Decimal = Decimal("0")
    valor_ajustes_debito: Decimal = Decimal("0")
    valor_ajustes_credito: Decimal = Decimal("0")

    @property
    def saldo_apurado(self) -> Decimal:
        debitos = self.valor_debitos + self.valor_estorno_creditos + self.valor_ajustes_debito
        creditos = (
            self.valor_creditos
            + self.valor_estorno_debitos
            + self.valor_ajustes_credito
            + self.valor_saldo_credor_anterior
        )
        return debitos - creditos

    @property
    def saldo_devedor(self) -> Decimal:
        return max(Decimal("0"), self.saldo_apurado)

    @property
    def saldo_credor(self) -> Decimal:
        return max(Decimal("0"), -self.saldo_apurado)


@dataclass
class Inventario:
    """Item do inventário (Bloco H)."""

    codigo_item: str
    descricao: str
    unidade: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal
    propriedade: str = "0"  # 0=próprio, 1=terceiros, 2=propriedade em poder de terceiros
    conta_contabil: str | None = None


class SPEDFiscalManager:
    """
    Gerenciador do SPED Fiscal (EFD ICMS/IPI).

    Gera arquivo no formato texto do SPED.
    """

    # Versão do leiaute
    VERSAO_LEIAUTE = "017"  # Versão atual

    def __init__(
        self,
        cnpj: str,
        razao_social: str,
        inscricao_estadual: str,
        uf: str,
        codigo_municipio: str,
        perfil: PerfilArquivo = PerfilArquivo.PERFIL_A,
    ):
        """
        Inicializa o gerenciador.

        Args:
            cnpj: CNPJ da empresa
            razao_social: Razão social
            inscricao_estadual: Inscrição Estadual
            uf: Unidade Federativa
            codigo_municipio: Código IBGE do município
            perfil: Perfil de apresentação
        """
        self.cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "")
        self.razao_social = razao_social
        self.ie = inscricao_estadual.replace(".", "").replace("-", "")
        self.uf = uf
        self.cod_mun = codigo_municipio
        self.perfil = perfil

        # Dados para geração
        self.participantes: dict[str, Participante] = {}
        self.produtos: dict[str, Produto] = {}
        self.documentos: list[DocumentoFiscal] = []
        self.inventario: list[Inventario] = []
        self.apuracao_icms: ApuracaoICMS | None = None

    def adicionar_participante(self, participante: Participante) -> None:
        """Adiciona um participante ao cadastro."""
        self.participantes[participante.codigo] = participante

    def adicionar_produto(self, produto: Produto) -> None:
        """Adiciona um produto ao cadastro."""
        self.produtos[produto.codigo] = produto

    def adicionar_documento(self, documento: DocumentoFiscal) -> None:
        """Adiciona um documento fiscal."""
        self.documentos.append(documento)

    def adicionar_inventario(self, item: Inventario) -> None:
        """Adiciona um item ao inventário."""
        self.inventario.append(item)

    def calcular_apuracao(self, periodo: str) -> ApuracaoICMS:
        """
        Calcula a apuração de ICMS do período.

        Args:
            periodo: Período YYYY-MM

        Returns:
            Apuração calculada
        """
        apuracao = ApuracaoICMS(periodo=periodo)

        for doc in self.documentos:
            # Saídas = Débitos
            if doc.cfop.startswith(("5", "6", "7")):
                apuracao.valor_debitos += doc.valor_icms
            # Entradas = Créditos
            elif doc.cfop.startswith(("1", "2", "3")):
                apuracao.valor_creditos += doc.valor_icms

        self.apuracao_icms = apuracao
        logger.info(f"Apuração ICMS {periodo}: Débitos={apuracao.valor_debitos}, Créditos={apuracao.valor_creditos}")

        return apuracao

    def gerar_arquivo(
        self, periodo_inicio: date, periodo_fim: date, finalidade: FinalidadeArquivo = FinalidadeArquivo.ORIGINAL
    ) -> str:
        """
        Gera o arquivo SPED Fiscal.

        Args:
            periodo_inicio: Data inicial do período
            periodo_fim: Data final do período
            finalidade: Finalidade do arquivo

        Returns:
            Conteúdo do arquivo
        """
        linhas = []
        contador = {"registros": {}}

        # Bloco 0 - Abertura
        linhas.extend(self._gerar_bloco_0(periodo_inicio, periodo_fim, finalidade, contador))

        # Bloco C - Documentos Fiscais (Mercadorias)
        linhas.extend(self._gerar_bloco_c(contador))

        # Bloco E - Apuração ICMS/IPI
        linhas.extend(self._gerar_bloco_e(periodo_inicio, contador))

        # Bloco H - Inventário
        linhas.extend(self._gerar_bloco_h(periodo_fim, contador))

        # Bloco 9 - Encerramento
        linhas.extend(self._gerar_bloco_9(contador))

        conteudo = "\r\n".join(linhas)
        logger.info(f"Gerado arquivo SPED Fiscal: {len(linhas)} registros")

        return conteudo

    def _gerar_bloco_0(
        self, periodo_inicio: date, periodo_fim: date, finalidade: FinalidadeArquivo, contador: dict
    ) -> list[str]:
        """Gera bloco 0 - Abertura e Identificação."""
        linhas = []

        # Registro 0000 - Abertura do Arquivo
        r0000 = self._pipe(
            [
                "0000",
                self.VERSAO_LEIAUTE,
                "0",  # Código finalidade
                periodo_inicio.strftime("%d%m%Y"),
                periodo_fim.strftime("%d%m%Y"),
                self.razao_social[:100],
                self.cnpj,
                "",  # CPF
                self.uf,
                self.ie,
                self.cod_mun,
                "",  # IM
                "",  # SUFRAMA
                self.perfil.value,
                TipoAtividade.OUTROS.value,
            ]
        )
        linhas.append(r0000)
        self._contar(contador, "0000")

        # Registro 0001 - Abertura do Bloco 0
        linhas.append(self._pipe(["0001", IndicadorMovimento.COM_DADOS.value]))
        self._contar(contador, "0001")

        # Registro 0005 - Dados Complementares
        r0005 = self._pipe(
            [
                "0005",
                self.razao_social,  # Fantasia
                "",  # CEP
                "",  # Endereço
                "",  # Número
                "",  # Complemento
                "",  # Bairro
                "",  # Telefone
                "",  # Fax
                "",  # Email
            ]
        )
        linhas.append(r0005)
        self._contar(contador, "0005")

        # Registro 0100 - Contador
        r0100 = self._pipe(
            [
                "0100",
                "CONTADOR",
                "00000000000",  # CPF
                "000000",  # CRC
                "",  # CNPJ escritório
                "",  # CEP
                "",  # Endereço
                "",  # Número
                "",  # Complemento
                "",  # Bairro
                "",  # Telefone
                "",  # Fax
                "",  # Email
                "",  # Código município
            ]
        )
        linhas.append(r0100)
        self._contar(contador, "0100")

        # Registro 0150 - Participantes
        for part in self.participantes.values():
            r0150 = self._pipe(
                [
                    "0150",
                    part.codigo,
                    part.nome,
                    "1" if len(part.cnpj_cpf) == 14 else "2",  # Tipo pessoa
                    part.cnpj_cpf if len(part.cnpj_cpf) == 14 else "",
                    part.cnpj_cpf if len(part.cnpj_cpf) == 11 else "",
                    part.inscricao_estadual or "",
                    part.codigo_municipio or "",
                    "",  # SUFRAMA
                    part.endereco or "",
                    "",  # Número
                    "",  # Complemento
                    "",  # Bairro
                ]
            )
            linhas.append(r0150)
            self._contar(contador, "0150")

        # Registro 0200 - Produtos
        for prod in self.produtos.values():
            r0200 = self._pipe(
                [
                    "0200",
                    prod.codigo,
                    prod.descricao,
                    prod.codigo_barras or "",
                    "",  # Código anterior
                    prod.unidade,
                    prod.tipo_item,
                    prod.ncm or "",
                    "",  # EX_IPI
                    "",  # Gênero
                    "",  # Serviço
                    str(prod.aliquota_icms),
                    prod.cest or "",
                ]
            )
            linhas.append(r0200)
            self._contar(contador, "0200")

        # Registro 0990 - Encerramento do Bloco 0
        qtd_0 = sum(v for k, v in contador["registros"].items() if k.startswith("0"))
        linhas.append(self._pipe(["0990", str(qtd_0 + 1)]))
        self._contar(contador, "0990")

        return linhas

    def _gerar_bloco_c(self, contador: dict) -> list[str]:
        """Gera bloco C - Documentos Fiscais de Mercadorias."""
        linhas = []

        # Registro C001 - Abertura do Bloco C
        tem_movimento = "0" if self.documentos else "1"
        linhas.append(self._pipe(["C001", tem_movimento]))
        self._contar(contador, "C001")

        # Agrupa documentos por tipo
        docs_nfe = [d for d in self.documentos if d.tipo in ("55", "65")]

        for doc in docs_nfe:
            # Registro C100 - Nota Fiscal Eletrônica
            r_c100 = self._pipe(
                [
                    "C100",
                    "0" if doc.cfop.startswith(("1", "2", "3")) else "1",  # IND_OPER
                    "0",  # IND_EMIT (próprio)
                    doc.participante.codigo,
                    doc.tipo,
                    "00",  # SIT_DOC
                    doc.serie,
                    doc.numero,
                    doc.chave,
                    doc.data_emissao.strftime("%d%m%Y"),
                    doc.data_entrada_saida.strftime("%d%m%Y"),
                    str(doc.valor_total),
                    "0",  # IND_PGTO
                    # VL_DESC recebia `doc.valor_total`: o campo do DESCONTO levava o valor
                    # CHEIO da nota. Uma NF-e de R$ 2.581,00 saía declarando R$ 2.581,00 de
                    # desconto. E VL_MERC, que é o valor das mercadorias, saía zerado.
                    "0",  # VL_DESC
                    "0",  # VL_ABAT_NT
                    str(doc.valor_total),  # VL_MERC
                    "0",  # IND_FRT
                    "0",  # VL_FRT
                    "0",  # VL_SEG
                    "0",  # VL_OUT_DA
                    str(doc.valor_icms),  # VL_BC_ICMS
                    str(doc.valor_icms),  # VL_ICMS
                    "0",  # VL_BC_ICMS_ST
                    "0",  # VL_ICMS_ST
                    "0",  # VL_IPI
                    str(doc.valor_pis),  # VL_PIS
                    str(doc.valor_cofins),  # VL_COFINS
                    "0",  # VL_PIS_ST
                    "0",  # VL_COFINS_ST
                ]
            )
            linhas.append(r_c100)
            self._contar(contador, "C100")

            # Registro C170 - Itens do documento. O perfil A exige o detalhe por item, e
            # ele nunca era emitido: o `DocumentoFiscal` tinha o campo `itens` e ninguém o
            # preenchia nem o lia.
            for it in doc.itens:
                linhas.append(
                    self._pipe(
                        [
                            "C170",
                            str(it.get("numero") or ""),
                            str(it.get("codigo") or ""),
                            str(it.get("descricao") or "")[:255],
                            _n(it.get("quantidade")),
                            str(it.get("unidade") or "UN"),
                            _n(it.get("valor_total")),
                            "0",  # VL_DESC
                            "0",  # IND_MOV (0 = movimentação física)
                            str(it.get("cst") or ""),
                            str(it.get("cfop") or ""),
                            "",  # COD_NAT
                            _n(it.get("icms_base")),
                            _n(it.get("icms_aliquota")),
                            _n(it.get("icms_valor")),
                        ]
                    )
                )
                self._contar(contador, "C170")

            # Registro C190 - Analítico por CST + CFOP + ALÍQUOTA, somando os itens.
            # Antes saía UM C190 por documento, com CST fixo "00", o CFOP do documento e —
            # o pior — o VALOR do ICMS no campo da ALÍQUOTA. Nota com dois CFOPs diferentes
            # saía declarando um só.
            analitico: dict[tuple[str, str, str], dict[str, Decimal]] = {}
            for it in doc.itens:
                chave = (str(it.get("cst") or ""), str(it.get("cfop") or ""),
                         _n(it.get("icms_aliquota")))
                acc = analitico.setdefault(chave, {"opr": Decimal("0"), "bc": Decimal("0"),
                                                   "icms": Decimal("0")})
                acc["opr"] += _d(it.get("valor_total"))
                acc["bc"] += _d(it.get("icms_base"))
                acc["icms"] += _d(it.get("icms_valor"))
            if not analitico:  # documento sem item detalhado: mantém a linha do documento
                analitico[("", doc.cfop, "0")] = {
                    "opr": doc.valor_total, "bc": doc.valor_icms, "icms": doc.valor_icms}
            for (cst, cfop, aliq), acc in sorted(analitico.items()):
                linhas.append(
                    self._pipe(
                        [
                            "C190",
                            cst,
                            cfop,
                            aliq,
                            str(acc["opr"]),
                            str(acc["bc"]),
                            str(acc["icms"]),
                            "0",  # VL_BC_ICMS_ST
                            "0",  # VL_ICMS_ST
                            "0",  # VL_RED_BC
                            "0",  # VL_IPI
                            "",  # COD_OBS
                        ]
                    )
                )
                self._contar(contador, "C190")

        # Registro C990 - Encerramento do Bloco C
        qtd_c = sum(v for k, v in contador["registros"].items() if k.startswith("C"))
        linhas.append(self._pipe(["C990", str(qtd_c + 1)]))
        self._contar(contador, "C990")

        return linhas

    def _gerar_bloco_e(self, periodo_inicio: date, contador: dict) -> list[str]:
        """Gera bloco E - Apuração ICMS/IPI."""
        linhas = []

        # Registro E001 - Abertura do Bloco E
        linhas.append(self._pipe(["E001", "0"]))
        self._contar(contador, "E001")

        # Calcula apuração se não calculada
        if not self.apuracao_icms:
            self.calcular_apuracao(periodo_inicio.strftime("%Y-%m"))

        ap = self.apuracao_icms or ApuracaoICMS(periodo=periodo_inicio.strftime("%Y-%m"))

        # Registro E100 - Período de Apuração
        r_e100 = self._pipe(
            [
                "E100",
                periodo_inicio.strftime("%d%m%Y"),
                periodo_inicio.replace(day=28).strftime("%d%m%Y"),
            ]
        )
        linhas.append(r_e100)
        self._contar(contador, "E100")

        # Registro E110 - Apuração ICMS
        r_e110 = self._pipe(
            [
                "E110",
                str(ap.valor_debitos),
                str(ap.valor_ajustes_debito),
                str(ap.valor_debitos + ap.valor_ajustes_debito),
                str(ap.valor_creditos),
                str(ap.valor_ajustes_credito),
                str(ap.valor_creditos + ap.valor_ajustes_credito),
                str(ap.valor_saldo_credor_anterior),
                str(ap.saldo_devedor),
                str(ap.saldo_credor),
                str(ap.saldo_devedor),  # Dedução
                str(ap.saldo_devedor),  # A recolher
                str(ap.saldo_credor),  # Saldo credor transportar
                "0",  # DEB_ESP
            ]
        )
        linhas.append(r_e110)
        self._contar(contador, "E110")

        # Registro E990 - Encerramento do Bloco E
        qtd_e = sum(v for k, v in contador["registros"].items() if k.startswith("E"))
        linhas.append(self._pipe(["E990", str(qtd_e + 1)]))
        self._contar(contador, "E990")

        return linhas

    def _gerar_bloco_h(self, data_inventario: date, contador: dict) -> list[str]:
        """Gera bloco H - Inventário Físico."""
        linhas = []

        # Registro H001 - Abertura do Bloco H
        tem_inventario = "0" if self.inventario else "1"
        linhas.append(self._pipe(["H001", tem_inventario]))
        self._contar(contador, "H001")

        if self.inventario:
            # Registro H005 - Totais do Inventário
            valor_total = sum(i.valor_total for i in self.inventario)
            r_h005 = self._pipe(
                [
                    "H005",
                    data_inventario.strftime("%d%m%Y"),
                    str(valor_total),
                    "00",  # MOT_INV (fim do período)
                ]
            )
            linhas.append(r_h005)
            self._contar(contador, "H005")

            # Registro H010 - Itens do Inventário
            for item in self.inventario:
                r_h010 = self._pipe(
                    [
                        "H010",
                        item.codigo_item,
                        item.unidade,
                        str(item.quantidade),
                        str(item.valor_unitario),
                        str(item.valor_total),
                        item.propriedade,
                        "",  # COD_PART
                        "",  # TXT_COMPL
                        item.conta_contabil or "",
                        "0",  # VL_ITEM_IR
                    ]
                )
                linhas.append(r_h010)
                self._contar(contador, "H010")

        # Registro H990 - Encerramento do Bloco H
        qtd_h = sum(v for k, v in contador["registros"].items() if k.startswith("H"))
        linhas.append(self._pipe(["H990", str(qtd_h + 1)]))
        self._contar(contador, "H990")

        return linhas

    def _gerar_bloco_9(self, contador: dict) -> list[str]:
        """Gera bloco 9 - Controle e Encerramento."""
        linhas = []

        # Registro 9001 - Abertura do Bloco 9
        linhas.append(self._pipe(["9001", "0"]))
        self._contar(contador, "9001")

        # Registro 9900 - Registros do arquivo
        for reg, qtd in sorted(contador["registros"].items()):
            linhas.append(self._pipe(["9900", reg, str(qtd)]))
            self._contar(contador, "9900")

        # Adicionar 9900 para 9990 e 9999
        linhas.append(self._pipe(["9900", "9990", "1"]))
        self._contar(contador, "9900")
        linhas.append(self._pipe(["9900", "9999", "1"]))
        self._contar(contador, "9900")

        # Registro 9990 - Encerramento do Bloco 9
        qtd_9 = sum(v for k, v in contador["registros"].items() if k.startswith("9"))
        linhas.append(self._pipe(["9990", str(qtd_9 + 1)]))

        # Registro 9999 - Encerramento do Arquivo
        total_registros = sum(contador["registros"].values()) + 2
        linhas.append(self._pipe(["9999", str(total_registros)]))

        return linhas

    def _pipe(self, campos: list[str]) -> str:
        """Formata campos com separador pipe."""
        return "|" + "|".join(campos) + "|"

    def _contar(self, contador: dict, registro: str) -> None:
        """Conta registros."""
        if registro not in contador["registros"]:
            contador["registros"][registro] = 0
        contador["registros"][registro] += 1

    def validar_arquivo(self, conteudo: str) -> dict[str, Any]:
        """
        Valida o arquivo SPED gerado.

        Args:
            conteudo: Conteúdo do arquivo

        Returns:
            Resultado da validação
        """
        erros = []
        avisos = []

        linhas = conteudo.split("\r\n")

        # Verifica se tem registros obrigatórios
        registros = set()
        for linha in linhas:
            if linha.startswith("|"):
                partes = linha.split("|")
                if len(partes) >= 2:
                    registros.add(partes[1])

        obrigatorios = {"0000", "0001", "0990", "9001", "9990", "9999"}
        faltantes = obrigatorios - registros
        if faltantes:
            erros.append(f"Registros obrigatórios faltantes: {faltantes}")

        return {
            "valido": len(erros) == 0,
            "erros": erros,
            "avisos": avisos,
            "total_registros": len(linhas),
            "hash": hashlib.sha256(conteudo.encode()).hexdigest(),
        }
