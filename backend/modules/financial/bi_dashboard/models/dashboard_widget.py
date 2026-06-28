"""Model de Widget de Dashboard Financeiro.

NOTA DE ALINHAMENTO (schema real):
A tabela ``financial_widgets`` foi criada pela migration sprint30 com colunas em
PT-BR e NAO possui ``condominio_id`` (o tenant vem do ``financial_dashboards``).
Este model mapeia os atributos Python (em ingles, usados pelo restante do codigo)
para as colunas reais via ``Column("nome_real", ...)``. Atributos que nao possuem
coluna real correspondente sao expostos como atributos Python simples (defaults),
apenas para serializacao/escrita em memoria, sem serem incluidos no SELECT.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from core.models.base import Base


def _enum_values(enum_cls):
    """Persiste/le os enums pelo VALUE (lowercase, igual ao banco)."""
    return [member.value for member in enum_cls]


class WidgetType(StrEnum):
    """Tipo de widget (valores alinhados ao enum Postgres ``widget_type``)."""

    CARD = "card"
    CHART = "chart"
    TABLE = "table"
    GAUGE = "gauge"
    MAP = "map"
    LIST = "list"
    TEXT = "text"
    IMAGE = "image"
    KPI_CARD = "kpi"
    FILTER = "filter"
    CUSTOM = "custom"


class WidgetSize(StrEnum):
    """Tamanho do widget (enum Postgres ``widget_size``)."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    EXTRA_LARGE = "xlarge"
    FULL_WIDTH = "full"


class ChartType(StrEnum):
    """Tipo de grafico (enum Postgres ``chart_type``)."""

    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    DONUT = "donut"
    AREA = "area"
    SCATTER = "scatter"
    BUBBLE = "bubble"
    HEATMAP = "heatmap"
    TREEMAP = "treemap"
    FUNNEL = "funnel"
    RADAR = "radar"
    WATERFALL = "waterfall"
    CANDLESTICK = "candlestick"
    GAUGE = "gauge"
    SPARKLINE = "sparkline"
    COMBO = "combo"


class DataSource(StrEnum):
    """Fonte de dados do widget (enum Postgres ``data_source``)."""

    CASH_FLOW = "cash_flow"
    ACCOUNTS_PAYABLE = "accounts_payable"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    BANK_ACCOUNTS = "bank_accounts"
    PURCHASES = "purchases"
    INVENTORY = "inventory"
    ACCOUNTING = "accounting"
    FISCAL = "fiscal"
    COSTING = "costing"
    BUDGET = "budget"
    CUSTOM_QUERY = "custom_query"
    EXTERNAL_API = "external_api"


