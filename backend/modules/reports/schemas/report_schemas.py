"""
Schemas Pydantic para o módulo de Relatórios Gerenciais
Sprint 34: Relatórios Gerenciais
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# ========================
# ReportTemplate Schemas
# ========================

class ReportTemplateBase(BaseModel):
    """Base para ReportTemplate."""
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: str = Field(..., description="Categoria do relatório")
    report_type: str = Field(default="summary")
    default_format: str = Field(default="pdf")
    supported_formats: Optional[List[str]] = None


class ReportTemplateCreate(ReportTemplateBase):
    """Schema para criação de template."""
    layout_config: Optional[Dict[str, Any]] = None
    header_config: Optional[Dict[str, Any]] = None
    footer_config: Optional[Dict[str, Any]] = None
    sections: Optional[List[Dict[str, Any]]] = None
    data_sources: Optional[List[Dict[str, Any]]] = None
    query_template: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    charts: Optional[List[Dict[str, Any]]] = None
    tables: Optional[List[Dict[str, Any]]] = None
    metrics: Optional[List[Dict[str, Any]]] = None
    theme: Optional[str] = "default"
    visibility: str = Field(default="private")
    allowed_roles: Optional[List[str]] = None
    allowed_users: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class ReportTemplateUpdate(BaseModel):
    """Schema para atualização de template."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    report_type: Optional[str] = None
    default_format: Optional[str] = None
    supported_formats: Optional[List[str]] = None
    layout_config: Optional[Dict[str, Any]] = None
    sections: Optional[List[Dict[str, Any]]] = None
    data_sources: Optional[List[Dict[str, Any]]] = None
    parameters: Optional[Dict[str, Any]] = None
    charts: Optional[List[Dict[str, Any]]] = None
    theme: Optional[str] = None
    visibility: Optional[str] = None
    tags: Optional[List[str]] = None


class ReportTemplateResponse(ReportTemplateBase):
    """Schema de resposta de template."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    status: str
    version: int
    usage_count: int
    last_used_at: Optional[datetime] = None
    avg_generation_time: Optional[int] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    ativo: bool


class ReportTemplateList(BaseModel):
    """Lista paginada de templates."""
    items: List[ReportTemplateResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ========================
# ReportSchedule Schemas
# ========================

class ReportScheduleBase(BaseModel):
    """Base para ReportSchedule."""
    template_id: UUID
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    frequency: str
    timezone: str = Field(default="America/Sao_Paulo")


class ReportScheduleCreate(ReportScheduleBase):
    """Schema para criação de agendamento."""
    cron_expression: Optional[str] = None
    data_period: Optional[str] = None
    data_start_offset: Optional[int] = None
    data_end_offset: Optional[int] = None
    relative_period: bool = True
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    max_executions: Optional[int] = None
    report_parameters: Optional[Dict[str, Any]] = None
    report_format: str = "pdf"
    report_filename_pattern: Optional[str] = None
    delivery_method: str = "email"
    delivery_config: Optional[Dict[str, Any]] = None
    recipients: Optional[List[str]] = None
    cc_recipients: Optional[List[str]] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    notify_on_success: bool = False
    notify_on_failure: bool = True
    tags: Optional[List[str]] = None


class ReportScheduleUpdate(BaseModel):
    """Schema para atualização de agendamento."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    frequency: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    report_parameters: Optional[Dict[str, Any]] = None
    report_format: Optional[str] = None
    delivery_method: Optional[str] = None
    recipients: Optional[List[str]] = None
    email_subject: Optional[str] = None
    tags: Optional[List[str]] = None


