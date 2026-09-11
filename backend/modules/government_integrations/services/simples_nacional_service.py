"""
Service para Simples Nacional.

Camada de serviço para operações do Simples Nacional.
"""

import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Any

from ..core.simples_nacional import (
    DAS,
    PGDASD,
    AnexoSimples,
    ReceitaCompetencia,
    SimplesNacionalManager,
    TipoReceita,
)

logger = logging.getLogger(__name__)


class SimplesNacionalService:
    """Service para operações do Simples Nacional."""

    def __init__(self):
        """Inicializa o service."""
        self.cnpj = os.getenv("SIMPLES_CNPJ", os.getenv("EMPRESA_CNPJ", "35710481000103"))
        self.razao_social = os.getenv("EMPRESA_RAZAO_SOCIAL", "Conecta Seguranca LTDA")
        anexo_str = os.getenv("SIMPLES_ANEXO", "III")

        self.anexo_principal = {
            "I": AnexoSimples.ANEXO_I,
            "II": AnexoSimples.ANEXO_II,
            "III": AnexoSimples.ANEXO_III,
            "IV": AnexoSimples.ANEXO_IV,
            "V": AnexoSimples.ANEXO_V,
        }.get(anexo_str, AnexoSimples.ANEXO_III)

        self.manager = SimplesNacionalManager(
            cnpj=self.cnpj,
            razao_social=self.razao_social,
            anexo_principal=self.anexo_principal,
        )

        logger.info(f"Simples Nacional Service inicializado - CNPJ: {self.cnpj}, Anexo: {self.anexo_principal.value}")

    def consultar_opcao(self) -> dict[str, Any]:
        """
        Consulta situação da opção pelo Simples Nacional.

        Returns:
            Dict com situação da opção
        """
        return self.manager.consultar_opcao()

    def simular_calculo(
        self,
        receita_mensal: str,
        rbt12: str,
        folha_12_meses: str | None = None,
    ) -> dict[str, Any]:
        """
        Simula cálculo do Simples Nacional.

        Args:
            receita_mensal: Receita do mês
            rbt12: Receita Bruta 12 meses
            folha_12_meses: Folha de salários 12 meses (para Fator R)

        Returns:
            Dict com simulação detalhada
        """
        return self.manager.simular_calculo(
            receita_mensal=Decimal(receita_mensal),
            rbt12=Decimal(rbt12),
            folha_12_meses=Decimal(folha_12_meses) if folha_12_meses else None,
        )

    def calcular_pgdasd(
        self,
        competencia: str,
        receitas: list[dict[str, Any]],
        rbt12: str,
        folha_12_meses: str | None = None,
    ) -> dict[str, Any]:
        """
        Calcula o PGDAS-D (declaração mensal).

        Args:
            competencia: Competência YYYY-MM
            receitas: Lista de receitas do mês
            rbt12: Receita Bruta 12 meses
            folha_12_meses: Folha de salários 12 meses

        Returns:
            Dict com PGDAS-D calculado
        """
        lista_receitas = []
        for rec in receitas:
            tipo = TipoReceita(rec.get("tipo_receita", "servicos"))
            anexo = AnexoSimples(rec.get("anexo", self.anexo_principal.value))

            lista_receitas.append(
                ReceitaCompetencia(
                    competencia=competencia,
                    tipo_receita=tipo,
                    anexo=anexo,
                    valor_bruto=Decimal(str(rec["valor_bruto"])),
                    deducoes=Decimal(str(rec.get("deducoes", "0"))),
                )
            )

        pgdasd = self.manager.calcular_pgdasd(
            competencia=competencia,
            receitas=lista_receitas,
            rbt12=Decimal(rbt12),
            folha_12_meses=Decimal(folha_12_meses) if folha_12_meses else None,
        )

        logger.info(f"PGDAS-D calculado: {competencia}, Receita: {pgdasd.receita_mes}, Devido: {pgdasd.valor_devido}")

        return self._pgdasd_to_dict(pgdasd)

    def gerar_das(
        self,
        competencia: str,
        receitas: list[dict[str, Any]],
        rbt12: str,
        folha_12_meses: str | None = None,
        data_vencimento: str | None = None,
    ) -> dict[str, Any]:
        """
        Gera DAS para uma competência.

        Args:
            competencia: Competência YYYY-MM
            receitas: Lista de receitas
            rbt12: Receita Bruta 12 meses
            folha_12_meses: Folha de salários 12 meses
            data_vencimento: Data de vencimento (YYYY-MM-DD)

        Returns:
            Dict com DAS gerado
        """
        lista_receitas = []
        for rec in receitas:
            tipo = TipoReceita(rec.get("tipo_receita", "servicos"))
            anexo = AnexoSimples(rec.get("anexo", self.anexo_principal.value))

            lista_receitas.append(
                ReceitaCompetencia(
                    competencia=competencia,
                    tipo_receita=tipo,
                    anexo=anexo,
                    valor_bruto=Decimal(str(rec["valor_bruto"])),
                    deducoes=Decimal(str(rec.get("deducoes", "0"))),
                )
            )

        pgdasd = self.manager.calcular_pgdasd(
            competencia=competencia,
            receitas=lista_receitas,
            rbt12=Decimal(rbt12),
            folha_12_meses=Decimal(folha_12_meses) if folha_12_meses else None,
        )

        dt_venc = None
        if data_vencimento:
            dt_venc = datetime.strptime(data_vencimento, "%Y-%m-%d").date()

        das = self.manager.gerar_das(pgdasd, dt_venc)

        logger.info(f"DAS gerado: {das.numero_documento}, Valor: {das.valor_total}")

        return {
            "pgdasd": self._pgdasd_to_dict(pgdasd),
            "das": self._das_to_dict(das),
        }

    def calcular_fator_r(
        self,
        folha_12_meses: str,
        rbt12: str,
    ) -> dict[str, Any]:
        """
        Calcula o Fator R e determina o anexo aplicável.

        Args:
            folha_12_meses: Folha de salários 12 meses
            rbt12: Receita Bruta 12 meses

        Returns:
            Dict com Fator R e anexo
        """
        fator_r, anexo = self.manager.calcular_fator_r(
            folha_12_meses=Decimal(folha_12_meses),
            rbt12=Decimal(rbt12),
        )

        return {
            "folha_12_meses": folha_12_meses,
            "rbt12": rbt12,
            "fator_r": str(fator_r),
            "fator_r_percentual": str(fator_r * 100),
            "anexo_aplicavel": anexo.value,
            "observacao": (
                "Fator R >= 28%: Anexo III (alíquotas menores)"
                if anexo == AnexoSimples.ANEXO_III
                else "Fator R < 28%: Anexo V (alíquotas maiores)"
            ),
        }

    def obter_tabela_aliquotas(self, anexo: str = "III") -> dict[str, Any]:
        """
        Retorna a tabela de alíquotas de um anexo.

        Args:
            anexo: Anexo (I, II, III, IV, V)

        Returns:
            Dict com tabela de alíquotas
        """
        anexo_enum = AnexoSimples(anexo)

        tabela = {
            AnexoSimples.ANEXO_III: self.manager.ANEXO_III,
            AnexoSimples.ANEXO_IV: self.manager.ANEXO_IV,
            AnexoSimples.ANEXO_V: self.manager.ANEXO_V,
        }.get(anexo_enum, self.manager.ANEXO_III)

        return {
            "anexo": anexo,
            "descricao": self._get_anexo_descricao(anexo_enum),
            "faixas": [
                {
                    "faixa": f.faixa,
                    "receita_inicio": str(f.receita_bruta_inicio),
                    "receita_fim": str(f.receita_bruta_fim),
                    "aliquota_nominal": str(f.aliquota_nominal * 100) + "%",
                    "valor_deduzir": str(f.valor_deduzir),
                }
                for f in tabela
            ],
        }

    def consultar_pendencias(self) -> dict[str, Any]:
        """
        Consulta pendências no Simples Nacional.

        Returns:
            Dict com pendências
        """
        return self.manager.consultar_pendencias()

    def listar_anexos(self) -> dict[str, Any]:
        """
        Lista os anexos disponíveis.

        Returns:
            Dict com anexos
        """
        anexos = [
            {"codigo": "I", "descricao": "Comércio"},
            {"codigo": "II", "descricao": "Indústria"},
            {"codigo": "III", "descricao": "Serviços (Fator R >= 28%)"},
            {"codigo": "IV", "descricao": "Serviços (construção, vigilância com cessão)"},
            {"codigo": "V", "descricao": "Serviços (Fator R < 28%)"},
        ]

        return {
            "anexos": anexos,
            "anexo_atual": self.anexo_principal.value,
        }

    def listar_tipos_receita(self) -> dict[str, Any]:
        """
        Lista os tipos de receita.

        Returns:
            Dict com tipos de receita
        """
        return {
            "tipos": [
                {"codigo": "revenda", "descricao": "Revenda de mercadorias"},
                {"codigo": "producao", "descricao": "Venda de produção própria"},
                {"codigo": "servicos", "descricao": "Prestação de serviços"},
                {"codigo": "locacao", "descricao": "Locação de bens"},
            ]
        }

    def validar_status(self) -> dict[str, Any]:
        """
        Valida status da configuração.

        Returns:
            Dict com status
        """
        return {
            "cnpj": self.cnpj,
            "razao_social": self.razao_social,
            "anexo_principal": self.anexo_principal.value,
            "anexo_descricao": self._get_anexo_descricao(self.anexo_principal),
            "portal_simples": self.manager.URL_PORTAL,
            # número ao lado do formatado: o teto do Simples é usado em CONTA (quanto
            # falta para estourar), e string obriga quem consome a fazer parsing de
            # milhar e vírgula — onde se erra por um fator de mil sem perceber.
            "limite_receita_anual": 4800000.0,
            "limite_receita_anual_formatado": "R$ 4.800.000,00",
            "operacoes_disponiveis": [
                "Consultar opção",
                "Simular cálculo",
                "Calcular PGDAS-D",
                "Gerar DAS",
                "Calcular Fator R",
                "Consultar pendências",
            ],
        }

    def _get_anexo_descricao(self, anexo: AnexoSimples) -> str:
        """Retorna descrição do anexo."""
        descricoes = {
            AnexoSimples.ANEXO_I: "Comércio",
            AnexoSimples.ANEXO_II: "Indústria",
            AnexoSimples.ANEXO_III: "Serviços (vigilância, limpeza - Fator R >= 28%)",
            AnexoSimples.ANEXO_IV: "Serviços (construção, vigilância com cessão)",
            AnexoSimples.ANEXO_V: "Serviços (TI, engenharia - Fator R < 28%)",
        }
        return descricoes.get(anexo, anexo.name)

    def _pgdasd_to_dict(self, pgdasd: PGDASD) -> dict[str, Any]:
        """Converte PGDAS-D para dict."""
        return {
            "competencia": pgdasd.competencia,
            "cnpj": pgdasd.cnpj,
            "razao_social": pgdasd.razao_social,
            "data_apuracao": pgdasd.data_apuracao.isoformat(),
            "rbt12": str(pgdasd.rbt12),
            "receita_mes": str(pgdasd.receita_mes),
            "aliquota_efetiva": str(pgdasd.aliquota_efetiva),
            "aliquota_percentual": str(pgdasd.aliquota_efetiva * 100) + "%",
            "valor_devido": str(pgdasd.valor_devido),
            "receitas": [
                {
                    "tipo": r.tipo_receita.value,
                    "anexo": r.anexo.value,
                    "valor_bruto": str(r.valor_bruto),
                    "deducoes": str(r.deducoes),
                    "valor_liquido": str(r.valor_liquido),
                }
                for r in pgdasd.receitas
            ],
            "transmitida": pgdasd.transmitida,
            "numero_recibo": pgdasd.numero_recibo,
        }

    def _das_to_dict(self, das: DAS) -> dict[str, Any]:
        """Converte DAS para dict."""
        return {
            "numero_documento": das.numero_documento,
            "competencia": das.competencia,
            "data_vencimento": das.data_vencimento.isoformat(),
            "valor_principal": str(das.valor_principal),
            "valor_multa": str(das.valor_multa),
            "valor_juros": str(das.valor_juros),
            "valor_total": str(das.valor_total),
            "codigo_barras": das.codigo_barras,
            "linha_digitavel": das.linha_digitavel,
            "composicao": {
                "irpj": str(das.irpj),
                "csll": str(das.csll),
                "cofins": str(das.cofins),
                "pis": str(das.pis),
                "cpp": str(das.cpp),
                "icms": str(das.icms),
                "iss": str(das.iss),
            },
            "situacao": das.situacao,
        }


# Singleton
_simples_nacional_service: SimplesNacionalService | None = None


def get_simples_nacional_service() -> SimplesNacionalService:
    """Retorna instância singleton do service."""
    global _simples_nacional_service
    if _simples_nacional_service is None:
        _simples_nacional_service = SimplesNacionalService()
    return _simples_nacional_service
