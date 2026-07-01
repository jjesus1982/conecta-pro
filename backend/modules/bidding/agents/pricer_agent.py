"""
PRICER Agent - Precificacao para propostas de licitacao
========================================================
Calcula precos com BDI, impostos por regime tributario,
e gera 3 cenarios: conservador, moderado, agressivo.
"""

import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from modules.bidding.agents.base_agent import AgentConfig, AgentStatus, BaseAgent

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# DTOs
# ──────────────────────────────────────────────


class RegimeTributario(StrEnum):
    """Regime tributario da empresa."""

    SIMPLES_NACIONAL = "simples"
    LUCRO_PRESUMIDO = "lucro_presumido"
    LUCRO_REAL = "lucro_real"


class CenarioTipo(StrEnum):
    """Tipo de cenario de precificacao."""

    CONSERVADOR = "conservador"
    MODERADO = "moderado"
    AGRESSIVO = "agressivo"


class PostoServico(BaseModel):
    """Posto de servico (portaria/servicos para condominios) para calculo."""

    tipo: str = "12x36"  # 12x36, 44h, 24h, diurno, noturno
    quantidade: int = 1
    armado: bool = False
    escala_descricao: str | None = None
    adicional_noturno: bool = False
    # Periculosidade 30% só p/ cargos com direito na CCT (Vigia, Eletricista
    # AT/BT, Téc. Manut. Máquinas) — NÃO default p/ todos.
    adicional_periculosidade: bool = False
    insalubridade: bool = False  # 10% só p/ Piscineiro, Aux. Controle Pragas


class CustoMaoDeObra(BaseModel):
    """Detalhamento do custo de mao de obra."""

    salario_base: Decimal = Decimal("0")
    adicional_periculosidade: Decimal = Decimal("0")
    adicional_noturno: Decimal = Decimal("0")
    adicional_insalubridade: Decimal = Decimal("0")
    horas_extras: Decimal = Decimal("0")
    total_remuneracao: Decimal = Decimal("0")

    # Encargos sociais e trabalhistas
    inss_patronal: Decimal = Decimal("0")
    fgts: Decimal = Decimal("0")
    terceiros_sistema_s: Decimal = Decimal("0")
    provisao_ferias: Decimal = Decimal("0")
    provisao_13o: Decimal = Decimal("0")
    provisao_rescisao: Decimal = Decimal("0")
    total_encargos: Decimal = Decimal("0")

    # Beneficios
    vale_transporte: Decimal = Decimal("0")
    vale_alimentacao: Decimal = Decimal("0")
    assistencia_medica: Decimal = Decimal("0")
    seguro_vida: Decimal = Decimal("0")
    uniforme_epi: Decimal = Decimal("0")
    total_beneficios: Decimal = Decimal("0")

    # Repasse contratual obrigatorio 7,5% (CCT SINDECOMPRESTS 2026 Clausula 2a §3º)
    repasse_contratual: Decimal = Decimal("0")

    # Total por posto/mes
    custo_mensal_unitario: Decimal = Decimal("0")

    # Quantidade e total
    quantidade_profissionais: int = 0
    custo_mensal_total: Decimal = Decimal("0")


class CenarioPrecificacao(BaseModel):
    """Cenario de precificacao."""

    tipo: CenarioTipo
    descricao: str

    # Custos
    custo_mao_de_obra: CustoMaoDeObra
    custos_indiretos: Decimal = Decimal("0")
    custo_total_direto: Decimal = Decimal("0")

    # BDI
    bdi_percentual: Decimal = Decimal("0")
    valor_bdi: Decimal = Decimal("0")

    # Impostos
    impostos_detalhamento: dict[str, Decimal] = Field(default_factory=dict)
    total_impostos: Decimal = Decimal("0")

    # Lucro
    margem_lucro_percentual: Decimal = Decimal("0")
    valor_lucro: Decimal = Decimal("0")

    # Totais
    preco_mensal: Decimal = Decimal("0")
    preco_anual: Decimal = Decimal("0")
    preco_total_contrato: Decimal = Decimal("0")


