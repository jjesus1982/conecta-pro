"""
Financial AI Command Center Controller.
Agrega todos os agentes de IA financeiros em endpoints unificados.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session as get_db_session
from modules.financial.agents.billing_automator import BillingAutomatorAgent
from modules.financial.agents.cashflow_predictor import CashflowPredictorAgent
from modules.financial.agents.collection_negotiator import CollectionNegotiatorAgent
from modules.financial.agents.financial_advisor import FinancialAdvisorAgent
from modules.financial.agents.orchestrator import run_command_center
from modules.financial.agents.pricing_optimizer import PricingOptimizerAgent
from modules.financial.agents.risk_monitor import RiskMonitorAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["Financial AI"])


# ===================================================================
# SCHEMAS DE RESPONSE
# ===================================================================


class RiskAlert(BaseModel):
    level: str  # "verde", "amarelo", "laranja", "vermelho", "critico"
    category: str  # "inadimplencia", "liquidez", "margem", "concentracao"
    title: str
    description: str
    value: float | None = None
    action: str | None = None


class AIInsight(BaseModel):
    type: str  # "oportunidade", "risco", "informacao"
    icon: str  # emoji
    title: str
    description: str
    priority: int  # 1-5


class CashflowPoint(BaseModel):
    date: str
    expected_balance: float
    optimistic_balance: float
    pessimistic_balance: float


class CashflowPrediction(BaseModel):
    current_balance: float
    predicted_30d: float
    predicted_60d: float
    predicted_90d: float
    trend: str  # "positivo", "negativo", "estavel"
    confidence: float  # 0-1
    points: list[CashflowPoint]
    gaps: list[dict]  # datas com saldo negativo projetado
    scenario_optimistic: float
    scenario_pessimistic: float


class HealthCheck(BaseModel):
    score: int  # 0-100
    classification: str  # "excelente", "bom", "atencao", "critico"
    liquidity: float
    default_rate: float
    revenue_trend: str
    margin_avg: float
    alerts_count: int


class CommandCenterResponse(BaseModel):
    health: HealthCheck
    alerts: list[RiskAlert]
    insights: list[AIInsight]
    cashflow: CashflowPrediction | None = None
    updated_at: str


# ===================================================================
# HELPERS INTERNOS
# ===================================================================


async def _calculate_default_metrics(session: AsyncSession, condominio_id: str):
    """Calcula métricas de inadimplência e pagamentos futuros."""
    from sqlalchemy import and_, func, select

    from modules.financial.models.payable_account import PayableAccount
    from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus

    today = date.today()

    # Total de contas a receber
    total_recv_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0))
    if condominio_id:
        try:
            cid = UUID(condominio_id)
            total_recv_q = total_recv_q.where(ReceivableAccount.condominio_id == cid)
        except Exception:  # noqa: S110
            pass
    total_recv = (await session.execute(total_recv_q)).scalar_one() or Decimal("0")

    # Inadimplência: vencidas e não pagas
    overdue_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
        and_(
            ReceivableAccount.due_date < today,
            ReceivableAccount.status.notin_(
                [
                    ReceivableStatus.PAGA.value,
                    ReceivableStatus.CANCELADA.value,
                ]
            ),
        )
    )
    overdue_recv = (await session.execute(overdue_q)).scalar_one() or Decimal("0")

    # Contas a pagar vencendo nos próximos 7 dias
    week_ahead = today + timedelta(days=7)
    payable_q = select(func.coalesce(func.sum(PayableAccount.net_value), 0)).where(
        and_(
            PayableAccount.due_date >= today,
            PayableAccount.due_date <= week_ahead,
            PayableAccount.status.notin_(["paga", "cancelada"]),
        )
    )
    upcoming_payables = (await session.execute(payable_q)).scalar_one() or Decimal("0")

    default_rate = float(overdue_recv / total_recv * 100) if total_recv > 0 else 0.0

    return {
        "total_recv": total_recv,
        "overdue_recv": overdue_recv,
        "default_rate": default_rate,
        "upcoming_payables": upcoming_payables,
    }


def _build_alerts(metrics: dict) -> list[RiskAlert]:
    """Gera alertas baseados em regras (threshold-based)."""
    alerts = []
    default_rate = metrics["default_rate"]
    overdue_recv = metrics["overdue_recv"]
    upcoming_payables = metrics["upcoming_payables"]

    if default_rate > 5:
        alerts.append(
            RiskAlert(
                level="vermelho",
                category="inadimplencia",
                title=f"Inadimplência em {default_rate:.1f}%",
                description=(f"R$ {float(overdue_recv):,.2f} em atraso. Taxa acima do limite aceitável de 5%."),
                value=float(overdue_recv),
                action="Acionar régua de cobrança para clientes em atraso",
            )
        )
    elif default_rate > 3:
        alerts.append(
            RiskAlert(
                level="amarelo",
                category="inadimplencia",
                title=f"Inadimplência em {default_rate:.1f}%",
                description=(f"R$ {float(overdue_recv):,.2f} em atraso. Monitorar evolução."),
                value=float(overdue_recv),
                action="Enviar lembretes de cobrança",
            )
        )

    if float(upcoming_payables) > 50000:
        alerts.append(
            RiskAlert(
                level="laranja",
                category="liquidez",
                title=f"Vencimentos próximos: R$ {float(upcoming_payables):,.2f}",
                description=("Concentração de pagamentos nos próximos 7 dias. Verifique o saldo disponível."),
                value=float(upcoming_payables),
                action="Verificar saldo disponível e antecipar recebimentos se necessário",
            )
        )

    return alerts


def _build_insights(metrics: dict) -> list[AIInsight]:
    """Gera insights proativos baseados nas métricas calculadas."""
    insights = []
    default_rate = metrics["default_rate"]
    upcoming_payables = metrics["upcoming_payables"]

    if default_rate < 2:
        insights.append(
            AIInsight(
                type="oportunidade",
                icon="✅",
                title="Inadimplência sob controle",
                description=(
                    f"Taxa de {default_rate:.1f}% está excelente. "
                    "Considere oferecer condições diferenciadas para bons pagadores."
                ),
                priority=3,
            )
        )

    if float(upcoming_payables) > 0:
        insights.append(
            AIInsight(
                type="informacao",
                icon="📅",
                title=f"R$ {float(upcoming_payables):,.2f} a pagar em 7 dias",
                description="Organize o fluxo de caixa para garantir liquidez nos vencimentos.",
                priority=2,
            )
        )

    return insights


def _build_health(metrics: dict, alerts: list[RiskAlert]) -> HealthCheck:
    """Calcula o health score financeiro."""
    default_rate = metrics["default_rate"]
    upcoming_payables = metrics["upcoming_payables"]
    total_recv = metrics["total_recv"]
    overdue_recv = metrics["overdue_recv"]

    score = 100
    score -= min(30, int(default_rate * 6))  # -6 por % de inadimplência
    if float(upcoming_payables) > 100000:
        score -= 10
    if len(alerts) > 3:
        score -= 10
    score = max(0, min(100, score))

    if score >= 80:
        classification = "excelente"
    elif score >= 60:
        classification = "bom"
    elif score >= 40:
        classification = "atencao"
    else:
        classification = "critico"

    return HealthCheck(
        score=score,
        classification=classification,
        liquidity=float(total_recv - overdue_recv),
        default_rate=default_rate,
        revenue_trend="estavel",
        margin_avg=0.0,
        alerts_count=len(alerts),
    )


# ===================================================================
# ENDPOINT 1 — COMMAND CENTER
# ===================================================================


@router.get("/command-center", response_model=CommandCenterResponse)
async def get_command_center(
    condominio_id: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Retorna visão consolidada do AI Command Center financeiro."""
    from datetime import datetime

    default_health = HealthCheck(
        score=70,
        classification="bom",
        liquidity=0.0,
        default_rate=0.0,
        revenue_trend="estavel",
        margin_avg=0.0,
        alerts_count=0,
    )

    try:
        result = await run_command_center(session)
        hd = result.get("health", {})
        health = HealthCheck(
            score=hd.get("score", 70),
            classification=hd.get("classification", "bom"),
            liquidity=hd.get("liquidity", 0.0),
            default_rate=hd.get("default_rate", 0.0),
            revenue_trend=hd.get("revenue_trend", "estavel"),
            margin_avg=hd.get("margin_avg", 0.0),
            alerts_count=hd.get("alerts_count", 0),
        )
        alerts = [RiskAlert(**a) for a in result.get("alerts", []) if isinstance(a, dict)]
        insights = [AIInsight(**i) for i in result.get("insights", []) if isinstance(i, dict)]
        cf = result.get("cashflow")
        cashflow = None
        if cf and isinstance(cf, dict):
            try:
                cashflow = CashflowPrediction(
                    current_balance=cf.get("current_balance", 0.0),
                    predicted_30d=cf.get("predicted_30d", 0.0),
                    predicted_60d=cf.get("predicted_60d", 0.0),
                    predicted_90d=cf.get("predicted_90d", 0.0),
                    trend=cf.get("trend", "estavel"),
                    confidence=cf.get("confidence", 0.3),
                    points=[CashflowPoint(**p) for p in cf.get("points", [])],
                    gaps=cf.get("gaps", []),
                    scenario_optimistic=cf.get("scenario_optimistic", 0.0),
                    scenario_pessimistic=cf.get("scenario_pessimistic", 0.0),
                )
            except Exception as exc:
                logger.debug("Erro ao montar CashflowPrediction: %s", exc)

        return CommandCenterResponse(
            health=health,
            alerts=alerts,
            insights=insights,
            cashflow=cashflow,
            updated_at=result.get("updated_at", datetime.now().isoformat()),
        )

    except Exception as exc:
        logger.warning("Erro no command center (agentes): %s. Usando fallback.", exc)
        try:
            metrics = await _calculate_default_metrics(session, condominio_id)
            fallback_alerts = _build_alerts(metrics)
            fallback_insights = _build_insights(metrics)
            fallback_health = _build_health(metrics, fallback_alerts)
            return CommandCenterResponse(
                health=fallback_health,
                alerts=fallback_alerts,
                insights=fallback_insights,
                updated_at=datetime.now().isoformat(),
            )
        except Exception as exc2:
            logger.warning("Erro no fallback do command center: %s", exc2)

    return CommandCenterResponse(
        health=default_health,
        alerts=[],
        insights=[],
        updated_at=datetime.now().isoformat(),
    )


