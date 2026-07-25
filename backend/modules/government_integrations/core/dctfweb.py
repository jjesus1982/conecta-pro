"""
DCTFWeb - Declaração de Débitos e Créditos Tributários Federais Previdenciários
             e de Outras Entidades e Fundos.

Portal: https://cav.receita.fazenda.gov.br/
Documentação: Manual da DCTFWeb

A DCTFWeb é gerada automaticamente a partir de:
- eSocial (folha de pagamento)
- EFD-Reinf (retenções)

Funcionalidades:
- Consulta de declarações
- Geração de DARF
- Vinculação de créditos
- Transmissão de declaração
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class TipoDeclaracao(StrEnum):
    """Tipo de declaração DCTFWeb."""

    MENSAL = "1"  # DCTFWeb Mensal
    ANUAL = "2"  # DCTFWeb 13º Salário
    DIARIA = "3"  # DCTFWeb Diária (espetáculos desportivos)
    ESPECIAL = "4"  # DCTFWeb Especial (situações especiais)


class SituacaoDeclaracao(StrEnum):
    """Situação da declaração."""

    EM_ANDAMENTO = "em_andamento"
    APURADA = "apurada_pendente_entrega"  # calculada no ERP; entrega via e-CAC (contador)
    ATIVA = "ativa"
    RETIFICADA = "retificada"
    EXCLUIDA = "excluida"


class TipoCredito(StrEnum):
    """Tipo de crédito vinculável."""

    SALARIO_FAMILIA = "1"
    SALARIO_MATERNIDADE = "2"
    RETENCAO_LEI_9711 = "3"
    COMPENSACAO = "4"
    SUSPENSAO = "5"
    PARCELAMENTO = "6"


@dataclass
class DebitoContribuicao:
    """Débito de contribuição previdenciária."""

    codigo_receita: str
    descricao: str
    valor_principal: Decimal
    valor_acrescimos: Decimal = Decimal("0")
    periodo_apuracao: str = ""  # YYYY-MM
    cnpj_tomador: str | None = None
    numero_processo: str | None = None

    @property
    def valor_total(self) -> Decimal:
        return self.valor_principal + self.valor_acrescimos


@dataclass
class CreditoVinculavel:
    """Crédito vinculável à DCTFWeb."""

    tipo: TipoCredito
    descricao: str
    valor: Decimal
    periodo_apuracao: str
    numero_documento: str | None = None


@dataclass
class DARF:
    """Documento de Arrecadação de Receitas Federais."""

    codigo_receita: str
    periodo_apuracao: str
    data_vencimento: date
    valor_principal: Decimal
    valor_multa: Decimal = Decimal("0")
    valor_juros: Decimal = Decimal("0")
    valor_total: Decimal = Decimal("0")
    numero_referencia: str | None = None
    codigo_barras: str | None = None
    linha_digitavel: str | None = None

    def __post_init__(self):
        if self.valor_total == Decimal("0"):
            self.valor_total = self.valor_principal + self.valor_multa + self.valor_juros


@dataclass
class DCTFWebDeclaracao:
    """Representação de uma DCTFWeb."""

    # Identificação
    numero_recibo: str | None = None
    tipo: TipoDeclaracao = TipoDeclaracao.MENSAL
    situacao: SituacaoDeclaracao = SituacaoDeclaracao.EM_ANDAMENTO

    # Período
    periodo_apuracao: str = ""  # YYYY-MM
    data_transmissao: datetime | None = None

    # Contribuinte
    cnpj: str = ""
    razao_social: str = ""

    # Valores
    debitos: list[DebitoContribuicao] = field(default_factory=list)
    creditos: list[CreditoVinculavel] = field(default_factory=list)

    # DARFs gerados
    darfs: list[DARF] = field(default_factory=list)

    @property
    def total_debitos(self) -> Decimal:
        return sum(d.valor_total for d in self.debitos)

    @property
    def total_creditos(self) -> Decimal:
        return sum(c.valor for c in self.creditos)

    @property
    def saldo_a_pagar(self) -> Decimal:
        return max(Decimal("0"), self.total_debitos - self.total_creditos)


class DCTFWebManager:
    """
    Gerenciador DCTFWeb.

    Integra dados do eSocial e EFD-Reinf para gerar a DCTFWeb.
    """

    # Códigos de receita
    CODIGOS_RECEITA = {
        # Contribuição previdenciária
        "1138": "CP Patronal - Empregados/Avulsos",
        "1141": "CP Patronal - Contribuintes Individuais",
        "1162": "CP Descontada do Segurado",
        "1171": "GILRAT/RAT Ajustado",
        # Outras entidades (Sistema S)
        "1184": "Terceiros - Salário Educação",
        "1187": "Terceiros - INCRA",
        "1190": "Terceiros - SENAI",
        "1193": "Terceiros - SESI",
        "1196": "Terceiros - SENAC",
        "1199": "Terceiros - SESC",
        "1202": "Terceiros - SEBRAE",
        "1205": "Terceiros - SENAR",
        "1208": "Terceiros - SEST",
        "1211": "Terceiros - SENAT",
        "1214": "Terceiros - SESCOOP",
        # Retenção
        "1701": "Retenção Lei 9.711/98 - Serviços",
    }

    def __init__(
        self,
        cnpj: str,
        razao_social: str,
        ambiente: str = "producao",
    ):
        """
        Inicializa o gerenciador.

        Args:
            cnpj: CNPJ do contribuinte
            razao_social: Razão social
            ambiente: 'producao' ou 'homologacao'
        """
        self.cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "")
        self.razao_social = razao_social
        self.ambiente = ambiente

    def criar_declaracao(
        self, periodo_apuracao: str, tipo: TipoDeclaracao = TipoDeclaracao.MENSAL
    ) -> DCTFWebDeclaracao:
        """
        Cria uma nova declaração DCTFWeb.

        Args:
            periodo_apuracao: Período no formato YYYY-MM
            tipo: Tipo da declaração

        Returns:
            Declaração criada
        """
        return DCTFWebDeclaracao(
            tipo=tipo,
            periodo_apuracao=periodo_apuracao,
            cnpj=self.cnpj,
            razao_social=self.razao_social,
        )

    def importar_esocial(self, declaracao: DCTFWebDeclaracao, dados_esocial: dict[str, Any]) -> DCTFWebDeclaracao:
        """
        Importa dados do eSocial para a DCTFWeb.

        Args:
            declaracao: Declaração a ser preenchida
            dados_esocial: Dados vindos do eSocial

        Returns:
            Declaração atualizada
        """
        # Contribuição patronal
        if "contribuicao_patronal" in dados_esocial:
            valor = Decimal(str(dados_esocial["contribuicao_patronal"]))
            if valor > 0:
                declaracao.debitos.append(
                    DebitoContribuicao(
                        codigo_receita="1138",
                        descricao="CP Patronal - Empregados",
                        valor_principal=valor,
                        periodo_apuracao=declaracao.periodo_apuracao,
                    )
                )

        # Contribuição descontada do segurado
        if "contribuicao_segurado" in dados_esocial:
            valor = Decimal(str(dados_esocial["contribuicao_segurado"]))
            if valor > 0:
                declaracao.debitos.append(
                    DebitoContribuicao(
                        codigo_receita="1162",
                        descricao="CP Descontada do Segurado",
                        valor_principal=valor,
                        periodo_apuracao=declaracao.periodo_apuracao,
                    )
                )

        # RAT
        if "rat" in dados_esocial:
            valor = Decimal(str(dados_esocial["rat"]))
            if valor > 0:
                declaracao.debitos.append(
                    DebitoContribuicao(
                        codigo_receita="1171",
                        descricao="GILRAT/RAT Ajustado",
                        valor_principal=valor,
                        periodo_apuracao=declaracao.periodo_apuracao,
                    )
                )

        # Terceiros (Sistema S)
        if "terceiros" in dados_esocial:
            for cod, valor in dados_esocial["terceiros"].items():
                valor_decimal = Decimal(str(valor))
                if valor_decimal > 0 and cod in self.CODIGOS_RECEITA:
                    declaracao.debitos.append(
                        DebitoContribuicao(
                            codigo_receita=cod,
                            descricao=self.CODIGOS_RECEITA[cod],
                            valor_principal=valor_decimal,
                            periodo_apuracao=declaracao.periodo_apuracao,
                        )
                    )

        # Salário família (crédito)
        if "salario_familia" in dados_esocial:
            valor = Decimal(str(dados_esocial["salario_familia"]))
            if valor > 0:
                declaracao.creditos.append(
                    CreditoVinculavel(
                        tipo=TipoCredito.SALARIO_FAMILIA,
                        descricao="Salário-Família",
                        valor=valor,
                        periodo_apuracao=declaracao.periodo_apuracao,
                    )
                )

        # Salário maternidade (crédito)
        if "salario_maternidade" in dados_esocial:
            valor = Decimal(str(dados_esocial["salario_maternidade"]))
            if valor > 0:
                declaracao.creditos.append(
                    CreditoVinculavel(
                        tipo=TipoCredito.SALARIO_MATERNIDADE,
                        descricao="Salário-Maternidade",
                        valor=valor,
                        periodo_apuracao=declaracao.periodo_apuracao,
                    )
                )

        logger.info(f"Importados dados eSocial: {len(declaracao.debitos)} débitos, {len(declaracao.creditos)} créditos")
        return declaracao

    def importar_reinf(self, declaracao: DCTFWebDeclaracao, dados_reinf: dict[str, Any]) -> DCTFWebDeclaracao:
        """
        Importa dados da EFD-Reinf para a DCTFWeb.

        Args:
            declaracao: Declaração a ser preenchida
            dados_reinf: Dados vindos da EFD-Reinf

        Returns:
            Declaração atualizada
        """
        # Retenções de serviços tomados (R-2010)
        if "retencoes_tomados" in dados_reinf:
            for ret in dados_reinf["retencoes_tomados"]:
                valor = Decimal(str(ret.get("valor_retencao", 0)))
                if valor > 0:
                    declaracao.creditos.append(
                        CreditoVinculavel(
                            tipo=TipoCredito.RETENCAO_LEI_9711,
                            descricao=f"Retenção Lei 9.711/98 - {ret.get('cnpj_prestador', '')}",
                            valor=valor,
                            periodo_apuracao=declaracao.periodo_apuracao,
                            numero_documento=ret.get("numero_nf"),
                        )
                    )

        # Retenções de serviços prestados (R-2020) - débito
        if "retencoes_prestados" in dados_reinf:
            total_retido = Decimal("0")
            for ret in dados_reinf["retencoes_prestados"]:
                total_retido += Decimal(str(ret.get("valor_retencao", 0)))

            if total_retido > 0:
                declaracao.debitos.append(
                    DebitoContribuicao(
                        codigo_receita="1701",
                        descricao="Retenção Lei 9.711/98 - Serviços Prestados",
                        valor_principal=total_retido,
                        periodo_apuracao=declaracao.periodo_apuracao,
                    )
                )

        logger.info("Importados dados EFD-Reinf para DCTFWeb")
        return declaracao

    def gerar_darfs(self, declaracao: DCTFWebDeclaracao, data_vencimento: date | None = None) -> list[DARF]:
        """
        Gera DARFs para os débitos da declaração.

        Args:
            declaracao: Declaração com os débitos
            data_vencimento: Data de vencimento (default: dia 20 do mês seguinte)

        Returns:
            Lista de DARFs gerados
        """
        if data_vencimento is None:
            # Vencimento padrão: dia 20 do mês seguinte
            ano, mes = map(int, declaracao.periodo_apuracao.split("-"))
            if mes == 12:
                ano += 1
                mes = 1
            else:
                mes += 1
            data_vencimento = date(ano, mes, 20)

        darfs = []

        # Agrupa débitos por código de receita
        debitos_por_codigo: dict[str, Decimal] = {}
        for debito in declaracao.debitos:
            if debito.codigo_receita not in debitos_por_codigo:
                debitos_por_codigo[debito.codigo_receita] = Decimal("0")
            debitos_por_codigo[debito.codigo_receita] += debito.valor_principal

        # Aplica créditos (simplificado)
        total_creditos = declaracao.total_creditos
        for codigo, valor in debitos_por_codigo.items():
            if total_creditos > 0:
                credito_aplicar = min(total_creditos, valor)
                valor -= credito_aplicar
                total_creditos -= credito_aplicar

            if valor > 0:
                darf = DARF(
                    codigo_receita=codigo,
                    periodo_apuracao=declaracao.periodo_apuracao,
                    data_vencimento=data_vencimento,
                    valor_principal=valor,
                )
                darfs.append(darf)

        declaracao.darfs = darfs
        logger.info(f"Gerados {len(darfs)} DARFs para período {declaracao.periodo_apuracao}")

        return darfs

    def transmitir(self, declaracao: DCTFWebDeclaracao) -> dict[str, Any]:
        """
        Fecha a APURAÇÃO da DCTFWeb (não transmite).

        A DCTFWeb NÃO tem web service de transmissão: ela é montada na Receita a
        partir do eSocial + EFD-Reinf e ENTREGUE/confessada no portal e-CAC. O ERP
        apura os débitos (da folha real) e prepara os DARFs, mas a entrega é feita
        pelo contador via e-CAC. Este método NÃO forja recibo nem marca "transmitida"
        — retorna a apuração pronta com situação honesta (pendente de entrega).

        Args:
            declaracao: Declaração apurada

        Returns:
            Apuração pronta + orientação de entrega (sem protocolo fabricado)
        """
        declaracao.data_transmissao = None
        declaracao.numero_recibo = None
        declaracao.situacao = SituacaoDeclaracao.APURADA

        logger.info(
            f"DCTFWeb {declaracao.periodo_apuracao} apurada (saldo {declaracao.saldo_a_pagar}) "
            "— entrega via e-CAC pelo contador; sem transmissão automática."
        )

        return {
            "transmitido": False,
            "numero_recibo": None,
            "situacao": declaracao.situacao.value,
            "entrega": "e-CAC (Receita) pelo contador — DCTFWeb não possui WS de transmissão",
            "mensagem": (
                "Apuração pronta a partir da folha real. A DCTFWeb é montada pela Receita "
                "(eSocial + EFD-Reinf) e confessada no e-CAC; o ERP não emite protocolo."
            ),
            "total_debitos": str(declaracao.total_debitos),
            "total_creditos": str(declaracao.total_creditos),
            "saldo_a_pagar": str(declaracao.saldo_a_pagar),
            "quantidade_darfs": len(declaracao.darfs),
        }

    def consultar(self, periodo_apuracao: str) -> dict[str, Any]:
        """
        Consulta declaração DCTFWeb por período.

        Args:
            periodo_apuracao: Período no formato YYYY-MM

        Returns:
            Dados da declaração
        """
        # Na implementação real, consultaria o portal da Receita
        return {
            "periodo_apuracao": periodo_apuracao,
            "cnpj": self.cnpj,
            "situacao": "consulta_pendente",
            "mensagem": "Implementar consulta via e-CAC",
        }