class ReportScheduleResponse(ReportScheduleBase):
    """Schema de resposta de agendamento."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    status: str
    next_execution_at: Optional[datetime] = None
    last_execution_at: Optional[datetime] = None
    execution_count: int
    success_count: int
    failure_count: int
    delivery_method: str
    recipients: Optional[List[str]] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    ativo: bool


class ReportScheduleList(BaseModel):
    """Lista paginada de agendamentos."""
    items: List[ReportScheduleResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ========================
# ReportExport Schemas
# ========================

class ReportExportCreate(BaseModel):
    """Schema para criação de exportação.

    data_period_* e report_title/subtitle não têm coluna própria na tabela
    report_exports — são persistidos em extra_metadata (JSONB) pelo service.
    """
    template_id: UUID
    format: str = "pdf"
    parameters: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    data_period_start: Optional[datetime] = None
    data_period_end: Optional[datetime] = None
    report_title: Optional[str] = None
    report_subtitle: Optional[str] = None


class ReportExportResponse(BaseModel):
    """Schema de resposta de exportação (campos = colunas reais de report_exports)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: Optional[UUID] = None
    template_id: UUID
    schedule_id: Optional[UUID] = None
    export_id: str
    status: str
    trigger: str
    format: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    download_url: Optional[str] = None
    download_token: Optional[str] = None
    download_count: int
    expires_at: Optional[datetime] = None
    processing_time_ms: Optional[int] = None
    row_count: Optional[int] = None
    page_count: Optional[int] = None
    error_message: Optional[str] = None
    delivered: bool
    delivered_at: Optional[datetime] = None
    requested_by: Optional[UUID] = None
    created_at: datetime