# ===================================================================
# ENDPOINT 2 — RISKS
# ===================================================================


@router.get("/risks", response_model=list[RiskAlert])
async def get_risks(
    condominio_id: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna lista de alertas de risco financeiro via RiskMonitorAgent.

    Verifica:
    - Contas a receber vencidas (inadimplência por faixa)
    - Liquidez dos próximos 7 dias
    - Concentração de receita (>20% em 1 cliente)
    - Margem operacional
    """
    try:
        agent = RiskMonitorAgent(session)
        raw_alerts = await agent.scan()
        return [RiskAlert(**a) for a in raw_alerts if isinstance(a, dict)]
    except Exception as exc:
        logger.warning("Erro no RiskMonitorAgent, usando fallback: %s", exc)
        # Fallback com lógica original
        alerts: list[RiskAlert] = []
        try:
            from sqlalchemy import func, select

            from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus

            metrics = await _calculate_default_metrics(session, condominio_id)
            alerts = _build_alerts(metrics)
            total_recv = metrics["total_recv"]
            if total_recv > 0:
                conc_q = (
                    select(
                        ReceivableAccount.customer_id,
                        func.sum(ReceivableAccount.net_value).label("total"),
                    )
                    .where(ReceivableAccount.status != ReceivableStatus.CANCELADA.value)
                    .group_by(ReceivableAccount.customer_id)
                    .order_by(func.sum(ReceivableAccount.net_value).desc())
                    .limit(1)
                )
                top_result = (await session.execute(conc_q)).first()
                if top_result and top_result.total:
                    concentration = float(top_result.total / total_recv * 100)
                    if concentration > 40:
                        alerts.append(
                            RiskAlert(
                                level="amarelo",
                                category="concentracao",
                                title=f"Concentração de receita: {concentration:.0f}% em 1 cliente",
                                description=(
                                    "Alto risco de concentração. "
                                    "Diversifique a base de clientes para reduzir dependência."
                                ),
                                value=float(top_result.total),
                                action="Prospectar novos clientes para diluir concentração de receita",
                            )
                        )
        except Exception as exc2:
            logger.warning("Erro no fallback de riscos: %s", exc2)
        return alerts


# ===================================================================
# ENDPOINT 3 — ADVISOR (LLM com fallback baseado em regras)
# ===================================================================


@router.post("/advisor", status_code=201)
async def ask_advisor(
    question: str = Query(...),
    condominio_id: str = Query(default=""),
    current_user=Depends(get_current_user),
):
    """
    Responde perguntas financeiras em linguagem natural.

    Usa o LLM Provider (Anthropic) quando a API key estiver configurada.
    Caso contrário, aplica lógica de regras como fallback inteligente.
    """
    from core.config.settings import settings

    question_lower = question.lower()

    # Tentar LLM se a key estiver disponível
    api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
    if api_key:
        try:
            from modules.ai.conversation.services.llm_provider import LLMModel, LLMProvider

            llm = LLMProvider()
            system_prompt = (
                "Você é um assistente financeiro especializado em empresas de segurança patrimonial. "
                "Responda de forma concisa e prática, focando em ações concretas. "
                "Use linguagem simples, sem jargões. Máximo de 3 parágrafos."
            )
            answer = await llm.generate(
                model=LLMModel.CLAUDE_3_HAIKU,
                system=system_prompt,
                messages=[{"role": "user", "content": question}],
                max_tokens=512,
            )
            return {"answer": answer, "data": None}
        except Exception as exc:
            logger.warning("LLM indisponível, usando fallback: %s", exc)

    # Fallback baseado em regras
    if any(w in question_lower for w in ["contrato", "rentável", "rentavel", "margem"]):
        return {
            "answer": (
                "Para visualizar a margem por contrato, acesse a página de Custeio ABC e filtre por "
                "tipo de serviço. Os contratos de Portaria Remota e Segurança Eletrônica tendem a ter "
                "as maiores margens (35-40%)."
            ),
            "data": None,
        }
    if any(w in question_lower for w in ["inadimpl", "atraso", "cobrança", "cobranca"]):
        return {
            "answer": (
                "Acesse Cobranças > Inadimplentes para ver a lista completa. "
                "Priorize clientes com mais de 30 dias de atraso e ative a régua de cobrança automática."
            ),
            "data": None,
        }
    if any(w in question_lower for w in ["fluxo", "caixa", "saldo"]):
        return {
            "answer": (
                "Acesse Fluxo de Caixa para ver a previsão de 90 dias. "
                "O painel mostra gaps projetados e sugere ações preventivas."
            ),
            "data": None,
        }
    if any(w in question_lower for w in ["custo", "horas extras", "folha"]):
        return {
            "answer": (
                "Acesse Custeio ABC para ver o custo detalhado por posto e contrato. "
                "Anomalias de horas extras aparecem como alertas no dashboard."
            ),
            "data": None,
        }

    return {
        "answer": (
            "Posso ajudar com análise de inadimplência, fluxo de caixa, "
            "custos por contrato e precificação. "
            "Faça uma pergunta específica sobre essas áreas."
        ),
        "data": None,
    }


# ===================================================================
# ENDPOINT 4 — CASHFLOW PREDICTION
# ===================================================================


@router.get("/cashflow-prediction", response_model=CashflowPrediction)
async def get_cashflow_prediction(
    days: int = Query(default=90, ge=7, le=365),
    condominio_id: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna previsão de fluxo de caixa para os próximos N dias.

    Usa CashflowPredictorAgent (Fase 2); com fallback para CashFlowAIService
    e projeção linear simples.
    """

    today = date.today()

    # Tentar CashflowPredictorAgent (Fase 2)
    try:
        agent = CashflowPredictorAgent(session)
        cf = await agent.predict(days=days)
        if cf:
            return CashflowPrediction(
                current_balance=cf.get("current_balance", 0.0),
                predicted_30d=cf.get("predicted_30d", 0.0),
                predicted_60d=cf.get("predicted_60d", 0.0),
                predicted_90d=cf.get("predicted_90d", 0.0),
                trend=cf.get("trend", "estavel"),
                confidence=cf.get("confidence", 0.3),
                points=[CashflowPoint(**p) for p in cf.get("points", [])],
                gaps=cf.get("gaps", []),
                scenario_optimistic=cf.get("scenario_optimistic", 0.0),
                scenario_pessimistic=cf.get("scenario_pessimistic", 0.0),
            )
    except Exception as exc:
        logger.debug("CashflowPredictorAgent indisponível, usando fallback: %s", exc)

    # Fallback: CashFlowAIService
    try:
        from modules.financial.services.cashflow_ai_service import CashFlowAIService

        ai_service = CashFlowAIService(session)
        months_ahead = max(1, days // 30)
        forecast = await ai_service.generate_forecast(
            condominio_id=condominio_id or None,
            months_ahead=months_ahead,
        )
        if forecast:
            return forecast
    except Exception as exc:
        logger.debug("CashFlowAIService indisponível, usando fallback: %s", exc)

    # Fallback: projeção simples baseada em dados históricos
    try:
        from sqlalchemy import and_, func, select

        from modules.financial.models.payable_account import PayableAccount
        from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus

        # Receita média dos últimos 30 dias
        past_30 = today - timedelta(days=30)
        recv_q = select(func.coalesce(func.sum(ReceivableAccount.net_value), 0)).where(
            and_(
                ReceivableAccount.payment_date >= past_30,
                ReceivableAccount.status == ReceivableStatus.PAGA.value,
            )
        )
        avg_recv_month = float((await session.execute(recv_q)).scalar_one() or 0)

        pay_q = select(func.coalesce(func.sum(PayableAccount.net_value), 0)).where(
            and_(
                PayableAccount.payment_date >= past_30,
                PayableAccount.status == "paga",
            )
        )
        avg_pay_month = float((await session.execute(pay_q)).scalar_one() or 0)

        net_daily = (avg_recv_month - avg_pay_month) / 30
        current_balance = avg_recv_month - avg_pay_month  # estimativa de saldo atual

        # Gerar pontos de projeção (a cada 7 dias)
        points: list[CashflowPoint] = []
        gaps: list[dict] = []
        balance = current_balance
        step = 7
        for i in range(step, days + 1, step):
            balance += net_daily * step
            point_date = today + timedelta(days=i)
            expected = balance
            optimistic = balance * 1.10
            pessimistic = balance * 0.90
            points.append(
                CashflowPoint(
                    date=point_date.isoformat(),
                    expected_balance=round(expected, 2),
                    optimistic_balance=round(optimistic, 2),
                    pessimistic_balance=round(pessimistic, 2),
                )
            )
            if pessimistic < 0:
                gaps.append({"date": point_date.isoformat(), "projected_balance": round(pessimistic, 2)})

        days_30 = current_balance + net_daily * 30
        days_60 = current_balance + net_daily * 60
        days_90 = current_balance + net_daily * 90

        if net_daily > 0:
            trend = "positivo"
        elif net_daily < 0:
            trend = "negativo"
        else:
            trend = "estavel"

        return CashflowPrediction(
            current_balance=round(current_balance, 2),
            predicted_30d=round(days_30, 2),
            predicted_60d=round(days_60, 2),
            predicted_90d=round(days_90, 2),
            trend=trend,
            confidence=0.65,
            points=points,
            gaps=gaps,
            scenario_optimistic=round(days_90 * 1.15, 2),
            scenario_pessimistic=round(days_90 * 0.85, 2),
        )

    except Exception as exc:
        logger.warning("Erro ao gerar previsão de caixa: %s", exc)
        # Resposta neutra em caso de falha total
        return CashflowPrediction(
            current_balance=0.0,
            predicted_30d=0.0,
            predicted_60d=0.0,
            predicted_90d=0.0,
            trend="estavel",
            confidence=0.0,
            points=[],
            gaps=[],
            scenario_optimistic=0.0,
            scenario_pessimistic=0.0,
        )


# ===================================================================
# ENDPOINT 5a — COLLECTION: ANÁLISE DE INADIMPLENTES
# ===================================================================


@router.get("/collection/analyze")
async def get_collection_analysis(
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna análise completa de inadimplentes com estratégias de cobrança
    personalizadas por nível de atraso (CollectionNegotiatorAgent).
    """
    agent = CollectionNegotiatorAgent(session)
    return await agent.analisar()


@router.get("/collection/receivable/{receivable_id}")
async def analyze_receivable(
    receivable_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Analisa uma conta a receber específica e retorna a melhor estratégia de cobrança."""
    agent = CollectionNegotiatorAgent(session)
    return await agent.analyze_receivable(receivable_id)


# ===================================================================
# ENDPOINT 5b — PRICING: CALCULADORA DE PRECIFICAÇÃO
# ===================================================================


class PricingRequest(BaseModel):
    tipo: str = "portaria"  # portaria, limpeza, jardinagem, seguranca_eletronica, portaria_remota
    quantidade: float = 1.0  # Postos / m2 / câmeras / pontos
    escala: str = "12x36"  # 12x36, 44h, 8h, 24h, 12h_diurno, 12h_noturno
    localizacao: str = "default"  # sp_capital, rj_capital, grandes_capitais, interior_sp, nordeste, norte


@router.post("/pricing/calculate", status_code=201)
async def calculate_pricing(
    request: PricingRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Calcula precificação ótima para um contrato de segurança.

    Retorna custo estimado detalhado e preços em 3 margens:
    - Mínima (10%), Ideal (25%), Premium (40%).
    """
    agent = PricingOptimizerAgent(session)
    return await agent.calcular_preco(
        tipo=request.tipo,
        qtd_postos=request.quantidade,
        escala=request.escala,
        localizacao=request.localizacao,
    )


# ===================================================================
# ENDPOINT 5c — ADVISOR: SAÚDE FINANCEIRA + RECOMENDAÇÕES + CHAT
# ===================================================================


@router.get("/advisor/health")
async def get_financial_health(
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna health check completo da saúde financeira da empresa.
    Score 0-100, indicadores detalhados, narrativa e alertas críticos.
    """
    agent = FinancialAdvisorAgent(session)
    return await agent.gerar_health_check()


@router.get("/advisor/recommendations")
async def get_recommendations(
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna lista priorizada de recomendações financeiras baseadas nos dados reais do sistema.
    """
    agent = FinancialAdvisorAgent(session)
    return await agent.gerar_recomendacoes()


class AdvisorChatRequest(BaseModel):
    pergunta: str
    condominio_id: str = ""


@router.post("/advisor/chat", status_code=201)
async def advisor_chat(
    request: AdvisorChatRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Chat com o Financial Advisor Agent.
    Responde perguntas em linguagem natural com dados reais do sistema.
    """
    agent = FinancialAdvisorAgent(session)
    return await agent.responder_pergunta(request.pergunta)


@router.get("/advisor/relatorio")
async def get_relatorio_executivo(
    periodo: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Gera relatório executivo financeiro completo para o período.

    Query param: periodo=YYYY-MM (padrão: mês atual)

    Retorna: sumário executivo, KPIs, destaques, pontos de atenção,
    comparativo com período anterior e recomendações priorizadas.
    """
    agent = FinancialAdvisorAgent(session)
    return await agent.gerar_relatorio_executivo(periodo or None)


# ===================================================================
# ENDPOINT 5d — COSTING: MARGEM POR TIPO DE SERVIÇO
# ===================================================================


@router.get("/costing/margin-by-type")
async def get_margin_by_service_type(
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna margem média por tipo de serviço (portaria, limpeza, jardinagem,
    seguranca_eletronica, portaria_remota) para o mês atual e os 2 anteriores.

    Se não houver dados reais, retorna benchmarks de demonstração.
    """
    from modules.financial.agents.costing_analyzer import CostingAnalyzerAgent

    agent = CostingAnalyzerAgent(session)
    return await agent.execute("get_margin_by_service_type")


# ===================================================================
# ENDPOINTS PHASE 4 — BILLING AUTOMATOR
# ===================================================================


def _parse_mes(mes_str: str | None) -> date:
    """Converte string 'YYYY-MM' em date (primeiro dia do mês)."""
    today = date.today()
    if not mes_str:
        return today.replace(day=1)
    try:
        parts = mes_str.split("-")
        return date(int(parts[0]), int(parts[1]), 1)
    except Exception:
        return today.replace(day=1)


@router.get("/billing/summary")
async def get_billing_summary(
    mes: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna resumo de faturamento do mês.

    Query param: mes=YYYY-MM (padrão: mês atual)
    """
    mes_date = _parse_mes(mes)
    agent = BillingAutomatorAgent(session)
    return await agent.gerar_resumo_faturamento(mes_date)


@router.get("/billing/contracts")
async def get_billing_contracts(
    mes: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna lista de contratos pendentes de faturamento no mês.

    Query param: mes=YYYY-MM (padrão: mês atual)
    """
    mes_date = _parse_mes(mes)
    agent = BillingAutomatorAgent(session)
    return await agent.listar_contratos_para_faturar(mes_date)


class MedicaoRequest(BaseModel):
    tipo: str = "portaria"
    descricao: str = "Contrato de portaria/serviços para condomínios"
    periodo_dias: int = 30


@router.post("/billing/medicao", status_code=201)
async def calcular_medicao(
    request: MedicaoRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Calcula medição de um contrato por tipo de serviço.

    Tipos: portaria, limpeza, jardinagem, seguranca_eletronica, portaria_remota
    """
    agent = BillingAutomatorAgent(session)
    return agent.calcular_medicao(
        contrato_descricao=request.descricao,
        tipo=request.tipo,
        periodo_dias=request.periodo_dias,
    )


@router.get("/billing/preview")
async def get_billing_preview(
    mes: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna preview do faturamento automático do mês.

    Query param: mes=YYYY-MM (padrão: mês atual)
    """
    mes_date = _parse_mes(mes)
    agent = BillingAutomatorAgent(session)
    return await agent.executar_faturamento_preview(mes_date)


class ContratoAtivadoRequest(BaseModel):
    contrato_id: int
    valor_mensal: float
    tipo_servico: str
    cliente_nome: str = ""


@router.post("/billing/contrato-ativado", status_code=201)
async def contrato_ativado(
    request: ContratoAtivadoRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Simula ativação de contrato CRM → cria conta a receber automaticamente.

    Body: {contrato_id, valor_mensal, tipo_servico, cliente_nome}
    """
    from modules.financial.integrations.crm_integration import on_contrato_ativado

    return await on_contrato_ativado(
        contrato_id=request.contrato_id,
        valor_mensal=request.valor_mensal,
        tipo_servico=request.tipo_servico,
        session=session,
        cliente_nome=request.cliente_nome,
    )


# ===================================================================
# ENDPOINT PHASE 3 — COSTING BY TYPE
# ===================================================================


class RegistrarCustoRequest(BaseModel):
    tipo: str  # portaria, limpeza, jardinagem, seguranca_eletronica, portaria_remota
    contrato_id: int | None = None
    mes: str  # YYYY-MM  (ex: 2026-03)
    custo_total: float
    margem_contratual: float = 0.0
    breakdown: dict[str, float] = {}


@router.get("/costing/by-type")
async def get_costing_by_type(
    tipo: str = Query(
        ..., description="Tipo de serviço: portaria, limpeza, jardinagem, seguranca_eletronica, portaria_remota"
    ),
    mes: str = Query(default="", description="Mês no formato YYYY-MM (padrão: mês atual)"),
    contrato_id: int = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna breakdown de custos para um tipo de serviço em um mês.
    Prioriza dados reais das tabelas de custo; usa benchmarks como fallback.
    """
    from modules.financial.services.cost_by_type_service import CostByTypeService

    if mes:
        try:
            parts = mes.split("-")
            ref_date = date(int(parts[0]), int(parts[1]), 1)
        except Exception:
            ref_date = date.today().replace(day=1)
    else:
        ref_date = date.today().replace(day=1)

    service = CostByTypeService(session)
    resultado = await service.calcular_custo_estimado(
        tipo=tipo,
        contrato_id=contrato_id,
        mes=ref_date,
    )
    registros = await service.listar_custos_por_tipo(tipo=tipo, mes=ref_date)
    resultado["registros"] = registros
    return resultado


@router.get("/costing/summary")
async def get_costing_summary(
    mes: str = Query(default="", description="Mês no formato YYYY-MM (padrão: mês atual)"),
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Retorna resumo de custos e margens para todos os tipos de serviço no mês.
    Inclui análise AI do CostingAnalyzerAgent.
    """
    from modules.financial.agents.costing_analyzer import CostingAnalyzerAgent
    from modules.financial.services.cost_by_type_service import CostByTypeService

    if mes:
        try:
            parts = mes.split("-")
            ref_date = date(int(parts[0]), int(parts[1]), 1)
        except Exception:
            ref_date = date.today().replace(day=1)
    else:
        ref_date = date.today().replace(day=1)

    service = CostByTypeService(session)
    resumo = await service.get_resumo_margem_por_tipo(ref_date)

    # Tentar análise AI do CostingAnalyzerAgent
    analise = None
    try:
        agent = CostingAnalyzerAgent(session)
        analise = await agent.analisar_margens()
    except Exception as exc:
        logger.debug("CostingAnalyzerAgent indisponível no summary: %s", exc)

    return {
        "mes": ref_date.isoformat(),
        "resumo_por_tipo": resumo,
        "analise_ai": analise,
        "total_custo": sum(r["custo_total"] for r in resumo),
        "total_margem": sum(r["margem_contratual"] for r in resumo),
    }


@router.post("/costing/registrar", status_code=201)
async def registrar_custo_tipo(
    request: RegistrarCustoRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Registra um custo real para um tipo de serviço.
    Cria o registro na tabela correspondente ao tipo.
    """
    from modules.financial.services.cost_by_type_service import CostByTypeService

    try:
        parts = request.mes.split("-")
        mes_date = date(int(parts[0]), int(parts[1]), 1)
    except Exception:
        raise HTTPException(status_code=400, detail="Formato de mês inválido. Use YYYY-MM.")

    service = CostByTypeService(session)
    resultado = await service.registrar_custo(
        tipo=request.tipo,
        contrato_id=request.contrato_id,
        mes=mes_date,
        custo_total=request.custo_total,
        margem_contratual=request.margem_contratual,
        breakdown=request.breakdown,
    )

    if "erro" in resultado:
        raise HTTPException(status_code=400, detail=resultado["erro"])

    return resultado


@router.get("/agents/status", summary="Status dos agentes GEDEON financeiros")
async def get_agents_status(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Status de todos os agentes com skills carregadas."""
    from datetime import datetime

    from modules.financial.agents.skill_loader import SkillLoader

    agents_config = [
        {
            "name": "FinancialAdvisorAgent",
            "schedule": "diário 07:30",
            "skills": ["dre-gerencial", "kpis-financeiros", "analise-fluxo-caixa-real"],
        },
        {
            "name": "CashflowPredictorAgent",
            "schedule": "diário 07:00",
            "skills": ["projecao-fluxo-caixa-12-meses", "analise-fluxo-caixa-real"],
        },
        {"name": "RiskMonitorAgent", "schedule": "5 minutos", "skills": ["kpis-financeiros", "matriz-riscos-negocio"]},
        {"name": "CollectionNegotiatorAgent", "schedule": "diário 09:00", "skills": ["gestao-inadimplencia"]},
        {
            "name": "PricingOptimizerAgent",
            "schedule": "mensal dia 1",
            "skills": ["framework-precificacao-margem", "break-even-ponto-equilibrio"],
        },
        {"name": "TaxCalculatorAgent", "schedule": "trimestral dia 20", "skills": ["tributario-lucro-real"]},
        {"name": "BillingAutomatorAgent", "schedule": "diário 08:00", "skills": []},
        {"name": "CostingAnalyzerAgent", "schedule": "mensal dia 1", "skills": ["analise-margem-por-servico"]},
    ]

    skills_available = SkillLoader.list_available()

    return {
        "total_agents": len(agents_config),
        "skills_available": len(skills_available),
        "skills_list": skills_available,
        "gedeon_layer": "Layer 2 — Financial",
        "timestamp": datetime.now().isoformat(),
        "agents": [
            {
                **agent,
                "skills_loaded": [s for s in agent["skills"] if any(s in sk for sk in skills_available)],
                "skills_missing": [s for s in agent["skills"] if not any(s in sk for sk in skills_available)],
            }
            for agent in agents_config
        ],
    }
