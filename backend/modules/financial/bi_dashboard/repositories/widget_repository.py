"""Repository de Widget de Dashboard Financeiro."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from modules.financial.bi_dashboard.models.dashboard_config import FinancialDashboard
from modules.financial.bi_dashboard.models.dashboard_widget import (
    DataSource,
    FinancialWidget,
)


def _scope_by_condominio(query, condominio_id):
    """Escopa widgets pelo tenant via join com financial_dashboards.

    A tabela financial_widgets nao possui condominio_id; o tenant e herdado
    do dashboard ao qual o widget pertence.
    """
    if condominio_id is None:
        return query
    return query.join(
        FinancialDashboard,
        FinancialWidget.dashboard_id == FinancialDashboard.id,
    ).filter(FinancialDashboard.condominio_id == condominio_id)
from modules.financial.bi_dashboard.schemas.widget_schemas import (
    WidgetCreate,
    WidgetFilters,
    WidgetUpdate,
)


class WidgetRepository:
    """Repository para operacoes de Widget."""

    def __init__(self, db: Session):
        """Inicializa repository."""
        self.db = db

    def create(
        self,
        condominio_id: UUID,
        data: WidgetCreate,
        created_by: UUID = None,
    ) -> FinancialWidget:
        """Cria novo widget."""
        widget = FinancialWidget(
            condominio_id=condominio_id,
            dashboard_id=data.dashboard_id,
            codigo=data.codigo,
            titulo=data.titulo,
            subtitulo=data.subtitulo,
            descricao=data.descricao,
            tipo=data.tipo,
            tamanho=data.tamanho,
            chart_type=data.chart_type,
            data_source=data.data_source,
            position_x=data.position.x,
            position_y=data.position.y,
            width=data.position.w,
            height=data.position.h,
            custom_query=data.custom_query,
            query_params=data.query_params,
            metric_field=data.data_config.metric_field,
            dimension_field=data.data_config.dimension_field,
            time_field=data.data_config.time_field,
            aggregation=data.data_config.aggregation,
            group_by=data.data_config.group_by,
            sort_by=data.data_config.sort_by,
            sort_order=data.data_config.sort_order,
            limit=data.data_config.limit,
            filters=data.data_config.filters,
            date_range_days=data.data_config.date_range_days,
            comparison_enabled=data.comparison_enabled,
            comparison_period=data.comparison_period,
            value_format=data.style_config.value_format,
            decimal_places=data.style_config.decimal_places,
            show_percentage=data.style_config.show_percentage,
            show_trend=data.style_config.show_trend,
            show_comparison=data.style_config.show_comparison,
            show_legend=data.style_config.show_legend,
            colors=data.style_config.colors,
            background_color=data.style_config.background_color,
            border_color=data.style_config.border_color,
            text_color=data.style_config.text_color,
            icon=data.style_config.icon,
            threshold_warning=data.thresholds.warning,
            threshold_critical=data.thresholds.critical,
            threshold_success=data.thresholds.success,
            invert_colors=data.thresholds.invert_colors,
            is_clickable=data.is_clickable,
            click_action=data.click_action,
            drill_down_enabled=data.drill_down_enabled,
            drill_down_config=data.drill_down_config,
            cache_ttl_seconds=data.cache_ttl_seconds,
            created_by=created_by,
        )
        self.db.add(widget)
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def get_by_id(
        self,
        widget_id: UUID,
        condominio_id: UUID = None,
    ) -> FinancialWidget | None:
        """Busca widget por ID."""
        query = self.db.query(FinancialWidget).filter(FinancialWidget.id == widget_id)
        query = _scope_by_condominio(query, condominio_id)
        return query.first()

    def get_by_dashboard(
        self,
        dashboard_id: UUID,
        condominio_id: UUID = None,
    ) -> list[FinancialWidget]:
        """Lista widgets de um dashboard."""
        query = self.db.query(FinancialWidget).filter(FinancialWidget.dashboard_id == dashboard_id)
        query = _scope_by_condominio(query, condominio_id)
        return query.order_by(
            FinancialWidget.position_y,
            FinancialWidget.position_x,
        ).all()

    def list_all(
        self,
        condominio_id: UUID,
        filters: WidgetFilters = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[FinancialWidget], int]:
        """Lista widgets com filtros."""
        query = _scope_by_condominio(self.db.query(FinancialWidget), condominio_id)

        if filters:
            if filters.dashboard_id:
                query = query.filter(FinancialWidget.dashboard_id == filters.dashboard_id)
            if filters.tipo:
                query = query.filter(FinancialWidget.tipo == filters.tipo)
            if filters.data_source:
                query = query.filter(FinancialWidget.data_source == filters.data_source)
            if filters.is_visible is not None:
                query = query.filter(FinancialWidget.is_visible == filters.is_visible)
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.filter(FinancialWidget.titulo.ilike(search_term))

        total = query.count()
        items = query.order_by(FinancialWidget.order).offset(skip).limit(limit).all()
        return items, total

    def update(
        self,
        widget: FinancialWidget,
        data: WidgetUpdate,
    ) -> FinancialWidget:
        """Atualiza widget."""
        update_data = data.model_dump(exclude_unset=True)

        # Processa posicao separadamente
        if "position" in update_data and update_data["position"]:
            pos = update_data.pop("position")
            widget.position_x = pos.get("x", widget.position_x)
            widget.position_y = pos.get("y", widget.position_y)
            widget.width = pos.get("w", widget.width)
            widget.height = pos.get("h", widget.height)

        # Processa data_config separadamente
        if "data_config" in update_data and update_data["data_config"]:
            dc = update_data.pop("data_config")
            for field, value in dc.items():
                if hasattr(widget, field):
                    setattr(widget, field, value)

        # Processa style_config separadamente
        if "style_config" in update_data and update_data["style_config"]:
            sc = update_data.pop("style_config")
            for field, value in sc.items():
                if hasattr(widget, field):
                    setattr(widget, field, value)

        # Processa thresholds separadamente
        if "thresholds" in update_data and update_data["thresholds"]:
            th = update_data.pop("thresholds")
            if "warning" in th:
                widget.threshold_warning = th["warning"]
            if "critical" in th:
                widget.threshold_critical = th["critical"]
            if "success" in th:
                widget.threshold_success = th["success"]
            if "invert_colors" in th:
                widget.invert_colors = th["invert_colors"]

        # Atualiza campos restantes
        for field, value in update_data.items():
            if hasattr(widget, field):
                setattr(widget, field, value)

        self.db.commit()
        self.db.refresh(widget)
        return widget

    def delete(self, widget: FinancialWidget) -> bool:
        """Deleta widget."""
        self.db.delete(widget)
        self.db.commit()
        return True

    def update_position(
        self,
        widget: FinancialWidget,
        x: int,
        y: int,
        w: int = None,
        h: int = None,
    ) -> FinancialWidget:
        """Atualiza posicao do widget."""
        widget.position_x = x
        widget.position_y = y
        if w is not None:
            widget.width = w
        if h is not None:
            widget.height = h
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def bulk_update_positions(
        self,
        widgets_data: list[dict],
        condominio_id: UUID,
    ) -> list[FinancialWidget]:
        """Atualiza posicoes em lote."""
        updated = []
        for wd in widgets_data:
            widget = self.get_by_id(wd["id"], condominio_id)
            if widget:
                widget.position_x = wd.get("x", widget.position_x)
                widget.position_y = wd.get("y", widget.position_y)
                widget.width = wd.get("w", widget.width)
                widget.height = wd.get("h", widget.height)
                updated.append(widget)

        self.db.commit()
        return updated

    def set_visibility(
        self,
        widget: FinancialWidget,
        is_visible: bool,
    ) -> FinancialWidget:
        """Define visibilidade do widget."""
        widget.is_visible = is_visible
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def mark_loaded(self, widget: FinancialWidget) -> FinancialWidget:
        """Marca widget como carregado."""
        widget.set_loaded()
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def set_error(
        self,
        widget: FinancialWidget,
        error: str,
    ) -> FinancialWidget:
        """Define erro no widget."""
        widget.set_error(error)
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def clone(
        self,
        widget: FinancialWidget,
        target_dashboard_id: UUID,
        new_codigo: str = None,
        new_titulo: str = None,
        created_by: UUID = None,
    ) -> FinancialWidget:
        """Clona widget para outro dashboard."""
        new_widget = FinancialWidget(
            condominio_id=widget.condominio_id,
            dashboard_id=target_dashboard_id,
            codigo=new_codigo or f"{widget.codigo}-COPY",
            titulo=new_titulo or f"{widget.titulo} (Copia)",
            subtitulo=widget.subtitulo,
            descricao=widget.descricao,
            tipo=widget.tipo,
            tamanho=widget.tamanho,
            chart_type=widget.chart_type,
            data_source=widget.data_source,
            position_x=0,
            position_y=0,
            width=widget.width,
            height=widget.height,
            custom_query=widget.custom_query,
            query_params=widget.query_params,
            metric_field=widget.metric_field,
            dimension_field=widget.dimension_field,
            time_field=widget.time_field,
            aggregation=widget.aggregation,
            group_by=widget.group_by,
            filters=widget.filters,
            date_range_days=widget.date_range_days,
            value_format=widget.value_format,
            decimal_places=widget.decimal_places,
            colors=widget.colors,
            icon=widget.icon,
            threshold_warning=widget.threshold_warning,
            threshold_critical=widget.threshold_critical,
            threshold_success=widget.threshold_success,
            cache_ttl_seconds=widget.cache_ttl_seconds,
            created_by=created_by,
        )
        self.db.add(new_widget)
        self.db.commit()
        self.db.refresh(new_widget)
        return new_widget

    def get_by_data_source(
        self,
        condominio_id: UUID,
        data_source: DataSource,
    ) -> list[FinancialWidget]:
        """Lista widgets por fonte de dados."""
        query = _scope_by_condominio(self.db.query(FinancialWidget), condominio_id)
        return query.filter(FinancialWidget.data_source == data_source).all()

    def get_needing_refresh(
        self,
        condominio_id: UUID,
    ) -> list[FinancialWidget]:
        """Lista widgets que precisam refresh."""
        datetime.utcnow()
        query = _scope_by_condominio(self.db.query(FinancialWidget), condominio_id)
        return query.filter(
            FinancialWidget.is_visible,
            FinancialWidget.last_updated_at
            < func.now() - func.cast(FinancialWidget.cache_ttl_seconds, type_=func.Integer),
        ).all()
