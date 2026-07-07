"""FinancialAdvisorAgent — Consultor financeiro estrategico com dados reais."""

from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select

from modules.financial.agents.base_agent import BaseAgent
from modules.financial.agents.skill_loader import SkillLoader
from modules.financial.models.payable_account import PayableAccount, PayableStatus
from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus

# Respostas para perguntas frequentes (keyword -> resposta base)
_FAQ: dict[str, str] = {
    "inadimplencia": (
        "A inadimplencia e calculada dividindo o total de recebimentos em atraso pelo total "
        "de receitas previstas. Taxas abaixo de 3% sao consideradas saudaveis para empresas "
        "de seguranca patrimonial. Acima de 5%, e necessario acionar ativamente a regua de cobranca."
    ),
    "margem": (
        "A margem operacional ideal para empresas de seguranca fica entre 15% e 25%. "
        "Margens abaixo de 10% indicam necessidade de revisao de precificacao ou corte de custos. "
        "A maior parte dos custos e com folha de pagamento (70-80% da receita)."
    ),
    "fluxo": (
        "O fluxo de caixa saudavel requer que as entradas superem as saidas em pelo menos 15%. "
        "Monitore vencimentos dos proximos 7 e 30 dias diariamente. "
        "Antecipe recebimentos via boleto ou PIX antes de datas criticas de pagamento."
    ),
    "contrato": (
        "Contratos de seguranca devem ser precificados com margem minima de 10% sobre custos diretos. "
        "Considere reajuste anual pelo INPC/IGP-M + 2-5% para cobrir variacao salarial. "
        "Contratos abaixo de 3 postos raramente sao lucrativos sem economia de escala."
    ),
    "custo": (
        "Os principais custos de uma empresa de seguranca sao: folha (65-75%), "
        "encargos sociais (25-35% sobre folha), uniformes/EPIs (2-4%), "
        "supervisao e overhead (8-12%), e impostos sobre faturamento (Simples/Lucro Presumido)."
    ),
    "provisao": (
        "Provisione mensalmente: 13o salario (8,33%), ferias (11,11%), FGTS (8%). "
        "Total de provisoes trabalhistas: ~27,44% sobre a folha. "
        "Mantenha reserva minima de 2 meses de despesas fixas no caixa."
    ),
}