class PricingInput(BaseModel):
    """Dados de entrada para precificacao."""

    # Postos
    postos: list[PostoServico] = Field(default_factory=list)

    # Valores de referencia — piso da CCT SINDECOMPRESTS 2026 (agentes de
    # portaria/servicos p/ condominios, NAO vigilancia armada). Fonte unica:
    # tabela cct_cargos (piso da categoria R$1.670). Idealmente sobrescrito
    # via cct_pricing_source.piso_cargo(); default = piso da categoria.
    salario_base_categoria: Decimal = Decimal("1670.00")
    salario_base_categoria_armado: Decimal = Decimal("1670.00")

    # Beneficios (valores mensais por posto) — VR R$22/dia (CCT 2026)
    vale_transporte_dia: Decimal = Decimal("11.00")
    vale_alimentacao_dia: Decimal = Decimal("22.00")
    assistencia_medica: Decimal = Decimal("250.00")
    seguro_vida: Decimal = Decimal("15.00")
    uniforme_epi_mensal: Decimal = Decimal("120.00")

    # Regime tributario
    regime_tributario: RegimeTributario = RegimeTributario.LUCRO_REAL

    # Contrato
    prazo_contrato_meses: int = 12
    valor_estimado_edital: Decimal | None = None

    # Custos indiretos
    custo_administrativo_percentual: Decimal = Decimal("8.0")
    custo_equipamento_mensal: Decimal = Decimal("0")  # CFTV, radio, etc


class PricingResponse(BaseModel):
    """Resultado completo da precificacao."""

    # Cenarios
    cenarios: list[CenarioPrecificacao] = Field(default_factory=list)

    # Cenario recomendado
    cenario_recomendado: CenarioTipo = CenarioTipo.MODERADO

    # Resumo
    preco_mensal_recomendado: Decimal = Decimal("0")
    preco_total_recomendado: Decimal = Decimal("0")

    # Comparacao com edital
    valor_estimado_edital: Decimal | None = None
    diferenca_percentual: Decimal | None = None  # vs estimado edital

    # Metadados
    regime_tributario: str = ""
    prazo_contrato_meses: int = 12
    calculado_em: datetime | None = None
    observacoes: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Aliquotas por regime tributario
# ──────────────────────────────────────────────

ALIQUOTAS = {
    RegimeTributario.SIMPLES_NACIONAL: {
        # Anexo IV (vigilancia) - faixa 3 (faturamento 720k-1.8M)
        "aliquota_unica": Decimal("13.50"),
        "iss": Decimal("3.50"),
        "pis": Decimal("0"),  # Ja incluso no DAS
        "cofins": Decimal("0"),
        "irpj": Decimal("0"),
        "csll": Decimal("0"),
        "inss_patronal": Decimal("20.0"),  # Anexo IV nao inclui CPP
    },
    RegimeTributario.LUCRO_PRESUMIDO: {
        "iss": Decimal("5.00"),
        "pis": Decimal("0.65"),
        "cofins": Decimal("3.00"),
        "irpj": Decimal("4.80"),  # 15% sobre 32%
        "csll": Decimal("2.88"),  # 9% sobre 32%
        "inss_patronal": Decimal("20.0"),
    },
    RegimeTributario.LUCRO_REAL: {
        "iss": Decimal("5.00"),
        "pis": Decimal("1.65"),
        "cofins": Decimal("7.60"),
        "irpj": Decimal("4.80"),
        "csll": Decimal("2.88"),
        "inss_patronal": Decimal("20.0"),
    },
}

# Encargos trabalhistas comuns
ENCARGOS_TRABALHISTAS = {
    "fgts": Decimal("8.0"),
    "terceiros_sistema_s": Decimal("5.8"),  # SESC/SENAC/SEBRAE/INCRA/SAL-EDUCACAO
    "provisao_ferias": Decimal("12.10"),  # 1/12 + 1/3
    "provisao_13o": Decimal("8.93"),  # 1/12 + encargos
    "provisao_rescisao": Decimal("5.20"),  # Multa FGTS + aviso previo proporcional
}

