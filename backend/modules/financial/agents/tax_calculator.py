"""
TaxCalculatorAgent — Calculadora de Impostos Multi-Regime
Suporta: Lucro Real + Simples Nacional (Anexo III)
Empresa: Conecta Mais (grupo com 2 CNPJs)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)


# ─── TABELAS DE ALÍQUOTAS ────────────────────────────────────────────────────

SIMPLES_ANEXO_III = [
    # (limite_rbt12, aliquota, deducao)
    (Decimal("180000.00"), Decimal("0.06"), Decimal("0.00")),
    (Decimal("360000.00"), Decimal("0.112"), Decimal("9360.00")),
    (Decimal("720000.00"), Decimal("0.135"), Decimal("17640.00")),
    (Decimal("1800000.00"), Decimal("0.16"), Decimal("35640.00")),
    (Decimal("3600000.00"), Decimal("0.21"), Decimal("125640.00")),
    (Decimal("4800000.00"), Decimal("0.33"), Decimal("648000.00")),
]

# Distribuição Faixa 3 Anexo III (vigilância/segurança - mais comum)
DISTRIBUICAO_SIMPLES_III = {
    "irpj": Decimal("0.04"),
    "csll": Decimal("0.035"),
    "cofins": Decimal("0.1282"),
    "pis": Decimal("0.0278"),
    "cpp": Decimal("0.434"),  # Contribuição Patronal Previdenciária
    "iss": Decimal("0.335"),
}

LUCRO_REAL = {
    "irpj_base": Decimal("0.15"),
    "irpj_adicional": Decimal("0.10"),
    "irpj_limite_trimestral": Decimal("60000.00"),
    "csll": Decimal("0.09"),
    "pis_ncum": Decimal("0.0165"),  # Não cumulativo
    "cofins_ncum": Decimal("0.076"),  # Não cumulativo
    "iss_manaus": Decimal("0.05"),
    "presuncao_servicos": Decimal("0.32"),
}


# ─── DATACLASSES DE RESULTADO ─────────────────────────────────────────────────


@dataclass
class DetalhamentoImposto:
    nome: str
    aliquota: Decimal
    base_calculo: Decimal
    valor: Decimal
    retido_fonte: bool = False
    zerado_por_liminar: bool = False


@dataclass
class CalculoSimples:
    regime: str = "simples_nacional"
    anexo: str = "III"
    receita_bruta_mes: Decimal = Decimal("0")
    receita_bruta_12_meses: Decimal = Decimal("0")
    aliquota_nominal: Decimal = Decimal("0")
    deducao: Decimal = Decimal("0")
    aliquota_efetiva: Decimal = Decimal("0")
    valor_das: Decimal = Decimal("0")
    distribuicao: dict = field(default_factory=dict)
    liminares_aplicadas: list[str] = field(default_factory=list)
    economia_liminares: Decimal = Decimal("0")

    @property
    def carga_tributaria_percentual(self) -> Decimal:
        if self.receita_bruta_mes == 0:
            return Decimal("0")
        return (self.valor_das / self.receita_bruta_mes * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass
class CalculoLucroReal:
    regime: str = "lucro_real"
    receita_bruta_mes: Decimal = Decimal("0")
    receita_bruta_trimestre: Decimal = Decimal("0")
    custos_dedutiveis: Decimal = Decimal("0")
    lucro_bruto: Decimal = Decimal("0")
    irpj: Decimal = Decimal("0")
    irpj_adicional: Decimal = Decimal("0")
    csll: Decimal = Decimal("0")
    pis: Decimal = Decimal("0")
    cofins: Decimal = Decimal("0")
    iss: Decimal = Decimal("0")
    total_impostos_mes: Decimal = Decimal("0")
    detalhamento: list[DetalhamentoImposto] = field(default_factory=list)

    @property
    def carga_tributaria_percentual(self) -> Decimal:
        if self.receita_bruta_mes == 0:
            return Decimal("0")
        return (self.total_impostos_mes / self.receita_bruta_mes * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass
class ComparativoRegimes:
    receita_bruta_anual: Decimal
    simples_nacional_total: Decimal
    simples_nacional_percentual: Decimal
    lucro_real_total: Decimal
    lucro_real_percentual: Decimal
    economia_simples: Decimal  # Quanto economiza no Simples vs Lucro Real
    recomendacao: str
    observacoes: list[str] = field(default_factory=list)


@dataclass
class CalculoRetencoes:
    """Retenções na fonte sobre NFS-e"""

    valor_servico: Decimal
    inss: Decimal = Decimal("0")
    ir: Decimal = Decimal("0")
    csll: Decimal = Decimal("0")
    pis: Decimal = Decimal("0")
    cofins: Decimal = Decimal("0")
    iss: Decimal = Decimal("0")
    total_retencoes: Decimal = Decimal("0")
    valor_liquido: Decimal = Decimal("0")
    liminares_aplicadas: list[str] = field(default_factory=list)


# ─── AGENT ────────────────────────────────────────────────────────────────────


class TaxCalculatorAgent:
    """
    Calculadora de impostos multi-regime.

    Suporta:
    - Lucro Real (IRPJ + CSLL + PIS ncum + COFINS ncum + ISS)
    - Simples Nacional Anexo III (DAS com liminares)

    Uso:
        agent = TaxCalculatorAgent()
        resultado = agent.calcular_simples(
            receita_mes=Decimal("50000"),
            rbt12=Decimal("500000"),
            liminares=["pis_cofins_zero", "inss_nao_retido"]
        )
    """

    # ── Simples Nacional ──────────────────────────────────────────────────────

    def calcular_simples(
        self,
        receita_mes: Decimal,
        rbt12: Decimal,
        anexo: str = "III",
        liminares: list[str] | None = None,
    ) -> CalculoSimples:
        """
        Calcula DAS do Simples Nacional.

        Args:
            receita_mes: Receita bruta do mês
            rbt12: Receita bruta acumulada 12 meses
            anexo: Anexo do Simples (III para vigilância)
            liminares: Lista de liminares ativas (ex: ["pis_cofins_zero"])

        Returns:
            CalculoSimples com alíquota efetiva e valor do DAS
        """
        liminares = liminares or []
        resultado = CalculoSimples(
            regime="simples_nacional",
            anexo=anexo,
            receita_bruta_mes=receita_mes,
            receita_bruta_12_meses=rbt12,
        )

        if receita_mes <= 0:
            return resultado

        # 1. Determinar faixa
        aliquota, deducao = self._obter_faixa_simples(rbt12)
        resultado.aliquota_nominal = aliquota
        resultado.deducao = deducao

        # 2. Alíquota efetiva = ((RBT12 × Aliq) − PD) / RBT12
        if rbt12 > 0:
            aliquota_efetiva = ((rbt12 * aliquota) - deducao) / rbt12
        else:
            aliquota_efetiva = aliquota
        resultado.aliquota_efetiva = aliquota_efetiva.quantize(Decimal("0.0001"), ROUND_HALF_UP)

        # 3. DAS = receita_mes × alíquota_efetiva
        das_base = (receita_mes * aliquota_efetiva).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # 4. Distribuição por componente
        distribuicao = {}
        for componente, percentual in DISTRIBUICAO_SIMPLES_III.items():
            distribuicao[componente] = (das_base * percentual).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # 5. Aplicar liminares (reduz o DAS proporcionalmente se PIS/COFINS zerados)
        economia = Decimal("0")
        if "pis_cofins_zero" in liminares:
            # PIS e COFINS saem da base do DAS (bitributação reconhecida)
            pct_pis_cofins = DISTRIBUICAO_SIMPLES_III["pis"] + DISTRIBUICAO_SIMPLES_III["cofins"]
            economia_pis_cofins = (das_base * pct_pis_cofins).quantize(Decimal("0.01"), ROUND_HALF_UP)
            economia += economia_pis_cofins
            distribuicao["pis"] = Decimal("0")
            distribuicao["cofins"] = Decimal("0")
            resultado.liminares_aplicadas.append("pis_cofins_zero")

        resultado.valor_das = (das_base - economia).quantize(Decimal("0.01"), ROUND_HALF_UP)
        resultado.distribuicao = {k: float(v) for k, v in distribuicao.items()}
        resultado.economia_liminares = economia

        return resultado

    def _obter_faixa_simples(self, rbt12: Decimal) -> tuple[Decimal, Decimal]:
        """Retorna (alíquota_nominal, deducao) para o RBT12 informado."""
        for limite, aliquota, deducao in SIMPLES_ANEXO_III:
            if rbt12 <= limite:
                return aliquota, deducao
        # Acima do limite do Simples → usar última faixa (empresa já deveria sair)
        return SIMPLES_ANEXO_III[-1][1], SIMPLES_ANEXO_III[-1][2]

    # ── Lucro Real ────────────────────────────────────────────────────────────

    def calcular_lucro_real(
        self,
        receita_mes: Decimal,
        receita_trimestre: Decimal,
        custos_dedutiveis_mes: Decimal = Decimal("0"),
    ) -> CalculoLucroReal:
        """
        Calcula impostos no regime Lucro Real.

        Args:
            receita_mes: Receita bruta mensal
            receita_trimestre: Receita bruta do trimestre (para IRPJ adicional)
            custos_dedutiveis_mes: Créditos PIS/COFINS (compras com nota)

        Returns:
            CalculoLucroReal com detalhamento de cada imposto

        Nota:
            IRPJ/CSLL calculados sobre lucro presumido (32% serviços)
            PIS/COFINS não-cumulativos: 1.65% e 7.6%
            ISS Manaus: 5%
        """
        resultado = CalculoLucroReal(
            receita_bruta_mes=receita_mes,
            receita_bruta_trimestre=receita_trimestre,
            custos_dedutiveis=custos_dedutiveis_mes,
        )

        if receita_mes <= 0:
            return resultado

        # Base de cálculo IRPJ/CSLL. Lucro REAL de fato = receita − custos/despesas dedutíveis.
        # Só cai na presunção de 32% (aproximação Presumido) quando não há custo informado.
        if custos_dedutiveis_mes and custos_dedutiveis_mes > 0:
            lucro_presumido_mes = max(Decimal("0"), receita_mes - custos_dedutiveis_mes)
            lucro_trimestre = max(Decimal("0"), receita_trimestre - custos_dedutiveis_mes * 3)
        else:
            lucro_presumido_mes = receita_mes * LUCRO_REAL["presuncao_servicos"]
            lucro_trimestre = receita_trimestre * LUCRO_REAL["presuncao_servicos"]
        resultado.lucro_bruto = lucro_presumido_mes

        # 1. IRPJ base = 15% sobre lucro
        irpj_base = (lucro_presumido_mes * LUCRO_REAL["irpj_base"]).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # 2. IRPJ adicional (10% sobre excedente de R$ 60k/trimestre, proporcional ao mês)
        excedente = max(Decimal("0"), lucro_trimestre - LUCRO_REAL["irpj_limite_trimestral"])
        irpj_adicional_trim = (excedente * LUCRO_REAL["irpj_adicional"]).quantize(Decimal("0.01"), ROUND_HALF_UP)
        irpj_adicional_mes = (irpj_adicional_trim / 3).quantize(Decimal("0.01"), ROUND_HALF_UP)

        resultado.irpj = irpj_base
        resultado.irpj_adicional = irpj_adicional_mes

        # 3. CSLL = 9%
        csll = (lucro_presumido_mes * LUCRO_REAL["csll"]).quantize(Decimal("0.01"), ROUND_HALF_UP)
        resultado.csll = csll

        # 4. PIS não-cumulativo = 1.65%
        pis = (receita_mes * LUCRO_REAL["pis_ncum"]).quantize(Decimal("0.01"), ROUND_HALF_UP)
        resultado.pis = pis

        # 5. COFINS não-cumulativo = 7.6%
        cofins = (receita_mes * LUCRO_REAL["cofins_ncum"]).quantize(Decimal("0.01"), ROUND_HALF_UP)
        resultado.cofins = cofins

        # 6. ISS = 5% (Manaus)
        iss = (receita_mes * LUCRO_REAL["iss_manaus"]).quantize(Decimal("0.01"), ROUND_HALF_UP)
        resultado.iss = iss

        # Total mensal
        resultado.total_impostos_mes = (irpj_base + irpj_adicional_mes + csll + pis + cofins + iss).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )

        # Detalhamento
        resultado.detalhamento = [
            DetalhamentoImposto("IRPJ (15%)", LUCRO_REAL["irpj_base"], lucro_presumido_mes, irpj_base),
            DetalhamentoImposto(
                "IRPJ Adicional (10%)", LUCRO_REAL["irpj_adicional"], excedente / 3, irpj_adicional_mes
            ),
            DetalhamentoImposto("CSLL (9%)", LUCRO_REAL["csll"], lucro_presumido_mes, csll),
            DetalhamentoImposto("PIS (1,65% nc)", LUCRO_REAL["pis_ncum"], receita_mes, pis),
            DetalhamentoImposto("COFINS (7,6% nc)", LUCRO_REAL["cofins_ncum"], receita_mes, cofins),
            DetalhamentoImposto("ISS (5% Manaus)", LUCRO_REAL["iss_manaus"], receita_mes, iss),
        ]

        return resultado

    # ── Comparativo ──────────────────────────────────────────────────────────

    def comparar_regimes(
        self,
        receita_anual: Decimal,
        custos_dedutiveis_anual: Decimal = Decimal("0"),
        liminares: list[str] | None = None,
    ) -> ComparativoRegimes:
        """
        Compara carga tributária entre Simples Nacional e Lucro Real.
        Útil para decidir quando migrar Eletrônica de volta para o Simples.
        """
        liminares = liminares or []
        receita_mes = (receita_anual / 12).quantize(Decimal("0.01"), ROUND_HALF_UP)
        receita_trimestre = (receita_anual / 4).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # Simples
        simples = self.calcular_simples(
            receita_mes=receita_mes,
            rbt12=receita_anual,
            liminares=liminares,
        )
        simples_anual = (simples.valor_das * 12).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # Lucro Real
        lr = self.calcular_lucro_real(
            receita_mes=receita_mes,
            receita_trimestre=receita_trimestre,
            custos_dedutiveis_mes=(custos_dedutiveis_anual / 12).quantize(Decimal("0.01"), ROUND_HALF_UP),
        )
        lr_anual = (lr.total_impostos_mes * 12).quantize(Decimal("0.01"), ROUND_HALF_UP)

        economia = (lr_anual - simples_anual).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # Percentuais
        pct_simples = (
            (simples_anual / receita_anual * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
            if receita_anual
            else Decimal("0")
        )
        pct_lr = (
            (lr_anual / receita_anual * 100).quantize(Decimal("0.01"), ROUND_HALF_UP) if receita_anual else Decimal("0")
        )

        if simples_anual < lr_anual:
            recomendacao = f"Simples Nacional e mais vantajoso. Economia anual estimada: R$ {economia:,.2f} ({pct_lr - pct_simples:.1f}pp a menos de impostos)."
        elif lr_anual < simples_anual:
            recomendacao = f"Lucro Real e mais vantajoso para este faturamento. Diferenca: R$ {-economia:,.2f}/ano."
        else:
            recomendacao = "Os regimes apresentam carga tributaria equivalente."

        observacoes = []
        if receita_anual > Decimal("4800000"):
            observacoes.append(
                "ATENCAO: Faturamento acima do limite do Simples Nacional (R$ 4,8M). Verificar sublimite AM."
            )
        if receita_anual > Decimal("3600000"):
            observacoes.append("Faixa 6 do Simples (33%). Avaliar Lucro Presumido como alternativa.")

        return ComparativoRegimes(
            receita_bruta_anual=receita_anual,
            simples_nacional_total=simples_anual,
            simples_nacional_percentual=pct_simples,
            lucro_real_total=lr_anual,
            lucro_real_percentual=pct_lr,
            economia_simples=economia,
            recomendacao=recomendacao,
            observacoes=observacoes,
        )

    # ── Retenções na Fonte ───────────────────────────────────────────────────

    def calcular_retencoes_nfse(
        self,
        valor_servico: Decimal,
        regime_empresa: str = "simples_nacional",
        liminares: list[str] | None = None,
    ) -> CalculoRetencoes:
        """
        Calcula retenções na fonte sobre NFS-e.

        Regras:
        - INSS 11%: Se Simples, verificar liminar. Se Lucro Real, sempre retém.
        - IR 1.5%: Para serviços de vigilância acima de R$ 215,05/mês
        - CSLL 1%: Empresa tomadora PJ
        - PIS 0.65% + COFINS 3%: Se Lucro Real. Se Simples + liminar: zerados
        - ISS 5%: Retenção pelo tomador (Manaus)
        """
        liminares = liminares or []
        resultado = CalculoRetencoes(valor_servico=valor_servico)

        # INSS 11%
        if regime_empresa == "lucro_real" or "inss_nao_retido" not in liminares:
            resultado.inss = (valor_servico * Decimal("0.11")).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            resultado.liminares_aplicadas.append("inss_nao_retido")

        # IR 1.5% (vigilância - serviços especializados)
        if valor_servico >= Decimal("215.05"):
            resultado.ir = (valor_servico * Decimal("0.015")).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # CSLL 1%
        resultado.csll = (valor_servico * Decimal("0.01")).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # PIS 0.65% + COFINS 3%
        if "pis_cofins_zero" in liminares and regime_empresa == "simples_nacional":
            resultado.liminares_aplicadas.append("pis_cofins_zero")
        else:
            resultado.pis = (valor_servico * Decimal("0.0065")).quantize(Decimal("0.01"), ROUND_HALF_UP)
            resultado.cofins = (valor_servico * Decimal("0.03")).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # ISS 5% Manaus
        resultado.iss = (valor_servico * Decimal("0.05")).quantize(Decimal("0.01"), ROUND_HALF_UP)

        resultado.total_retencoes = (
            resultado.inss + resultado.ir + resultado.csll + resultado.pis + resultado.cofins + resultado.iss
        ).quantize(Decimal("0.01"), ROUND_HALF_UP)

        resultado.valor_liquido = (valor_servico - resultado.total_retencoes).quantize(Decimal("0.01"), ROUND_HALF_UP)

        return resultado

    # ── Verificação Limite Simples ─────────────────────────────────────────

    def verificar_limite_simples(
        self,
        rbt12: Decimal,
        limite_nacional: Decimal = Decimal("4800000"),
        sublimite_am: Decimal = Decimal("3600000"),
    ) -> dict:
        """
        Verifica se empresa está próxima do limite do Simples Nacional.

        Returns:
            dict com status, percentual_utilizado, alertas
        """
        pct_nacional = (rbt12 / limite_nacional * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)
        pct_sublimite = (rbt12 / sublimite_am * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)

        alertas = []
        status = "ok"

        if rbt12 >= limite_nacional:
            status = "limite_excedido"
            alertas.append("LIMITE DO SIMPLES EXCEDIDO! Empresa deve sair do Simples Nacional.")
        elif rbt12 >= sublimite_am:
            status = "sublimite_am_excedido"
            alertas.append("Sublimite estadual AM excedido (R$ 3,6M). ICMS e ISS passam ao regime normal.")
        elif pct_nacional >= 80:
            status = "atencao"
            alertas.append(f"{pct_nacional}% do limite nacional atingido. Monitorar crescimento.")
        elif pct_nacional >= 60:
            alertas.append(f"{pct_nacional}% do limite nacional. Planejamento tributario recomendado.")

        return {
            "rbt12": float(rbt12),
            "limite_nacional": float(limite_nacional),
            "sublimite_am": float(sublimite_am),
            "percentual_limite_nacional": float(pct_nacional),
            "percentual_sublimite_am": float(pct_sublimite),
            "status": status,
            "alertas": alertas,
        }