class FinancialAdvisorAgent(BaseAgent):
    """Agente consultor financeiro estrategico."""

    name = "financial_advisor"

    def _load_skills(self) -> str:
        """Carrega skills DRE + KPIs + Cashflow para este agente."""
        return SkillLoader.load_multiple(
            [
                "dre-gerencial",
                "kpis-financeiros",
                "analise-fluxo-caixa-real",
                "diagnostico-financeiro-completo",
            ]
        )

    def _get_enriched_system_prompt(self, base_prompt: str = "") -> str:
        """System prompt enriquecido com skills reais da Conecta Mais."""
        skills = self._load_skills()
        return f"""Você é o FinancialAdvisorAgent da Conecta Mais.
CNPJ: 35.710.481/0001-03 | Manaus/AM | Lucro Real desde jan/2026

DADOS REAIS (atualizado diariamente):
- MRR bruto: R$270.586,96 (13 NFS-e março/2026)
- MRR líquido: R$243.241,98 (entra no banco Inter)
- Saldo Inter: R$88.684,29 (Banco Inter — único banco ativo)
- Score saúde: 25/100 (CRÍTICO)
- Compliance Lucro Real: 100%
- 10 clientes condomínios em Manaus/AM

SKILLS ESPECIALIZADAS:
{skills}

{base_prompt}

REGRAS:
- Sempre use dados reais do banco via SQL
- Nunca invente números
- Retorne JSON estruturado conforme schemas das skills
- Priorize ações que melhorem o score de saúde (atual: 25/100)"""

    async def responder_pergunta(self, pergunta: str) -> dict:
        """
        Responde perguntas financeiras com dados reais do banco.

        Args:
            pergunta: Pergunta em linguagem natural

        Returns:
            dict com resposta, dados_relevantes e recomendacoes
        """
        try:
            pergunta_lower = pergunta.lower()

            # Identifica o topico da pergunta
            topico = "geral"
            for keyword in _FAQ:
                if keyword in pergunta_lower:
                    topico = keyword
                    break

            # Busca dados reais para contextualizar a resposta
            health = await self.gerar_health_check()
            recomendacoes = await self.gerar_recomendacoes()

            # Monta resposta contextualizada
            resposta_base = _FAQ.get(topico, "")
            if not resposta_base:
                resposta_base = self._resposta_generica(pergunta, health)

            resposta_contextualizada = self._contextualizar_resposta(resposta_base, topico, health)

            return {
                "pergunta": pergunta,
                "topico": topico,
                "resposta": resposta_contextualizada,
                "dados_contexto": {
                    "inadimplencia_atual": health.get("taxa_inadimplencia", 0),
                    "margem_atual": health.get("margem_30d", 0),
                    "score_saude": health.get("score", 0),
                    "tendencia": health.get("tendencia_receita", "estavel"),
                },
                "recomendacoes_relacionadas": [r for r in recomendacoes if r.get("categoria") == topico][:3],
                "fonte": "dados_reais_sistema",
            }

        except Exception as exc:
            self.logger.warning(f"[{self.name}] Erro ao responder pergunta: {exc}")
            return {
                "pergunta": pergunta,
                "topico": "geral",
                "resposta": self._resposta_fallback_pergunta(pergunta),
                "dados_contexto": {},
                "recomendacoes_relacionadas": [],
                "fonte": "fallback",
            }

    async def gerar_health_check(self) -> dict:
        """
        Gera relatorio completo de saude financeira com dados reais.

        Returns:
            dict com score, indicadores e analise narrativa
        """
        today = date.today()
        past_30 = today - timedelta(days=30)
        past_60 = today - timedelta(days=60)
        past_90 = today - timedelta(days=90)

        try:
            # --- Receitas --- FONTE REAL: recebimentos de cliente no extrato Inter (categorizados),
            # pois receivable_accounts PAGA nos últimos 30d fica vazio (recebíveis de competências
            # passadas). bank_transactions 'Recebimento cliente' = dinheiro real que entrou.
            from sqlalchemy import text as _text
            recv_30 = float((await self.session.execute(_text(
                "SELECT COALESCE(SUM(amount),0) FROM bank_transactions "
                "WHERE category='Recebimento cliente' AND transaction_date >= :p AND transaction_date <= :t"
            ), {"p": past_30, "t": today})).scalar() or 0)
            recv_prev = float((await self.session.execute(_text(
                "SELECT COALESCE(SUM(amount),0) FROM bank_transactions "
                "WHERE category='Recebimento cliente' AND transaction_date >= :p60 AND transaction_date < :p30"
            ), {"p60": past_60, "p30": past_30})).scalar() or 0)

            # --- Despesas ---
            pay_30_q = select(func.coalesce(func.sum(PayableAccount.net_value), 0)).where(
                and_(
                    PayableAccount.payment_date >= past_30,
                    PayableAccount.payment_date <= today,
                    PayableAccount.status == PayableStatus.PAGA.value,
                )
            )
            pay_30 = float((await self.session.execute(pay_30_q)).scalar_one() or 0)

            # --- Inadimplencia ---
            total_vencimento_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
                and_(
                    ReceivableAccount.due_date >= past_90,
                    ReceivableAccount.due_date <= today,
                    ReceivableAccount.status != ReceivableStatus.CANCELADA.value,
                )
            )
            total_vencido = float((await self.session.execute(total_vencimento_q)).scalar_one() or 0)

            # Numerador (em atraso) usa a MESMA janela do denominador (past_90..today)
            # para que a taxa nunca ultrapasse 100%. Sem o piso past_90, titulos
            # vencidos ha muito tempo entravam no numerador mas nao no denominador,
            # produzindo taxas impossiveis (>100%).
            em_atraso_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
                and_(
                    ReceivableAccount.due_date >= past_90,
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                            ReceivableStatus.BAIXADA.value,
                        ]
                    ),
                )
            )
            em_atraso = float((await self.session.execute(em_atraso_q)).scalar_one() or 0)

            # Contagem de inadimplentes (mesma janela past_90..today)
            cnt_inadimplentes_q = select(func.count(ReceivableAccount.id)).where(
                and_(
                    ReceivableAccount.due_date >= past_90,
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                            ReceivableStatus.BAIXADA.value,
                        ]
                    ),
                )
            )
            cnt_inadimplentes = int((await self.session.execute(cnt_inadimplentes_q)).scalar_one() or 0)

            # --- Proximos vencimentos (7 dias) ---
            proximos_7d_q = select(func.coalesce(func.sum(PayableAccount.net_value), 0)).where(
                and_(
                    PayableAccount.due_date >= today,
                    PayableAccount.due_date <= today + timedelta(days=7),
                    PayableAccount.status.notin_(
                        [
                            PayableStatus.PAGA.value,
                            PayableStatus.CANCELADA.value,
                        ]
                    ),
                )
            )
            vencimentos_7d = float((await self.session.execute(proximos_7d_q)).scalar_one() or 0)

            # --- Calculos derivados ---
            margem_30d = ((recv_30 - pay_30) / recv_30 * 100) if recv_30 > 0 else 0.0
            # Cap defensivo em 100%: em_atraso (vencidos e nao pagos) e sempre um
            # subconjunto de total_vencido (todos os vencidos, pagos ou nao) na
            # mesma janela, entao a taxa nunca deveria exceder 100%.
            taxa_inadimplencia = (
                min(em_atraso / total_vencido * 100, 100.0) if total_vencido > 0 else 0.0
            )

            if recv_30 > recv_prev * 1.02:
                tendencia = "crescimento"
                tendencia_pct = round((recv_30 - recv_prev) / recv_prev * 100, 1) if recv_prev > 0 else 0
            elif recv_30 < recv_prev * 0.98:
                tendencia = "queda"
                tendencia_pct = round((recv_30 - recv_prev) / recv_prev * 100, 1) if recv_prev > 0 else 0
            else:
                tendencia = "estavel"
                tendencia_pct = 0.0

            # --- Score de saude (0-100) ---
            score = self._calcular_score(taxa_inadimplencia, margem_30d, tendencia, vencimentos_7d, recv_30)

            if score >= 80:
                classificacao = "excelente"
                cor = "verde"
            elif score >= 60:
                classificacao = "bom"
                cor = "azul"
            elif score >= 40:
                classificacao = "atencao"
                cor = "amarelo"
            else:
                classificacao = "critico"
                cor = "vermelho"

            narrativa = self._gerar_narrativa(
                score, taxa_inadimplencia, margem_30d, tendencia, tendencia_pct, recv_30, pay_30
            )

            return {
                "score": score,
                "classificacao": classificacao,
                "cor": cor,
                "narrativa": narrativa,
                "indicadores": {
                    "receita_30d": round(recv_30, 2),
                    "receita_periodo_anterior": round(recv_prev, 2),
                    "despesas_30d": round(pay_30, 2),
                    "margem_30d": round(margem_30d, 2),
                    "taxa_inadimplencia": round(taxa_inadimplencia, 2),
                    "total_em_atraso": round(em_atraso, 2),
                    "qtd_inadimplentes": cnt_inadimplentes,
                    "vencimentos_proximos_7d": round(vencimentos_7d, 2),
                    "tendencia_receita": tendencia,
                    "tendencia_pct": tendencia_pct,
                },
                "alertas_criticos": self._gerar_alertas_criticos(
                    taxa_inadimplencia, margem_30d, vencimentos_7d, recv_30
                ),
            }

        except Exception as exc:
            self.logger.warning(f"[{self.name}] Erro no health_check: {exc}")
            return self._health_check_fallback()

    async def gerar_recomendacoes(self) -> list[dict]:
        """
        Gera lista priorizada de recomendacoes financeiras com base nos dados reais.

        Returns:
            Lista de recomendacoes ordenadas por prioridade
        """
        try:
            health = await self.gerar_health_check()
            indicadores = health.get("indicadores", {})

            recomendacoes: list[dict] = []

            taxa_inad = indicadores.get("taxa_inadimplencia", 0)
            margem = indicadores.get("margem_30d", 0)
            tendencia = indicadores.get("tendencia_receita", "estavel")
            em_atraso = indicadores.get("total_em_atraso", 0)
            vencimentos_7d = indicadores.get("vencimentos_proximos_7d", 0)
            recv_30 = indicadores.get("receita_30d", 0)
            pay_30 = indicadores.get("despesas_30d", 0)

            # Recomendacao 1: Inadimplencia alta
            if taxa_inad > 5:
                recomendacoes.append(
                    {
                        "prioridade": 1,
                        "categoria": "inadimplencia",
                        "titulo": "Acionar regua de cobranca imediatamente",
                        "descricao": (
                            f"Taxa de inadimplencia em {taxa_inad:.1f}% (acima do limite critico de 5%). "
                            f"Total de R$ {em_atraso:,.2f} em atraso. "
                            "Ative a regua de cobranca automatica e priorize os maiores devedores."
                        ),
                        "impacto_estimado": round(em_atraso * 0.40, 2),
                        "prazo_sugerido": "Esta semana",
                        "acao": "Acessar modulo Cobranças > Inadimplentes",
                    }
                )
            elif taxa_inad > 2:
                recomendacoes.append(
                    {
                        "prioridade": 2,
                        "categoria": "inadimplencia",
                        "titulo": "Monitorar inadimplencia crescente",
                        "descricao": (
                            f"Taxa de {taxa_inad:.1f}% esta acima do ideal (<2%). "
                            "Envie lembretes preventivos antes do vencimento."
                        ),
                        "impacto_estimado": round(em_atraso * 0.20, 2),
                        "prazo_sugerido": "Proximos 15 dias",
                        "acao": "Configurar lembretes automaticos no modulo Cobranças",
                    }
                )

            # Recomendacao 2: Margem baixa
            if margem < 5:
                recomendacoes.append(
                    {
                        "prioridade": 1,
                        "categoria": "margem",
                        "titulo": "Revisar precificacao — margem critica",
                        "descricao": (
                            f"Margem operacional de {margem:.1f}% esta criticamente baixa. "
                            "Revise contratos com menor margem e renegocie fornecedores."
                        ),
                        "impacto_estimado": round(recv_30 * 0.10, 2),
                        "prazo_sugerido": "Este mes",
                        "acao": "Usar o Otimizador de Precos para recalcular contratos",
                    }
                )
            elif margem < 10:
                recomendacoes.append(
                    {
                        "prioridade": 2,
                        "categoria": "margem",
                        "titulo": "Aumentar margem operacional",
                        "descricao": (
                            f"Margem de {margem:.1f}% esta abaixo do recomendado (15-25%). "
                            "Identifique contratos deficitarios e aplique reajuste."
                        ),
                        "impacto_estimado": round(recv_30 * 0.05, 2),
                        "prazo_sugerido": "Proximos 30 dias",
                        "acao": "Revisar precificacao dos contratos mais antigos",
                    }
                )

            # Recomendacao 3: Tendencia de queda
            if tendencia == "queda":
                recomendacoes.append(
                    {
                        "prioridade": 2,
                        "categoria": "receita",
                        "titulo": "Tendencia de queda na receita",
                        "descricao": (
                            f"Receita caiu {abs(indicadores.get('tendencia_pct', 0)):.1f}% "
                            "em relacao ao periodo anterior. "
                            "Verifique cancelamentos de contratos e oportunidades de expansao."
                        ),
                        "impacto_estimado": 0.0,
                        "prazo_sugerido": "Imediato",
                        "acao": "Analisar historico de contratos e prospectar novos clientes",
                    }
                )

            # Recomendacao 4: Vencimentos proximos
            if vencimentos_7d > recv_30 * 0.5 and recv_30 > 0:
                recomendacoes.append(
                    {
                        "prioridade": 1,
                        "categoria": "fluxo",
                        "titulo": "Concentracao de pagamentos nos proximos 7 dias",
                        "descricao": (
                            f"R$ {vencimentos_7d:,.2f} em pagamentos vencem nos proximos 7 dias, "
                            f"representando {vencimentos_7d / recv_30 * 100:.0f}% da receita mensal. "
                            "Garanta liquidez suficiente no caixa."
                        ),
                        "impacto_estimado": vencimentos_7d,
                        "prazo_sugerido": "Esta semana",
                        "acao": "Verificar saldo bancario e antecipar recebimentos se necessario",
                    }
                )

            # Recomendacao 5: Boas praticas (sempre presente)
            recomendacoes.append(
                {
                    "prioridade": 5,
                    "categoria": "provisao",
                    "titulo": "Manter provisoes trabalhistas em dia",
                    "descricao": (
                        "Provisione mensalmente 27,44% da folha bruta para 13o, ferias e FGTS. "
                        "Mantenha reserva minima de 2 meses de despesas fixas."
                    ),
                    "impacto_estimado": round(pay_30 * 0.27, 2),
                    "prazo_sugerido": "Todo mes",
                    "acao": "Criar conta de despesa mensal para provisoes trabalhistas",
                }
            )

            # Ordena por prioridade
            recomendacoes.sort(key=lambda x: x["prioridade"])
            return recomendacoes

        except Exception as exc:
            self.logger.warning(f"[{self.name}] Erro em gerar_recomendacoes: {exc}")
            return [
                {
                    "prioridade": 1,
                    "categoria": "geral",
                    "titulo": "Verifique os dados financeiros",
                    "descricao": "Nao foi possivel gerar recomendacoes. Verifique se ha dados no sistema.",
                    "impacto_estimado": 0.0,
                    "prazo_sugerido": "Imediato",
                    "acao": "Cadastrar receitas e despesas no modulo financeiro",
                }
            ]

    async def gerar_relatorio_executivo(self, periodo: str | None = None) -> dict:
        """
        Gera relatório executivo financeiro completo para o período informado.

        Args:
            periodo: String 'YYYY-MM' (padrão: mês atual)

        Returns:
            dict com sumário executivo, KPIs, destaques, pontos de atenção,
            comparativo com período anterior, projeções e recomendações.
        """
        import calendar
        from calendar import monthrange

        today = date.today()

        # Parse período
        if periodo:
            try:
                parts = periodo.split("-")
                ano, mes = int(parts[0]), int(parts[1])
            except Exception:
                ano, mes = today.year, today.month
        else:
            ano, mes = today.year, today.month

        # Datas do período atual
        _, ultimo_dia = monthrange(ano, mes)
        inicio_atual = date(ano, mes, 1)
        fim_atual = date(ano, mes, ultimo_dia)

        # Datas do período anterior
        if mes == 1:
            mes_ant, ano_ant = 12, ano - 1
        else:
            mes_ant, ano_ant = mes - 1, ano
        _, ultimo_dia_ant = monthrange(ano_ant, mes_ant)
        inicio_ant = date(ano_ant, mes_ant, 1)
        fim_ant = date(ano_ant, mes_ant, ultimo_dia_ant)

        nome_mes = calendar.month_name[mes]
        nome_mes_pt = {
            "January": "Janeiro",
            "February": "Fevereiro",
            "March": "Março",
            "April": "Abril",
            "May": "Maio",
            "June": "Junho",
            "July": "Julho",
            "August": "Agosto",
            "September": "Setembro",
            "October": "Outubro",
            "November": "Novembro",
            "December": "Dezembro",
        }.get(nome_mes, nome_mes)

        try:
            from sqlalchemy import and_, func, select

            from modules.financial.models.payable_account import PayableAccount, PayableStatus
            from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus

            # === KPIs DO PERÍODO ATUAL ===
            # Receita recebida
            recv_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
                and_(
                    ReceivableAccount.payment_date >= inicio_atual,
                    ReceivableAccount.payment_date <= fim_atual,
                    ReceivableAccount.status == ReceivableStatus.PAGA.value,
                )
            )
            receita_atual = float((await self.session.execute(recv_q)).scalar_one() or 0)

            # Receita prevista (emitida)
            recv_prev_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
                and_(
                    ReceivableAccount.due_date >= inicio_atual,
                    ReceivableAccount.due_date <= fim_atual,
                    ReceivableAccount.status != ReceivableStatus.CANCELADA.value,
                )
            )
            receita_prevista = float((await self.session.execute(recv_prev_q)).scalar_one() or 0)

            # Despesas pagas
            pay_q = select(func.coalesce(func.sum(PayableAccount.net_value), 0)).where(
                and_(
                    PayableAccount.payment_date >= inicio_atual,
                    PayableAccount.payment_date <= fim_atual,
                    PayableAccount.status == PayableStatus.PAGA.value,
                )
            )
            despesas_atual = float((await self.session.execute(pay_q)).scalar_one() or 0)

            # Inadimplência do período
            inad_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
                and_(
                    ReceivableAccount.due_date >= inicio_atual,
                    ReceivableAccount.due_date <= fim_atual,
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                            ReceivableStatus.BAIXADA.value,
                        ]
                    ),
                )
            )
            inadimplencia_valor = float((await self.session.execute(inad_q)).scalar_one() or 0)
            taxa_inadimplencia = (inadimplencia_valor / receita_prevista * 100) if receita_prevista > 0 else 0.0

            # Contagem de inadimplentes
            cnt_inad_q = select(func.count(ReceivableAccount.id)).where(
                and_(
                    ReceivableAccount.due_date >= inicio_atual,
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                            ReceivableStatus.BAIXADA.value,
                        ]
                    ),
                )
            )
            qtd_inadimplentes = int((await self.session.execute(cnt_inad_q)).scalar_one() or 0)

            saldo_liquido = receita_atual - despesas_atual
            margem = (saldo_liquido / receita_atual * 100) if receita_atual > 0 else 0.0

            # === KPIs DO PERÍODO ANTERIOR ===
            recv_ant_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
                and_(
                    ReceivableAccount.payment_date >= inicio_ant,
                    ReceivableAccount.payment_date <= fim_ant,
                    ReceivableAccount.status == ReceivableStatus.PAGA.value,
                )
            )
            receita_anterior = float((await self.session.execute(recv_ant_q)).scalar_one() or 0)

            pay_ant_q = select(func.coalesce(func.sum(PayableAccount.net_value), 0)).where(
                and_(
                    PayableAccount.payment_date >= inicio_ant,
                    PayableAccount.payment_date <= fim_ant,
                    PayableAccount.status == PayableStatus.PAGA.value,
                )
            )
            despesas_anterior = float((await self.session.execute(pay_ant_q)).scalar_one() or 0)

            saldo_anterior = receita_anterior - despesas_anterior
            margem_anterior = (saldo_anterior / receita_anterior * 100) if receita_anterior > 0 else 0.0

            # Variações
            var_receita = ((receita_atual - receita_anterior) / receita_anterior * 100) if receita_anterior > 0 else 0.0
            var_margem = margem - margem_anterior

            # === SCORE DO PERÍODO ===
            health = await self.gerar_health_check()
            score = health.get("score", 50)
            classificacao = health.get("classificacao", "atencao")

            # === DESTAQUES (positivos) ===
            destaques = []
            if var_receita > 5:
                destaques.append(
                    {
                        "icone": "📈",
                        "titulo": f"Crescimento de receita: +{var_receita:.1f}%",
                        "descricao": f"Receita aumentou R$ {receita_atual - receita_anterior:,.2f} em relação ao mês anterior.",
                    }
                )
            if margem > 15:
                destaques.append(
                    {
                        "icone": "✅",
                        "titulo": f"Margem operacional saudável: {margem:.1f}%",
                        "descricao": "Operação manteve boa rentabilidade no período.",
                    }
                )
            if taxa_inadimplencia < 2 and receita_prevista > 0:
                destaques.append(
                    {
                        "icone": "💚",
                        "titulo": f"Inadimplência controlada: {taxa_inadimplencia:.1f}%",
                        "descricao": "Taxa abaixo do benchmark da indústria (<2%).",
                    }
                )
            if saldo_liquido > 0:
                destaques.append(
                    {
                        "icone": "💰",
                        "titulo": f"Resultado positivo: R$ {saldo_liquido:,.2f}",
                        "descricao": "Empresa gerou caixa no período.",
                    }
                )

            # === PONTOS DE ATENÇÃO ===
            pontos_atencao = []
            if taxa_inadimplencia > 5:
                pontos_atencao.append(
                    {
                        "icone": "🚨",
                        "nivel": "critico",
                        "titulo": f"Inadimplência em {taxa_inadimplencia:.1f}%",
                        "descricao": f"{qtd_inadimplentes} cliente(s) em atraso totalizando R$ {inadimplencia_valor:,.2f}.",
                        "acao": "Acionar régua de cobrança imediatamente",
                    }
                )
            elif taxa_inadimplencia > 2:
                pontos_atencao.append(
                    {
                        "icone": "⚠️",
                        "nivel": "alerta",
                        "titulo": f"Inadimplência acima do ideal: {taxa_inadimplencia:.1f}%",
                        "descricao": f"R$ {inadimplencia_valor:,.2f} em aberto.",
                        "acao": "Enviar lembretes e ativar cobrança preventiva",
                    }
                )
            if margem < 5 and receita_atual > 0:
                pontos_atencao.append(
                    {
                        "icone": "📉",
                        "nivel": "critico",
                        "titulo": f"Margem crítica: {margem:.1f}%",
                        "descricao": "Receitas e despesas muito próximas. Risco de prejuízo.",
                        "acao": "Revisar contratos e cortar custos desnecessários",
                    }
                )
            elif margem < 10 and receita_atual > 0:
                pontos_atencao.append(
                    {
                        "icone": "📊",
                        "nivel": "alerta",
                        "titulo": f"Margem abaixo do recomendado: {margem:.1f}%",
                        "descricao": "Meta: acima de 15% para empresas de segurança.",
                        "acao": "Revisar precificação dos contratos mais antigos",
                    }
                )
            if var_receita < -5:
                pontos_atencao.append(
                    {
                        "icone": "⬇️",
                        "nivel": "alerta",
                        "titulo": f"Queda de receita: {var_receita:.1f}%",
                        "descricao": f"Receita reduziu R$ {abs(receita_atual - receita_anterior):,.2f} vs. período anterior.",
                        "acao": "Investigar cancelamentos e prospectar novos contratos",
                    }
                )

            # Se não há pontos de atenção críticos
            if not pontos_atencao:
                pontos_atencao.append(
                    {
                        "icone": "✅",
                        "nivel": "ok",
                        "titulo": "Nenhuma irregularidade crítica identificada",
                        "descricao": "Todos os indicadores dentro dos parâmetros aceitáveis.",
                        "acao": "Manter monitoramento contínuo",
                    }
                )

            # === SUMÁRIO EXECUTIVO ===
            if score >= 80:
                status_texto = "excelente saúde financeira"
            elif score >= 60:
                status_texto = "boa situação financeira"
            elif score >= 40:
                status_texto = "situação financeira que requer atenção"
            else:
                status_texto = "situação financeira crítica"

            if var_receita > 2:
                tendencia_texto = f"crescimento de {var_receita:.1f}% na receita"
            elif var_receita < -2:
                tendencia_texto = f"retração de {abs(var_receita):.1f}% na receita"
            else:
                tendencia_texto = "estabilidade na receita"

            sumario = (
                f"Em {nome_mes_pt}/{ano}, a empresa apresentou {status_texto} "
                f"(score {score}/100), com {tendencia_texto} em relação ao mês anterior. "
                f"A margem operacional foi de {margem:.1f}% sobre receita de R$ {receita_atual:,.2f}."
            )
            if taxa_inadimplencia > 3:
                sumario += f" Atenção: inadimplência de {taxa_inadimplencia:.1f}% requer ação imediata."

            # === RECOMENDAÇÕES PRIORITÁRIAS ===
            recomendacoes = await self.gerar_recomendacoes()
            top_recomendacoes = recomendacoes[:3]

            return {
                "periodo": f"{ano:04d}-{mes:02d}",
                "titulo": f"Relatório Executivo Financeiro — {nome_mes_pt}/{ano}",
                "gerado_em": datetime.now().isoformat(),
                "sumario_executivo": sumario,
                "score_saude": score,
                "classificacao": classificacao,
                "kpis": {
                    "receita_realizada": round(receita_atual, 2),
                    "receita_prevista": round(receita_prevista, 2),
                    "despesas": round(despesas_atual, 2),
                    "saldo_liquido": round(saldo_liquido, 2),
                    "margem_pct": round(margem, 2),
                    "inadimplencia_valor": round(inadimplencia_valor, 2),
                    "inadimplencia_pct": round(taxa_inadimplencia, 2),
                    "qtd_inadimplentes": qtd_inadimplentes,
                },
                "comparativo": {
                    "receita_anterior": round(receita_anterior, 2),
                    "despesas_anterior": round(despesas_anterior, 2),
                    "saldo_anterior": round(saldo_anterior, 2),
                    "margem_anterior": round(margem_anterior, 2),
                    "variacao_receita_pct": round(var_receita, 2),
                    "variacao_margem_pct": round(var_margem, 2),
                },
                "destaques": destaques,
                "pontos_atencao": pontos_atencao,
                "recomendacoes_prioritarias": top_recomendacoes,
            }

        except Exception as exc:
            self.logger.warning(f"[{self.name}] Erro ao gerar relatório executivo: {exc}")
            today_str = f"{today.year:04d}-{today.month:02d}"
            return {
                "periodo": periodo or today_str,
                "titulo": f"Relatório Executivo — {periodo or today_str}",
                "gerado_em": datetime.now().isoformat(),
                "sumario_executivo": "Não foi possível gerar o relatório com os dados disponíveis.",
                "score_saude": 50,
                "classificacao": "atencao",
                "kpis": {
                    "receita_realizada": 0.0,
                    "receita_prevista": 0.0,
                    "despesas": 0.0,
                    "saldo_liquido": 0.0,
                    "margem_pct": 0.0,
                    "inadimplencia_valor": 0.0,
                    "inadimplencia_pct": 0.0,
                    "qtd_inadimplentes": 0,
                },
                "comparativo": {
                    "receita_anterior": 0.0,
                    "despesas_anterior": 0.0,
                    "saldo_anterior": 0.0,
                    "margem_anterior": 0.0,
                    "variacao_receita_pct": 0.0,
                    "variacao_margem_pct": 0.0,
                },
                "destaques": [],
                "pontos_atencao": [],
                "recomendacoes_prioritarias": [],
            }

    async def _execute(self, **kwargs) -> dict:
        """Execucao padrao: retorna health check completo."""
        return await self.gerar_health_check()

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _calcular_score(
        self,
        taxa_inad: float,
        margem: float,
        tendencia: str,
        vencimentos_7d: float,
        recv_30: float,
    ) -> int:
        score = 0

        # Inadimplencia (30 pts)
        if taxa_inad < 2:
            score += 30
        elif taxa_inad < 5:
            score += 20
        elif taxa_inad < 10:
            score += 10

        # Margem (30 pts)
        if margem > 20:
            score += 30
        elif margem > 10:
            score += 20
        elif margem > 5:
            score += 10
        elif margem > 0:
            score += 5

        # Tendencia (25 pts)
        if tendencia == "crescimento":
            score += 25
        elif tendencia == "estavel":
            score += 15

        # Liquidez proximos 7 dias (15 pts)
        risco_liquidez = (vencimentos_7d / recv_30) if recv_30 > 0 else 0
        if risco_liquidez < 0.3:
            score += 15
        elif risco_liquidez < 0.5:
            score += 10
        elif risco_liquidez < 0.8:
            score += 5

        return min(score, 100)

    def _gerar_narrativa(
        self,
        score: int,
        taxa_inad: float,
        margem: float,
        tendencia: str,
        tendencia_pct: float,
        recv_30: float,
        pay_30: float,
    ) -> str:
        partes = []

        if score >= 80:
            partes.append("A empresa apresenta excelente saude financeira.")
        elif score >= 60:
            partes.append("A situacao financeira e boa, com pontos de melhoria.")
        elif score >= 40:
            partes.append("A situacao financeira requer atencao em algumas areas.")
        else:
            partes.append("A situacao financeira e critica e requer acao imediata.")

        if recv_30 > 0:
            partes.append(
                f"Nos ultimos 30 dias, a receita foi de R$ {recv_30:,.2f} "
                f"com despesas de R$ {pay_30:,.2f} (margem de {margem:.1f}%)."
            )

        if tendencia == "crescimento":
            partes.append(f"A receita cresceu {tendencia_pct:.1f}% em relacao ao periodo anterior.")
        elif tendencia == "queda":
            partes.append(f"Atencao: a receita caiu {abs(tendencia_pct):.1f}% em relacao ao periodo anterior.")

        if taxa_inad > 5:
            partes.append(f"A taxa de inadimplencia de {taxa_inad:.1f}% esta acima do limite recomendado.")
        elif taxa_inad <= 2:
            partes.append(f"A taxa de inadimplencia de {taxa_inad:.1f}% esta dentro do ideal.")

        return " ".join(partes)

    def _gerar_alertas_criticos(
        self,
        taxa_inad: float,
        margem: float,
        vencimentos_7d: float,
        recv_30: float,
    ) -> list[dict]:
        alertas = []
        if taxa_inad > 5:
            alertas.append(
                {
                    "nivel": "critico",
                    "mensagem": f"Taxa de inadimplencia em {taxa_inad:.1f}% — acionar cobranca urgente",
                }
            )
        if margem < 5 and recv_30 > 0:
            alertas.append(
                {
                    "nivel": "critico",
                    "mensagem": f"Margem operacional em {margem:.1f}% — revisar precificacao",
                }
            )
        if recv_30 > 0 and vencimentos_7d > recv_30 * 0.7:
            alertas.append(
                {
                    "nivel": "alerta",
                    "mensagem": f"R$ {vencimentos_7d:,.2f} vencem nos proximos 7 dias — verificar liquidez",
                }
            )
        return alertas

    def _resposta_generica(self, pergunta: str, health: dict) -> str:
        score = health.get("score", 50)
        classificacao = health.get("classificacao", "atencao")
        return (
            f"Com base nos dados financeiros atuais (score de saude: {score}/100 — {classificacao}), "
            "posso ajudar com analises de inadimplencia, margem operacional, fluxo de caixa, "
            "precificacao de contratos e provisoes trabalhistas. "
            "Reformule sua pergunta com um desses temas para obter uma resposta mais precisa."
        )

    def _contextualizar_resposta(self, resposta_base: str, topico: str, health: dict) -> str:
        indicadores = health.get("indicadores", {})
        contexto = ""

        if topico == "inadimplencia":
            taxa = indicadores.get("taxa_inadimplencia", 0)
            em_atraso = indicadores.get("total_em_atraso", 0)
            contexto = f"\n\nSeu cenario atual: taxa de inadimplencia de {taxa:.1f}% com R$ {em_atraso:,.2f} em atraso."
        elif topico == "margem":
            margem = indicadores.get("margem_30d", 0)
            contexto = f"\n\nSua margem atual dos ultimos 30 dias: {margem:.1f}%."
        elif topico == "fluxo":
            venc = indicadores.get("vencimentos_proximos_7d", 0)
            recv = indicadores.get("receita_30d", 0)
            contexto = (
                f"\n\nSeus proximos 7 dias: R$ {venc:,.2f} em vencimentos. Receita ultimos 30 dias: R$ {recv:,.2f}."
            )

        return resposta_base + contexto

    def _resposta_fallback_pergunta(self, pergunta: str) -> str:
        return (
            "No momento nao consigo acessar os dados financeiros para responder com precisao. "
            "Os principais indicadores para monitorar em uma empresa de seguranca patrimonial sao: "
            "taxa de inadimplencia (meta < 2%), margem operacional (meta > 15%), "
            "fluxo de caixa projetado para 30/60/90 dias, e provisoes trabalhistas em dia."
        )

    def _health_check_fallback(self) -> dict:
        return {
            "score": 50,
            "classificacao": "atencao",
            "cor": "amarelo",
            "narrativa": "Nao foi possivel calcular os indicadores. Verifique se ha dados no sistema.",
            "indicadores": {
                "receita_30d": 0.0,
                "receita_periodo_anterior": 0.0,
                "despesas_30d": 0.0,
                "margem_30d": 0.0,
                "taxa_inadimplencia": 0.0,
                "total_em_atraso": 0.0,
                "qtd_inadimplentes": 0,
                "vencimentos_proximos_7d": 0.0,
                "tendencia_receita": "estavel",
                "tendencia_pct": 0.0,
            },
            "alertas_criticos": [],
        }

    async def _fallback(self, **kwargs) -> dict:
        """Fallback: retorna health check neutro."""
        return self._health_check_fallback()