# Fatores de escala (quantos profissionais por posto)
FATOR_ESCALA = {
    "12x36": Decimal("2.20"),  # 2 titulares + cobertura ferias/folgas
    "44h": Decimal("1.15"),  # 1 titular + cobertura
    "24h": Decimal("4.40"),  # 4 titulares + cobertura
    "diurno": Decimal("1.15"),
    "noturno": Decimal("1.15"),
}


# ──────────────────────────────────────────────
# PRICER Agent
# ──────────────────────────────────────────────


class PricerAgent(BaseAgent):
    """
    Agente PRICER - Precificacao de propostas de licitacao.

    Responsabilidades:
    - Calcular custo de mao de obra (salario + encargos + beneficios)
    - Aplicar BDI (Beneficios e Despesas Indiretas)
    - Calcular impostos por regime tributario
    - Gerar 3 cenarios: conservador, moderado, agressivo
    - Comparar com valor estimado do edital
    """

    AGENT_NAME = "pricer"
    AGENT_DESCRIPTION = "Precificacao de propostas de licitacao com BDI"
    AGENT_STATUS = AgentStatus.DEVELOPMENT

    # Margens de lucro por cenario
    MARGEM_CONSERVADOR = Decimal("12.0")
    MARGEM_MODERADO = Decimal("8.0")
    MARGEM_AGRESSIVO = Decimal("4.5")

    # BDI base (sem impostos e lucro)
    BDI_ADMINISTRACAO = Decimal("6.0")
    BDI_SEGURO_GARANTIA = Decimal("1.0")
    BDI_RISCO = Decimal("1.5")
    BDI_DESPESAS_FINANCEIRAS = Decimal("0.8")

    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config)

    async def execute(
        self,
        pricing_input: PricingInput | dict | None = None,
        analysis: dict | None = None,
        **kwargs,
    ) -> dict:
        """
        Calcula precificacao para proposta de licitacao.

        Args:
            pricing_input: Dados de entrada para precificacao.
            analysis: Resultado do ANALYST (opcional, para extrair dados do edital).

        Returns:
            PricingResponse como dict.
        """
        # Converter dict para PricingInput se necessario
        if isinstance(pricing_input, dict):
            pricing_input = PricingInput(**pricing_input)

        if pricing_input is None:
            pricing_input = self._build_input_from_analysis(analysis) if analysis else PricingInput()

        # Se nao tem postos definidos, criar um default
        if not pricing_input.postos:
            pricing_input.postos = [PostoServico(tipo="12x36", quantidade=1)]

        # Gerar 3 cenarios
        cenarios = [
            self._calcular_cenario(pricing_input, CenarioTipo.CONSERVADOR),
            self._calcular_cenario(pricing_input, CenarioTipo.MODERADO),
            self._calcular_cenario(pricing_input, CenarioTipo.AGRESSIVO),
        ]

        # Cenario recomendado
        cenario_recomendado = CenarioTipo.MODERADO
        moderado = cenarios[1]

        # Se o preco moderado esta acima do estimado, recomendar agressivo
        observacoes = []
        diferenca = None
        if pricing_input.valor_estimado_edital and pricing_input.valor_estimado_edital > 0:
            valor_edital_mensal = pricing_input.valor_estimado_edital / pricing_input.prazo_contrato_meses
            diferenca = (moderado.preco_mensal - valor_edital_mensal) / valor_edital_mensal * 100
            if diferenca > Decimal("5"):
                cenario_recomendado = CenarioTipo.AGRESSIVO
                observacoes.append(f"Preco moderado {diferenca:.1f}% acima do estimado - recomendado cenario agressivo")
            elif diferenca < Decimal("-15"):
                cenario_recomendado = CenarioTipo.CONSERVADOR
                observacoes.append(
                    f"Preco moderado {abs(diferenca):.1f}% abaixo do estimado - margem para cenario conservador"
                )

        # Selecionar cenario recomendado
        idx = [CenarioTipo.CONSERVADOR, CenarioTipo.MODERADO, CenarioTipo.AGRESSIVO].index(cenario_recomendado)
        recomendado = cenarios[idx]

        response = PricingResponse(
            cenarios=cenarios,
            cenario_recomendado=cenario_recomendado,
            preco_mensal_recomendado=recomendado.preco_mensal,
            preco_total_recomendado=recomendado.preco_total_contrato,
            valor_estimado_edital=pricing_input.valor_estimado_edital,
            diferenca_percentual=diferenca,
            regime_tributario=pricing_input.regime_tributario.value,
            prazo_contrato_meses=pricing_input.prazo_contrato_meses,
            calculado_em=datetime.utcnow(),
            observacoes=observacoes,
        )

        self.logger.info(
            f"Precificacao: {cenario_recomendado.value} R${recomendado.preco_mensal:,.2f}/mes "
            f"(total R${recomendado.preco_total_contrato:,.2f})"
        )

        return response.model_dump(mode="json")

    def _calcular_cenario(
        self,
        inp: PricingInput,
        cenario: CenarioTipo,
    ) -> CenarioPrecificacao:
        """Calcula um cenario completo de precificacao."""
        d = Decimal
        margem = {
            CenarioTipo.CONSERVADOR: self.MARGEM_CONSERVADOR,
            CenarioTipo.MODERADO: self.MARGEM_MODERADO,
            CenarioTipo.AGRESSIVO: self.MARGEM_AGRESSIVO,
        }[cenario]

        descricao = {
            CenarioTipo.CONSERVADOR: "Margem alta, menor risco, maior preco",
            CenarioTipo.MODERADO: "Equilibrio entre margem e competitividade",
            CenarioTipo.AGRESSIVO: "Margem minima, maximo de competitividade",
        }[cenario]

        # 1. Calcular custo de mao de obra
        custo_mdo = self._calcular_mao_de_obra(inp)

        # 2. Custos indiretos
        custos_indiretos = (
            custo_mdo.custo_mensal_total * inp.custo_administrativo_percentual / d("100") + inp.custo_equipamento_mensal
        )
        custos_indiretos = custos_indiretos.quantize(d("0.01"), rounding=ROUND_HALF_UP)

        # 3. Custo total direto
        custo_total_direto = custo_mdo.custo_mensal_total + custos_indiretos

        # 4. BDI (sem impostos e lucro)
        bdi_base = self.BDI_ADMINISTRACAO + self.BDI_SEGURO_GARANTIA + self.BDI_RISCO + self.BDI_DESPESAS_FINANCEIRAS

        # 5. Impostos
        aliquotas = ALIQUOTAS[inp.regime_tributario]
        impostos_detalhamento = {}

        if inp.regime_tributario == RegimeTributario.SIMPLES_NACIONAL:
            # Simples usa aliquota unica sobre faturamento
            total_impostos_pct = aliquotas["aliquota_unica"]
            impostos_detalhamento["das_simples"] = total_impostos_pct
        else:
            for imposto in ["iss", "pis", "cofins", "irpj", "csll"]:
                if imposto in aliquotas:
                    impostos_detalhamento[imposto] = aliquotas[imposto]
            total_impostos_pct = sum(impostos_detalhamento.values())

        # 6. BDI total = base + lucro + impostos
        bdi_total = bdi_base + margem + total_impostos_pct

        # 7. Calcular preco
        # Preco = Custo / (1 - BDI/100)
        divisor = d("1") - bdi_total / d("100")
        if divisor <= 0:
            divisor = d("0.01")  # Fallback

        preco_mensal = (custo_total_direto / divisor).quantize(d("0.01"), rounding=ROUND_HALF_UP)

        # Valores de BDI, impostos e lucro
        valor_bdi_base = (custo_total_direto * bdi_base / d("100")).quantize(d("0.01"), rounding=ROUND_HALF_UP)
        total_impostos = (preco_mensal * total_impostos_pct / d("100")).quantize(d("0.01"), rounding=ROUND_HALF_UP)
        valor_lucro = (preco_mensal * margem / d("100")).quantize(d("0.01"), rounding=ROUND_HALF_UP)

        # Totais
        preco_anual = preco_mensal * 12
        preco_total = preco_mensal * inp.prazo_contrato_meses

        # Converter impostos para dict serializavel
        impostos_dict = dict(impostos_detalhamento)

        return CenarioPrecificacao(
            tipo=cenario,
            descricao=descricao,
            custo_mao_de_obra=custo_mdo,
            custos_indiretos=custos_indiretos,
            custo_total_direto=custo_total_direto,
            bdi_percentual=bdi_total,
            valor_bdi=valor_bdi_base,
            impostos_detalhamento=impostos_dict,
            total_impostos=total_impostos,
            margem_lucro_percentual=margem,
            valor_lucro=valor_lucro,
            preco_mensal=preco_mensal,
            preco_anual=preco_anual,
            preco_total_contrato=preco_total,
        )

    def _calcular_mao_de_obra(self, inp: PricingInput) -> CustoMaoDeObra:
        """Calcula custo total de mao de obra para todos os postos."""
        d = Decimal

        total_profissionais = 0
        custo_total = d("0")

        # Para simplificar, calculamos um custo medio ponderado
        total_salario = d("0")
        total_periculosidade = d("0")
        total_noturno = d("0")
        total_insalubridade = d("0")
        total_encargos = d("0")
        total_beneficios = d("0")
        total_repasse = d("0")

        for posto in inp.postos:
            # Fator de escala (quantos profissionais por posto)
            fator = FATOR_ESCALA.get(posto.tipo, d("1.15"))
            profissionais_posto = int((fator * posto.quantidade).quantize(d("1"), rounding=ROUND_HALF_UP))
            total_profissionais += profissionais_posto

            # Salario base
            salario = inp.salario_base_categoria_armado if posto.armado else inp.salario_base_categoria

            # Adicionais CCT — periculosidade 30% e insalubridade 10% sobre o
            # PISO da categoria (nao sobre salario minimo velho).
            periculosidade = salario * d("0.30") if posto.adicional_periculosidade else d("0")
            noturno = salario * d("0.20") if posto.adicional_noturno else d("0")
            insalubridade = salario * d("0.10") if posto.insalubridade else d("0")

            remuneracao = salario + periculosidade + noturno + insalubridade

            # Encargos sobre remuneracao
            aliq = ALIQUOTAS[inp.regime_tributario]
            inss_patronal = remuneracao * aliq["inss_patronal"] / d("100")
            fgts = remuneracao * ENCARGOS_TRABALHISTAS["fgts"] / d("100")
            terceiros = remuneracao * ENCARGOS_TRABALHISTAS["terceiros_sistema_s"] / d("100")
            prov_ferias = remuneracao * ENCARGOS_TRABALHISTAS["provisao_ferias"] / d("100")
            prov_13o = remuneracao * ENCARGOS_TRABALHISTAS["provisao_13o"] / d("100")
            prov_rescisao = remuneracao * ENCARGOS_TRABALHISTAS["provisao_rescisao"] / d("100")

            encargos_total = inss_patronal + fgts + terceiros + prov_ferias + prov_13o + prov_rescisao

            # Beneficios
            dias_uteis = d("22")
            vt = inp.vale_transporte_dia * dias_uteis
            va = inp.vale_alimentacao_dia * dias_uteis
            beneficios_total = vt + va + inp.assistencia_medica + inp.seguro_vida + inp.uniforme_epi_mensal

            # Repasse contratual obrigatorio 7,5% (CCT Clausula 2a §3º) sobre o
            # custo (remuneracao + encargos + beneficios).
            custo_sem_repasse = remuneracao + encargos_total + beneficios_total
            repasse = custo_sem_repasse * d("0.075")
            custo_unitario = custo_sem_repasse + repasse

            # Acumular para o total (proporcional aos profissionais)
            fator_qtd = d(str(profissionais_posto))
            total_salario += salario * fator_qtd
            total_periculosidade += periculosidade * fator_qtd
            total_noturno += noturno * fator_qtd
            total_insalubridade += insalubridade * fator_qtd
            total_encargos += encargos_total * fator_qtd
            total_beneficios += beneficios_total * fator_qtd
            total_repasse += repasse * fator_qtd
            custo_total += custo_unitario * fator_qtd

        # Montar resposta
        total_remuneracao = total_salario + total_periculosidade + total_noturno + total_insalubridade
        custo_unitario_medio = (custo_total / d(str(max(total_profissionais, 1)))).quantize(
            d("0.01"), rounding=ROUND_HALF_UP
        )

        return CustoMaoDeObra(
            salario_base=total_salario.quantize(d("0.01")),
            adicional_periculosidade=total_periculosidade.quantize(d("0.01")),
            adicional_noturno=total_noturno.quantize(d("0.01")),
            adicional_insalubridade=total_insalubridade.quantize(d("0.01")),
            total_remuneracao=total_remuneracao.quantize(d("0.01")),
            total_encargos=total_encargos.quantize(d("0.01")),
            vale_transporte=(inp.vale_transporte_dia * d("22") * d(str(total_profissionais))).quantize(d("0.01")),
            vale_alimentacao=(inp.vale_alimentacao_dia * d("22") * d(str(total_profissionais))).quantize(d("0.01")),
            assistencia_medica=(inp.assistencia_medica * d(str(total_profissionais))).quantize(d("0.01")),
            seguro_vida=(inp.seguro_vida * d(str(total_profissionais))).quantize(d("0.01")),
            uniforme_epi=(inp.uniforme_epi_mensal * d(str(total_profissionais))).quantize(d("0.01")),
            total_beneficios=total_beneficios.quantize(d("0.01")),
            repasse_contratual=total_repasse.quantize(d("0.01")),
            custo_mensal_unitario=custo_unitario_medio,
            quantidade_profissionais=total_profissionais,
            custo_mensal_total=custo_total.quantize(d("0.01")),
        )

    def _build_input_from_analysis(self, analysis: dict) -> PricingInput:
        """Constroi PricingInput a partir dos dados do ANALYST."""
        postos = []

        tipos_posto = analysis.get("tipos_posto", [])
        qtd_postos = analysis.get("quantidade_postos") or 1
        armado = analysis.get("armamento_necessario", False)

        if tipos_posto:
            # Distribuir postos pelos tipos informados
            por_tipo = max(1, qtd_postos // len(tipos_posto))
            for tipo in tipos_posto:
                tipo_normalizado = self._normalizar_tipo_posto(tipo)
                postos.append(
                    PostoServico(
                        tipo=tipo_normalizado,
                        quantidade=por_tipo,
                        armado=armado,
                        adicional_noturno="noturno" in tipo.lower() or "24h" in tipo.lower(),
                    )
                )
        else:
            postos.append(
                PostoServico(
                    tipo="12x36",
                    quantidade=qtd_postos,
                    armado=armado,
                )
            )

        valor_estimado = analysis.get("valor_estimado")
        prazo = analysis.get("prazo_contrato_meses") or 12

        return PricingInput(
            postos=postos,
            prazo_contrato_meses=prazo,
            valor_estimado_edital=Decimal(str(valor_estimado)) if valor_estimado else None,
        )

    def _normalizar_tipo_posto(self, tipo: str) -> str:
        """Normaliza descricao de tipo de posto para chave padrao."""
        tipo_lower = tipo.lower().strip()
        if "12x36" in tipo_lower or "12 x 36" in tipo_lower:
            return "12x36"
        if "24h" in tipo_lower or "24 h" in tipo_lower:
            return "24h"
        if "44h" in tipo_lower or "44 h" in tipo_lower:
            return "44h"
        if "noturno" in tipo_lower:
            return "noturno"
        if "diurno" in tipo_lower:
            return "diurno"
        return "12x36"  # Default
