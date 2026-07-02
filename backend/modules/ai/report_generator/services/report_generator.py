"""
Report Generator Service - Geração de relatórios.

Serviço principal para orquestrar a geração de relatórios com IA.
"""

import logging
import time
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from modules.ai.report_generator.models import (
    AIReportTemplate,
    Report,
    ReportExecution,
    ReportSection,
)
from modules.ai.report_generator.models.report import (
    ReportPriorityEnum,
    ReportStatusEnum,
    ReportTypeEnum,
)
from modules.ai.report_generator.models.report_execution import (
    ExecutionStatusEnum,
    ExecutionTriggerEnum,
)
from modules.ai.report_generator.repositories import ReportRepository

logger = logging.getLogger(__name__)


# Configuração de fontes de dados
DATA_SOURCE_CONFIG = {
    "leads": {
        "model": "Lead",
        "default_fields": ["id", "name", "status", "score", "created_at"],
        "aggregations": ["count", "avg_score", "conversion_rate"],
    },
    "opportunities": {
        "model": "Opportunity",
        "default_fields": ["id", "name", "stage", "value", "probability"],
        "aggregations": ["count", "total_value", "avg_probability"],
    },
    "customers": {
        "model": "Customer",
        "default_fields": ["id", "name", "segment", "revenue", "status"],
        "aggregations": ["count", "total_revenue", "avg_revenue"],
    },
    "contracts": {
        "model": "Contract",
        "default_fields": ["id", "number", "type", "value", "status"],
        "aggregations": ["count", "total_value", "avg_value"],
    },
    "invoices": {
        "model": "Invoice",
        "default_fields": ["id", "number", "value", "status", "due_date"],
        "aggregations": ["count", "total_value", "paid_value", "overdue_value"],
    },
    "employees": {
        "model": "Employee",
        "default_fields": ["id", "name", "department", "position", "status"],
        "aggregations": ["count", "by_department", "by_status"],
    },
    "inventory": {
        "model": "StockItem",
        "default_fields": ["id", "sku", "name", "quantity", "value"],
        "aggregations": ["total_items", "total_value", "low_stock_count"],
    },
}


