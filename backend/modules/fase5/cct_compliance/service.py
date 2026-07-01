"""
modules/fase5/cct_compliance/service.py - CCT Compliance Service
================================================================
Servico de validacao e compliance CCT SINDCOND 2026
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from .enums import TipoBeneficio, TipoCargo, TipoJornada
from .models import (
    BENEFICIOS_CCT_2026,
    TABELA_PISOS_SINDCOND_2026,
    ValidacaoCCT,
)

logger = logging.getLogger(__name__)


class CCTComplianceService:
    """
    Servico de compliance CCT SINDCOND 2026.

    Responsabilidades:
    1. Validar salarios contra pisos da CCT
    2. Verificar beneficios obrigatorios
    3. Validar jornadas de trabalho
    4. Calcular encargos e custos
    5. Gerar relatorios de compliance
    """

    def __init__(self):
        self.tabela_pisos = TABELA_PISOS_SINDCOND_2026
        self.beneficios_obrigatorios = BENEFICIOS_CCT_2026
        self.ano_vigencia = 2026
        self.reajuste_percentual = Decimal("7.1")

    def validar_salario(self, cargo: TipoCargo, salario_informado: Decimal) -> dict[str, Any]:
        """Valida salario contra piso da CCT."""
        piso = self.tabela_pisos.get(cargo)

        if not piso:
            return {"valido": False, "erro": f"Cargo {cargo.value} nao encontrado na tabela CCT"}

        diferenca = salario_informado - piso
        percentual_diferenca = ((salario_informado / piso) - 1) * 100

        return {
            "valido": salario_informado >= piso,
            "cargo": cargo.value,
            "piso_cct": str(piso),
            "salario_informado": str(salario_informado),
            "diferenca": str(diferenca),
            "percentual_diferenca": f"{percentual_diferenca:.2f}%",
            "alerta": "Salario abaixo do piso CCT" if salario_informado < piso else None,
        }

    def validar_jornada(self, cargo: TipoCargo, jornada: TipoJornada) -> dict[str, Any]:
        """Valida jornada de trabalho."""
        jornadas_validas = self._get_jornadas_permitidas(cargo)

        return {
            "valido": jornada in jornadas_validas,
            "cargo": cargo.value,
            "jornada_informada": jornada.value,
            "jornadas_permitidas": [j.value for j in jornadas_validas],
            "alerta": f"Jornada {jornada.value} nao permitida para {cargo.value}"
            if jornada not in jornadas_validas
            else None,
        }

    def validar_beneficios(self, beneficios_informados: list[TipoBeneficio]) -> dict[str, Any]:
        """Valida beneficios contra obrigatorios da CCT."""
        obrigatorios = set(self.beneficios_obrigatorios.keys())
        informados = set(beneficios_informados)

        faltantes = obrigatorios - informados
        extras = informados - obrigatorios

        return {
            "valido": len(faltantes) == 0,
            "beneficios_obrigatorios": [b.value for b in obrigatorios],
            "beneficios_informados": [b.value for b in informados],
            "beneficios_faltantes": [b.value for b in faltantes],
            "beneficios_extras": [b.value for b in extras],
            "alerta": f"Beneficios faltantes: {[b.value for b in faltantes]}" if faltantes else None,
        }

    def validar_completo(
        self,
        cargo: TipoCargo,
        salario: Decimal,
        jornada: TipoJornada,
        beneficios: list[TipoBeneficio],
        funcionario_id: UUID | None = None,
    ) -> ValidacaoCCT:
        """Executa validacao completa de compliance CCT."""
        logger.info(f"Validando compliance CCT para cargo {cargo.value}")

        # Validar salario
        resultado_salario = self.validar_salario(cargo, salario)

        # Validar jornada
        resultado_jornada = self.validar_jornada(cargo, jornada)

        # Validar beneficios
        resultado_beneficios = self.validar_beneficios(beneficios)

        # Criar validacao
        validacao = ValidacaoCCT(
            funcionario_id=funcionario_id,
            cargo=cargo,
            salario_conforme=resultado_salario["valido"],
            salario_informado=salario,
            salario_minimo_cct=Decimal(resultado_salario.get("piso_cct", "0")),
            diferenca_salario=Decimal(resultado_salario.get("diferenca", "0")),
            jornada_conforme=resultado_jornada["valido"],
            jornada_informada=jornada,
            beneficios_conformes=resultado_beneficios["valido"],
            beneficios_faltantes=[TipoBeneficio(b) for b in resultado_beneficios.get("beneficios_faltantes", [])],
            detalhes={"salario": resultado_salario, "jornada": resultado_jornada, "beneficios": resultado_beneficios},
        )

        # Adicionar alertas
        if resultado_salario.get("alerta"):
            validacao.alertas.append(resultado_salario["alerta"])
        if resultado_jornada.get("alerta"):
            validacao.alertas.append(resultado_jornada["alerta"])
        if resultado_beneficios.get("alerta"):
            validacao.alertas.append(resultado_beneficios["alerta"])

        # Adicionar recomendacoes
        if not resultado_salario["valido"]:
            validacao.recomendacoes.append(f"Ajustar salario para minimo R$ {resultado_salario['piso_cct']}")
        if resultado_beneficios.get("beneficios_faltantes"):
            validacao.recomendacoes.append(f"Incluir beneficios: {resultado_beneficios['beneficios_faltantes']}")

        # Calcular score
        validacao.calcular_score()

        logger.info(f"Validacao CCT concluida: {validacao.status.value} (score: {validacao.score})")

        return validacao

    def calcular_custo_funcionario(
        self,
        cargo: TipoCargo,
        salario_base: Decimal | None = None,
        jornada: TipoJornada = TipoJornada.JORNADA_44H,
        incluir_encargos: bool = True,
    ) -> dict[str, Any]:
        """Calcula custo total de um funcionario."""
        # Usar piso se salario nao informado
        salario = salario_base or self.tabela_pisos.get(cargo, Decimal("0"))

        # Beneficios
        beneficios_total = Decimal("0")
        beneficios_detalhes = []

        for tipo, beneficio in self.beneficios_obrigatorios.items():
            valor = beneficio.valor_estimado_mensal
            beneficios_total += valor
            beneficios_detalhes.append({"tipo": tipo.value, "valor_mensal": str(valor)})

        # Encargos (estimativa)
        if incluir_encargos:
            # INSS patronal: 20%
            inss = salario * Decimal("0.20")
            # FGTS: 8%
            fgts = salario * Decimal("0.08")
            # RAT: 2%
            rat = salario * Decimal("0.02")
            # Sistema S: 3.3%
            sistema_s = salario * Decimal("0.033")
            # Provisao ferias + 1/3: 11.11%
            ferias = salario * Decimal("0.1111")
            # Provisao 13o: 8.33%
            decimo_terceiro = salario * Decimal("0.0833")

            encargos_total = inss + fgts + rat + sistema_s + ferias + decimo_terceiro
            encargos_percentual = (encargos_total / salario * 100).quantize(Decimal("0.01"))
        else:
            encargos_total = Decimal("0")
            encargos_percentual = Decimal("0")

        custo_total = salario + beneficios_total + encargos_total

        return {
            "cargo": cargo.value,
            "jornada": jornada.value,
            "salario_base": str(salario),
            "beneficios": {"total": str(beneficios_total), "detalhes": beneficios_detalhes},
            "encargos": {
                "total": str(encargos_total.quantize(Decimal("0.01"))),
                "percentual": f"{encargos_percentual}%",
                "incluido": incluir_encargos,
            },
            "custo_total_mensal": str(custo_total.quantize(Decimal("0.01"))),
            "custo_total_anual": str((custo_total * 12).quantize(Decimal("0.01"))),
        }

    def gerar_proposta_comercial(
        self, cargos: list[dict[str, Any]], margem_lucro_percentual: Decimal = Decimal("15")
    ) -> dict[str, Any]:
        """Gera proposta comercial baseada na CCT."""
        itens_proposta = []
        custo_total = Decimal("0")

        for item in cargos:
            cargo = TipoCargo(item["cargo"])
            quantidade = item.get("quantidade", 1)
            jornada = TipoJornada(item.get("jornada", "44h_semanais"))

            custo = self.calcular_custo_funcionario(cargo, jornada=jornada)
            custo_mensal = Decimal(custo["custo_total_mensal"])
            custo_item = custo_mensal * quantidade

            itens_proposta.append(
                {
                    "cargo": cargo.value,
                    "quantidade": quantidade,
                    "jornada": jornada.value,
                    "custo_unitario": str(custo_mensal),
                    "custo_total": str(custo_item),
                }
            )

            custo_total += custo_item

        # Aplicar margem
        valor_margem = custo_total * (margem_lucro_percentual / 100)
        valor_proposta = custo_total + valor_margem

        return {
            "data_proposta": datetime.now().isoformat(),
            "vigencia_cct": f"SINDCOND {self.ano_vigencia}",
            "itens": itens_proposta,
            "subtotal_custos": str(custo_total.quantize(Decimal("0.01"))),
            "margem_percentual": f"{margem_lucro_percentual}%",
            "valor_margem": str(valor_margem.quantize(Decimal("0.01"))),
            "valor_proposta_mensal": str(valor_proposta.quantize(Decimal("0.01"))),
            "valor_proposta_anual": str((valor_proposta * 12).quantize(Decimal("0.01"))),
            "observacoes": [
                "Valores baseados na CCT SINDCOND 2026",
                f"Reajuste anual previsto: {self.reajuste_percentual}%",
                "Beneficios inclusos: VA, Cesta basica, VT, Seguro de vida",
            ],
        }

    def listar_cargos(self) -> list[dict[str, Any]]:
        """Lista todos os cargos com pisos salariais."""
        return [
            {"cargo": cargo.value, "piso_salarial": str(piso), "vigencia": self.ano_vigencia}
            for cargo, piso in self.tabela_pisos.items()
        ]

    def obter_piso_salarial(self, cargo: TipoCargo) -> Decimal | None:
        """Obtem piso salarial de um cargo."""
        return self.tabela_pisos.get(cargo)

    def _get_jornadas_permitidas(self, cargo: TipoCargo) -> list[TipoJornada]:
        """Retorna jornadas permitidas para um cargo."""
        # Cargos que permitem 12x36
        cargos_12x36 = [
            TipoCargo.PORTEIRO,
            TipoCargo.PORTEIRO_LIDER,
            TipoCargo.CONTROLADOR_ACESSO,
            TipoCargo.AGENTE_PORTARIA,
            TipoCargo.AGENTE_PORTARIA_LIDER,
            TipoCargo.FOLGUISTA,
        ]

        if cargo in cargos_12x36:
            return [TipoJornada.JORNADA_44H, TipoJornada.ESCALA_12X36, TipoJornada.ESCALA_6X1]

        # Cargos administrativos
        cargos_administrativos = [
            TipoCargo.AUXILIAR_ADMINISTRATIVO,
            TipoCargo.RECEPCIONISTA,
            TipoCargo.SECRETARIA,
            TipoCargo.GERENTE_PREDIAL,
            TipoCargo.SINDICO_PROFISSIONAL,
        ]

        if cargo in cargos_administrativos:
            return [TipoJornada.JORNADA_44H, TipoJornada.ESCALA_5X2, TipoJornada.MEIO_PERIODO]

        # Padrao para demais cargos
        return [TipoJornada.JORNADA_44H, TipoJornada.ESCALA_6X1]