class FinancialWidget(Base):
    """Widget de Dashboard Financeiro (mapeado para o schema real)."""

    __tablename__ = "financial_widgets"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    dashboard_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_dashboards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identificacao
    titulo = Column(String(200), nullable=False)
    descricao = Column(Text)

    # Tipo e Aparencia
    tipo = Column(
        SQLEnum(
            WidgetType,
            name="widget_type",
            create_type=False,
            values_callable=_enum_values,
        ),
        default=WidgetType.KPI_CARD,
        nullable=False,
    )
    tamanho = Column(
        SQLEnum(
            WidgetSize,
            name="widget_size",
            create_type=False,
            values_callable=_enum_values,
        ),
        default=WidgetSize.MEDIUM,
        nullable=False,
    )
    chart_type = Column(
        "tipo_grafico",
        SQLEnum(
            ChartType,
            name="chart_type",
            create_type=False,
            values_callable=_enum_values,
        ),
    )

    # Posicionamento (Grid Layout) -> colunas PT-BR reais
    position_x = Column("posicao_x", Integer, default=0, nullable=False)
    position_y = Column("posicao_y", Integer, default=0, nullable=False)
    width = Column("largura", Integer, default=4, nullable=False)
    height = Column("altura", Integer, default=3, nullable=False)
    order = Column(Integer, default=0)

    # Fonte de Dados
    data_source = Column(
        "fonte_dados",
        SQLEnum(
            DataSource,
            name="data_source",
            create_type=False,
            values_callable=_enum_values,
        ),
    )
    query_params = Column("query_config", JSONB, default=dict)

    # Configuracao de Dados
    aggregation = Column("agregacao", String(50), default="sum")
    limit = Column("limite_registros", Integer, default=10)

    # Filtros
    filters = Column("filtros", JSONB, default=dict)
    date_range_days = Column("periodo_dias", Integer, default=30)
    comparison_enabled = Column("comparar_periodo_anterior", Boolean, default=False)

    # Cores e Estilo
    colors = Column("cores", JSONB, default=list)

    # Estado
    is_visible = Column("is_visivel", Boolean, default=True, nullable=False)
    is_clickable = Column("is_interativo", Boolean, default=True, nullable=False)
    last_error = Column("ultimo_erro", Text)
    last_updated_at = Column("ultimo_refresh", DateTime)
    cache_ttl_seconds = Column("cache_ttl_segundos", Integer, default=300)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    dashboard = relationship("FinancialDashboard", back_populates="widgets")

    # ------------------------------------------------------------------
    # Atributos sem coluna real (defaults para serializacao/escrita).
    # O tenant do widget e herdado do dashboard (financial_dashboards).
    # ------------------------------------------------------------------
    condominio_id = None
    codigo = None
    subtitulo = None
    custom_query = None
    metric_field = None
    dimension_field = None
    time_field = "created_at"
    group_by = []
    sort_by = None
    sort_order = "desc"
    comparison_period = None
    value_format = "currency"
    decimal_places = 2
    show_percentage = False
    show_trend = True
    show_comparison = False
    show_legend = True
    background_color = None
    border_color = None
    text_color = None
    icon = None
    threshold_warning = None
    threshold_critical = None
    threshold_success = None
    invert_colors = False
    click_action = None
    drill_down_enabled = False
    drill_down_config = {}
    is_loading = False
    created_by = None

    def __repr__(self) -> str:
        """Representacao do widget."""
        return f"<FinancialWidget {self.id}: {self.titulo}>"

    @property
    def is_chart(self) -> bool:
        """Verifica se widget eh um grafico."""
        return self.tipo == WidgetType.CHART

    @property
    def is_kpi(self) -> bool:
        """Verifica se widget eh um KPI card."""
        return self.tipo == WidgetType.KPI_CARD

    @property
    def needs_refresh(self) -> bool:
        """Verifica se widget precisa refresh."""
        if not self.last_updated_at:
            return True
        elapsed = (datetime.utcnow() - self.last_updated_at).total_seconds()
        return elapsed > (self.cache_ttl_seconds or 300)

    @property
    def grid_position(self) -> dict:
        """Retorna posicao no grid."""
        return {
            "x": self.position_x,
            "y": self.position_y,
            "w": self.width,
            "h": self.height,
        }

    def move_to(self, x: int, y: int) -> None:
        """Move widget para nova posicao."""
        self.position_x = x
        self.position_y = y

    def resize(self, width: int, height: int) -> None:
        """Redimensiona widget."""
        self.width = width
        self.height = height

    def set_error(self, error: str) -> None:
        """Define erro no widget."""
        self.is_loading = False
        self.last_error = error

    def set_loaded(self) -> None:
        """Marca widget como carregado."""
        self.is_loading = False
        self.last_error = None
        self.last_updated_at = datetime.utcnow()

    def get_color_for_value(self, value: Decimal) -> str:
        """Retorna cor baseada nos thresholds."""
        if self.threshold_critical and value <= self.threshold_critical:
            return "#f44336" if not self.invert_colors else "#4caf50"
        if self.threshold_warning and value <= self.threshold_warning:
            return "#ff9800"
        if self.threshold_success and value >= self.threshold_success:
            return "#4caf50" if not self.invert_colors else "#f44336"
        return "#2196f3"
