#!/usr/bin/env python3
"""
CONECTA PRO - CRM 360° + Customer Journey Service
==============================================
FASE 3 ONDA 3: Transformação Digital

NOTA (2026-07): Este serviço NÃO é servido por nenhum controller/router.
Ele existe apenas como estrutura de domínio (dataclasses/enums) e é exercitado
por testes. Toda a fabricação de dados via `random` foi REMOVIDA. O serviço
inicializa com um conjunto FIXO e determinístico de clientes-semente (sem
aleatoriedade e sem métricas inventadas por RNG). Interações e insights
preditivos iniciam VAZIOS — só existem quando alimentados de fato via
`track_customer_interaction`, refletindo honestamente "sem dado ainda".

Recursos (estrutura):
- Visão 360° completa do cliente
- Mapeamento da jornada do cliente
- Rastreamento de interações multi-canal
- Segmentação de clientes
- Gestão de lifecycle do cliente
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomerSegment(Enum):
    VIP = "vip"
    PREMIUM = "premium"
    STANDARD = "standard"
    BRONZE = "bronze"
    PROSPECT = "prospect"
    CHURNING = "churning"
    INACTIVE = "inactive"


class CustomerStage(Enum):
    LEAD = "lead"
    PROSPECT = "prospect"
    CUSTOMER = "customer"
    LOYAL = "loyal"
    ADVOCATE = "advocate"
    CHURNED = "churned"


class InteractionType(Enum):
    EMAIL = "email"
    PHONE = "phone"
    WHATSAPP = "whatsapp"
    PORTAL = "portal"
    MOBILE_APP = "mobile_app"
    FACE_TO_FACE = "face_to_face"
    SYSTEM = "system"
    SOCIAL_MEDIA = "social_media"


class InteractionDirection(Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class JourneyStage(Enum):
    AWARENESS = "awareness"
    CONSIDERATION = "consideration"
    DECISION = "decision"
    ONBOARDING = "onboarding"
    ACTIVE_USE = "active_use"
    EXPANSION = "expansion"
    RENEWAL = "renewal"
    ADVOCACY = "advocacy"
    CHURN = "churn"


class TouchpointCategory(Enum):
    MARKETING = "marketing"
    SALES = "sales"
    SUPPORT = "support"
    PRODUCT = "product"
    BILLING = "billing"
    TECHNICAL = "technical"


@dataclass
class CustomerInteraction:
    """Interação com o cliente em qualquer canal."""

    id: str
    customer_id: str
    timestamp: datetime
    type: InteractionType
    direction: InteractionDirection
    channel: str
    touchpoint_category: TouchpointCategory
    subject: str
    description: str
    sentiment_score: float  # -1 to 1
    satisfaction_score: float | None = None  # 0 to 10
    outcome: str | None = None
    next_action: str | None = None
    agent_id: str | None = None
    duration_seconds: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomerTouchpoint:
    """Ponto de contato na jornada do cliente."""

    id: str
    name: str
    category: TouchpointCategory
    channel: str
    stage: JourneyStage
    is_digital: bool
    importance_score: float  # 0 to 10
    satisfaction_avg: float
    conversion_rate: float
    description: str


@dataclass
class CustomerJourney:
    """Jornada completa do cliente."""

    customer_id: str
    current_stage: JourneyStage
    journey_start_date: datetime
    touchpoints_visited: list[str]
    interactions_count: int
    satisfaction_avg: float
    time_in_stage_days: int
    next_predicted_stage: JourneyStage | None
    stage_progression_probability: float
    churn_risk_score: float  # 0 to 1
    lifetime_value_predicted: float
    journey_health_score: float  # 0 to 100


@dataclass
class CustomerSegmentProfile:
    """Perfil de segmento de cliente."""

    segment: CustomerSegment
    criteria: dict[str, Any]
    customer_count: int
    avg_lifetime_value: float
    avg_satisfaction: float
    churn_rate: float
    growth_rate: float
    preferred_channels: list[str]
    behavior_patterns: dict[str, Any]


@dataclass
class Customer360:
    """Visão 360° completa do cliente."""

    id: str
    basic_info: dict[str, Any]
    segment: CustomerSegment
    stage: CustomerStage
    journey: CustomerJourney
    interactions: list[CustomerInteraction]
    behavioral_insights: dict[str, Any]
    preferences: dict[str, Any]
    satisfaction_metrics: dict[str, float]
    financial_metrics: dict[str, float]
    engagement_metrics: dict[str, float]
    risk_indicators: dict[str, float]
    opportunities: list[dict[str, Any]]
    next_best_actions: list[dict[str, Any]]
    created_at: datetime
    last_updated: datetime


@dataclass
class PredictiveInsight:
    """Insight preditivo sobre cliente."""

    customer_id: str
    insight_type: str
    prediction: str
    confidence_score: float
    impact_score: float  # 0 to 10
    recommendation: str
    data_sources: list[str]
    expires_at: datetime
    created_at: datetime


@dataclass
class CRMAnalytics:
    """Analytics completo do CRM."""

    total_customers: int
    active_customers: int
    new_customers_month: int
    churned_customers_month: int
    avg_customer_satisfaction: float
    avg_lifetime_value: float
    customer_acquisition_cost: float
    churn_rate: float
    segment_distribution: dict[str, int]
    stage_distribution: dict[str, int]
    interaction_volume_daily: int
    response_time_avg_hours: float
    conversion_rates: dict[str, float]


# ---------------------------------------------------------------------------
# Semente FIXA e determinística (sem random, sem métricas fabricadas por RNG).
# Cada valor é uma constante conhecida — nada é inventado a cada execução.
# Interações e insights preditivos NÃO são pré-populados: começam vazios e só
# passam a existir quando registrados de fato.
# ---------------------------------------------------------------------------
_SEED_CUSTOMERS: list[dict[str, Any]] = [
    {
        "id": "CUST_0001",
        "name": "Condomínio Jardim Europa",
        "location": "São Paulo - Zona Sul",
        "segment": CustomerSegment.VIP,
        "stage": CustomerStage.LOYAL,
        "monthly_revenue": 12000.0,
        "lifetime_value": 350000.0,
        "overall_satisfaction": 9.2,
        "feature_adoption_rate": 0.9,
        "churn_risk_score": 0.1,
    },
    {
        "id": "CUST_0002",
        "name": "Condomínio Vila Madalena",
        "location": "São Paulo - Zona Oeste",
        "segment": CustomerSegment.VIP,
        "stage": CustomerStage.ADVOCATE,
        "monthly_revenue": 13500.0,
        "lifetime_value": 420000.0,
        "overall_satisfaction": 9.5,
        "feature_adoption_rate": 0.92,
        "churn_risk_score": 0.08,
    },
    {
        "id": "CUST_0003",
        "name": "Residencial Parque das Flores",
        "location": "São Paulo - Zona Norte",
        "segment": CustomerSegment.PREMIUM,
        "stage": CustomerStage.CUSTOMER,
        "monthly_revenue": 6000.0,
        "lifetime_value": 180000.0,
        "overall_satisfaction": 8.7,
        "feature_adoption_rate": 0.75,
        "churn_risk_score": 0.15,
    },
    {
        "id": "CUST_0004",
        "name": "Edifício Corporate Center",
        "location": "São Paulo - Central",
        "segment": CustomerSegment.STANDARD,
        "stage": CustomerStage.CUSTOMER,
        "monthly_revenue": 3000.0,
        "lifetime_value": 85000.0,
        "overall_satisfaction": 8.1,
        "feature_adoption_rate": 0.6,
        "churn_risk_score": 0.25,
    },
]


class CRM360Service:
    """Serviço CRM 360° + Customer Journey.

    Sem `random`: a semente é FIXA. Interações e insights preditivos iniciam
    vazios (honestos) e só existem quando alimentados de fato.
    """

    def __init__(self):
        self.customers: dict[str, Customer360] = {}
        self.interactions: dict[str, CustomerInteraction] = {}
        self.touchpoints: dict[str, CustomerTouchpoint] = {}
        self.segments: dict[CustomerSegment, CustomerSegmentProfile] = {}
        self.predictive_insights: dict[str, list[PredictiveInsight]] = {}

        # Inicializar com semente FIXA (determinística, sem RNG)
        self._initialize_seed_data()

    def _initialize_seed_data(self):
        """Inicializar com semente FIXA determinística (sem random)."""
        now = datetime.now()

        for seed in _SEED_CUSTOMERS:
            current_stage = self._get_journey_stage_from_customer_stage(seed["stage"])

            journey = CustomerJourney(
                customer_id=seed["id"],
                current_stage=current_stage,
                journey_start_date=now,
                touchpoints_visited=[],
                interactions_count=0,
                satisfaction_avg=seed["overall_satisfaction"],
                time_in_stage_days=0,
                next_predicted_stage=self._predict_next_journey_stage(current_stage),
                stage_progression_probability=0.0,
                churn_risk_score=seed["churn_risk_score"],
                lifetime_value_predicted=seed["lifetime_value"],
                journey_health_score=0.0,
            )

            customer = Customer360(
                id=seed["id"],
                basic_info={
                    "name": seed["name"],
                    "type": "condomínio",
                    "created_date": now.isoformat(),
                    "location": seed["location"],
                },
                segment=seed["segment"],
                stage=seed["stage"],
                journey=journey,
                interactions=[],
                behavioral_insights={},
                preferences={"language": "pt-br", "timezone": "America/Sao_Paulo"},
                satisfaction_metrics={"overall_satisfaction": seed["overall_satisfaction"]},
                financial_metrics={
                    "monthly_revenue": seed["monthly_revenue"],
                    "lifetime_value": seed["lifetime_value"],
                },
                engagement_metrics={"feature_adoption_rate": seed["feature_adoption_rate"]},
                risk_indicators={"churn_probability": seed["churn_risk_score"]},
                opportunities=[],
                next_best_actions=self._generate_next_best_actions(seed["stage"]),
                created_at=now,
                last_updated=now,
            )

            self.customers[seed["id"]] = customer
            # Insights preditivos iniciam VAZIOS (sem dado real ainda)
            self.predictive_insights[seed["id"]] = []

        self._generate_segment_profiles()

    def _get_journey_stage_from_customer_stage(self, customer_stage: CustomerStage) -> JourneyStage:
        """Mapear customer stage para journey stage."""
        mapping = {
            CustomerStage.LEAD: JourneyStage.AWARENESS,
            CustomerStage.PROSPECT: JourneyStage.CONSIDERATION,
            CustomerStage.CUSTOMER: JourneyStage.ACTIVE_USE,
            CustomerStage.LOYAL: JourneyStage.EXPANSION,
            CustomerStage.ADVOCATE: JourneyStage.ADVOCACY,
            CustomerStage.CHURNED: JourneyStage.CHURN,
        }
        return mapping.get(customer_stage, JourneyStage.ACTIVE_USE)

    def _predict_next_journey_stage(self, current_stage: JourneyStage) -> JourneyStage | None:
        """Predizer próximo estágio da jornada (determinístico)."""
        progression_map = {
            JourneyStage.AWARENESS: JourneyStage.CONSIDERATION,
            JourneyStage.CONSIDERATION: JourneyStage.DECISION,
            JourneyStage.DECISION: JourneyStage.ONBOARDING,
            JourneyStage.ONBOARDING: JourneyStage.ACTIVE_USE,
            JourneyStage.ACTIVE_USE: JourneyStage.EXPANSION,
            JourneyStage.EXPANSION: JourneyStage.RENEWAL,
            JourneyStage.RENEWAL: JourneyStage.ADVOCACY,
            JourneyStage.ADVOCACY: JourneyStage.EXPANSION,  # Ciclo de renovação
            JourneyStage.CHURN: None,
        }
        return progression_map.get(current_stage)

    def _generate_next_best_actions(self, stage: CustomerStage) -> list[dict[str, Any]]:
        """Próximas melhores ações (playbook fixo por estágio, sem RNG)."""
        actions_map = {
            CustomerStage.LEAD: [
                {
                    "action": "send_welcome_email",
                    "priority": "high",
                    "description": "Enviar email de boas-vindas personalizado",
                },
                {"action": "schedule_demo", "priority": "medium", "description": "Agendar demonstração do produto"},
            ],
            CustomerStage.PROSPECT: [
                {
                    "action": "send_proposal",
                    "priority": "high",
                    "description": "Enviar proposta comercial personalizada",
                },
                {"action": "schedule_call", "priority": "medium", "description": "Agendar call de acompanhamento"},
            ],
            CustomerStage.CUSTOMER: [
                {
                    "action": "check_satisfaction",
                    "priority": "medium",
                    "description": "Verificar nível de satisfação atual",
                },
                {"action": "identify_upsell", "priority": "low", "description": "Identificar oportunidades de upsell"},
            ],
            CustomerStage.LOYAL: [
                {"action": "referral_program", "priority": "high", "description": "Incluir no programa de indicação"},
                {"action": "case_study", "priority": "medium", "description": "Convidar para case study"},
            ],
            CustomerStage.ADVOCATE: [
                {
                    "action": "testimonial_request",
                    "priority": "high",
                    "description": "Solicitar depoimento/testemunhal",
                },
                {"action": "advisory_board", "priority": "medium", "description": "Convidar para advisory board"},
            ],
        }
        return actions_map.get(stage, [])

    def _generate_segment_profiles(self):
        """Gerar perfis de segmentos a partir dos clientes reais em memória (sem RNG)."""
        # Critérios fixos por segmento (regras de negócio, não valores fabricados)
        segments_criteria = {
            CustomerSegment.VIP: {"monthly_revenue_min": 8000},
            CustomerSegment.PREMIUM: {"monthly_revenue_min": 4000},
            CustomerSegment.STANDARD: {"monthly_revenue_min": 2000},
            CustomerSegment.BRONZE: {"monthly_revenue_min": 800},
        }

        for segment, criteria in segments_criteria.items():
            segment_customers = [c for c in self.customers.values() if c.segment == segment]

            avg_ltv = (
                sum(c.financial_metrics.get("lifetime_value", 0.0) for c in segment_customers) / len(segment_customers)
                if segment_customers
                else 0.0
            )
            avg_satisfaction = (
                sum(c.satisfaction_metrics.get("overall_satisfaction", 0.0) for c in segment_customers)
                / len(segment_customers)
                if segment_customers
                else 0.0
            )
            avg_churn = (
                sum(c.risk_indicators.get("churn_probability", 0.0) for c in segment_customers) / len(segment_customers)
                if segment_customers
                else 0.0
            )

            profile = CustomerSegmentProfile(
                segment=segment,
                criteria=criteria,
                customer_count=len(segment_customers),
                avg_lifetime_value=avg_ltv,
                avg_satisfaction=avg_satisfaction,
                churn_rate=avg_churn,
                growth_rate=0.0,
                preferred_channels=["email", "whatsapp", "portal"]
                if segment in [CustomerSegment.VIP, CustomerSegment.PREMIUM]
                else ["whatsapp", "phone"],
                behavior_patterns={},
            )

            self.segments[segment] = profile

    async def get_customer_360(self, customer_id: str) -> Customer360 | None:
        """Obter visão 360° de um cliente."""
        return self.customers.get(customer_id)

    async def get_all_customers(
        self, segment: CustomerSegment | None = None, stage: CustomerStage | None = None
    ) -> list[Customer360]:
        """Obter todos os clientes com filtros opcionais."""
        customers = list(self.customers.values())

        if segment:
            customers = [c for c in customers if c.segment == segment]

        if stage:
            customers = [c for c in customers if c.stage == stage]

        return customers

    async def track_customer_interaction(self, interaction: CustomerInteraction) -> bool:
        """Registrar nova interação com cliente."""
        try:
            self.interactions[interaction.id] = interaction

            # Atualizar customer 360
            if interaction.customer_id in self.customers:
                customer = self.customers[interaction.customer_id]
                customer.interactions.append(interaction)
                customer.last_updated = datetime.now()

                # Atualizar métricas de engagement
                customer.journey.interactions_count += 1

                # Atualizar satisfaction se fornecido
                if interaction.satisfaction_score:
                    current_avg = customer.satisfaction_metrics["overall_satisfaction"]
                    new_avg = (current_avg + interaction.satisfaction_score) / 2
                    customer.satisfaction_metrics["overall_satisfaction"] = new_avg

                logger.info(f"Interação registrada: {interaction.type.value} para cliente {interaction.customer_id}")

                return True

            return False

        except Exception as e:
            logger.error(f"Erro ao registrar interação: {str(e)}")
            return False

    async def update_customer_journey_stage(self, customer_id: str, new_stage: JourneyStage) -> bool:
        """Atualizar estágio da jornada do cliente."""
        if customer_id not in self.customers:
            return False

        customer = self.customers[customer_id]
        old_stage = customer.journey.current_stage

        customer.journey.current_stage = new_stage
        customer.journey.time_in_stage_days = 0  # Reset timer
        customer.journey.next_predicted_stage = self._predict_next_journey_stage(new_stage)
        customer.last_updated = datetime.now()

        logger.info(f"Cliente {customer_id}: {old_stage.value} → {new_stage.value}")
        return True

    async def segment_customers(self) -> dict[CustomerSegment, list[str]]:
        """Realizar segmentação automática de clientes."""
        segmented = {segment: [] for segment in CustomerSegment}

        for customer_id, customer in self.customers.items():
            # Lógica de segmentação baseada em múltiplos fatores
            monthly_revenue = customer.financial_metrics.get("monthly_revenue", 0)
            satisfaction = customer.satisfaction_metrics.get("overall_satisfaction", 0)
            engagement = customer.engagement_metrics.get("feature_adoption_rate", 0)

            # Calcular score composto
            segment_score = monthly_revenue / 1000 * 0.5 + satisfaction * 0.3 + engagement * 10 * 0.2

            # Determinar segmento
            if segment_score >= 15:
                new_segment = CustomerSegment.VIP
            elif segment_score >= 10:
                new_segment = CustomerSegment.PREMIUM
            elif segment_score >= 6:
                new_segment = CustomerSegment.STANDARD
            else:
                new_segment = CustomerSegment.BRONZE

            # Atualizar segmento se mudou
            if customer.segment != new_segment:
                customer.segment = new_segment
                customer.last_updated = datetime.now()
                logger.info(f"Cliente {customer_id} re-segmentado para {new_segment.value}")

            segmented[customer.segment].append(customer_id)

        return segmented

    async def get_predictive_insights(self, customer_id: str | None = None) -> list[PredictiveInsight]:
        """Obter insights preditivos.

        Insights só existem se tiverem sido registrados de fato. Sem dado,
        retorna lista vazia (honesto) — nunca insight fabricado.
        """
        if customer_id:
            return self.predictive_insights.get(customer_id, [])

        # Retornar todos os insights
        all_insights = []
        for insights in self.predictive_insights.values():
            all_insights.extend(insights)

        return sorted(all_insights, key=lambda x: x.impact_score, reverse=True)

    async def generate_customer_health_score(self, customer_id: str) -> float:
        """Gerar score de saúde do cliente."""
        customer = self.customers.get(customer_id)
        if not customer:
            return 0.0

        # Fatores para o health score
        satisfaction_factor = customer.satisfaction_metrics["overall_satisfaction"] / 10
        engagement_factor = customer.engagement_metrics["feature_adoption_rate"]
        financial_factor = min(1.0, customer.financial_metrics["monthly_revenue"] / 5000)
        churn_factor = 1 - customer.journey.churn_risk_score

        # Peso dos fatores
        health_score = (
            satisfaction_factor * 0.3 + engagement_factor * 0.25 + financial_factor * 0.25 + churn_factor * 0.2
        )

        return min(100, health_score * 100)

    async def get_crm_analytics(self) -> CRMAnalytics:
        """Obter analytics completo do CRM (agregado a partir dos dados em memória)."""
        total_customers = len(self.customers)
        active_customers = len([c for c in self.customers.values() if c.stage not in [CustomerStage.CHURNED]])

        # Calcular métricas do mês atual
        current_month = datetime.now().replace(day=1)
        new_customers_month = len([c for c in self.customers.values() if c.created_at >= current_month])

        churned_customers_month = len(
            [c for c in self.customers.values() if c.stage == CustomerStage.CHURNED and c.last_updated >= current_month]
        )

        # Métricas de satisfação e valor
        avg_satisfaction = (
            sum(c.satisfaction_metrics["overall_satisfaction"] for c in self.customers.values()) / total_customers
            if total_customers > 0
            else 0
        )

        avg_ltv = (
            sum(c.financial_metrics["lifetime_value"] for c in self.customers.values()) / total_customers
            if total_customers > 0
            else 0
        )

        # Distribuições
        segment_distribution = {}
        stage_distribution = {}

        for customer in self.customers.values():
            segment_distribution[customer.segment.value] = segment_distribution.get(customer.segment.value, 0) + 1
            stage_distribution[customer.stage.value] = stage_distribution.get(customer.stage.value, 0) + 1

        return CRMAnalytics(
            total_customers=total_customers,
            active_customers=active_customers,
            new_customers_month=new_customers_month,
            churned_customers_month=churned_customers_month,
            avg_customer_satisfaction=avg_satisfaction,
            avg_lifetime_value=avg_ltv,
            customer_acquisition_cost=0.0,
            churn_rate=churned_customers_month / total_customers if total_customers > 0 else 0,
            segment_distribution=segment_distribution,
            stage_distribution=stage_distribution,
            interaction_volume_daily=len(self.interactions) // 30,  # Aproximação
            response_time_avg_hours=0.0,
            conversion_rates={},
        )

    async def get_customer_recommendations(self, customer_id: str) -> list[dict[str, Any]]:
        """Obter recomendações personalizadas para um cliente."""
        customer = self.customers.get(customer_id)
        if not customer:
            return []

        recommendations = []

        # Recomendações baseadas no health score
        health_score = await self.generate_customer_health_score(customer_id)

        if health_score < 70:
            recommendations.append(
                {
                    "type": "health_improvement",
                    "priority": "high",
                    "title": "Melhorar Saúde do Cliente",
                    "description": f"Health score baixo ({health_score:.0f}%). Revisar satisfação e engajamento.",
                    "actions": ["Agendar call de feedback", "Revisar onboarding", "Oferecer treinamento"],
                }
            )

        # Recomendações baseadas no segmento
        if customer.segment in [CustomerSegment.VIP, CustomerSegment.PREMIUM]:
            recommendations.append(
                {
                    "type": "vip_treatment",
                    "priority": "high",
                    "title": "Tratamento VIP",
                    "description": "Cliente premium merece atenção especial.",
                    "actions": ["Account manager dedicado", "Suporte prioritário", "Early access features"],
                }
            )

        # Recomendações baseadas em oportunidades
        for opportunity in customer.opportunities:
            recommendations.append(
                {
                    "type": "opportunity",
                    "priority": "medium",
                    "title": opportunity["title"],
                    "description": opportunity["description"],
                    "actions": [f"Apresentar proposta de {opportunity['type']}", "Agendar reunião comercial"],
                }
            )

        return recommendations

    async def search_customers(self, query: str, filters: dict[str, Any] = None) -> list[Customer360]:
        """Buscar clientes por diversos critérios."""
        results = []
        query_lower = query.lower()
        filters = filters or {}

        for customer in self.customers.values():
            # Busca textual
            if (
                query_lower in customer.basic_info.get("name", "").lower()
                or query_lower in customer.basic_info.get("location", "").lower()
                or query_lower in customer.id.lower()
            ):
                # Aplicar filtros
                if filters.get("segment") and customer.segment != filters["segment"]:
                    continue
                if filters.get("stage") and customer.stage != filters["stage"]:
                    continue
                if (
                    filters.get("min_revenue")
                    and customer.financial_metrics["monthly_revenue"] < filters["min_revenue"]
                ):
                    continue

                results.append(customer)

        return results


# Instância singleton do serviço
crm_360_service = CRM360Service()


if __name__ == "__main__":
    # Teste básico
    async def test_crm_360():
        service = CRM360Service()

        # Obter analytics
        analytics = await service.get_crm_analytics()
        print(f"Total Customers: {analytics.total_customers}")
        print(f"Average Satisfaction: {analytics.avg_customer_satisfaction:.2f}")

        # Obter cliente específico
        customers = await service.get_all_customers()
        if customers:
            customer = customers[0]
            health = await service.generate_customer_health_score(customer.id)
            print(f"Customer {customer.basic_info['name']} Health Score: {health:.1f}%")

    asyncio.run(test_crm_360())