class ReportExportList(BaseModel):
    """Lista paginada de exportações."""
    items: List[ReportExportResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ReportExportDownload(BaseModel):
    """Resposta para download."""
    download_url: str
    filename: str
    content_type: str
    file_size: int
    expires_at: Optional[datetime] = None


# ========================
# ExecutiveKPI Schemas
# ========================

class ExecutiveKPIBase(BaseModel):
    """Base para ExecutiveKPI."""
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: str
    kpi_type: str
    direction: str = "increase"


class ExecutiveKPICreate(ExecutiveKPIBase):
    """Schema para criação de KPI."""
    unit: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    decimal_places: int = 2
    target_value: Optional[float] = None
    baseline_value: Optional[float] = None
    warning_threshold_low: Optional[float] = None
    warning_threshold_high: Optional[float] = None
    critical_threshold_low: Optional[float] = None
    critical_threshold_high: Optional[float] = None
    aggregation_period: str = "monthly"
    calculation_formula: Optional[str] = None
    data_source: Optional[str] = None
    data_query: Optional[str] = None
    owner_id: Optional[UUID] = None
    department: Optional[str] = None
    chart_type: str = "gauge"
    visible_on_dashboard: bool = True
    alerts_enabled: bool = True
    alert_recipients: Optional[List[str]] = None
    yearly_target: Optional[float] = None
    tags: Optional[List[str]] = None


class ExecutiveKPIUpdate(BaseModel):
    """Schema para atualização de KPI."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    target_value: Optional[float] = None
    warning_threshold_low: Optional[float] = None
    warning_threshold_high: Optional[float] = None
    critical_threshold_low: Optional[float] = None
    critical_threshold_high: Optional[float] = None
    owner_id: Optional[UUID] = None
    department: Optional[str] = None
    visible_on_dashboard: Optional[bool] = None
    alerts_enabled: Optional[bool] = None
    tags: Optional[List[str]] = None


class ExecutiveKPIValueUpdate(BaseModel):
    """Schema para atualização de valor do KPI."""
    value: float
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class ExecutiveKPIResponse(ExecutiveKPIBase):
    """Schema de resposta de KPI."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    status: str
    unit: Optional[str] = None
    current_value: Optional[float] = None
    previous_value: Optional[float] = None
    target_value: Optional[float] = None
    alert_level: str
    trend: Optional[str] = None
    variance: Optional[float] = None
    variance_percentage: Optional[float] = None
    aggregation_period: str
    owner_name: Optional[str] = None
    department: Optional[str] = None
    visible_on_dashboard: bool
    last_calculated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    ativo: bool


class ExecutiveKPIList(BaseModel):
    """Lista paginada de KPIs."""
    items: List[ExecutiveKPIResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class KPIDashboard(BaseModel):
    """Dashboard de KPIs."""
    kpis: List[ExecutiveKPIResponse]
    summary: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    trends: Dict[str, Any]


# ========================
# Benchmark Schemas
# ========================

class BenchmarkBase(BaseModel):
    """Base para Benchmark."""
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: str
    benchmark_type: str
    source: str


class BenchmarkCreate(BenchmarkBase):
    """Schema para criação de benchmark."""
    industry: Optional[str] = None
    sub_industry: Optional[str] = None
    market_segment: Optional[str] = None
    geographic_region: Optional[str] = None
    company_size: Optional[str] = None
    reference_value: float
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    median_value: Optional[float] = None
    average_value: Optional[float] = None
    percentile_25: Optional[float] = None
    percentile_75: Optional[float] = None
    percentile_90: Optional[float] = None
    unit: Optional[str] = None
    is_percentage: bool = False
    is_currency: bool = False
    currency_code: Optional[str] = None
    reference_year: Optional[int] = None
    reference_quarter: Optional[int] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    sample_size: Optional[int] = None
    related_kpi_ids: Optional[List[UUID]] = None
    visible_on_dashboard: bool = True
    tags: Optional[List[str]] = None


class BenchmarkUpdate(BaseModel):
    """Schema para atualização de benchmark."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    reference_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    median_value: Optional[float] = None
    percentile_25: Optional[float] = None
    percentile_75: Optional[float] = None
    percentile_90: Optional[float] = None
    valid_until: Optional[datetime] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    visible_on_dashboard: Optional[bool] = None
    tags: Optional[List[str]] = None


class BenchmarkCompanyValue(BaseModel):
    """Schema para atualizar valor da empresa."""
    company_value: float


class BenchmarkResponse(BenchmarkBase):
    """Schema de resposta de benchmark."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    status: str
    industry: Optional[str] = None
    reference_value: float
    median_value: Optional[float] = None
    unit: Optional[str] = None
    is_percentage: bool
    is_currency: bool
    reference_year: Optional[int] = None
    current_company_value: Optional[float] = None
    comparison_result: Optional[str] = None
    deviation: Optional[float] = None
    deviation_percentage: Optional[float] = None
    percentile_rank: Optional[float] = None
    target_value: Optional[float] = None
    visible_on_dashboard: bool
    last_updated_from_source: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    ativo: bool


class BenchmarkList(BaseModel):
    """Lista paginada de benchmarks."""
    items: List[BenchmarkResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ========================
# Dashboard Schemas
# ========================

class ReportsDashboard(BaseModel):
    """Dashboard geral de relatórios."""
    total_templates: int
    active_schedules: int
    exports_today: int
    exports_this_month: int
    pending_exports: int
    failed_exports: int
    top_templates: List[Dict[str, Any]]
    recent_exports: List[ReportExportResponse]
    schedule_health: Dict[str, Any]


class ExecutiveDashboard(BaseModel):
    """Dashboard executivo."""
    kpis: List[ExecutiveKPIResponse]
    benchmarks: List[BenchmarkResponse]
    alerts: List[Dict[str, Any]]
    summary: Dict[str, Any]
    trends: Dict[str, Any]
    comparisons: List[Dict[str, Any]]


# ========================
# Filter Schemas
# ========================

class ReportTemplateFilter(BaseModel):
    """Filtros para templates."""
    category: Optional[str] = None
    report_type: Optional[str] = None
    status: Optional[str] = None
    visibility: Optional[str] = None
    created_by: Optional[UUID] = None
    tags: Optional[List[str]] = None
    search: Optional[str] = None


class ReportScheduleFilter(BaseModel):
    """Filtros para agendamentos."""
    template_id: Optional[UUID] = None
    status: Optional[str] = None
    frequency: Optional[str] = None
    delivery_method: Optional[str] = None
    created_by: Optional[UUID] = None


class ReportExportFilter(BaseModel):
    """Filtros para exportações."""
    template_id: Optional[UUID] = None
    schedule_id: Optional[UUID] = None
    status: Optional[str] = None
    trigger: Optional[str] = None
    format: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    requested_by: Optional[UUID] = None


class ExecutiveKPIFilter(BaseModel):
    """Filtros para KPIs."""
    category: Optional[str] = None
    status: Optional[str] = None
    alert_level: Optional[str] = None
    owner_id: Optional[UUID] = None
    department: Optional[str] = None
    visible_on_dashboard: Optional[bool] = None
    tags: Optional[List[str]] = None


class BenchmarkFilter(BaseModel):
    """Filtros para benchmarks."""
    category: Optional[str] = None
    benchmark_type: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    industry: Optional[str] = None
    visible_on_dashboard: Optional[bool] = None
    tags: Optional[List[str]] = None
