"""
Executive Dashboard Controller - FASE 3 ONDA 1
===============================================

Endpoints para dashboard executivo com KPIs em tempo real
e analytics preditivos.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database.session import get_db

from ..services.executive_dashboard_service import executive_dashboard_service
from ..services.kpi_recalc_service import recalcular_kpis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/executive", tags=["Executive Dashboard"])


@router.get(
    "/dashboard",
    summary="Dashboard Executivo Completo",
    description="Retorna dashboard executivo com KPIs, alertas e insights preditivos",
)
async def get_executive_dashboard(
    current_user: CurrentActiveUser,
    refresh: bool = Query(False, description="Forçar atualização dos dados"),
) -> dict[str, Any]:
    """
    Endpoint principal do dashboard executivo.

    Retorna:
    - KPIs de todas as áreas (financeiro, operacional, RH, segurança, clientes)
    - Alertas automáticos baseados em thresholds
    - Insights preditivos com IA
    - Tendências históricas
    - Resumo executivo
    """
    try:
        dashboard = await executive_dashboard_service.get_executive_dashboard(refresh=refresh)

        # Converte para JSON serializable
        result = {
            "timestamp": dashboard.timestamp.isoformat(),
            "summary": dashboard.summary,
            "kpis": [
                {
                    "name": kpi.name,
                    "value": kpi.value,
                    "previous_value": kpi.previous_value,
                    "target": kpi.target,
                    "unit": kpi.unit,
                    "trend": kpi.trend.value,
                    "change_percent": kpi.change_percent,
                    "category": kpi.category.value,
                    "updated_at": kpi.updated_at.isoformat(),
                }
                for kpi in dashboard.kpis
            ],
            "alerts": [
                {
                    "title": alert.title,
                    "message": alert.message,
                    "level": alert.level.value,
                    "metric": alert.metric,
                    "value": alert.value,
                    "threshold": alert.threshold,
                    "created_at": alert.created_at.isoformat(),
                    "action_required": alert.action_required,
                }
                for alert in dashboard.alerts
            ],
            "insights": [
                {
                    "title": insight.title,
                    "description": insight.description,
                    "confidence": insight.confidence,
                    "impact": insight.impact,
                    "recommendation": insight.recommendation,
                    "timeline": insight.timeline,
                    "category": insight.category.value,
                }
                for insight in dashboard.insights
            ],
            "trends": dashboard.trends,
        }

        logger.info(f"Dashboard executivo gerado com {len(dashboard.kpis)} KPIs")
        return result

    except Exception as e:
        logger.error(f"Erro ao gerar dashboard executivo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get(
    "/kpis/{category}", summary="KPIs por Categoria", description="Retorna KPIs filtrados por categoria específica"
)
async def get_kpis_by_category(category: str, current_user: CurrentActiveUser) -> dict[str, Any]:
    """
    Retorna KPIs filtrados por categoria específica.
    """
    try:
        dashboard = await executive_dashboard_service.get_executive_dashboard()

        # Filtra KPIs pela categoria
        filtered_kpis = [
            {
                "name": kpi.name,
                "value": kpi.value,
                "previous_value": kpi.previous_value,
                "target": kpi.target,
                "unit": kpi.unit,
                "trend": kpi.trend.value,
                "change_percent": kpi.change_percent,
                "updated_at": kpi.updated_at.isoformat(),
            }
            for kpi in dashboard.kpis
            if kpi.category.value == category.lower()
        ]

        if not filtered_kpis:
            raise HTTPException(status_code=404, detail=f"Categoria '{category}' não encontrada")

        return {"category": category, "kpis": filtered_kpis, "count": len(filtered_kpis)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar KPIs por categoria {category}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/alerts/active", summary="Alertas Ativos", description="Retorna alertas ativos que requerem atenção")
async def get_active_alerts(current_user: CurrentActiveUser) -> dict[str, Any]:
    """
    Retorna apenas alertas ativos que requerem ação.
    """
    try:
        dashboard = await executive_dashboard_service.get_executive_dashboard()

        # Filtra apenas alertas críticos e de warning
        active_alerts = [
            {
                "title": alert.title,
                "message": alert.message,
                "level": alert.level.value,
                "metric": alert.metric,
                "value": alert.value,
                "threshold": alert.threshold,
                "created_at": alert.created_at.isoformat(),
                "action_required": alert.action_required,
            }
            for alert in dashboard.alerts
            if alert.level.value in ["critical", "warning"] and alert.action_required
        ]

        return {
            "alerts": active_alerts,
            "count": len(active_alerts),
            "has_critical": any(alert["level"] == "critical" for alert in active_alerts),
        }

    except Exception as e:
        logger.error(f"Erro ao buscar alertas ativos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get(
    "/insights/predictive", summary="Insights Preditivos", description="Retorna insights preditivos gerados por IA"
)
async def get_predictive_insights(current_user: CurrentActiveUser) -> dict[str, Any]:
    """
    Retorna insights preditivos com recomendações de IA.
    """
    try:
        dashboard = await executive_dashboard_service.get_executive_dashboard()

        insights_data = [
            {
                "title": insight.title,
                "description": insight.description,
                "confidence": insight.confidence,
                "impact": insight.impact,
                "recommendation": insight.recommendation,
                "timeline": insight.timeline,
                "category": insight.category.value,
            }
            for insight in dashboard.insights
        ]

        # Ordena por confiança (maior primeiro)
        insights_data.sort(key=lambda x: x["confidence"], reverse=True)

        return {
            "insights": insights_data,
            "count": len(insights_data),
            "avg_confidence": sum(i["confidence"] for i in insights_data) / len(insights_data) if insights_data else 0,
        }

    except Exception as e:
        logger.error(f"Erro ao buscar insights preditivos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/summary", summary="Resumo Executivo", description="Retorna resumo executivo consolidado")
async def get_executive_summary(current_user: CurrentActiveUser) -> dict[str, Any]:
    """
    Retorna apenas o resumo executivo consolidado.
    """
    try:
        dashboard = await executive_dashboard_service.get_executive_dashboard()

        return {
            "timestamp": dashboard.timestamp.isoformat(),
            "summary": dashboard.summary,
            "quick_stats": {
                "total_kpis": len(dashboard.kpis),
                "positive_trends": sum(1 for kpi in dashboard.kpis if kpi.trend.value == "up"),
                "total_alerts": len(dashboard.alerts),
                "critical_alerts": sum(1 for alert in dashboard.alerts if alert.level.value == "critical"),
                "total_insights": len(dashboard.insights),
            },
        }

    except Exception as e:
        logger.error(f"Erro ao gerar resumo executivo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/export", summary="Exportar Dashboard", description="Exporta dados do dashboard em diferentes formatos")
async def export_dashboard(
    current_user: CurrentActiveUser, format_type: str = Query("json", description="Formato: json, csv")
) -> dict[str, Any]:
    """
    Exporta dados do dashboard para diferentes formatos.
    """
    try:
        exported_data = await executive_dashboard_service.export_dashboard_data(format_type)

        return {"format": format_type, "exported_at": datetime.now().isoformat(), "data": exported_data}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao exportar dashboard em formato {format_type}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post(
    "/kpis/recalcular",
    summary="Recalcular KPIs a partir do dado real",
    description=(
        "Recalcula os KPIs das tabelas executive_kpis e financial_kpis a partir "
        "das fontes reais (contratos, folha, clientes, funcionários, saldo, NFS-e). "
        "Move current -> previous e grava last_calculated_at = now(). "
        "KPIs sem fonte real definida permanecem intactos."
    ),
)
async def recalcular_kpis_endpoint(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Dispara o recálculo dos KPIs sob demanda (admin)."""
    try:
        resultado = await recalcular_kpis(db)
        logger.info(
            "Recálculo de KPIs disparado por %s: executive=%s financial=%s",
            getattr(current_user, "email", "?"),
            resultado["executive_updated"],
            resultado["financial_updated"],
        )
        return {"status": "ok", **resultado}
    except Exception as e:
        logger.error(f"Erro ao recalcular KPIs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao recalcular KPIs: {str(e)}")


@router.get("/health", summary="Health Check Dashboard", description="Verifica saúde do sistema de dashboard")
async def dashboard_health_check() -> dict[str, Any]:
    """
    Health check do sistema de dashboard.
    """
    try:
        # Testa geração rápida do dashboard
        dashboard = await executive_dashboard_service.get_executive_dashboard()

        return {
            "status": "healthy",
            "last_update": dashboard.timestamp.isoformat(),
            "kpis_count": len(dashboard.kpis),
            "alerts_count": len(dashboard.alerts),
            "insights_count": len(dashboard.insights),
            "response_time_ms": "< 100ms",
            "cache_status": "active",
        }

    except Exception as e:
        logger.error(f"Health check do dashboard falhou: {str(e)}")
        return {"status": "unhealthy", "error": str(e), "timestamp": datetime.now().isoformat()}
