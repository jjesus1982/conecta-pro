"""
ServiceAIService - Análises e Recomendações com IA
Sprint 31: Gestão de Serviços
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from modules.services.models import (
    OrderPriority,
    OrderStatus,
    ServiceCatalog,
    ServiceCategory,
    ServiceOrder,
    ServiceStatus,
    SLAConfig,
)
from modules.services.repositories import ServiceRepository
from modules.services.schemas import (
    ServiceAnalysis,
    ServiceCatalogStats,
    ServiceOrderStats,
    ServiceRecommendation,
    SLAAnalysis,
)

logger = logging.getLogger(__name__)


class ServiceAIService:
    """
    Serviço de IA para análises e recomendações.
    Fornece insights e previsões baseados em dados.
    """

    def __init__(self, db: Session):
        """
        Inicializa o serviço.

        Args:
            db: Sessão do banco de dados
        """
        self.db = db
        self.repository = ServiceRepository(db)

    # ============================================================
    # SERVICE ANALYSIS
    # ============================================================

    def analyze_service(self, service_id: UUID) -> ServiceAnalysis | None:
        """
        Analisa performance de um serviço.

        Args:
            service_id: ID do serviço

        Returns:
            ServiceAnalysis ou None
        """
        service = self.repository.get_service_catalog_by_id(service_id)
        if not service:
            return None

        orders = self.repository.list_service_orders(service_id=service_id, limit=1000)

        performance_score = self._calculate_performance_score(service, orders)
        revenue_score = self._calculate_revenue_score(service)
        demand_score = self._calculate_demand_score(orders)
        efficiency_score = self._calculate_efficiency_score(orders)

        trends = self._analyze_trends(orders)
        insights = self._generate_insights(service, orders, performance_score, demand_score)
        recommendations = self._generate_service_recommendations(
            service, performance_score, revenue_score, demand_score
        )

        return ServiceAnalysis(
            service_id=service_id,
            service_name=service.name,
            performance_score=performance_score,
            revenue_score=revenue_score,
            demand_score=demand_score,
            efficiency_score=efficiency_score,
            trends=trends,
            insights=insights,
            recommendations=recommendations,
        )

    def analyze_all_services(self) -> list[ServiceAnalysis]:
        """Analisa todos os serviços ativos."""
        services = self.repository.list_service_catalogs(status=ServiceStatus.ATIVO, limit=500)

        analyses = []
        for service in services:
            analysis = self.analyze_service(service.id)
            if analysis:
                analyses.append(analysis)

        return sorted(analyses, key=lambda x: x.performance_score, reverse=True)

    def get_service_recommendations(
        self, client_id: UUID | None = None, category: ServiceCategory | None = None, limit: int = 10
    ) -> list[ServiceRecommendation]:
        """
        Gera recomendações de serviços.

        Args:
            client_id: ID do cliente (para personalização)
            category: Categoria desejada
            limit: Limite de recomendações

        Returns:
            Lista de recomendações
        """
        filters = {"status": ServiceStatus.ATIVO, "is_available": True, "limit": 100}

        if category:
            filters["category"] = category

        services = self.repository.list_service_catalogs(**filters)

        if client_id:
            client_orders = self.repository.list_service_orders(
                client_id=client_id, status=OrderStatus.CONCLUIDA, limit=50
            )
            recommendations = self._personalize_recommendations(services, client_orders)
        else:
            recommendations = self._rank_services(services)

        return recommendations[:limit]

    def predict_service_demand(self, service_id: UUID, days_ahead: int = 30) -> dict[str, Any]:
        """
        Prevê demanda para um serviço.

        Args:
            service_id: ID do serviço
            days_ahead: Dias à frente para previsão

        Returns:
            Dict com previsão de demanda
        """
        service = self.repository.get_service_catalog_by_id(service_id)
        if not service:
            return {}

        orders = self.repository.list_service_orders(service_id=service_id, limit=500)

        historical = self._analyze_historical_demand(orders)
        prediction = self._project_demand(historical, days_ahead)
        confidence = self._calculate_confidence(historical)

        return {
            "service_id": str(service_id),
            "service_name": service.name,
            "prediction_period_days": days_ahead,
            "historical_data": historical,
            "predicted_demand": prediction,
            "confidence_score": confidence,
            "factors": self._identify_demand_factors(orders),
            "generated_at": datetime.utcnow().isoformat(),
        }

    # ============================================================
    # SLA ANALYSIS
    # ============================================================

    def analyze_sla(self, sla_id: UUID) -> SLAAnalysis | None:
        """
        Analisa compliance de um SLA.

        Args:
            sla_id: ID do SLA

        Returns:
            SLAAnalysis ou None
        """
        sla = self.repository.get_sla_config_by_id(sla_id)
        if not sla:
            return None

        compliance_percent = float(sla.current_compliance_percent or 0)
        trend = self._analyze_sla_trend(sla)
        at_risk = self._count_at_risk_orders(sla)
        forecast = self._forecast_breaches(sla)
        recommendations = self._generate_sla_recommendations(sla)

        return SLAAnalysis(
            sla_id=sla_id,
            sla_name=sla.name,
            compliance_percent=compliance_percent,
            trend=trend,
            at_risk_orders=at_risk,
            breach_forecast=forecast,
            recommendations=recommendations,
        )

    def get_sla_dashboard(self) -> dict[str, Any]:
        """
        Retorna dashboard de SLAs.

        Returns:
            Dict com visão geral de SLAs
        """
        slas = self.repository.list_sla_configs(is_active=True, limit=100)

        total_compliance = 0.0
        critical_count = 0
        warning_count = 0
        healthy_count = 0

        sla_summaries = []

        for sla in slas:
            compliance = float(sla.current_compliance_percent or 0)
            status = sla.compliance_status

            if status == "critico":
                critical_count += 1
            elif status == "atencao":
                warning_count += 1
            else:
                healthy_count += 1

            if sla.total_orders > 0:
                total_compliance += compliance

            sla_summaries.append(
                {
                    "id": str(sla.id),
                    "name": sla.name,
                    "compliance": compliance,
                    "status": status,
                    "total_orders": sla.total_orders,
                    "breached": sla.orders_breached,
                }
            )

        avg_compliance = total_compliance / len(slas) if slas else 0.0

        return {
            "summary": {
                "total_slas": len(slas),
                "average_compliance": round(avg_compliance, 2),
                "critical": critical_count,
                "warning": warning_count,
                "healthy": healthy_count,
            },
            "slas": sorted(sla_summaries, key=lambda x: x["compliance"]),
            "generated_at": datetime.utcnow().isoformat(),
        }

    # ============================================================
    # ORDER ANALYSIS
    # ============================================================

    def analyze_order_patterns(self, days: int = 30) -> dict[str, Any]:
        """
        Analisa padrões de ordens de serviço.

        Args:
            days: Período de análise

        Returns:
            Dict com análise de padrões
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        orders = self.repository.list_service_orders(limit=1000)
        recent_orders = [o for o in orders if o.created_at >= start_date]

        by_day = self._group_by_day(recent_orders)
        by_category = self._group_by_category(recent_orders)
        by_priority = self._group_by_priority(recent_orders)
        by_status = self._group_by_status(recent_orders)

        peak_hours = self._identify_peak_hours(recent_orders)
        avg_duration = self._calculate_avg_duration(recent_orders)
        completion_rate = self._calculate_completion_rate(recent_orders)

        return {
            "period_days": days,
            "total_orders": len(recent_orders),
            "patterns": {
                "by_day": by_day,
                "by_category": by_category,
                "by_priority": by_priority,
                "by_status": by_status,
                "peak_hours": peak_hours,
            },
            "metrics": {
                "avg_duration_hours": avg_duration,
                "completion_rate": completion_rate,
                "orders_per_day": (len(recent_orders) / days if days > 0 else 0),
            },
            "generated_at": datetime.utcnow().isoformat(),
        }

    def identify_bottlenecks(self) -> list[dict[str, Any]]:
        """
        Identifica gargalos no processo.

        Returns:
            Lista de gargalos identificados
        """
        bottlenecks = []

        pending_orders = self.repository.list_service_orders(status=OrderStatus.PENDENTE, limit=500)
        if len(pending_orders) > 20:
            bottlenecks.append(
                {
                    "type": "queue",
                    "severity": "high" if len(pending_orders) > 50 else "medium",
                    "description": f"{len(pending_orders)} ordens pendentes",
                    "recommendation": "Aumentar capacidade de atendimento",
                }
            )

        in_progress = self.repository.list_service_orders(status=OrderStatus.EM_ANDAMENTO, limit=500)
        overdue = [o for o in in_progress if o.is_overdue]
        if overdue:
            bottlenecks.append(
                {
                    "type": "overdue",
                    "severity": "critical",
                    "description": f"{len(overdue)} ordens em atraso",
                    "recommendation": "Priorizar resolução de atrasos",
                }
            )

        paused = self.repository.list_service_orders(status=OrderStatus.PAUSADA, limit=100)
        if len(paused) > 5:
            bottlenecks.append(
                {
                    "type": "blocked",
                    "severity": "medium",
                    "description": f"{len(paused)} ordens pausadas",
                    "recommendation": "Investigar motivos de bloqueio",
                }
            )

        slas = self.repository.list_sla_configs(is_active=True, limit=100)
        critical_slas = [s for s in slas if s.compliance_status == "critico"]
        if critical_slas:
            bottlenecks.append(
                {
                    "type": "sla",
                    "severity": "critical",
                    "description": f"{len(critical_slas)} SLAs em estado crítico",
                    "recommendation": "Revisar processos e capacidade",
                }
            )

        return sorted(bottlenecks, key=lambda x: {"critical": 0, "high": 1, "medium": 2}.get(x["severity"], 3))

    # ============================================================
    # STATISTICS
    # ============================================================

    def get_service_catalog_stats(self) -> ServiceCatalogStats:
        """Retorna estatísticas do catálogo."""
        return self.repository.get_service_catalog_stats()

    def get_order_stats(self, client_id: UUID | None = None, service_id: UUID | None = None) -> ServiceOrderStats:
        """
        Retorna estatísticas de ordens.

        Args:
            client_id: Filtro por cliente
            service_id: Filtro por serviço

        Returns:
            ServiceOrderStats
        """
        return self.repository.get_order_stats(client_id=client_id)

    def get_executive_dashboard(self) -> dict[str, Any]:
        """
        Retorna dashboard executivo.

        Returns:
            Dict com métricas executivas
        """
        catalog_stats = self.get_service_catalog_stats()
        order_stats = self.get_order_stats()
        sla_dashboard = self.get_sla_dashboard()
        bottlenecks = self.identify_bottlenecks()

        return {
            "services": {
                "total": catalog_stats.total_services,
                "active": catalog_stats.active_services,
                "total_revenue": float(catalog_stats.total_revenue),
                "avg_rating": catalog_stats.avg_rating,
            },
            "orders": {
                "total": order_stats.total_orders,
                "by_status": order_stats.by_status,
                "overdue": order_stats.overdue_count,
                "avg_completion_hours": order_stats.avg_completion_time_hours,
                "avg_rating": order_stats.avg_rating,
                "sla_compliance": order_stats.sla_compliance_percent,
            },
            "sla": sla_dashboard["summary"],
            "bottlenecks": bottlenecks[:5],
            "generated_at": datetime.utcnow().isoformat(),
        }

    # ============================================================
    # PRIVATE HELPER METHODS
    # ============================================================

    def _calculate_performance_score(self, service: ServiceCatalog, orders: list[ServiceOrder]) -> float:
        """Calcula score de performance."""
        # Use service completion rate as baseline if no orders
        if not orders:
            return service.completion_rate if service.completion_rate else 50.0

        completed = [o for o in orders if o.status == OrderStatus.CONCLUIDA]
        if not completed:
            return 50.0

        completion_rate = len(completed) / len(orders)
        sla_met = sum(1 for o in completed if o.sla_resolution_met)
        sla_rate = sla_met / len(completed) if completed else 0

        ratings = [o.rating for o in completed if o.rating]
        avg_rating = sum(ratings) / len(ratings) if ratings else 3.0

        score = completion_rate * 30 + sla_rate * 40 + (avg_rating / 5) * 30

        return min(100.0, max(0.0, score))

    def _calculate_revenue_score(self, service: ServiceCatalog) -> float:
        """Calcula score de receita."""
        if not service.total_revenue:
            return 0.0

        revenue = float(service.total_revenue)

        if revenue >= 100000:
            return 100.0
        elif revenue >= 50000:
            return 80.0
        elif revenue >= 10000:
            return 60.0
        elif revenue >= 1000:
            return 40.0
        return 20.0

    def _calculate_demand_score(self, orders: list[ServiceOrder]) -> float:
        """Calcula score de demanda."""
        if not orders:
            return 0.0

        recent = datetime.utcnow() - timedelta(days=30)
        recent_orders = [o for o in orders if o.created_at >= recent]

        if len(recent_orders) >= 50:
            return 100.0
        elif len(recent_orders) >= 20:
            return 80.0
        elif len(recent_orders) >= 10:
            return 60.0
        elif len(recent_orders) >= 5:
            return 40.0
        return 20.0

    def _calculate_efficiency_score(self, orders: list[ServiceOrder]) -> float:
        """Calcula score de eficiência."""
        completed = [o for o in orders if o.status == OrderStatus.CONCLUIDA and o.actual_duration_hours]

        if not completed:
            return 50.0

        durations = [float(o.actual_duration_hours) for o in completed]
        avg_duration = sum(durations) / len(durations)

        if avg_duration <= 2:
            return 100.0
        elif avg_duration <= 4:
            return 80.0
        elif avg_duration <= 8:
            return 60.0
        elif avg_duration <= 24:
            return 40.0
        return 20.0

    def _analyze_trends(self, orders: list[ServiceOrder]) -> dict[str, Any]:
        """Analisa tendências."""
        if not orders:
            return {"trend": "stable", "growth": 0}

        now = datetime.utcnow()
        last_30 = [o for o in orders if o.created_at >= now - timedelta(days=30)]
        prev_30 = [o for o in orders if now - timedelta(days=60) <= o.created_at < now - timedelta(days=30)]

        if not prev_30:
            growth = 100 if last_30 else 0
        else:
            growth = ((len(last_30) - len(prev_30)) / len(prev_30)) * 100

        if growth > 10:
            trend = "growing"
        elif growth < -10:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "growth_percent": round(growth, 2),
            "last_30_days": len(last_30),
            "previous_30_days": len(prev_30),
        }

    def _generate_insights(
        self, service: ServiceCatalog, orders: list[ServiceOrder], performance: float, demand: float
    ) -> list[str]:
        """Gera insights sobre o serviço."""
        insights = []

        if performance >= 80:
            insights.append(f"Serviço '{service.name}' tem excelente performance")
        elif performance < 50:
            insights.append(f"Serviço '{service.name}' precisa de atenção na performance")

        if demand >= 80:
            insights.append("Alta demanda nos últimos 30 dias")
        elif demand < 30:
            insights.append("Baixa demanda recente - avaliar promoções")

        if service.avg_rating and float(service.avg_rating) >= 4.5:
            insights.append("Alta satisfação dos clientes")
        elif service.avg_rating and float(service.avg_rating) < 3.0:
            insights.append("Satisfação do cliente abaixo da média")

        # Analyze order patterns
        if orders:
            overdue = [o for o in orders if o.is_overdue]
            if overdue:
                insights.append(f"{len(overdue)} ordens em atraso identificadas")

        return insights

    def _generate_service_recommendations(
        self, service: ServiceCatalog, performance: float, revenue: float, demand: float
    ) -> list[str]:
        """Gera recomendações para o serviço."""
        recommendations = []

        if performance < 50:
            recommendations.append("Revisar processos de execução do serviço")

        if demand < 30:
            recommendations.append("Considerar campanhas de marketing ou promoções")

        if revenue < 30 and demand >= 50:
            recommendations.append("Avaliar precificação - demanda alta mas receita baixa")

        if service.completion_rate and service.completion_rate < 80:
            recommendations.append("Investigar causas de cancelamento de ordens")

        return recommendations

    def _personalize_recommendations(
        self, services: list[ServiceCatalog], client_orders: list[ServiceOrder]
    ) -> list[ServiceRecommendation]:
        """Personaliza recomendações para cliente."""
        used_services = {o.service_id for o in client_orders}
        categories_used = set()

        for order in client_orders:
            service = self.repository.get_service_catalog_by_id(order.service_id)
            if service:
                categories_used.add(service.category)

        recommendations = []

        for service in services:
            if service.id in used_services:
                continue

            confidence = 0.5

            if service.category in categories_used:
                confidence += 0.3

            if service.avg_rating and float(service.avg_rating) >= 4.0:
                confidence += 0.1

            if service.total_orders >= 10:
                confidence += 0.1

            reason = self._determine_recommendation_reason(service, categories_used, used_services)

            recommendations.append(
                ServiceRecommendation(
                    service_id=service.id,
                    service_name=service.name,
                    recommendation_type="personalized",
                    confidence=min(1.0, confidence),
                    reason=reason,
                    potential_impact="Baseado no histórico do cliente",
                    priority="normal",
                )
            )

        return sorted(recommendations, key=lambda x: x.confidence, reverse=True)

    def _rank_services(self, services: list[ServiceCatalog]) -> list[ServiceRecommendation]:
        """Rankeia serviços para recomendação geral."""
        recommendations = []

        for service in services:
            confidence = 0.5

            if service.avg_rating:
                confidence += float(service.avg_rating) / 10

            if service.total_orders >= 50:
                confidence += 0.2
            elif service.total_orders >= 10:
                confidence += 0.1

            recommendations.append(
                ServiceRecommendation(
                    service_id=service.id,
                    service_name=service.name,
                    recommendation_type="popular",
                    confidence=min(1.0, confidence),
                    reason=f"Serviço bem avaliado com {service.total_orders} ordens",
                    potential_impact=None,
                    priority="normal",
                )
            )

        return sorted(recommendations, key=lambda x: x.confidence, reverse=True)

    def _determine_recommendation_reason(
        self, service: ServiceCatalog, categories_used: set, used_services: set
    ) -> str:
        """Determina razão da recomendação."""
        if service.category in categories_used:
            return "Similar aos serviços que você já utilizou"
        if service.id in used_services:
            return "Complemento a serviços anteriormente contratados"
        if service.avg_rating and float(service.avg_rating) >= 4.5:
            return "Altamente recomendado por outros clientes"
        return "Serviço popular em sua região"

    def _analyze_historical_demand(self, orders: list[ServiceOrder]) -> dict[str, Any]:
        """Analisa demanda histórica."""
        if not orders:
            return {"monthly_avg": 0, "trend": "unknown"}

        by_month: dict[str, int] = {}
        for order in orders:
            key = order.created_at.strftime("%Y-%m")
            by_month[key] = by_month.get(key, 0) + 1

        monthly_avg = sum(by_month.values()) / len(by_month) if by_month else 0

        return {"monthly_avg": round(monthly_avg, 2), "monthly_data": by_month, "total_orders": len(orders)}

    def _project_demand(self, historical: dict[str, Any], days: int) -> dict[str, Any]:
        """Projeta demanda futura."""
        monthly_avg = historical.get("monthly_avg", 0)
        daily_avg = monthly_avg / 30

        return {"expected_orders": round(daily_avg * days), "daily_average": round(daily_avg, 2), "period_days": days}

    def _calculate_confidence(self, historical: dict[str, Any]) -> float:
        """Calcula confiança da previsão."""
        total = historical.get("total_orders", 0)

        if total >= 100:
            return 0.9
        elif total >= 50:
            return 0.7
        elif total >= 20:
            return 0.5
        return 0.3

    def _identify_demand_factors(self, orders: list[ServiceOrder]) -> list[str]:
        """Identifica fatores de demanda."""
        factors = []

        if not orders:
            return factors

        priorities = [o.priority for o in orders if o.priority]
        urgents = [p for p in priorities if p in [OrderPriority.URGENTE, OrderPriority.CRITICA]]
        if len(urgents) > len(priorities) * 0.3:
            factors.append("Alta taxa de urgência")

        return factors

    def _analyze_sla_trend(self, sla: SLAConfig) -> str:
        """Analisa tendência do SLA."""
        if sla.total_orders < 10:
            return "insufficient_data"

        compliance = float(sla.current_compliance_percent or 0)
        target = float(sla.target_availability_percent or 99)

        if compliance >= target:
            return "improving"
        elif compliance >= target * 0.95:
            return "stable"
        return "declining"

    def _count_at_risk_orders(self, sla: SLAConfig) -> int:
        """Conta ordens em risco."""
        if not sla.service_id:
            return 0

        orders = self.repository.list_service_orders(
            service_id=sla.service_id, status=OrderStatus.EM_ANDAMENTO, limit=100
        )

        at_risk = 0
        now = datetime.utcnow()

        for order in orders:
            if order.started_at and sla.resolution_time_minutes:
                deadline = sla.calculate_deadline(order.started_at)
                remaining = (deadline - now).total_seconds() / 60
                if 0 < remaining < 60:
                    at_risk += 1

        return at_risk

    def _forecast_breaches(self, sla: SLAConfig) -> dict[str, Any]:
        """Prevê descumprimentos futuros."""
        breach_rate = sla.breach_rate / 100 if sla.breach_rate else 0

        return {
            "next_week_expected": round(breach_rate * 7, 1),
            "next_month_expected": round(breach_rate * 30, 1),
            "risk_level": ("high" if breach_rate > 0.1 else "medium" if breach_rate > 0.05 else "low"),
        }

    def _generate_sla_recommendations(self, sla: SLAConfig) -> list[str]:
        """Gera recomendações para SLA."""
        recommendations = []

        if sla.compliance_status == "critico":
            recommendations.append("Ação imediata necessária para compliance")

        if sla.breach_rate > 10:
            recommendations.append("Revisar tempos de resolução ou aumentar capacidade")

        if not sla.escalation_enabled:
            recommendations.append("Considerar habilitar escalonamento automático")

        return recommendations

    def _group_by_day(self, orders: list[ServiceOrder]) -> dict[str, int]:
        """Agrupa ordens por dia da semana."""
        days = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
        result = dict.fromkeys(days.values(), 0)

        for order in orders:
            day_name = days[order.created_at.weekday()]
            result[day_name] += 1

        return result

    def _group_by_category(self, orders: list[ServiceOrder]) -> dict[str, int]:
        """Agrupa ordens por categoria."""
        result: dict[str, int] = {}

        for order in orders:
            service = self.repository.get_service_catalog_by_id(order.service_id)
            if service:
                cat = service.category.value
                result[cat] = result.get(cat, 0) + 1

        return result

    def _group_by_priority(self, orders: list[ServiceOrder]) -> dict[str, int]:
        """Agrupa ordens por prioridade."""
        result: dict[str, int] = {}

        for order in orders:
            priority = order.priority.value if order.priority else "normal"
            result[priority] = result.get(priority, 0) + 1

        return result

    def _group_by_status(self, orders: list[ServiceOrder]) -> dict[str, int]:
        """Agrupa ordens por status."""
        result: dict[str, int] = {}

        for order in orders:
            status = order.status.value if order.status else "unknown"
            result[status] = result.get(status, 0) + 1

        return result

    def _identify_peak_hours(self, orders: list[ServiceOrder]) -> list[int]:
        """Identifica horários de pico."""
        hour_counts: dict[int, int] = {}

        for order in orders:
            hour = order.created_at.hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1

        if not hour_counts:
            return []

        avg = sum(hour_counts.values()) / len(hour_counts)
        peaks = [h for h, c in hour_counts.items() if c > avg * 1.5]

        return sorted(peaks)

    def _calculate_avg_duration(self, orders: list[ServiceOrder]) -> float:
        """Calcula duração média."""
        completed = [o for o in orders if o.status == OrderStatus.CONCLUIDA and o.actual_duration_hours]

        if not completed:
            return 0.0

        total = sum(float(o.actual_duration_hours) for o in completed)
        return round(total / len(completed), 2)

    def _calculate_completion_rate(self, orders: list[ServiceOrder]) -> float:
        """Calcula taxa de conclusão."""
        if not orders:
            return 0.0

        completed = [o for o in orders if o.status == OrderStatus.CONCLUIDA]
        return round((len(completed) / len(orders)) * 100, 2)
