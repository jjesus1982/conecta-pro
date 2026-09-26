"""
SPED Contábil - ECD (Escrituração Contábil Digital).

Portal: https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/sped-sistema-publico-de-escrituracao-digital/ecd
Documentação: Manual de Orientação do Leiaute da ECD

A ECD substitui os livros contábeis em papel:
- Diário Geral
- Diário Auxiliar
- Razão Auxiliar
- Livros Balancetes Diários, Balanços e fichas de lançamento

Blocos do arquivo:
- Bloco 0: Abertura e Identificação
- Bloco I: Lançamentos Contábeis
- Bloco J: Demonstrações Contábeis
- Bloco K: Conglomerados Econômicos
- Bloco 9: Controle e Encerramento
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class TipoECD(StrEnum):
    """Tipo de ECD."""

    LIVRO_DIARIO_GERAL = "G"
    LIVRO_DIARIO_RESUMIDO = "R"
    LIVRO_DIARIO_AUXILIAR = "A"
    LIVRO_RAZAO_AUXILIAR = "Z"
    LIVRO_BALANCETES = "B"


class NaturezaConta(StrEnum):
    """Natureza da conta contábil."""

    ATIVO = "01"
    PASSIVO = "02"
    PATRIMONIO_LIQUIDO = "03"
    RESULTADO_CREDORA = "04"
    RESULTADO_DEVEDORA = "05"


class IndicadorDC(StrEnum):
    """Indicador de débito/crédito."""

    DEBITO = "D"
    CREDITO = "C"


class TipoConta(StrEnum):
    """Tipo de conta."""

    SINTETICA = "S"
    ANALITICA = "A"


@dataclass
class ContaContabil:
    """Conta do plano de contas."""

    codigo: str
    descricao: str
    tipo: TipoConta
    nivel: int
    natureza: NaturezaConta
    codigo_pai: str | None = None
    codigo_referencial: str | None = None  # Referencial da RFB
    saldo_inicial_debito: Decimal = Decimal("0")
    saldo_inicial_credito: Decimal = Decimal("0")


@dataclass
class LancamentoContabil:
    """Lançamento contábil."""

    numero: int
    data: date
    conta_debito: str
    conta_credito: str
    valor: Decimal
    historico: str
    documento: str | None = None
    participante: str | None = None


@dataclass
class SaldoPeriodico:
    """Saldo periódico de uma conta."""

    codigo_conta: str
    data_inicio: date
    data_fim: date
    valor_saldo_inicial_debito: Decimal = Decimal("0")
    valor_saldo_inicial_credito: Decimal = Decimal("0")
    valor_debitos: Decimal = Decimal("0")
    valor_creditos: Decimal = Decimal("0")

    @property
    def saldo_final_debito(self) -> Decimal:
        saldo = (
            self.valor_saldo_inicial_debito
            + self.valor_debitos
            - self.valor_saldo_inicial_credito
            - self.valor_creditos
        )
        return max(Decimal("0"), saldo)

    @property
    def saldo_final_credito(self) -> Decimal:
        saldo = (
            self.valor_saldo_inicial_credito
            + self.valor_creditos
            - self.valor_saldo_inicial_debito
            - self.valor_debitos
        )
        return max(Decimal("0"), saldo)


@dataclass
class DemonstrativoBalancoPatrimonial:
    """Balanço Patrimonial."""

    data_referencia: date
    ativo_circulante: Decimal = Decimal("0")
    ativo_nao_circulante: Decimal = Decimal("0")
    passivo_circulante: Decimal = Decimal("0")
    passivo_nao_circulante: Decimal = Decimal("0")
    patrimonio_liquido: Decimal = Decimal("0")

    @property
    def total_ativo(self) -> Decimal:
        return self.ativo_circulante + self.ativo_nao_circulante

    @property
    def total_passivo_pl(self) -> Decimal:
        return self.passivo_circulante + self.passivo_nao_circulante + self.patrimonio_liquido


@dataclass
class DemonstrativoDRE:
    """Demonstração do Resultado do Exercício."""

    periodo_inicio: date
    periodo_fim: date
    receita_bruta: Decimal = Decimal("0")
    deducoes_receita: Decimal = Decimal("0")
    custos: Decimal = Decimal("0")
    despesas_operacionais: Decimal = Decimal("0")
    resultado_financeiro: Decimal = Decimal("0")
    outras_receitas_despesas: Decimal = Decimal("0")
    irpj_csll: Decimal = Decimal("0")

    @property
    def receita_liquida(self) -> Decimal:
        return self.receita_bruta - self.deducoes_receita

    @property
    def lucro_bruto(self) -> Decimal:
        return self.receita_liquida - self.custos

    @property
    def lucro_operacional(self) -> Decimal:
        return self.lucro_bruto - self.despesas_operacionais

    @property
    def lucro_antes_ir(self) -> Decimal:
        return self.lucro_operacional + self.resultado_financeiro + self.outras_receitas_despesas

    @property
    def lucro_liquido(self) -> Decimal:
        return self.lucro_antes_ir - self.irpj_csll


class SPEDContabilManager:
    """
    Gerenciador do SPED Contábil (ECD).

    Gera arquivo no formato texto do SPED.
    """

    # Versão do leiaute
    VERSAO_LEIAUTE = "10"  # Versão atual (2024)

    def __init__(
        self,
        cnpj: str,
        razao_social: str,
        tipo_ecd: TipoECD = TipoECD.LIVRO_DIARIO_GERAL,
        uf: str = "",
        inscricao_estadual: str = "",
        codigo_municipio: str = "",
        inscricao_municipal: str = "",
    ):
        """
        Inicializa o gerenciador.

        Args:
            cnpj: CNPJ da empresa
            razao_social: Razão social
            tipo_ecd: Tipo de livro
            uf, inscricao_estadual, codigo_municipio, inscricao_municipal:
                identificação do registro 0000. Saíam VAZIOS no arquivo gerado, não por
                falta de dado — a tabela `empresas` tem os quatro — mas porque o
                construtor não os aceitava. Perda de transporte, não de cadastro.
        """
        self.cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "")
        self.razao_social = razao_social
        self.tipo_ecd = tipo_ecd
        self.uf = (uf or "").strip().upper()
        self.inscricao_estadual = re.sub(r"\D", "", inscricao_estadual or "")
        self.codigo_municipio = re.sub(r"\D", "", codigo_municipio or "")
        self.inscricao_municipal = re.sub(r"\D", "", inscricao_municipal or "")

        # Dados para geração
        self.plano_contas: dict[str, ContaContabil] = {}
        self.lancamentos: list[LancamentoContabil] = []
        self.saldos_periodicos: list[SaldoPeriodico] = []
        self.balanco: DemonstrativoBalancoPatrimonial | None = None
        self.dre: DemonstrativoDRE | None = None

    def adicionar_conta(self, conta: ContaContabil) -> None:
        """Adiciona conta ao plano de contas."""
        self.plano_contas[conta.codigo] = conta

    def adicionar_lancamento(self, lancamento: LancamentoContabil) -> None:
        """Adiciona lançamento contábil."""
        self.lancamentos.append(lancamento)

    def calcular_saldos(self, periodo_inicio: date, periodo_fim: date) -> list[SaldoPeriodico]:
        """
        Calcula saldos periódicos das contas.

        Args:
            periodo_inicio: Data inicial
            periodo_fim: Data final

        Returns:
            Lista de saldos
        """
        saldos = {}

        # Inicializa com saldos iniciais do plano de contas
        for codigo, conta in self.plano_contas.items():
            if conta.tipo == TipoConta.ANALITICA:
                saldos[codigo] = SaldoPeriodico(
                    codigo_conta=codigo,
                    data_inicio=periodo_inicio,
                    data_fim=periodo_fim,
                    valor_saldo_inicial_debito=conta.saldo_inicial_debito,
                    valor_saldo_inicial_credito=conta.saldo_inicial_credito,
                )

        # Processa lançamentos
        for lanc in self.lancamentos:
            if periodo_inicio <= lanc.data <= periodo_fim:
                # Débito
                if lanc.conta_debito in saldos:
                    saldos[lanc.conta_debito].valor_debitos += lanc.valor

                # Crédito
                if lanc.conta_credito in saldos:
                    saldos[lanc.conta_credito].valor_creditos += lanc.valor

        self.saldos_periodicos = list(saldos.values())
        logger.info(f"Calculados saldos de {len(self.saldos_periodicos)} contas")

        return self.saldos_periodicos

    def gerar_arquivo(
        self, ano_referencia: int, periodo_inicio: date, periodo_fim: date, numero_ordem: str = "00001"
    ) -> str:
        """
        Gera o arquivo SPED Contábil.

        Args:
            ano_referencia: Ano de referência
            periodo_inicio: Data inicial do período
            periodo_fim: Data final do período
            numero_ordem: Número de ordem do livro

        Returns:
            Conteúdo do arquivo
        """
        linhas = []
        contador = {"registros": {}}

        # Bloco 0 - Abertura
        linhas.extend(self._gerar_bloco_0(ano_referencia, periodo_inicio, periodo_fim, numero_ordem, contador))

        # Bloco I - Lançamentos Contábeis
        linhas.extend(self._gerar_bloco_i(periodo_inicio, periodo_fim, contador))

        # Bloco J - Demonstrações Contábeis
        linhas.extend(self._gerar_bloco_j(periodo_fim, contador))

        # Bloco K - Conglomerados. Não se aplica a estas empresas, mas o leiaute exige a
        # abertura e o encerramento de TODO bloco: o arquivo saía sem K nenhum.
        linhas.append(self._pipe(["K001", "1"]))  # 1 = bloco sem dados
        self._contar(contador, "K001")
        linhas.append(self._pipe(["K990", "2"]))
        self._contar(contador, "K990")

        # Bloco 9 - Encerramento
        linhas.extend(self._gerar_bloco_9(contador))

        conteudo = "\r\n".join(linhas)
        logger.info(f"Gerado arquivo SPED Contábil: {len(linhas)} registros")

        return conteudo

    def _gerar_bloco_0(self, ano: int, dt_ini: date, dt_fim: date, _num_ord: str, contador: dict) -> list[str]:
        """Gera bloco 0 - Abertura e Identificação."""
        linhas = []

        # Registro 0000 - Abertura do Arquivo
        r0000 = self._pipe(
            [
                "0000",
                "LECD",
                dt_ini.strftime("%d%m%Y"),
                dt_fim.strftime("%d%m%Y"),
                self.razao_social,
                self.cnpj,
                self.uf,  # UF
                self.inscricao_estadual,  # IE
                self.codigo_municipio,  # COD_MUN
                self.inscricao_municipal,  # IM
                "0",  # IND_SIT_ESP
                "0",  # IND_SIT_INI_PER
                "0",  # IND_NIRE
                "0",  # IND_FIN_ESC
                "",  # COD_HASH_SUB
                "0",  # IND_GRANDE_PORTE
                "0",  # TIP_ECD
                "",  # COD_SCP
                "",  # IDENT_MF
                "0",  # IND_ESC_CONS
                "0",  # IND_CENTRALIZADA
                "0",  # IND_MUDANÇA_PC
                "0",  # COD_PLAN_REF
            ]
        )
        linhas.append(r0000)
        self._contar(contador, "0000")

        # Registro 0001 - Abertura do Bloco 0
        linhas.append(self._pipe(["0001", "0"]))
        self._contar(contador, "0001")

        # Registro 0007 - Outras Inscrições Cadastrais
        linhas.append(self._pipe(["0007", "", ""]))
        self._contar(contador, "0007")

        # Registro 0020 - Escrituração Contábil Descentralizada
        linhas.append(self._pipe(["0020", "0"]))
        self._contar(contador, "0020")

        # Registro 0990 - Encerramento do Bloco 0
        qtd_0 = sum(v for k, v in contador["registros"].items() if k.startswith("0"))
        linhas.append(self._pipe(["0990", str(qtd_0 + 1)]))
        self._contar(contador, "0990")

        return linhas

    def _gerar_bloco_i(self, dt_ini: date, dt_fim: date, contador: dict) -> list[str]:
        """Gera bloco I - Lançamentos Contábeis."""
        linhas = []

        # Registro I001 - Abertura do Bloco I
        linhas.append(self._pipe(["I001", "0"]))
        self._contar(contador, "I001")

        # Registro I010 - Identificação da Escrituração
        r_i010 = self._pipe(
            [
                "I010",
                "2",  # IND_ESC (2=Diário Geral)
                "2.01.01",  # COD_VER_LC
            ]
        )
        linhas.append(r_i010)
        self._contar(contador, "I010")

        # Registro I012 - Livros Auxiliares ao Diário
        # (opcional, não implementado)

        # Registro I015 - Identificação das Contas
        for _codigo, conta in sorted(self.plano_contas.items()):
            r_i015 = self._pipe(
                [
                    "I015",
                    conta.codigo,
                ]
            )
            linhas.append(r_i015)
            self._contar(contador, "I015")

        # Registro I030 - Termo de Abertura
        r_i030 = self._pipe(
            [
                "I030",
                "",  # DNRC_ABERT
                str(len([lanc for lanc in self.lancamentos if dt_ini <= lanc.data <= dt_fim])),  # NUM_ORD
                self.razao_social,
                "",  # NUM_LINHA
                dt_ini.strftime("%d%m%Y"),
                dt_fim.strftime("%d%m%Y"),
            ]
        )
        linhas.append(r_i030)
        self._contar(contador, "I030")

        # Registro I050 - Plano de Contas
        for _codigo, conta in sorted(self.plano_contas.items()):
            r_i050 = self._pipe(
                [
                    "I050",
                    dt_ini.strftime("%d%m%Y"),
                    conta.natureza.value,
                    # IND_CTA: 1=sintética, 2=analítica. Era "1" fixo em todas — inclusive
                    # nas folhas do plano, que são todas analíticas.
                    ("2" if conta.tipo == TipoConta.ANALITICA else "1"),
                    str(conta.nivel),
                    conta.codigo,
                    conta.codigo_pai or "",
                    conta.descricao,
                ]
            )
            linhas.append(r_i050)
            self._contar(contador, "I050")

            # Registro I051 - Plano de Contas Referencial
            if conta.codigo_referencial:
                r_i051 = self._pipe(
                    [
                        "I051",
                        "",  # COD_ENT_REF
                        "",  # COD_CCUS
                        conta.codigo_referencial,
                    ]
                )
                linhas.append(r_i051)
                self._contar(contador, "I051")

        # Calcula saldos se não calculados
        if not self.saldos_periodicos:
            self.calcular_saldos(dt_ini, dt_fim)

        # Registro I150 - Saldos Periódicos (só as DATAS) + I155 por conta.
        #
        # Antes saía UM I150 por conta, carregando os campos que pertencem ao I155 — e sem
        # COD_CTA. Não havia como saber de que conta era o saldo: `|I150|01012026|31122026|0|
        # 0|762821.40|589605.76|173215.64|0|`. No leiaute o I150 leva apenas DT_INI|DT_FIN, e
        # o detalhe por conta é o I155.
        if self.saldos_periodicos:
            linhas.append(
                self._pipe(["I150", dt_ini.strftime("%d%m%Y"), dt_fim.strftime("%d%m%Y")])
            )
            self._contar(contador, "I150")
            for saldo in sorted(self.saldos_periodicos, key=lambda x: x.codigo_conta):
                sld_ini = saldo.valor_saldo_inicial_debito - saldo.valor_saldo_inicial_credito
                sld_fim = sld_ini + saldo.valor_debitos - saldo.valor_creditos
                linhas.append(
                    self._pipe(
                        [
                            "I155",
                            saldo.codigo_conta,
                            "",  # COD_CCUS — não há centro de custo neste razão
                            str(abs(sld_ini)),
                            "D" if sld_ini >= 0 else "C",
                            str(saldo.valor_debitos),
                            str(saldo.valor_creditos),
                            str(abs(sld_fim)),
                            "D" if sld_fim >= 0 else "C",
                        ]
                    )
                )
                self._contar(contador, "I155")

        # Registro I200/I250 - Lançamentos Contábeis
        for _i, lanc in enumerate(sorted(self.lancamentos, key=lambda x: (x.data, x.numero)), 1):
            if dt_ini <= lanc.data <= dt_fim:
                # I200 - Lançamento Contábil
                r_i200 = self._pipe(
                    [
                        "I200",
                        str(lanc.numero),
                        lanc.data.strftime("%d%m%Y"),
                        str(lanc.valor),
                        "N",  # IND_LCTO (N=Normal, E=Encerramento, X=Estorno)
                    ]
                )
                linhas.append(r_i200)
                self._contar(contador, "I200")

                # I250 - Partidas do Lançamento
                # Débito
                r_i250_d = self._pipe(
                    [
                        "I250",
                        lanc.conta_debito,
                        "",  # COD_CCUS
                        str(lanc.valor),
                        IndicadorDC.DEBITO.value,
                        "",  # NUM_ARQ
                        "",  # COD_HIST_PAD
                        lanc.historico[:200],
                        "",  # COD_PART
                    ]
                )
                linhas.append(r_i250_d)
                self._contar(contador, "I250")

                # Crédito
                r_i250_c = self._pipe(
                    [
                        "I250",
                        lanc.conta_credito,
                        "",  # COD_CCUS
                        str(lanc.valor),
                        IndicadorDC.CREDITO.value,
                        "",  # NUM_ARQ
                        "",  # COD_HIST_PAD
                        lanc.historico[:200],
                        "",  # COD_PART
                    ]
                )
                linhas.append(r_i250_c)
                self._contar(contador, "I250")

        # Registro I350 - Saldos das Contas de Resultado
        contas_resultado = [
            c
            for c in self.plano_contas.values()
            if c.natureza in [NaturezaConta.RESULTADO_CREDORA, NaturezaConta.RESULTADO_DEVEDORA]
        ]

        for conta in contas_resultado:
            saldo = next((s for s in self.saldos_periodicos if s.codigo_conta == conta.codigo), None)
            if saldo:
                r_i350 = self._pipe(
                    [
                        "I350",
                        dt_fim.strftime("%d%m%Y"),
                        conta.codigo,
                        str(saldo.saldo_final_debito)
                        if conta.natureza == NaturezaConta.RESULTADO_DEVEDORA
                        else str(saldo.saldo_final_credito),
                        "D" if conta.natureza == NaturezaConta.RESULTADO_DEVEDORA else "C",
                    ]
                )
                linhas.append(r_i350)
                self._contar(contador, "I350")

        # Registro I990 - Encerramento do Bloco I
        qtd_i = sum(v for k, v in contador["registros"].items() if k.startswith("I"))
        linhas.append(self._pipe(["I990", str(qtd_i + 1)]))
        self._contar(contador, "I990")

        return linhas

    def _gerar_bloco_j(self, data_ref: date, contador: dict) -> list[str]:
        """Gera bloco J - Demonstrações Contábeis."""
        linhas = []

        # Registro J001 - Abertura do Bloco J
        tem_demo = "0" if (self.balanco or self.dre) else "1"
        linhas.append(self._pipe(["J001", tem_demo]))
        self._contar(contador, "J001")

        # J005 - Demonstrações Contábeis
        r_j005 = self._pipe(
            [
                "J005",
                data_ref.strftime("%d%m%Y"),
                "01",  # ID_DEM (01=Balanço)
                "BALANÇO PATRIMONIAL",
            ]
        )
        linhas.append(r_j005)
        self._contar(contador, "J005")

        if self.balanco:
            # J100 - Balanço Patrimonial
            # Ativo Circulante
            linhas.append(
                self._pipe(
                    [
                        "J100",
                        "1",  # COD_AGL
                        "1",  # NIVEL_AGL
                        "ATIVO CIRCULANTE",
                        str(self.balanco.ativo_circulante),
                        "D",
                    ]
                )
            )
            self._contar(contador, "J100")

            # Ativo Não Circulante
            linhas.append(
                self._pipe(
                    [
                        "J100",
                        "2",
                        "1",
                        "ATIVO NÃO CIRCULANTE",
                        str(self.balanco.ativo_nao_circulante),
                        "D",
                    ]
                )
            )
            self._contar(contador, "J100")

            # Passivo Circulante
            linhas.append(
                self._pipe(
                    [
                        "J100",
                        "3",
                        "1",
                        "PASSIVO CIRCULANTE",
                        str(self.balanco.passivo_circulante),
                        "C",
                    ]
                )
            )
            self._contar(contador, "J100")

            # Passivo Não Circulante
            linhas.append(
                self._pipe(
                    [
                        "J100",
                        "4",
                        "1",
                        "PASSIVO NÃO CIRCULANTE",
                        str(self.balanco.passivo_nao_circulante),
                        "C",
                    ]
                )
            )
            self._contar(contador, "J100")

            # Patrimônio Líquido
            linhas.append(
                self._pipe(
                    [
                        "J100",
                        "5",
                        "1",
                        "PATRIMÔNIO LÍQUIDO",
                        str(self.balanco.patrimonio_liquido),
                        "C",
                    ]
                )
            )
            self._contar(contador, "J100")

        if self.dre:
            # J150 - DRE
            r_j005_dre = self._pipe(
                [
                    "J005",
                    data_ref.strftime("%d%m%Y"),
                    "02",  # ID_DEM (02=DRE)
                    "DEMONSTRAÇÃO DO RESULTADO DO EXERCÍCIO",
                ]
            )
            linhas.append(r_j005_dre)
            self._contar(contador, "J005")

            linhas.append(
                self._pipe(
                    [
                        "J150",
                        "1",
                        "1",
                        "RECEITA BRUTA",
                        str(self.dre.receita_bruta),
                        "C",
                    ]
                )
            )
            self._contar(contador, "J150")

            linhas.append(
                self._pipe(
                    [
                        "J150",
                        "2",
                        "1",
                        "(-) DEDUÇÕES DA RECEITA",
                        str(self.dre.deducoes_receita),
                        "D",
                    ]
                )
            )
            self._contar(contador, "J150")

            linhas.append(
                self._pipe(
                    [
                        "J150",
                        "3",
                        "1",
                        "(=) RECEITA LÍQUIDA",
                        str(self.dre.receita_liquida),
                        "C",
                    ]
                )
            )
            self._contar(contador, "J150")

            linhas.append(
                self._pipe(
                    [
                        "J150",
                        "4",
                        "1",
                        "(-) CUSTOS",
                        str(self.dre.custos),
                        "D",
                    ]
                )
            )
            self._contar(contador, "J150")

            linhas.append(
                self._pipe(
                    [
                        "J150",
                        "5",
                        "1",
                        "(=) LUCRO/PREJUÍZO LÍQUIDO",
                        str(self.dre.lucro_liquido),
                        "C" if self.dre.lucro_liquido >= 0 else "D",
                    ]
                )
            )
            self._contar(contador, "J150")

        # J900 - Termo de Encerramento
        r_j900 = self._pipe(
            [
                "J900",
                "",  # DNRC_ENCER
                str(len(self.lancamentos)),
                self.razao_social,
            ]
        )
        linhas.append(r_j900)
        self._contar(contador, "J900")

        # J930 - Signatários
        r_j930 = self._pipe(
            [
                "J930",
                "",  # IDENT_NOM
                "CONTADOR",
                "",  # IDENT_CPF
                "",  # IDENT_QUALIF
                "",  # COD_ASSIN
                "",  # IND_CRC
                "",  # EMAIL
                "",  # FONE
                "",  # UF_CRC
                "",  # NUM_SEQ_CRC
                "",  # DT_CRC
                "",  # IND_RESP_LEGAL
            ]
        )
        linhas.append(r_j930)
        self._contar(contador, "J930")

        # Registro J990 - Encerramento do Bloco J
        qtd_j = sum(v for k, v in contador["registros"].items() if k.startswith("J"))
        linhas.append(self._pipe(["J990", str(qtd_j + 1)]))
        self._contar(contador, "J990")

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

        # O próprio 9900 precisa de um 9900. O laço acima itera um retrato do dicionário
        # ANTES de "9900" entrar nele, então esta linha faltava no arquivo.
        linhas.append(self._pipe(["9900", "9900", str(contador["registros"].get("9900", 0) + 3)]))
        self._contar(contador, "9900")
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
        """Conta registros.

        Os encerramentos de bloco (0990/I990/J990/9990) somam o VALOR deste dicionário,
        não a quantidade de chaves. Contar chaves dava `|I990|10|` num bloco de 17.863
        linhas — o PVA recusa o arquivo por divergência de contagem, e o número parecia
        plausível o bastante para ninguém olhar duas vezes.
        """
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

        obrigatorios = {"0000", "0001", "0990", "I001", "I010", "I990", "J001", "J990", "9001", "9990", "9999"}
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
