"""PricingOptimizerAgent — Calcula precificacao otima para contratos de seguranca.

Skills injetadas (T3 Fase 2):
- framework-precificacao-margem (Skill 04)
- break-even-ponto-equilibrio (Skill 02)
- analise-margem-por-servico (Skill 03)
CCT SINDECOMPRESTS 2026: piso R$1.847,93 + encargos 42% + VR + VT = R$3.354,86/posto
Benchmarks Manaus 2026: portaria diurna R$2.800-3.800 | noturna R$3.200-4.500/posto/mes
"""

from sqlalchemy import and_, func, select

from modules.financial.agents.base_agent import BaseAgent
from modules.financial.agents.skill_loader import SkillLoader
from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus

# Benchmarks de custo por tipo de servico
# Estrutura: tipo -> {custo_por_unidade, unidade, descricao, encargos_pct}
# custo_por_unidade: custo base mensal por posto/m2/unidade (R$)
# encargos_pct: percentual de encargos sociais sobre o custo base
_BENCHMARKS: dict[str, dict] = {
    "portaria": {
        "descricao": "Portaria 24h com 2 agentes de portaria por posto",
        "unidade": "posto",
        "custo_por_unidade": 8500.0,  # R$/posto/mes
        "encargos_pct": 0.72,  # CLT + beneficios (~72%)
        "equipamentos_fixos": 500.0,  # R$/mes (uniforme, EPI, radio)
        "supervisao_pct": 0.08,  # 8% sobre mao de obra
    },
    "limpeza": {
        "descricao": "Servicos de limpeza e conservacao",
        "unidade": "m2",
        "custo_por_unidade": 4.5,  # R$/m2/mes
        "encargos_pct": 0.68,
        "equipamentos_fixos": 800.0,
        "supervisao_pct": 0.07,
    },
    "jardinagem": {
        "descricao": "Manutencao de areas verdes",
        "unidade": "m2",
        "custo_por_unidade": 3.0,  # R$/m2/mes
        "encargos_pct": 0.65,
        "equipamentos_fixos": 400.0,
        "supervisao_pct": 0.06,
    },
    "seguranca_eletronica": {
        "descricao": "Monitoramento eletronico e CFTV",
        "unidade": "camera",
        "custo_por_unidade": 350.0,  # R$/camera/mes (monitoramento)
        "encargos_pct": 0.45,  # Menor — mais tecnologia, menos CLT
        "equipamentos_fixos": 1500.0,
        "supervisao_pct": 0.05,
    },
    "portaria_remota": {
        "descricao": "Portaria remota com monitoramento 24h",
        "unidade": "ponto",
        "custo_por_unidade": 1200.0,  # R$/ponto/mes
        "encargos_pct": 0.40,
        "equipamentos_fixos": 2000.0,
        "supervisao_pct": 0.05,
    },
}

# Fatores de escala de trabalho (multiplicador sobre custo base)
_FATORES_ESCALA = {
    "12x36": 1.0,
    "44h": 1.0,
    "12h_diurno": 0.55,
    "12h_noturno": 0.60,
    "8h": 0.40,
    "24h": 1.10,
    "plantao_12h": 0.55,
}

# Fator de localizacao (multiplicador sobre custo total)
_FATORES_LOCALIZACAO = {
    "sp_capital": 1.30,
    "rj_capital": 1.25,
    "grandes_capitais": 1.20,
    "interior_sp": 1.10,
    "interior_outros": 1.00,
    "nordeste": 0.90,
    "norte": 0.88,
    "default": 1.00,
}

_MARGENS = {
    "minima": 0.10,
    "ideal": 0.25,
    "premium": 0.40,
}


