"""
ExecutiveKPI Model - KPIs Executivos
Sprint 34: Relatórios Gerenciais
"""
# pylint: disable=too-many-return-statements

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class KPICategory(str, enum.Enum):
    """Categorias de KPI."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    COMMERCIAL = "commercial"
    HR = "hr"
    CUSTOMER = "customer"
    QUALITY = "quality"
    COMPLIANCE = "compliance"
    STRATEGIC = "strategic"


class KPIType(str, enum.Enum):
    """Tipos de KPI."""

    ABSOLUTE = "absolute"
    PERCENTAGE = "percentage"
    RATIO = "ratio"
    CURRENCY = "currency"
    COUNT = "count"
    AVERAGE = "average"
    INDEX = "index"
    GROWTH = "growth"


class KPIDirection(str, enum.Enum):
    """Direção desejada do KPI."""

    INCREASE = "increase"
    DECREASE = "decrease"
    MAINTAIN = "maintain"
    RANGE = "range"


class KPIStatus(str, enum.Enum):
    """Status do KPI."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"
    DEPRECATED = "deprecated"


class KPIAlertLevel(str, enum.Enum):
    """Nível de alerta do KPI."""

    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCELLENT = "excellent"


class AggregationPeriod(str, enum.Enum):
    """Período de agregação."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class ExecutiveKPI(Base):
    """KPI executivo para dashboards gerenciais."""

    __tablename__ = "executive_kpis"

    # Identificação
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Classificação
    category = Column(Enum(KPICategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    kpi_type = Column(Enum(KPIType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    direction = Column(
        Enum(KPIDirection, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=KPIDirection.INCREASE,
    )
    status = Column(
        Enum(KPIStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=KPIStatus.ACTIVE
    )

    # Unidade e formato
    unit = Column(String(20), nullable=True)
    prefix = Column(String(10), nullable=True)
    suffix = Column(String(10), nullable=True)
    decimal_places = Column(Integer, nullable=False, default=2)
    display_format = Column(String(50), nullable=True)

    # Valores
    current_value = Column(Float, nullable=True)
    previous_value = Column(Float, nullable=True)
    target_value = Column(Float, nullable=True)
    baseline_value = Column(Float, nullable=True)

    # Limites
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    warning_threshold_low = Column(Float, nullable=True)
    warning_threshold_high = Column(Float, nullable=True)
    critical_threshold_low = Column(Float, nullable=True)
    critical_threshold_high = Column(Float, nullable=True)

    # Período
    aggregation_period = Column(Enum(AggregationPeriod), nullable=False, default=AggregationPeriod.MONTHLY)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)

    # Cálculo
    calculation_formula = Column(Text, nullable=True)
    data_source = Column(String(200), nullable=True)
    data_query = Column(Text, nullable=True)
    calculation_config = Column(JSONB, nullable=True)

    # Status atual
    alert_level = Column(Enum(KPIAlertLevel), nullable=False, default=KPIAlertLevel.NORMAL)
    trend = Column(String(20), nullable=True)
    variance = Column(Float, nullable=True)
    variance_percentage = Column(Float, nullable=True)

    # Histórico
    historical_values = Column(JSONB, nullable=True)
    last_12_months = Column(JSONB, nullable=True)

    # Responsáveis
    owner_id = Column(UUID(as_uuid=True), nullable=True)
    owner_name = Column(String(200), nullable=True)
    department = Column(String(100), nullable=True)

    # Visualização
    chart_type = Column(String(50), nullable=True, default="gauge")
    color_scheme = Column(JSONB, nullable=True)
    display_order = Column(Integer, nullable=True)
    visible_on_dashboard = Column(Boolean, nullable=False, default=True)

    # Alertas
    alerts_enabled = Column(Boolean, nullable=False, default=True)
    alert_recipients = Column(JSONB, nullable=True)
    last_alert_at = Column(DateTime, nullable=True)
    alert_frequency = Column(String(50), nullable=True)

    # Metas
    yearly_target = Column(Float, nullable=True)
    quarterly_targets = Column(JSONB, nullable=True)
    monthly_targets = Column(JSONB, nullable=True)

    # Metadados
    tags = Column(JSONB, nullable=True)
    related_kpis = Column(JSONB, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Auditoria
    last_calculated_at = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    ativo = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_executive_kpis_tenant_code", "tenant_id", "code", unique=True),
        Index("ix_executive_kpis_category", "category"),
        Index("ix_executive_kpis_status", "status"),
        Index("ix_executive_kpis_alert_level", "alert_level"),
    )

    def update_value(
        self, new_value: float, period_start: datetime | None = None, period_end: datetime | None = None
    ) -> None:
        """Atualiza o valor do KPI."""
        self.previous_value = self.current_value
        self.current_value = new_value

        if period_start:
            self.period_start = period_start
        if period_end:
            self.period_end = period_end

        self._calculate_variance()
        self._determine_trend()
        self._update_alert_level()
        self._add_to_history()

        self.last_calculated_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def _calculate_variance(self) -> None:
        """Calcula variância em relação à meta."""
        if self.target_value and self.current_value is not None:
            self.variance = self.current_value - self.target_value
            if self.target_value != 0:
                self.variance_percentage = (self.variance / self.target_value) * 100

    def _determine_trend(self) -> None:
        """Determina tendência."""
        if self.previous_value is None or self.current_value is None:
            self.trend = "stable"
            return

        diff = self.current_value - self.previous_value
        if abs(diff) < 0.01:
            self.trend = "stable"
        elif diff > 0:
            self.trend = "up"
        else:
            self.trend = "down"

    def _update_alert_level(self) -> None:
        """Atualiza nível de alerta baseado nos thresholds."""
        if self.current_value is None:
            self.alert_level = KPIAlertLevel.NORMAL
            return

        value = self.current_value

        # Verifica critical
        if self.critical_threshold_low and value < self.critical_threshold_low:
            self.alert_level = KPIAlertLevel.CRITICAL
            return
        if self.critical_threshold_high and value > self.critical_threshold_high:
            self.alert_level = KPIAlertLevel.CRITICAL
            return

        # Verifica warning
        if self.warning_threshold_low and value < self.warning_threshold_low:
            self.alert_level = KPIAlertLevel.WARNING
            return
        if self.warning_threshold_high and value > self.warning_threshold_high:
            self.alert_level = KPIAlertLevel.WARNING
            return

        # Verifica excelente (atingiu meta com folga)
        if self.target_value:
            if self.direction == KPIDirection.INCREASE:
                if value >= self.target_value * 1.1:
                    self.alert_level = KPIAlertLevel.EXCELLENT
                    return
            elif self.direction == KPIDirection.DECREASE:
                if value <= self.target_value * 0.9:
                    self.alert_level = KPIAlertLevel.EXCELLENT
                    return

        self.alert_level = KPIAlertLevel.NORMAL

    def _add_to_history(self) -> None:
        """Adiciona valor ao histórico."""
        if not self.historical_values:
            self.historical_values = []

        entry = {
            "value": self.current_value,
            "date": datetime.utcnow().isoformat(),
            "target": self.target_value,
            "alert_level": self.alert_level.value,
        }
        self.historical_values.append(entry)

        # Mantém últimos 365 registros
        if len(self.historical_values) > 365:
            self.historical_values = self.historical_values[-365:]

    def set_target(
        self,
        target: float,
        yearly: float | None = None,
        quarterly: list[float] | None = None,
        monthly: list[float] | None = None,
    ) -> None:
        """Define metas."""
        self.target_value = target
        if yearly:
            self.yearly_target = yearly
        if quarterly:
            self.quarterly_targets = quarterly
        if monthly:
            self.monthly_targets = monthly
        self.updated_at = datetime.utcnow()

    def set_thresholds(
        self,
        warning_low: float | None = None,
        warning_high: float | None = None,
        critical_low: float | None = None,
        critical_high: float | None = None,
    ) -> None:
        """Define thresholds de alerta."""
        self.warning_threshold_low = warning_low
        self.warning_threshold_high = warning_high
        self.critical_threshold_low = critical_low
        self.critical_threshold_high = critical_high
        self._update_alert_level()
        self.updated_at = datetime.utcnow()

    def activate(self) -> None:
        """Ativa o KPI."""
        self.status = KPIStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Desativa o KPI."""
        self.status = KPIStatus.INACTIVE
        self.updated_at = datetime.utcnow()

    def deprecate(self) -> None:
        """Deprecia o KPI."""
        self.status = KPIStatus.DEPRECATED
        self.visible_on_dashboard = False
        self.updated_at = datetime.utcnow()

    @property
    def is_active(self) -> bool:
        """Verifica se está ativo."""
        return self.status == KPIStatus.ACTIVE and self.ativo

    @property
    def is_on_target(self) -> bool:
        """Verifica se está na meta."""
        if not self.target_value or self.current_value is None:
            return False

        if self.direction == KPIDirection.INCREASE:
            return self.current_value >= self.target_value
        elif self.direction == KPIDirection.DECREASE:
            return self.current_value <= self.target_value
        elif self.direction == KPIDirection.MAINTAIN:
            tolerance = self.target_value * 0.05
            return abs(self.current_value - self.target_value) <= tolerance
        return False

    @property
    def target_achievement(self) -> float | None:
        """Percentual de atingimento da meta."""
        if not self.target_value or self.current_value is None:
            return None

        if self.direction == KPIDirection.INCREASE:
            return (self.current_value / self.target_value) * 100
        elif self.direction == KPIDirection.DECREASE:
            if self.current_value == 0:
                return 100.0
            return (self.target_value / self.current_value) * 100
        return 100.0

    @property
    def formatted_value(self) -> str:
        """Valor formatado para exibição."""
        if self.current_value is None:
            return "N/A"

        value = round(self.current_value, self.decimal_places)
        formatted = f"{value:,.{self.decimal_places}f}"

        if self.prefix:
            formatted = f"{self.prefix}{formatted}"
        if self.suffix:
            formatted = f"{formatted}{self.suffix}"
        if self.unit:
            formatted = f"{formatted} {self.unit}"

        return formatted

    @property
    def needs_attention(self) -> bool:
        """Verifica se precisa de atenção."""
        return self.alert_level in [KPIAlertLevel.WARNING, KPIAlertLevel.CRITICAL]

    @property
    def is_improving(self) -> bool:
        """Verifica se está melhorando."""
        if self.direction == KPIDirection.INCREASE:
            return self.trend == "up"
        elif self.direction == KPIDirection.DECREASE:
            return self.trend == "down"
        return self.trend == "stable"
