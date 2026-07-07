"""
ReportService - Serviço principal de relatórios gerenciais
Sprint 34: Relatórios Gerenciais
"""
# pylint: disable=too-many-locals,too-many-public-methods,too-many-branches

import logging
from datetime import datetime
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.reports.models import (
    ReportTemplate,
    ReportSchedule,
    ReportExport,
    ExecutiveKPI,
    Benchmark,
    ReportCategory,
    ReportFormat,
    ReportType,
    ScheduleFrequency,
    DeliveryMethod,
    ExportTrigger,
    ExportFormat,
    KPICategory,
    KPIType,
    KPIDirection,
    BenchmarkCategory,
    BenchmarkType,
    BenchmarkSource,
)
from modules.reports.schemas import (
    ReportTemplateCreate,
    ReportTemplateUpdate,
    ReportScheduleCreate,
    ReportScheduleUpdate,
    ReportExportCreate,
    ExecutiveKPICreate,
    ExecutiveKPIUpdate,
    ExecutiveKPIValueUpdate,
    BenchmarkCreate,
    BenchmarkUpdate,
    BenchmarkCompanyValue,
    ReportsDashboard,
    ExecutiveDashboard,
)
from modules.reports.repositories import ReportRepository

logger = logging.getLogger(__name__)


class ReportService:
    """Serviço para relatórios gerenciais."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = ReportRepository(db)

    # ==================== ReportTemplate ====================

    async def create_template(
        self,
        tenant_id: UUID,
        data: ReportTemplateCreate,
        created_by: Optional[UUID] = None
    ) -> ReportTemplate:
        """Cria um template de relatório."""
        template = ReportTemplate(
            tenant_id=tenant_id,
            code=data.code,
            name=data.name,
            description=data.description,
            category=ReportCategory(data.category),
            report_type=ReportType(data.report_type),
            default_format=ReportFormat(data.default_format),
            supported_formats=data.supported_formats,
            layout_config=data.layout_config,
            header_config=data.header_config,
            footer_config=data.footer_config,
            sections=data.sections,
            data_sources=data.data_sources,
            query_template=data.query_template,
            parameters=data.parameters,
            filters=data.filters,
            charts=data.charts,
            tables=data.tables,
            metrics=data.metrics,
            theme=data.theme,
            visibility=data.visibility,
            allowed_roles=data.allowed_roles,
            allowed_users=data.allowed_users,
            tags=data.tags,
            created_by=created_by
        )

        return await self.repository.create_template(template)

    async def get_template(
        self,
        tenant_id: UUID,
        template_id: UUID
    ) -> Optional[ReportTemplate]:
        """Busca template por ID."""
        return await self.repository.get_template(tenant_id, template_id)

    async def list_templates(
        self,
        tenant_id: UUID,
        category: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[ReportTemplate], int]:
        """Lista templates com paginação."""
        skip = (page - 1) * page_size
        return await self.repository.list_templates(
            tenant_id, category, status, search, skip, page_size
        )

    async def update_template(
        self,
        tenant_id: UUID,
        template_id: UUID,
        data: ReportTemplateUpdate,
        updated_by: Optional[UUID] = None
    ) -> Optional[ReportTemplate]:
        """Atualiza um template."""
        template = await self.repository.get_template(tenant_id, template_id)
        if not template:
            return None

        if data.name:
            template.name = data.name
        if data.description is not None:
            template.description = data.description
        if data.report_type:
            template.report_type = ReportType(data.report_type)
        if data.default_format:
            template.default_format = ReportFormat(data.default_format)
        if data.supported_formats:
            template.supported_formats = data.supported_formats
        if data.layout_config:
            template.layout_config = data.layout_config
        if data.sections:
            template.sections = data.sections
        if data.data_sources:
            template.data_sources = data.data_sources
        if data.parameters:
            template.parameters = data.parameters
        if data.charts:
            template.charts = data.charts
        if data.theme:
            template.theme = data.theme
        if data.visibility:
            template.visibility = data.visibility
        if data.tags:
            template.tags = data.tags

        template.updated_by = updated_by
        template.updated_at = datetime.utcnow()

        return await self.repository.update_template(template)

    async def activate_template(
        self,
        tenant_id: UUID,
        template_id: UUID
    ) -> Optional[ReportTemplate]:
        """Ativa um template."""
        template = await self.repository.get_template(tenant_id, template_id)
        if not template:
            return None

        template.activate()
        return await self.repository.update_template(template)

    async def deactivate_template(
        self,
        tenant_id: UUID,
        template_id: UUID
    ) -> Optional[ReportTemplate]:
        """Desativa um template."""
        template = await self.repository.get_template(tenant_id, template_id)
        if not template:
            return None

        template.deactivate()
        return await self.repository.update_template(template)

    async def delete_template(
        self,
        tenant_id: UUID,
        template_id: UUID
    ) -> bool:
        """Remove um template."""
        template = await self.repository.get_template(tenant_id, template_id)
        if not template:
            return False

        await self.repository.delete_template(template)
        return True

    # ==================== ReportSchedule ====================

    async def create_schedule(
        self,
        tenant_id: UUID,
        data: ReportScheduleCreate,
        created_by: Optional[UUID] = None
    ) -> ReportSchedule:
        """Cria um agendamento."""
        schedule = ReportSchedule(
            tenant_id=tenant_id,
            template_id=data.template_id,
            name=data.name,
            description=data.description,
            frequency=ScheduleFrequency(data.frequency),
            cron_expression=data.cron_expression,
            timezone=data.timezone,
            data_period=data.data_period,
            data_start_offset=data.data_start_offset,
            data_end_offset=data.data_end_offset,
            relative_period=data.relative_period,
            start_date=data.start_date,
            end_date=data.end_date,
            max_executions=data.max_executions,
            report_parameters=data.report_parameters,
            report_format=data.report_format,
            report_filename_pattern=data.report_filename_pattern,
            delivery_method=DeliveryMethod(data.delivery_method),
            delivery_config=data.delivery_config,
            recipients=data.recipients,
            cc_recipients=data.cc_recipients,
            email_subject=data.email_subject,
            email_body=data.email_body,
            notify_on_success=data.notify_on_success,
            notify_on_failure=data.notify_on_failure,
            tags=data.tags,
            created_by=created_by
        )

        schedule.calculate_next_execution()
        return await self.repository.create_schedule(schedule)

    async def get_schedule(
        self,
        tenant_id: UUID,
        schedule_id: UUID
    ) -> Optional[ReportSchedule]:
        """Busca agendamento por ID."""
        return await self.repository.get_schedule(tenant_id, schedule_id)

    async def list_schedules(
        self,
        tenant_id: UUID,
        template_id: Optional[UUID] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[ReportSchedule], int]:
        """Lista agendamentos."""
        skip = (page - 1) * page_size
        return await self.repository.list_schedules(
            tenant_id, template_id, status, skip, page_size
        )

    async def update_schedule(
        self,
        tenant_id: UUID,
        schedule_id: UUID,
        data: ReportScheduleUpdate,
        updated_by: Optional[UUID] = None
    ) -> Optional[ReportSchedule]:
        """Atualiza um agendamento."""
        schedule = await self.repository.get_schedule(tenant_id, schedule_id)
        if not schedule:
            return None

        if data.name:
            schedule.name = data.name
        if data.description is not None:
            schedule.description = data.description
        if data.frequency:
            schedule.frequency = ScheduleFrequency(data.frequency)
        if data.cron_expression:
            schedule.cron_expression = data.cron_expression
        if data.timezone:
            schedule.timezone = data.timezone
        if data.start_date:
            schedule.start_date = data.start_date
        if data.end_date:
            schedule.end_date = data.end_date
        if data.report_parameters:
            schedule.report_parameters = data.report_parameters
        if data.report_format:
            schedule.report_format = data.report_format
        if data.delivery_method:
            schedule.delivery_method = DeliveryMethod(data.delivery_method)
        if data.recipients:
            schedule.recipients = data.recipients
        if data.email_subject:
            schedule.email_subject = data.email_subject
        if data.tags:
            schedule.tags = data.tags

        schedule.updated_by = updated_by
        schedule.updated_at = datetime.utcnow()
        schedule.calculate_next_execution()

        return await self.repository.update_schedule(schedule)

    async def pause_schedule(
        self,
        tenant_id: UUID,
        schedule_id: UUID
    ) -> Optional[ReportSchedule]:
        """Pausa um agendamento."""
        schedule = await self.repository.get_schedule(tenant_id, schedule_id)
        if not schedule:
            return None

        schedule.pause()
        return await self.repository.update_schedule(schedule)

    async def resume_schedule(
        self,
        tenant_id: UUID,
        schedule_id: UUID
    ) -> Optional[ReportSchedule]:
        """Retoma um agendamento."""
        schedule = await self.repository.get_schedule(tenant_id, schedule_id)
        if not schedule:
            return None

        schedule.resume()
        return await self.repository.update_schedule(schedule)

    async def cancel_schedule(
        self,
        tenant_id: UUID,
        schedule_id: UUID
    ) -> Optional[ReportSchedule]:
        """Cancela um agendamento."""
        schedule = await self.repository.get_schedule(tenant_id, schedule_id)
        if not schedule:
            return None

        schedule.cancel()
        return await self.repository.update_schedule(schedule)

    # ==================== ReportExport ====================

    async def create_export(
        self,
        tenant_id: UUID,
        data: ReportExportCreate,
        requested_by: Optional[UUID] = None,
        trigger: ExportTrigger = ExportTrigger.MANUAL
    ) -> ReportExport:
        """Cria uma exportação."""
        export = ReportExport.create_export(
            template_id=str(data.template_id),
            export_format=ExportFormat(data.format),
            trigger=trigger,
            requested_by=str(requested_by) if requested_by else None
        )

        export.tenant_id = tenant_id
        export.parameters = data.parameters
        export.filters = data.filters

        # Campos sem coluna própria em report_exports → extra_metadata (JSONB)
        extra = {
            key: value
            for key, value in {
                "data_period_start": data.data_period_start.isoformat() if data.data_period_start else None,
                "data_period_end": data.data_period_end.isoformat() if data.data_period_end else None,
                "report_title": data.report_title,
                "report_subtitle": data.report_subtitle,
            }.items()
            if value is not None
        }
        if extra:
            export.extra_metadata = extra

        return await self.repository.create_export(export)

    async def get_export(
        self,
        tenant_id: UUID,
        export_id: UUID
    ) -> Optional[ReportExport]:
        """Busca exportação por ID."""
        return await self.repository.get_export(tenant_id, export_id)

    async def get_export_by_token(self, token: str) -> Optional[ReportExport]:
        """Busca exportação por token."""
        return await self.repository.get_export_by_token(token)

    async def list_exports(
        self,
        tenant_id: UUID,
        template_id: Optional[UUID] = None,
        schedule_id: Optional[UUID] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[ReportExport], int]:
        """Lista exportações."""
        skip = (page - 1) * page_size
        return await self.repository.list_exports(
            tenant_id, template_id, schedule_id, status,
            start_date, end_date, skip, page_size
        )

    async def start_export_processing(
        self,
        tenant_id: UUID,
        export_id: UUID
    ) -> Optional[ReportExport]:
        """Inicia processamento de exportação."""
        export = await self.repository.get_export(tenant_id, export_id)
        if not export:
            return None

        export.start_processing()
        return await self.repository.update_export(export)

    async def complete_export(
        self,
        tenant_id: UUID,
        export_id: UUID,
        file_path: str,
        file_size: int,
        file_checksum: Optional[str] = None,
        records: Optional[int] = None,
        pages: Optional[int] = None
    ) -> Optional[ReportExport]:
        """Completa uma exportação."""
        export = await self.repository.get_export(tenant_id, export_id)
        if not export:
            return None

        export.complete(file_path, file_size, file_checksum, records, pages)

        # Atualiza estatísticas do template
        template = await self.repository.get_template(
            tenant_id, export.template_id
        )
        if template:
            template.record_usage(export.processing_time_ms)
            await self.repository.update_template(template)

        return await self.repository.update_export(export)

    async def fail_export(
        self,
        tenant_id: UUID,
        export_id: UUID,
        error_message: str,
        error_code: Optional[str] = None,
        error_details: Optional[dict] = None
    ) -> Optional[ReportExport]:
        """Marca exportação como falha."""
        export = await self.repository.get_export(tenant_id, export_id)
        if not export:
            return None

        export.fail(error_message, error_code, error_details)
        return await self.repository.update_export(export)

    async def record_download(
        self,
        token: str,
        user_id: Optional[UUID] = None
    ) -> bool:
        """Registra download."""
        export = await self.repository.get_export_by_token(token)
        if not export:
            return False

        if export.record_download(str(user_id) if user_id else None):
            await self.repository.update_export(export)
            return True
        return False

    # ==================== ExecutiveKPI ====================

    async def create_kpi(
        self,
        tenant_id: UUID,
        data: ExecutiveKPICreate,
        created_by: Optional[UUID] = None
    ) -> ExecutiveKPI:
        """Cria um KPI."""
        kpi = ExecutiveKPI(
            tenant_id=tenant_id,
            code=data.code,
            name=data.name,
            description=data.description,
            category=KPICategory(data.category),
            kpi_type=KPIType(data.kpi_type),
            direction=KPIDirection(data.direction),
            unit=data.unit,
            prefix=data.prefix,
            suffix=data.suffix,
            decimal_places=data.decimal_places,
            target_value=data.target_value,
            baseline_value=data.baseline_value,
            warning_threshold_low=data.warning_threshold_low,
            warning_threshold_high=data.warning_threshold_high,
            critical_threshold_low=data.critical_threshold_low,
            critical_threshold_high=data.critical_threshold_high,
            aggregation_period=data.aggregation_period,
            calculation_formula=data.calculation_formula,
            data_source=data.data_source,
            data_query=data.data_query,
            owner_id=data.owner_id,
            department=data.department,
            chart_type=data.chart_type,
            visible_on_dashboard=data.visible_on_dashboard,
            alerts_enabled=data.alerts_enabled,
            alert_recipients=data.alert_recipients,
            yearly_target=data.yearly_target,
            tags=data.tags,
            created_by=created_by
        )

        return await self.repository.create_kpi(kpi)

    async def get_kpi(
        self,
        tenant_id: UUID,
        kpi_id: UUID
    ) -> Optional[ExecutiveKPI]:
        """Busca KPI por ID."""
        return await self.repository.get_kpi(tenant_id, kpi_id)

    async def list_kpis(
        self,
        tenant_id: UUID,
        category: Optional[str] = None,
        status: Optional[str] = None,
        alert_level: Optional[str] = None,
        visible_on_dashboard: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[ExecutiveKPI], int]:
        """Lista KPIs."""
        skip = (page - 1) * page_size
        return await self.repository.list_kpis(
            tenant_id, category, status, alert_level,
            visible_on_dashboard, skip, page_size
        )

    async def update_kpi(
        self,
        tenant_id: UUID,
        kpi_id: UUID,
        data: ExecutiveKPIUpdate,
        updated_by: Optional[UUID] = None
    ) -> Optional[ExecutiveKPI]:
        """Atualiza um KPI."""
        kpi = await self.repository.get_kpi(tenant_id, kpi_id)
        if not kpi:
            return None

        if data.name:
            kpi.name = data.name
        if data.description is not None:
            kpi.description = data.description
        if data.target_value is not None:
            kpi.target_value = data.target_value
        if data.warning_threshold_low is not None:
            kpi.warning_threshold_low = data.warning_threshold_low
        if data.warning_threshold_high is not None:
            kpi.warning_threshold_high = data.warning_threshold_high
        if data.critical_threshold_low is not None:
            kpi.critical_threshold_low = data.critical_threshold_low
        if data.critical_threshold_high is not None:
            kpi.critical_threshold_high = data.critical_threshold_high
        if data.owner_id:
            kpi.owner_id = data.owner_id
        if data.department:
            kpi.department = data.department
        if data.visible_on_dashboard is not None:
            kpi.visible_on_dashboard = data.visible_on_dashboard
        if data.alerts_enabled is not None:
            kpi.alerts_enabled = data.alerts_enabled
        if data.tags:
            kpi.tags = data.tags

        kpi.updated_by = updated_by
        kpi.updated_at = datetime.utcnow()

        return await self.repository.update_kpi(kpi)

    async def update_kpi_value(
        self,
        tenant_id: UUID,
        kpi_id: UUID,
        data: ExecutiveKPIValueUpdate
    ) -> Optional[ExecutiveKPI]:
        """Atualiza valor do KPI."""
        kpi = await self.repository.get_kpi(tenant_id, kpi_id)
        if not kpi:
            return None

        kpi.update_value(data.value, data.period_start, data.period_end)
        return await self.repository.update_kpi(kpi)

    async def get_dashboard_kpis(
        self,
        tenant_id: UUID
    ) -> List[ExecutiveKPI]:
        """Retorna KPIs para dashboard."""
        return await self.repository.get_dashboard_kpis(tenant_id)

    async def get_kpis_needing_attention(
        self,
        tenant_id: UUID
    ) -> List[ExecutiveKPI]:
        """Retorna KPIs que precisam atenção."""
        return await self.repository.get_kpis_needing_attention(tenant_id)

    # ==================== Benchmark ====================

    async def create_benchmark(
        self,
        tenant_id: UUID,
        data: BenchmarkCreate,
        created_by: Optional[UUID] = None
    ) -> Benchmark:
        """Cria um benchmark."""
        benchmark = Benchmark(
            tenant_id=tenant_id,
            code=data.code,
            name=data.name,
            description=data.description,
            category=BenchmarkCategory(data.category),
            benchmark_type=BenchmarkType(data.benchmark_type),
            source=BenchmarkSource(data.source),
            industry=data.industry,
            sub_industry=data.sub_industry,
            market_segment=data.market_segment,
            geographic_region=data.geographic_region,
            company_size=data.company_size,
            reference_value=data.reference_value,
            min_value=data.min_value,
            max_value=data.max_value,
            median_value=data.median_value,
            average_value=data.average_value,
            percentile_25=data.percentile_25,
            percentile_75=data.percentile_75,
            percentile_90=data.percentile_90,
            unit=data.unit,
            is_percentage=data.is_percentage,
            is_currency=data.is_currency,
            currency_code=data.currency_code,
            reference_year=data.reference_year,
            reference_quarter=data.reference_quarter,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            source_name=data.source_name,
            source_url=data.source_url,
            sample_size=data.sample_size,
            related_kpi_ids=data.related_kpi_ids,
            visible_on_dashboard=data.visible_on_dashboard,
            tags=data.tags,
            created_by=created_by
        )

        return await self.repository.create_benchmark(benchmark)

    async def get_benchmark(
        self,
        tenant_id: UUID,
        benchmark_id: UUID
    ) -> Optional[Benchmark]:
        """Busca benchmark por ID."""
        return await self.repository.get_benchmark(tenant_id, benchmark_id)

    async def list_benchmarks(
        self,
        tenant_id: UUID,
        category: Optional[str] = None,
        benchmark_type: Optional[str] = None,
        industry: Optional[str] = None,
        status: Optional[str] = None,
        visible_on_dashboard: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Benchmark], int]:
        """Lista benchmarks."""
        skip = (page - 1) * page_size
        return await self.repository.list_benchmarks(
            tenant_id, category, benchmark_type, industry,
            status, visible_on_dashboard, skip, page_size
        )

    async def update_benchmark(
        self,
        tenant_id: UUID,
        benchmark_id: UUID,
        data: BenchmarkUpdate,
        updated_by: Optional[UUID] = None
    ) -> Optional[Benchmark]:
        """Atualiza um benchmark."""
        benchmark = await self.repository.get_benchmark(tenant_id, benchmark_id)
        if not benchmark:
            return None

        if data.name:
            benchmark.name = data.name
        if data.description is not None:
            benchmark.description = data.description
        if data.reference_value is not None:
            benchmark.update_reference_value(data.reference_value)
        if data.min_value is not None:
            benchmark.min_value = data.min_value
        if data.max_value is not None:
            benchmark.max_value = data.max_value
        if data.median_value is not None:
            benchmark.median_value = data.median_value
        if data.percentile_25 is not None:
            benchmark.percentile_25 = data.percentile_25
        if data.percentile_75 is not None:
            benchmark.percentile_75 = data.percentile_75
        if data.percentile_90 is not None:
            benchmark.percentile_90 = data.percentile_90
        if data.valid_until:
            benchmark.valid_until = data.valid_until
        if data.source_name:
            benchmark.source_name = data.source_name
        if data.source_url:
            benchmark.source_url = data.source_url
        if data.visible_on_dashboard is not None:
            benchmark.visible_on_dashboard = data.visible_on_dashboard
        if data.tags:
            benchmark.tags = data.tags

        benchmark.updated_by = updated_by
        benchmark.updated_at = datetime.utcnow()

        return await self.repository.update_benchmark(benchmark)

    async def update_company_value(
        self,
        tenant_id: UUID,
        benchmark_id: UUID,
        data: BenchmarkCompanyValue
    ) -> Optional[Benchmark]:
        """Atualiza valor da empresa no benchmark."""
        benchmark = await self.repository.get_benchmark(tenant_id, benchmark_id)
        if not benchmark:
            return None

        benchmark.update_company_value(data.company_value)
        return await self.repository.update_benchmark(benchmark)

    async def get_dashboard_benchmarks(
        self,
        tenant_id: UUID
    ) -> List[Benchmark]:
        """Retorna benchmarks para dashboard."""
        return await self.repository.get_dashboard_benchmarks(tenant_id)

    async def get_benchmarks_below_target(
        self,
        tenant_id: UUID
    ) -> List[Benchmark]:
        """Retorna benchmarks abaixo da meta."""
        return await self.repository.get_benchmarks_below_target(tenant_id)

    # ==================== Dashboard ====================

    async def get_reports_dashboard(
        self,
        tenant_id: UUID
    ) -> ReportsDashboard:
        """Retorna dashboard de relatórios."""
        stats = await self.repository.get_reports_dashboard_stats(tenant_id)
        top_templates = await self.repository.get_top_templates(tenant_id, 5)
        recent_exports, _ = await self.repository.list_exports(
            tenant_id, skip=0, limit=10
        )

        return ReportsDashboard(
            total_templates=stats["total_templates"],
            active_schedules=stats["active_schedules"],
            exports_today=stats["exports_today"],
            exports_this_month=stats["exports_this_month"],
            pending_exports=stats["pending_exports"],
            failed_exports=stats["failed_exports"],
            top_templates=[
                {"id": str(t.id), "name": t.name, "usage_count": t.usage_count}
                for t in top_templates
            ],
            # Objetos ORM reais — validados por ReportExportResponse (from_attributes)
            recent_exports=list(recent_exports),
            schedule_health={}
        )

    async def get_executive_dashboard(
        self,
        tenant_id: UUID
    ) -> ExecutiveDashboard:
        """Retorna dashboard executivo."""
        kpis = await self.get_dashboard_kpis(tenant_id)
        dashboard_benchmarks = await self.get_dashboard_benchmarks(tenant_id)
        attention_kpis = await self.get_kpis_needing_attention(tenant_id)

        alerts = [
            {"kpi_id": str(k.id), "name": k.name, "level": k.alert_level.value}
            for k in attention_kpis
        ]

        return ExecutiveDashboard(
            kpis=[
                {"id": str(k.id), "name": k.nome, "value": str(k.current_value)}
                for k in kpis
            ],
            benchmarks=[
                {"id": str(b.id), "name": b.nome, "value": str(b.reference_value)}
                for b in dashboard_benchmarks
            ],
            alerts=alerts,
            summary={
                "total_kpis": len(kpis),
                "on_target": sum(1 for k in kpis if k.is_on_target),
                "needs_attention": len(attention_kpis)
            },
            trends={},
            comparisons=[]
        )
