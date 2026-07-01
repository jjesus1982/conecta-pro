"""
DP Agent - Departamento Pessoal.
Responsavel por folha, admissao, demissao, ferias, beneficios, eSocial.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from ..core.events import Event, GPEventTypes
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


# ==========================================
# SKILLS
# ==========================================


class PayrollSkill:
    """Calculo completo de folha de pagamento."""

    # Tabela INSS 2026 (simplificada)
    INSS_FAIXAS = [
        (Decimal("1412.00"), Decimal("0.075")),
        (Decimal("2666.68"), Decimal("0.09")),
        (Decimal("4000.03"), Decimal("0.12")),
        (Decimal("7786.02"), Decimal("0.14")),
    ]
    INSS_TETO = Decimal("908.86")

    # Tabela IR 2026 (simplificada)
    IR_FAIXAS = [
        (Decimal("2259.20"), Decimal("0"), Decimal("0")),
        (Decimal("2826.65"), Decimal("0.075"), Decimal("169.44")),
        (Decimal("3751.05"), Decimal("0.15"), Decimal("381.44")),
        (Decimal("4664.68"), Decimal("0.225"), Decimal("662.77")),
        (Decimal("999999.99"), Decimal("0.275"), Decimal("896.00")),
    ]

    def calcular_inss(self, salario_bruto: Decimal) -> Decimal:
        """Calcula desconto INSS progressivo."""
        inss = Decimal("0")
        base_anterior = Decimal("0")

        for teto_faixa, aliquota in self.INSS_FAIXAS:
            if salario_bruto <= base_anterior:
                break
            base_calculo = min(salario_bruto, teto_faixa) - base_anterior
            if base_calculo > 0:
                inss += base_calculo * aliquota
            base_anterior = teto_faixa

        return min(inss, self.INSS_TETO).quantize(Decimal("0.01"))

    def calcular_ir(self, base_ir: Decimal) -> Decimal:
        """Calcula desconto IRRF."""
        for teto, aliquota, deducao in self.IR_FAIXAS:
            if base_ir <= teto:
                ir = (base_ir * aliquota) - deducao
                return max(ir, Decimal("0")).quantize(Decimal("0.01"))
        return Decimal("0")

    def calcular_fgts(self, salario_bruto: Decimal) -> Decimal:
        """Calcula FGTS (8% sobre bruto)."""
        return (salario_bruto * Decimal("0.08")).quantize(Decimal("0.01"))

    def calcular_folha(
        self,
        salario_base: Decimal,
        horas_extras_50: Decimal = Decimal("0"),
        horas_extras_100: Decimal = Decimal("0"),
        adicional_noturno_horas: Decimal = Decimal("0"),
        adicional_insalubridade: Decimal = Decimal("0"),
        adicional_periculosidade: Decimal = Decimal("0"),
        faltas_dias: int = 0,
        atrasos_horas: Decimal = Decimal("0"),
        desconto_vt: Decimal = Decimal("0"),
        desconto_plano_saude: Decimal = Decimal("0"),
        desconto_outros: Decimal = Decimal("0"),
        dependentes_ir: int = 0,
    ) -> dict[str, Any]:
        """Calcula folha completa de um funcionario."""
        # Valor hora
        valor_hora = salario_base / Decimal("220")

        # Proventos
        he_50 = horas_extras_50 * valor_hora * Decimal("1.5")
        he_100 = horas_extras_100 * valor_hora * Decimal("2.0")
        adic_not = adicional_noturno_horas * valor_hora * Decimal("0.2")
        total_proventos = salario_base + he_50 + he_100 + adic_not + adicional_insalubridade + adicional_periculosidade

        # Descontos por falta/atraso
        desconto_faltas = Decimal(faltas_dias) * (salario_base / Decimal("30"))
        desconto_atrasos = atrasos_horas * valor_hora

        salario_bruto = total_proventos - desconto_faltas - desconto_atrasos

        # INSS
        inss = self.calcular_inss(salario_bruto)

        # IR
        deducao_dependentes = Decimal(dependentes_ir) * Decimal("189.59")
        base_ir = salario_bruto - inss - deducao_dependentes
        ir = self.calcular_ir(base_ir)

        # FGTS (sobre bruto, nao desconta)
        fgts = self.calcular_fgts(salario_bruto)

        # Total descontos
        total_descontos = (
            inss + ir + desconto_vt + desconto_plano_saude + desconto_outros + desconto_faltas + desconto_atrasos
        )

        # Liquido
        salario_liquido = total_proventos - total_descontos

        return {
            "salario_base": float(salario_base),
            "valor_hora": float(valor_hora.quantize(Decimal("0.01"))),
            "proventos": {
                "salario_base": float(salario_base),
                "horas_extras_50": float(he_50.quantize(Decimal("0.01"))),
                "horas_extras_100": float(he_100.quantize(Decimal("0.01"))),
                "adicional_noturno": float(adic_not.quantize(Decimal("0.01"))),
                "adicional_insalubridade": float(adicional_insalubridade),
                "adicional_periculosidade": float(adicional_periculosidade),
                "total_proventos": float(total_proventos.quantize(Decimal("0.01"))),
            },
            "descontos": {
                "inss": float(inss),
                "ir": float(ir),
                "fgts_empresa": float(fgts),
                "vt": float(desconto_vt),
                "plano_saude": float(desconto_plano_saude),
                "faltas": float(desconto_faltas.quantize(Decimal("0.01"))),
                "atrasos": float(desconto_atrasos.quantize(Decimal("0.01"))),
                "outros": float(desconto_outros),
                "total_descontos": float(total_descontos.quantize(Decimal("0.01"))),
            },
            "salario_liquido": float(salario_liquido.quantize(Decimal("0.01"))),
        }


class VacationSkill:
    """Calculo e controle de ferias."""

    def calcular_ferias(
        self,
        salario_base: Decimal,
        dias: int = 30,
        abono_pecuniario: bool = False,
        media_horas_extras: Decimal = Decimal("0"),
    ) -> dict[str, Any]:
        """Calcula valores de ferias."""
        valor_dia = salario_base / Decimal("30")

        # Dias de gozo
        dias_gozo = dias
        if abono_pecuniario:
            dias_gozo = dias - 10  # Vende 10 dias

        # Base de ferias
        base_ferias = valor_dia * Decimal(dias_gozo) + media_horas_extras

        # 1/3 constitucional
        terco = base_ferias / Decimal("3")

        # Abono pecuniario
        valor_abono = Decimal("0")
        terco_abono = Decimal("0")
        if abono_pecuniario:
            valor_abono = valor_dia * Decimal("10")
            terco_abono = valor_abono / Decimal("3")

        total_bruto = base_ferias + terco + valor_abono + terco_abono

        return {
            "dias_gozo": dias_gozo,
            "dias_abono": 10 if abono_pecuniario else 0,
            "base_ferias": float(base_ferias.quantize(Decimal("0.01"))),
            "terco_constitucional": float(terco.quantize(Decimal("0.01"))),
            "abono_pecuniario": float(valor_abono.quantize(Decimal("0.01"))),
            "terco_abono": float(terco_abono.quantize(Decimal("0.01"))),
            "total_bruto": float(total_bruto.quantize(Decimal("0.01"))),
        }


class BenefitsSkill:
    """Gestao de beneficios."""

    VT_DESCONTO_MAX = Decimal("0.06")  # 6% do salario

    def calcular_desconto_vt(
        self, salario_base: Decimal, valor_diario_vt: Decimal, dias_uteis: int = 22
    ) -> dict[str, Any]:
        """Calcula desconto de Vale Transporte."""
        custo_total = valor_diario_vt * Decimal(dias_uteis)
        desconto_max = salario_base * self.VT_DESCONTO_MAX
        desconto = min(custo_total, desconto_max)

        return {
            "custo_total_empresa": float(custo_total.quantize(Decimal("0.01"))),
            "desconto_funcionario": float(desconto.quantize(Decimal("0.01"))),
            "custo_liquido_empresa": float((custo_total - desconto).quantize(Decimal("0.01"))),
        }


class ESocialSkill:
    """Geracao de eventos eSocial."""

    EVENTOS = {
        "admissao": "S-2200",
        "alteracao_cadastral": "S-2205",
        "alteracao_contratual": "S-2206",
        "aso": "S-2220",
        "afastamento_inicio": "S-2230",
        "afastamento_termino": "S-2230",
        "desligamento": "S-2299",
        "remuneracao": "S-1200",
        "pagamento": "S-1210",
    }

    def gerar_evento(self, tipo: str, dados: dict[str, Any]) -> dict[str, Any]:
        """Gera estrutura de evento eSocial."""
        codigo = self.EVENTOS.get(tipo)
        if not codigo:
            raise ValueError(f"Tipo de evento eSocial desconhecido: {tipo}")

        return {
            "tipo": tipo,
            "codigo_evento": codigo,
            "dados": dados,
            "status": "pendente",
            "gerado_em": datetime.utcnow().isoformat(),
        }

    def listar_eventos_pendentes(self, tipo: str = None) -> list[str]:
        """Lista codigos de eventos disponiveis."""
        if tipo:
            return [self.EVENTOS.get(tipo, "")]
        return list(self.EVENTOS.values())


class TaxSkill:
    """Calculo de encargos trabalhistas."""

    def calcular_encargos_empresa(self, salario_bruto: Decimal, rat: Decimal = Decimal("0.03")) -> dict[str, Any]:
        """Calcula encargos patronais."""
        inss_patronal = salario_bruto * Decimal("0.20")
        fgts = salario_bruto * Decimal("0.08")
        rat_valor = salario_bruto * rat
        sistema_s = salario_bruto * Decimal("0.058")  # SESI/SENAI/SEBRAE etc
        salario_educacao = salario_bruto * Decimal("0.025")

        total = inss_patronal + fgts + rat_valor + sistema_s + salario_educacao

        return {
            "inss_patronal": float(inss_patronal.quantize(Decimal("0.01"))),
            "fgts": float(fgts.quantize(Decimal("0.01"))),
            "rat": float(rat_valor.quantize(Decimal("0.01"))),
            "sistema_s": float(sistema_s.quantize(Decimal("0.01"))),
            "salario_educacao": float(salario_educacao.quantize(Decimal("0.01"))),
            "total_encargos": float(total.quantize(Decimal("0.01"))),
            "percentual_total": float(((total / salario_bruto) * 100).quantize(Decimal("0.01"))),
        }


# ==========================================
# DP AGENT
# ==========================================


class DPAgent(BaseAgent):
    """
    Agent do Departamento Pessoal.

    Responsabilidades:
    - Folha de pagamento
    - Admissao/demissao
    - Ferias e beneficios
    - eSocial
    - Encargos trabalhistas
    """

    AGENT_NAME = "DP_AGENT"
    AGENT_VERSION = "1.0.0"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Registra skills
        self.register_skill("PAYROLL", PayrollSkill())
        self.register_skill("VACATION", VacationSkill())
        self.register_skill("BENEFITS", BenefitsSkill())
        self.register_skill("ESOCIAL", ESocialSkill())
        self.register_skill("TAX", TaxSkill())

    @property
    def handled_events(self) -> list[str]:
        return [
            GPEventTypes.FUNCIONARIO_ADMITIDO,
            GPEventTypes.FUNCIONARIO_DEMITIDO,
            GPEventTypes.PONTO_BATIDO,
            GPEventTypes.PONTO_ATRASO,
            GPEventTypes.PONTO_FALTA,
            GPEventTypes.PONTO_HORA_EXTRA,
            GPEventTypes.PONTO_MES_FECHADO,
            GPEventTypes.DOCUMENTO_ASSINADO,
            GPEventTypes.LAUDO_EMITIDO,
            GPEventTypes.SUSPENSAO_APLICADA,
            GPEventTypes.ADVERTENCIA_APLICADA,
        ]

    async def _process_event(self, event: Event) -> None:
        """Processa eventos do DP."""
        handlers = {
            GPEventTypes.FUNCIONARIO_ADMITIDO: self._on_funcionario_admitido,
            GPEventTypes.FUNCIONARIO_DEMITIDO: self._on_funcionario_demitido,
            GPEventTypes.PONTO_MES_FECHADO: self._on_ponto_mes_fechado,
            GPEventTypes.PONTO_ATRASO: self._on_ponto_atraso,
            GPEventTypes.PONTO_FALTA: self._on_ponto_falta,
            GPEventTypes.LAUDO_EMITIDO: self._on_laudo_emitido,
            GPEventTypes.SUSPENSAO_APLICADA: self._on_suspensao_aplicada,
        }

        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)
        else:
            logger.debug(f"DP_AGENT: evento {event.event_type} recebido (sem handler especifico)")

    async def _on_funcionario_admitido(self, event: Event) -> None:
        """Novo funcionario admitido."""
        employee_id = event.payload.get("employee_id")
        logger.info(f"DP: Processando admissao de {employee_id}")

        # Gerar evento eSocial S-2200
        esocial = self.get_skill("ESOCIAL")
        esocial_event = esocial.gerar_evento("admissao", event.payload)

        await self.emit_event(
            event_type=GPEventTypes.DOCUMENTO_CRIADO,
            payload={
                "tipo": "evento_esocial",
                "codigo": esocial_event["codigo_evento"],
                "employee_id": employee_id,
            },
            affected_modules=["GED"],
        )

    async def _on_funcionario_demitido(self, event: Event) -> None:
        """Funcionario demitido."""
        employee_id = event.payload.get("employee_id")
        logger.info(f"DP: Processando demissao de {employee_id}")

        esocial = self.get_skill("ESOCIAL")
        esocial.gerar_evento("desligamento", event.payload)

    async def _on_ponto_mes_fechado(self, event: Event) -> None:
        """Mes de ponto fechado — gerar folha."""
        employee_id = event.payload.get("employee_id")
        month = event.payload.get("month")
        logger.info(f"DP: Gerando folha para {employee_id} ref {month}")

        await self.emit_event(
            event_type=GPEventTypes.FOLHA_CALCULADA,
            payload={"employee_id": employee_id, "month": month},
            affected_modules=["GED", "PORTAL"],
        )

    async def _on_ponto_atraso(self, event: Event) -> None:
        """Registra atraso para desconto em folha."""
        logger.info(f"DP: Atraso registrado - employee={event.payload.get('employee_id')}")

    async def _on_ponto_falta(self, event: Event) -> None:
        """Registra falta para desconto em folha."""
        logger.info(f"DP: Falta registrada - employee={event.payload.get('employee_id')}")

    async def _on_laudo_emitido(self, event: Event) -> None:
        """Laudo SST emitido — aplicar adicional se necessario."""
        tipo_laudo = event.payload.get("tipo_laudo")
        logger.info(f"DP: Laudo {tipo_laudo} recebido, verificando adicionais")

    async def _on_suspensao_aplicada(self, event: Event) -> None:
        """Suspensao aplicada — descontar dias."""
        dias = event.payload.get("dias", 0)
        logger.info(f"DP: Suspensao de {dias} dias - employee={event.payload.get('employee_id')}")