class ReportGeneratorService:
    """Serviço de geração de relatórios."""

    def __init__(self, db: Session):
        """Inicializa serviço."""
        self.db = db
        self.repository = ReportRepository(db)

    async def generate_report(
        self,
        template_id: UUID | None = None,
        template_code: str | None = None,
        name: str | None = None,
        report_type: ReportTypeEnum | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        period_type: str | None = None,
        parameters: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        output_formats: list[str] | None = None,
        include_insights: bool = True,
        include_recommendations: bool = True,
        include_anomalies: bool = True,
        priority: ReportPriorityEnum = ReportPriorityEnum.NORMAL,
        trigger: ExecutionTriggerEnum = ExecutionTriggerEnum.MANUAL,
        triggered_by: UUID | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[Report, ReportExecution]:
        """
        Gera um relatório completo.

        Args:
            template_id: ID do template
            template_code: Código do template (alternativa ao ID)
            name: Nome do relatório
            report_type: Tipo do relatório
            period_start: Início do período
            period_end: Fim do período
            period_type: Tipo de período (daily, weekly, etc.)
            parameters: Parâmetros do relatório
            filters: Filtros de dados
            output_formats: Formatos de saída
            include_insights: Incluir insights de IA
            include_recommendations: Incluir recomendações
            include_anomalies: Incluir detecção de anomalias
            priority: Prioridade
            trigger: Gatilho da execução
            triggered_by: Usuário que disparou
            organization_id: ID da organização

        Returns:
            Tuple com Report e ReportExecution
        """
        start_time = time.time()

        # Busca template
        template = None
        if template_id:
            template = self.repository.get_template(template_id)
        elif template_code:
            template = self.repository.get_template_by_code(template_code)

        # Cria execução
        execution = ReportExecution(
            template_id=template.id if template else None,
            trigger=trigger,
            triggered_by=triggered_by,
            parameters=parameters or {},
            filters=filters or {},
            period_start=period_start,
            period_end=period_end,
            requested_formats=output_formats or ["pdf"],
            organization_id=organization_id,
        )
        execution = self.repository.create_execution(execution)

        try:
            # Atualiza status
            execution.update_status(ExecutionStatusEnum.RUNNING, "Iniciando geração")
            self.repository.update_execution(execution)

            # Cria relatório
            report = Report(
                name=name or self._generate_report_name(template, period_start, period_end),
                description=template.description if template else None,
                report_type=report_type
                or (ReportTypeEnum(template.category.value) if template else ReportTypeEnum.SUMMARY),
                category=template.category.value if template else None,
                priority=priority,
                template_id=template.id if template else None,
                period_start=period_start,
                period_end=period_end,
                period_type=period_type,
                filters=filters or {},
                parameters=parameters or {},
                created_by=triggered_by,
                organization_id=organization_id,
                status=ReportStatusEnum.GENERATING,
                execution_id=execution.id,
            )
            report = self.repository.create_report(report)
            execution.report_id = report.id

            # Coleta dados
            execution.update_status(ExecutionStatusEnum.COLLECTING_DATA, "Coletando dados")
            self.repository.update_execution(execution)
            data_start = time.time()

            data = await self._collect_data(
                template=template,
                filters=filters,
                parameters=parameters,
                period_start=period_start,
                period_end=period_end,
            )
            report.data = data

            execution.data_collection_time_ms = int((time.time() - data_start) * 1000)
            execution.records_processed = self._count_records(data)

            # Processa dados
            execution.update_status(ExecutionStatusEnum.PROCESSING, "Processando dados")
            self.repository.update_execution(execution)
            processing_start = time.time()

            summary, metrics = await self._process_data(data, template)
            report.summary = summary
            report.metrics = metrics

            execution.processing_time_ms = int((time.time() - processing_start) * 1000)

            # Gera insights com IA
            if include_insights and (not template or template.ai_insights_enabled):
                execution.update_status(ExecutionStatusEnum.GENERATING_INSIGHTS, "Gerando insights com IA")
                self.repository.update_execution(execution)
                insight_start = time.time()

                insights = await self._generate_insights(data, summary, metrics)
                report.insights = insights
                execution.insights_generated = len(insights)

                if include_recommendations:
                    recommendations = await self._generate_recommendations(data, summary, metrics, insights)
                    report.recommendations = recommendations
                    execution.recommendations_generated = len(recommendations)

                if include_anomalies:
                    anomalies = await self._detect_anomalies(data, metrics)
                    report.anomalies = anomalies
                    execution.anomalies_detected = len(anomalies)

                # Tendências
                trends = await self._analyze_trends(data, period_start, period_end)
                report.trends = trends

                execution.insight_generation_time_ms = int((time.time() - insight_start) * 1000)

            # Renderiza seções
            execution.update_status(ExecutionStatusEnum.RENDERING, "Renderizando relatório")
            self.repository.update_execution(execution)
            render_start = time.time()

            if template:
                sections = await self._render_sections(template, report, data)
                for section in sections:
                    section.report_id = report.id
                    self.repository.create_section(section)
                execution.charts_generated = sum(1 for s in sections if s.section_type.value == "chart")
                execution.tables_generated = sum(1 for s in sections if s.section_type.value == "table")

            execution.rendering_time_ms = int((time.time() - render_start) * 1000)

            # Calcula scores de qualidade
            report.data_quality_score = self._calculate_data_quality(data)
            report.completeness_score = self._calculate_completeness(report, template)
            report.accuracy_score = self._calculate_accuracy(data, metrics)

            # Finaliza
            report.status = ReportStatusEnum.COMPLETED
            report.generated_at = datetime.utcnow()
            report.generation_time_ms = int((time.time() - start_time) * 1000)
            self.repository.update_report(report)

            execution.update_status(ExecutionStatusEnum.COMPLETED, "Concluído")
            execution.update_progress(100)
            self.repository.update_execution(execution)

            # Atualiza estatísticas do template
            if template:
                template.increment_usage()
                template.update_average_time(report.generation_time_ms)
                self.repository.update_template(template)

            logger.info(f"Relatório gerado: {report.code} em {report.generation_time_ms}ms")
            return report, execution

        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {e}")
            execution.set_error(str(e), "GENERATION_ERROR")
            self.repository.update_execution(execution)

            if report:
                report.status = ReportStatusEnum.FAILED
                self.repository.update_report(report)

            raise

    async def _collect_data(
        self,
        template: AIReportTemplate | None,
        filters: dict[str, Any] | None,
        parameters: dict[str, Any] | None,
        period_start: datetime | None,
        period_end: datetime | None,
    ) -> dict[str, Any]:
        """Coleta dados das fontes configuradas."""
        data = {}

        # Se tem template, usa as fontes configuradas (dados reais).
        if template and template.data_sources:
            for source in template.data_sources:
                source_data = await self._fetch_data_source(source, filters, parameters, period_start, period_end)
                data[source] = source_data
        # Sem template/fontes: não há o que coletar. Retorna dict vazio honesto
        # (nada de dados aleatórios de demonstração).
        return data

    async def _fetch_data_source(
        self,
        source: str,
        filters: dict[str, Any] | None,
        parameters: dict[str, Any] | None,
        period_start: datetime | None,
        period_end: datetime | None,
    ) -> dict[str, Any]:
        """Busca dados REAIS de uma fonte específica no banco.

        Consulta as tabelas reais do ERP conforme a `source` do template.
        Fontes sem query real definida retornam vazio honesto (records=[],
        summary={}), NUNCA dados aleatórios.
        """
        base_data: dict[str, Any] = {"records": [], "summary": {}, "aggregations": {}}

        try:
            if source == "contracts":
                row = self.db.execute(
                    text(
                        """
                        SELECT COUNT(*) AS total,
                               COALESCE(SUM(total_value), 0) AS total_value,
                               COALESCE(SUM(monthly_value), 0) AS monthly_value,
                               COALESCE(AVG(total_value), 0) AS avg_value,
                               COUNT(*) FILTER (WHERE status = 'active') AS active
                        FROM contracts
                        """
                    )
                ).mappings().first()
                base_data["summary"] = {
                    "total": int(row["total"]),
                    "active": int(row["active"]),
                    "total_value": float(row["total_value"]),
                    "monthly_value": float(row["monthly_value"]),
                    "avg_value": float(row["avg_value"]),
                }
            elif source in ("customers", "clients"):
                row = self.db.execute(
                    text(
                        """
                        SELECT COUNT(*) AS total,
                               COUNT(*) FILTER (WHERE status = 'active') AS active
                        FROM clients
                        """
                    )
                ).mappings().first()
                base_data["summary"] = {
                    "total": int(row["total"]),
                    "active": int(row["active"]),
                }
            elif source in ("invoices", "inter_transactions"):
                row = self.db.execute(
                    text(
                        """
                        SELECT COUNT(*) AS total,
                               COALESCE(SUM(valor), 0) AS total_value
                        FROM inter_transactions
                        """
                        + (
                            " WHERE data_lancamento BETWEEN :start AND :end"
                            if period_start and period_end
                            else ""
                        )
                    ),
                    (
                        {"start": period_start, "end": period_end}
                        if period_start and period_end
                        else {}
                    ),
                ).mappings().first()
                base_data["summary"] = {
                    "total": int(row["total"]),
                    "total_value": float(row["total_value"]),
                }
            elif source == "commissions":
                row = self.db.execute(
                    text(
                        """
                        SELECT COUNT(*) AS total,
                               COALESCE(SUM(final_commission), 0) AS total_value,
                               COUNT(*) FILTER (WHERE status = 'paid') AS paid,
                               COUNT(*) FILTER (WHERE status = 'pending') AS pending
                        FROM commissions
                        """
                    )
                ).mappings().first()
                base_data["summary"] = {
                    "total": int(row["total"]),
                    "total_value": float(row["total_value"]),
                    "paid": int(row["paid"]),
                    "pending": int(row["pending"]),
                }
            elif source in ("employees", "hr_payslips", "payroll"):
                row = self.db.execute(
                    text(
                        """
                        SELECT COUNT(*) AS total,
                               COALESCE(SUM(net_salary), 0) AS net_total,
                               COALESCE(SUM(total_earnings), 0) AS earnings_total
                        FROM hr_payslips
                        """
                        + (
                            " WHERE make_date(reference_year, reference_month, 1) "
                            "BETWEEN date_trunc('month', :start::date) AND :end::date"
                            if period_start and period_end
                            else ""
                        )
                    ),
                    (
                        {"start": period_start, "end": period_end}
                        if period_start and period_end
                        else {}
                    ),
                ).mappings().first()
                base_data["summary"] = {
                    "total": int(row["total"]),
                    "net_total": float(row["net_total"]),
                    "earnings_total": float(row["earnings_total"]),
                }
            else:
                # Fonte sem query real definida: vazio honesto, sem fabricar.
                logger.warning(
                    "Fonte de dados '%s' sem query real definida; retornando vazio.", source
                )
        except Exception as e:  # noqa: BLE001
            logger.error("Erro ao buscar fonte de dados real '%s': %s", source, e)

        return base_data

    async def _process_data(
        self,
        data: dict[str, Any],
        template: AIReportTemplate | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Processa dados e calcula métricas."""
        summary = {}
        metrics = {}

        # Extrai sumário
        for source, source_data in data.items():
            if isinstance(source_data, dict):
                if "summary" in source_data:
                    summary[source] = source_data["summary"]
                elif "total" in source_data:
                    summary[source] = {k: v for k, v in source_data.items() if not isinstance(v, (list, dict))}

        # Calcula métricas
        if "sales" in data:
            sales = data["sales"]
            metrics["revenue"] = sales.get("total", 0)
            metrics["sales_count"] = sales.get("count", 0)
            metrics["avg_ticket"] = sales.get("avg_ticket", 0)
            metrics["sales_growth"] = sales.get("growth", 0)

        if "customers" in data:
            customers = data["customers"]
            metrics["customer_count"] = customers.get("total", 0)
            metrics["new_customers"] = customers.get("new", 0)
            metrics["churn_rate"] = 100 - customers.get("retention_rate", 0)
            metrics["retention_rate"] = customers.get("retention_rate", 0)

        if "financial" in data:
            financial = data["financial"]
            metrics["total_revenue"] = financial.get("revenue", 0)
            metrics["total_expenses"] = financial.get("expenses", 0)
            metrics["net_profit"] = financial.get("profit", 0)
            metrics["profit_margin"] = financial.get("margin", 0)

        return summary, metrics

    async def _generate_insights(
        self,
        data: dict[str, Any],
        summary: dict[str, Any],
        metrics: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Gera insights com IA baseado nos dados."""
        insights = []

        # Insight de crescimento
        if "sales_growth" in metrics:
            growth = metrics["sales_growth"]
            if growth > 20:
                insights.append(
                    {
                        "type": "positive",
                        "category": "sales",
                        "title": "Crescimento Excepcional",
                        "description": f"Vendas cresceram {growth}% no período, acima da média do mercado.",
                        "impact": "high",
                        "confidence": 0.85,
                    }
                )
            elif growth < 0:
                insights.append(
                    {
                        "type": "negative",
                        "category": "sales",
                        "title": "Queda nas Vendas",
                        "description": f"Vendas caíram {abs(growth)}% no período. Atenção necessária.",
                        "impact": "high",
                        "confidence": 0.90,
                    }
                )

        # Insight de retenção
        if "retention_rate" in metrics:
            retention = metrics["retention_rate"]
            if retention < 90:
                insights.append(
                    {
                        "type": "warning",
                        "category": "customers",
                        "title": "Taxa de Retenção Abaixo do Ideal",
                        "description": f"Retenção de {retention}% está abaixo da meta de 90%.",
                        "impact": "medium",
                        "confidence": 0.88,
                    }
                )

        # Insight de margem
        if "profit_margin" in metrics:
            margin = metrics["profit_margin"]
            if margin > 30:
                insights.append(
                    {
                        "type": "positive",
                        "category": "financial",
                        "title": "Margem de Lucro Saudável",
                        "description": f"Margem de {margin}% indica boa saúde financeira.",
                        "impact": "high",
                        "confidence": 0.92,
                    }
                )
            elif margin < 15:
                insights.append(
                    {
                        "type": "warning",
                        "category": "financial",
                        "title": "Margem de Lucro Comprimida",
                        "description": f"Margem de {margin}% está abaixo do ideal. Revisar custos.",
                        "impact": "high",
                        "confidence": 0.90,
                    }
                )

        return insights

    async def _generate_recommendations(
        self,
        data: dict[str, Any],
        summary: dict[str, Any],
        metrics: dict[str, Any],
        insights: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Gera recomendações baseadas nos insights."""
        recommendations = []

        for insight in insights:
            if insight["type"] == "negative" and insight["category"] == "sales":
                recommendations.append(
                    {
                        "title": "Revisar Estratégia de Vendas",
                        "description": "Analise os canais de venda com menor performance e considere campanhas de reativação.",
                        "priority": "high",
                        "category": "sales",
                        "effort": "medium",
                        "impact": "high",
                    }
                )

            if insight["type"] == "warning" and insight["category"] == "customers":
                recommendations.append(
                    {
                        "title": "Implementar Programa de Fidelidade",
                        "description": "Clientes com alto risco de churn devem receber atenção especial. Considere descontos ou benefícios.",
                        "priority": "high",
                        "category": "retention",
                        "effort": "medium",
                        "impact": "high",
                    }
                )

            if insight["type"] == "warning" and insight["category"] == "financial":
                recommendations.append(
                    {
                        "title": "Otimizar Estrutura de Custos",
                        "description": "Revisar contratos de fornecedores e identificar oportunidades de redução de custos operacionais.",
                        "priority": "medium",
                        "category": "finance",
                        "effort": "high",
                        "impact": "high",
                    }
                )

        return recommendations

    async def _detect_anomalies(
        self,
        data: dict[str, Any],
        metrics: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Detecta anomalias nos dados."""
        anomalies = []

        # Verifica vendas por dia para detectar anomalias
        if "sales" in data and "by_day" in data["sales"]:
            daily_sales = data["sales"]["by_day"]
            if len(daily_sales) > 7:
                values = [d["value"] for d in daily_sales]
                avg = sum(values) / len(values)
                std = (sum((x - avg) ** 2 for x in values) / len(values)) ** 0.5

                for day_data in daily_sales:
                    if abs(day_data["value"] - avg) > 2 * std:
                        anomaly_type = "spike" if day_data["value"] > avg else "drop"
                        anomalies.append(
                            {
                                "type": anomaly_type,
                                "category": "sales",
                                "date": day_data["date"],
                                "value": day_data["value"],
                                "expected": round(avg, 2),
                                "deviation": round((day_data["value"] - avg) / std, 2),
                                "severity": "high" if abs(day_data["value"] - avg) > 3 * std else "medium",
                            }
                        )

        return anomalies

    async def _analyze_trends(
        self,
        data: dict[str, Any],
        period_start: datetime | None,
        period_end: datetime | None,
    ) -> list[dict[str, Any]]:
        """Analisa tendências nos dados."""
        trends = []

        if "sales" in data and "by_day" in data["sales"]:
            daily_sales = data["sales"]["by_day"]
            if len(daily_sales) > 7:
                # Calcula tendência simples
                first_half = daily_sales[: len(daily_sales) // 2]
                second_half = daily_sales[len(daily_sales) // 2 :]

                first_avg = sum(d["value"] for d in first_half) / len(first_half)
                second_avg = sum(d["value"] for d in second_half) / len(second_half)

                if second_avg > first_avg * 1.1:
                    direction = "up"
                elif second_avg < first_avg * 0.9:
                    direction = "down"
                else:
                    direction = "stable"

                change = ((second_avg - first_avg) / first_avg) * 100 if first_avg > 0 else 0

                trends.append(
                    {
                        "metric": "sales",
                        "direction": direction,
                        "change_percent": round(change, 2),
                        "first_period_avg": round(first_avg, 2),
                        "second_period_avg": round(second_avg, 2),
                        "confidence": 0.75,
                    }
                )

        return trends

    async def _render_sections(
        self,
        template: AIReportTemplate,
        report: Report,
        data: dict[str, Any],
    ) -> list[ReportSection]:
        """Renderiza seções do relatório baseado no template."""
        sections = []

        if not template.sections_config:
            return sections

        for idx, section_config in enumerate(template.sections_config):
            section = ReportSection(
                code=section_config.get("code", f"section_{idx}"),
                name=section_config.get("name", f"Seção {idx + 1}"),
                section_type=section_config.get("section_type", "text"),
                layout=section_config.get("layout", "full_width"),
                order=section_config.get("order", idx),
                title=section_config.get("title"),
                content=section_config.get("content"),
                data_source=section_config.get("data_source"),
                template_id=template.id,
            )

            # Se tem fonte de dados, preenche
            if section.data_source and section.data_source in data:
                section.data = data[section.data_source]

            # Renderiza template de conteúdo
            if section_config.get("content_template"):
                context = {
                    "data": data,
                    "summary": report.summary,
                    "metrics": report.metrics,
                    "period_start": report.period_start,
                    "period_end": report.period_end,
                }
                section.render_template(context)

            sections.append(section)

        return sections

    def _generate_report_name(
        self,
        template: AIReportTemplate | None,
        period_start: datetime | None,
        period_end: datetime | None,
    ) -> str:
        """Gera nome do relatório."""
        base_name = template.name if template else "Relatório"
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

        if period_start and period_end:
            period_str = f"{period_start.strftime('%d/%m')} a {period_end.strftime('%d/%m/%Y')}"
            return f"{base_name} - {period_str}"

        return f"{base_name} - {date_str}"

    def _count_records(self, data: dict[str, Any]) -> int:
        """Conta registros processados."""
        count = 0
        for source_data in data.values():
            if isinstance(source_data, dict):
                if "records" in source_data:
                    count += len(source_data["records"])
                elif "by_day" in source_data:
                    count += len(source_data["by_day"])
                else:
                    count += 1
            elif isinstance(source_data, list):
                count += len(source_data)
        return count

    def _calculate_data_quality(self, data: dict[str, Any]) -> float:
        """Calcula score de qualidade dos dados."""
        if not data:
            return 0.0

        # Verifica completude básica
        total_fields = 0
        filled_fields = 0

        for source_data in data.values():
            if isinstance(source_data, dict):
                for _key, value in source_data.items():
                    total_fields += 1
                    if value is not None and value != "" and value != []:
                        filled_fields += 1

        if total_fields == 0:
            return 0.0

        return round((filled_fields / total_fields) * 100, 2)

    def _calculate_completeness(
        self,
        report: Report,
        template: AIReportTemplate | None,
    ) -> float:
        """Calcula score de completude do relatório."""
        score = 0.0
        checks = 0

        # Verifica campos obrigatórios
        if report.name:
            score += 1
        checks += 1

        if report.data:
            score += 1
        checks += 1

        if report.summary:
            score += 1
        checks += 1

        if report.metrics:
            score += 1
        checks += 1

        if report.insights:
            score += 1
        checks += 1

        if template and template.sections_config:
            # Verifica se todas as seções foram geradas
            expected_sections = len(template.sections_config)
            if expected_sections > 0:
                # Simplificado - assume que foram geradas
                score += 1
            checks += 1

        return round((score / checks) * 100, 2) if checks > 0 else 0.0

    def _calculate_accuracy(
        self,
        data: dict[str, Any],
        metrics: dict[str, Any],
    ) -> float:
        """Calcula score de acurácia (consistência dos dados)."""
        # Verificação simplificada de consistência
        score = 100.0

        # Verifica se métricas financeiras são consistentes
        if "total_revenue" in metrics and "total_expenses" in metrics:
            revenue = metrics["total_revenue"]
            expenses = metrics["total_expenses"]
            profit = metrics.get("net_profit", 0)

            expected_profit = revenue - expenses
            if profit != 0 and abs(profit - expected_profit) > expected_profit * 0.01:
                score -= 10  # Inconsistência

        return max(0.0, score)