class PricingOptimizerAgent(BaseAgent):
    """Agente de otimizacao de precificacao para contratos de seguranca."""

    name = "pricing_optimizer"

    def _load_skills(self) -> str:
        """Carrega skills de precificação e margem."""
        return SkillLoader.load_multiple(
            [
                "framework-precificacao-margem",
                "break-even-ponto-equilibrio",
                "analise-margem-por-servico",
            ]
        )

    def _get_enriched_system_prompt(self, base_prompt: str = "") -> str:
        """System prompt com framework CCT 2026 Manaus."""
        skills = self._load_skills()
        return (
            "Você é o PricingOptimizerAgent da Conecta Mais.\n\n"
            "CCT SINDECOMPRESTS 2026 (vigência 01/01/2026 a 31/12/2026):\n"
            "- Piso da categoria: R$1.847,93/mês\n"
            "- Encargos (INSS + FGTS + férias + 13º): ~42%\n"
            "- Custo CLT total por posto: ~R$2.624,06/mês\n"
            "- VR: R$26,40/dia útil (22 dias = R$580,80/mês)\n"
            "- VT: ~R$150/mês (média)\n"
            "- Custo all-in por posto: ~R$3.354,86/mês\n\n"
            "BENCHMARKS MANAUS 2026:\n"
            "- Portaria diurna: R$2.800 – R$3.800/posto/mês\n"
            "- Portaria noturna: R$3.200 – R$4.500/posto/mês\n"
            "- Portaria remota: R$1.200 – R$2.500/mês\n"
            "- Manutenção CFTV: R$600 – R$1.200/mês\n\n"
            "MARGEM TARGET: 35% | MARGEM MÍNIMA: 20%\n"
            "ALERTA: Contratos sem cláusula de reajuste = margem negativa em 12m\n\n"
            f"SKILLS:\n{skills}\n\n"
            f"{base_prompt}\n\n"
            "Para cada análise:\n"
            "1. Calcular custo real (CCT 2026 + encargos + benefícios)\n"
            "2. Comparar com ticket atual\n"
            "3. Identificar margem real vs margem aparente\n"
            "4. Recomendar preço mínimo, ideal e premium"
        )

    async def calcular_preco(
        self,
        tipo: str,
        qtd_postos: float,
        escala: str = "12x36",
        localizacao: str = "default",
    ) -> dict:
        """
        Calcula precificacao otima para um contrato.

        Args:
            tipo: Tipo de servico (portaria, limpeza, jardinagem, seguranca_eletronica, portaria_remota)
            qtd_postos: Quantidade de postos/m2/cameras/pontos
            escala: Escala de trabalho (12x36, 44h, 12h_diurno, 12h_noturno, 8h, 24h)
            localizacao: Regiao (sp_capital, rj_capital, grandes_capitais, interior_sp, etc.)

        Returns:
            dict com custo_estimado, preco_minimo, preco_ideal, preco_premium, benchmark_info
        """
        return await self.execute(
            tipo=tipo,
            qtd_postos=qtd_postos,
            escala=escala,
            localizacao=localizacao,
        )

    async def _execute(
        self,
        tipo: str = "portaria",
        qtd_postos: float = 1.0,
        escala: str = "12x36",
        localizacao: str = "default",
        **kwargs,
    ) -> dict:
        # Normaliza tipo
        tipo_norm = tipo.lower().replace(" ", "_").replace("-", "_")
        if tipo_norm not in _BENCHMARKS:
            tipo_norm = "portaria"

        benchmark = _BENCHMARKS[tipo_norm]

        # Fator de escala
        fator_escala = _FATORES_ESCALA.get(escala.lower(), 1.0)

        # Fator de localizacao
        fator_loc = _FATORES_LOCALIZACAO.get(localizacao.lower(), _FATORES_LOCALIZACAO["default"])

        # Custo base de mao de obra
        custo_mao_obra_base = benchmark["custo_por_unidade"] * float(qtd_postos) * fator_escala
        custo_encargos = custo_mao_obra_base * benchmark["encargos_pct"]
        custo_mao_obra_total = custo_mao_obra_base + custo_encargos

        # Custos fixos e supervisao
        custo_equipamentos = benchmark["equipamentos_fixos"] * max(1.0, float(qtd_postos) * 0.5)
        custo_supervisao = custo_mao_obra_total * benchmark["supervisao_pct"]

        # Custo operacional total antes da localizacao
        custo_operacional = custo_mao_obra_total + custo_equipamentos + custo_supervisao

        # Aplicar fator de localizacao
        custo_estimado = custo_operacional * fator_loc

        # Precos por margem
        preco_minimo = custo_estimado / (1 - _MARGENS["minima"])
        preco_ideal = custo_estimado / (1 - _MARGENS["ideal"])
        preco_premium = custo_estimado / (1 - _MARGENS["premium"])

        # Busca contratos existentes do mesmo tipo para comparacao
        comparativo = await self._buscar_contratos_similares(tipo_norm, qtd_postos)

        resultado = {
            "tipo_servico": tipo_norm,
            "descricao": benchmark["descricao"],
            "unidade": benchmark["unidade"],
            "quantidade": float(qtd_postos),
            "escala": escala,
            "localizacao": localizacao,
            "custo_estimado": round(custo_estimado, 2),
            "breakdown_custo": {
                "mao_obra_base": round(custo_mao_obra_base, 2),
                "encargos_sociais": round(custo_encargos, 2),
                "equipamentos_epi": round(custo_equipamentos, 2),
                "supervisao": round(custo_supervisao, 2),
                "fator_localizacao": fator_loc,
                "fator_escala": fator_escala,
            },
            "precificacao": {
                "preco_minimo": round(preco_minimo, 2),
                "margem_minima_pct": round(_MARGENS["minima"] * 100, 1),
                "preco_ideal": round(preco_ideal, 2),
                "margem_ideal_pct": round(_MARGENS["ideal"] * 100, 1),
                "preco_premium": round(preco_premium, 2),
                "margem_premium_pct": round(_MARGENS["premium"] * 100, 1),
            },
            "por_unidade": {
                "custo_por_unidade": round(custo_estimado / float(qtd_postos), 2) if qtd_postos > 0 else 0,
                "preco_minimo_por_unidade": round(preco_minimo / float(qtd_postos), 2) if qtd_postos > 0 else 0,
                "preco_ideal_por_unidade": round(preco_ideal / float(qtd_postos), 2) if qtd_postos > 0 else 0,
            },
            "comparativo_mercado": comparativo,
            "recomendacao": self._gerar_recomendacao(custo_estimado, preco_ideal, comparativo),
        }

        return resultado

    async def _buscar_contratos_similares(self, tipo: str, qtd_postos: float) -> dict:
        """Busca contratos existentes para comparacao de preco."""
        try:
            # Busca recebiveis com descricao similar ao tipo de servico
            palavras_chave = {
                "portaria": ["portaria", "controlador de acesso", "seguranca"],
                "limpeza": ["limpeza", "conservacao", "higiene"],
                "jardinagem": ["jardim", "jardinagem", "areas verdes"],
                "seguranca_eletronica": ["cftv", "monitoramento", "camera"],
                "portaria_remota": ["portaria remota", "monitoramento remoto"],
            }
            palavras = palavras_chave.get(tipo, [tipo])

            # Conta contratos com receita recorrente compativel
            q = select(
                func.count(ReceivableAccount.id).label("qtd"),
                func.avg(ReceivableAccount.net_value).label("media"),
                func.min(ReceivableAccount.net_value).label("minimo"),
                func.max(ReceivableAccount.net_value).label("maximo"),
            ).where(
                and_(
                    ReceivableAccount.status != ReceivableStatus.CANCELADA.value,
                    ReceivableAccount.description.ilike(f"%{palavras[0]}%"),
                )
            )
            result = (await self.session.execute(q)).first()

            if result and result.qtd and result.qtd > 0:
                return {
                    "contratos_encontrados": int(result.qtd),
                    "valor_medio_mercado": round(float(result.media or 0), 2),
                    "valor_minimo_mercado": round(float(result.minimo or 0), 2),
                    "valor_maximo_mercado": round(float(result.maximo or 0), 2),
                }
        except Exception as exc:
            self.logger.debug(f"Erro ao buscar contratos similares: {exc}")

        return {
            "contratos_encontrados": 0,
            "valor_medio_mercado": 0.0,
            "valor_minimo_mercado": 0.0,
            "valor_maximo_mercado": 0.0,
        }

    def _gerar_recomendacao(self, custo: float, preco_ideal: float, comparativo: dict) -> str:
        """Gera texto de recomendacao baseado nos dados."""
        media_mercado = comparativo.get("valor_medio_mercado", 0)
        if media_mercado > 0:
            if preco_ideal > media_mercado * 1.10:
                return (
                    f"Seu preco ideal (R$ {preco_ideal:,.2f}) esta acima da media de mercado "
                    f"(R$ {media_mercado:,.2f}). Considere preco competitivo proximo a R$ {media_mercado * 1.05:,.2f}."
                )
            elif preco_ideal < media_mercado * 0.90:
                return (
                    "Seu custo estimado permite preco abaixo do mercado. "
                    "Use isso como vantagem competitiva ou aumente a margem."
                )
        return (
            f"Recomendamos preco entre R$ {custo * 1.15:,.2f} (margem minima) e "
            f"R$ {preco_ideal:,.2f} (margem ideal de 25%). "
            "Ajuste conforme a competitividade do cliente e volume do contrato."
        )

    async def _fallback(self, **kwargs) -> dict:
        """Retorna estrutura basica em caso de falha."""
        return {
            "tipo_servico": kwargs.get("tipo", "portaria"),
            "custo_estimado": 0.0,
            "precificacao": {
                "preco_minimo": 0.0,
                "margem_minima_pct": 10.0,
                "preco_ideal": 0.0,
                "margem_ideal_pct": 25.0,
                "preco_premium": 0.0,
                "margem_premium_pct": 40.0,
            },
            "comparativo_mercado": {"contratos_encontrados": 0},
            "recomendacao": "Nao foi possivel calcular. Verifique os parametros.",
            "erro": True,
        }
