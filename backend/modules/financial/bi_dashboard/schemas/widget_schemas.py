"""Schemas de Widget de Dashboard Financeiro."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.financial.bi_dashboard.models.dashboard_widget import (
    ChartType,
    DataSource,
    WidgetSize,
    WidgetType,
)


class WidgetBase(BaseModel):
    """Schema base de Widget."""

    titulo: str = Field(..., min_length=1, max_length=200)
    subtitulo: str | None = Field(None, max_length=500)
    descricao: str | None = Field(None, max_length=2000)
    tipo: WidgetType = Field(default=WidgetType.KPI_CARD)
    tamanho: WidgetSize = Field(default=WidgetSize.MEDIUM)
    chart_type: ChartType | None = None
    data_source: DataSource = Field(default=DataSource.CASH_FLOW)


class WidgetPosition(BaseModel):
    """Posicao do widget no grid."""

    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    w: int = Field(default=1, ge=1, le=12)
    h: int = Field(default=1, ge=1, le=8)


class WidgetDataConfig(BaseModel):
    """Configuracao de dados do widget."""

    metric_field: str | None = Field(None, max_length=100)
    dimension_field: str | None = Field(None, max_length=100)
    time_field: str = Field(default="created_at", max_length=100)
    aggregation: str = Field(default="sum", max_length=50)
    group_by: list = Field(default_factory=list)
    sort_by: str | None = Field(None, max_length=100)
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
    limit: int = Field(default=10, ge=1, le=1000)
    filters: dict = Field(default_factory=dict)
    date_range_days: int = Field(default=30, ge=1, le=365)


class WidgetStyleConfig(BaseModel):
    """Configuracao de estilo do widget."""

    colors: list = Field(default_factory=list)
    background_color: str | None = Field(None, max_length=20)
    border_color: str | None = Field(None, max_length=20)
    text_color: str | None = Field(None, max_length=20)
    icon: str | None = Field(None, max_length=100)
    value_format: str = Field(default="currency", max_length=50)
    decimal_places: int = Field(default=2, ge=0, le=8)
    show_percentage: bool = Field(default=False)
    show_trend: bool = Field(default=True)
    show_comparison: bool = Field(default=False)
    show_legend: bool = Field(default=True)


class WidgetThresholds(BaseModel):
    """Thresholds do widget para alertas."""

    warning: Decimal | None = None
    critical: Decimal | None = None
    success: Decimal | None = None
    invert_colors: bool = Field(default=False)


class WidgetCreate(WidgetBase):
    """Schema para criar Widget."""

    codigo: str = Field(..., min_length=1, max_length=50)
    dashboard_id: UUID
    position: WidgetPosition = Field(default_factory=WidgetPosition)
    data_config: WidgetDataConfig = Field(default_factory=WidgetDataConfig)
    style_config: WidgetStyleConfig = Field(default_factory=WidgetStyleConfig)
    thresholds: WidgetThresholds = Field(default_factory=WidgetThresholds)
    custom_query: str | None = None
    query_params: dict = Field(default_factory=dict)
    comparison_enabled: bool = Field(default=False)
    comparison_period: str | None = None
    is_clickable: bool = Field(default=True)
    click_action: str | None = None
    drill_down_enabled: bool = Field(default=False)
    drill_down_config: dict = Field(default_factory=dict)
    cache_ttl_seconds: int = Field(default=300, ge=0, le=86400)


class WidgetUpdate(BaseModel):
    """Schema para atualizar Widget."""

    titulo: str | None = Field(None, min_length=1, max_length=200)
    subtitulo: str | None = Field(None, max_length=500)
    descricao: str | None = Field(None, max_length=2000)
    tipo: WidgetType | None = None
    tamanho: WidgetSize | None = None
    chart_type: ChartType | None = None
    data_source: DataSource | None = None
    position: WidgetPosition | None = None
    data_config: WidgetDataConfig | None = None
    style_config: WidgetStyleConfig | None = None
    thresholds: WidgetThresholds | None = None
    custom_query: str | None = None
    query_params: dict | None = None
    comparison_enabled: bool | None = None
    comparison_period: str | None = None
    is_visible: bool | None = None
    is_clickable: bool | None = None
    click_action: str | None = None
    drill_down_enabled: bool | None = None
    drill_down_config: dict | None = None
    cache_ttl_seconds: int | None = Field(None, ge=0, le=86400)


class WidgetResponse(WidgetBase):
    """Schema de resposta de Widget."""

    id: UUID
    dashboard_id: UUID
    # condominio_id/codigo nao existem na tabela financial_widgets (schema real);
    # o tenant e herdado do dashboard. Mantidos como opcionais p/ compatibilidade.
    condominio_id: UUID | None = None
    codigo: str | None = None
    position_x: int
    position_y: int
    width: int
    height: int
    order: int
    custom_query: str | None = None
    query_params: dict = Field(default_factory=dict)
    metric_field: str | None = None
    dimension_field: str | None = None
    time_field: str = "created_at"
    aggregation: str = "sum"
    group_by: list = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)
    date_range_days: int = 30
    comparison_enabled: bool = False
    comparison_period: str | None = None
    value_format: str = "currency"
    decimal_places: int = 2
    show_percentage: bool = False
    show_trend: bool = True
    show_legend: bool = True
    colors: list = Field(default_factory=list)
    icon: str | None = None
    threshold_warning: Decimal | None = None
    threshold_critical: Decimal | None = None
    threshold_success: Decimal | None = None
    is_visible: bool = True
    is_clickable: bool = True
    drill_down_enabled: bool = False
    is_loading: bool = False
    last_error: str | None = None
    last_updated_at: datetime | None = None
    cache_ttl_seconds: int = 300
    is_chart: bool = False
    is_kpi: bool = True
    needs_refresh: bool = False
    grid_position: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "query_params",
        "filters",
        "colors",
        "aggregation",
        "date_range_days",
        "cache_ttl_seconds",
        mode="before",
    )
    @classmethod
    def _coerce_nullable_defaults(cls, value, info):
        """Colunas reais nullable (query_config, agregacao, filtros, periodo_dias,
        cores, cache_ttl_segundos) podem estar NULL no banco; o ``default=`` do
        model so vale no INSERT. Aplica o default declarado quando vier None."""
        if value is None:
            field = cls.model_fields[info.field_name]
            return field.get_default(call_default_factory=True)
        return value


class WidgetData(BaseModel):
    """Dados carregados do widget."""

    widget_id: UUID
    data: Any
    value: Decimal | None = None
    previous_value: Decimal | None = None
    change_percent: Decimal | None = None
    trend: str | None = None
    labels: list = Field(default_factory=list)
    series: list = Field(default_factory=list)
    table_data: list = Field(default_factory=list)
    total_rows: int = 0
    color: str | None = None
    alert_level: str | None = None
    loaded_at: datetime
    cached: bool = False
    ttl_remaining: int = 0


class WidgetFilters(BaseModel):
    """Filtros para busca de Widgets."""

    dashboard_id: UUID | None = None
    tipo: WidgetType | None = None
    data_source: DataSource | None = None
    is_visible: bool | None = None
    search: str | None = Field(None, max_length=200)


class WidgetBulkUpdate(BaseModel):
    """Atualizacao em lote de widgets."""

    widgets: list[dict] = Field(..., min_length=1)


class WidgetClone(BaseModel):
    """Schema para clonar widget."""

    target_dashboard_id: UUID
    new_codigo: str | None = Field(None, max_length=50)
    new_titulo: str | None = Field(None, max_length=200)
