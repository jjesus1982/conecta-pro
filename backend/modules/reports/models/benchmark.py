"""
Benchmark Model - Benchmarks de Mercado
Sprint 34: Relatórios Gerenciais
"""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class BenchmarkCategory(str, enum.Enum):
    """Categorias de benchmark."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    COMMERCIAL = "commercial"
    HR = "hr"
    QUALITY = "quality"
    CUSTOMER = "customer"
    INDUSTRY = "industry"
    MARKET = "market"


class BenchmarkType(str, enum.Enum):
    """Tipos de benchmark."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    INDUSTRY = "industry"
    COMPETITOR = "competitor"
    BEST_PRACTICE = "best_practice"
    HISTORICAL = "historical"


class BenchmarkSource(str, enum.Enum):
    """Fonte do benchmark."""

    INTERNAL_DATA = "internal_data"
    INDUSTRY_REPORT = "industry_report"
    MARKET_RESEARCH = "market_research"
    GOVERNMENT = "government"
    ASSOCIATION = "association"
    CONSULTANT = "consultant"
    PUBLIC_DATA = "public_data"
    CUSTOM = "custom"


class BenchmarkStatus(str, enum.Enum):
    """Status do benchmark."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"
    OUTDATED = "outdated"
    ARCHIVED = "archived"


class ComparisonResult(str, enum.Enum):
    """Resultado da comparação."""

    ABOVE = "above"
    BELOW = "below"
    AT_PAR = "at_par"
    EXCELLENT = "excellent"
    POOR = "poor"


class Benchmark(Base):
    """Benchmark de mercado para comparação."""

    __tablename__ = "benchmarks"

    # Identificação
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Classificação
    category = Column(Enum(BenchmarkCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    benchmark_type = Column(Enum(BenchmarkType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    source = Column(Enum(BenchmarkSource, values_callable=lambda x: [e.value for e in x]), nullable=False)
    status = Column(
        Enum(BenchmarkStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BenchmarkStatus.ACTIVE,
    )

    # Setor/Indústria
    industry = Column(String(100), nullable=True)
    sub_industry = Column(String(100), nullable=True)
    market_segment = Column(String(100), nullable=True)
    geographic_region = Column(String(100), nullable=True)
    company_size = Column(String(50), nullable=True)

    # Valores de referência
    reference_value = Column(Float, nullable=False)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    median_value = Column(Float, nullable=True)
    average_value = Column(Float, nullable=True)
    percentile_25 = Column(Float, nullable=True)
    percentile_75 = Column(Float, nullable=True)
    percentile_90 = Column(Float, nullable=True)

    # Unidade
    unit = Column(String(20), nullable=True)
    decimal_places = Column(Integer, nullable=False, default=2)
    is_percentage = Column(Boolean, nullable=False, default=False)
    is_currency = Column(Boolean, nullable=False, default=False)
    currency_code = Column(String(3), nullable=True)

    # Período de referência
    reference_year = Column(Integer, nullable=True)
    reference_quarter = Column(Integer, nullable=True)
    reference_month = Column(Integer, nullable=True)
    reference_date = Column(DateTime, nullable=True)
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)

    # Comparação atual
    current_company_value = Column(Float, nullable=True)
    comparison_result = Column(Enum(ComparisonResult, values_callable=lambda x: [e.value for e in x]), nullable=True)
    deviation = Column(Float, nullable=True)
    deviation_percentage = Column(Float, nullable=True)
    percentile_rank = Column(Float, nullable=True)

    # Metas baseadas no benchmark
    target_value = Column(Float, nullable=True)
    improvement_target = Column(Float, nullable=True)
    improvement_deadline = Column(DateTime, nullable=True)

    # Histórico
    historical_values = Column(JSONB, nullable=True)
    trend = Column(String(20), nullable=True)
    year_over_year_change = Column(Float, nullable=True)

    # Fonte de dados
    source_name = Column(String(200), nullable=True)
    source_url = Column(String(500), nullable=True)
    source_report = Column(String(200), nullable=True)
    source_date = Column(DateTime, nullable=True)
    sample_size = Column(Integer, nullable=True)

    # KPIs relacionados
    related_kpi_ids = Column(JSONB, nullable=True)
    calculation_method = Column(Text, nullable=True)

    # Alertas
    alert_if_below = Column(Float, nullable=True)
    alert_if_above = Column(Float, nullable=True)
    alerts_enabled = Column(Boolean, nullable=False, default=True)

    # Visualização
    display_order = Column(Integer, nullable=True)
    visible_on_dashboard = Column(Boolean, nullable=False, default=True)
    color_code = Column(String(7), nullable=True)
    icon = Column(String(50), nullable=True)

    # Metadados
    tags = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Auditoria
    last_updated_from_source = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    ativo = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_benchmarks_tenant_code", "tenant_id", "code", unique=True),
        Index("ix_benchmarks_category", "category"),
        Index("ix_benchmarks_type", "benchmark_type"),
        Index("ix_benchmarks_industry", "industry"),
        Index("ix_benchmarks_status", "status"),
    )

    def update_reference_value(self, new_value: float, source_date: datetime | None = None) -> None:
        """Atualiza o valor de referência."""
        # Guarda no histórico
        self._add_to_history(self.reference_value)

        self.reference_value = new_value
        if source_date:
            self.source_date = source_date
        self.last_updated_from_source = datetime.utcnow()
        self._recalculate_comparison()
        self.updated_at = datetime.utcnow()

    def update_company_value(self, company_value: float) -> None:
        """Atualiza o valor da empresa e recalcula comparação."""
        self.current_company_value = company_value
        self._recalculate_comparison()
        self.updated_at = datetime.utcnow()

    def _recalculate_comparison(self) -> None:
        """Recalcula a comparação."""
        if self.current_company_value is None or not self.reference_value:
            self.comparison_result = None
            self.deviation = None
            self.deviation_percentage = None
            return

        self.deviation = self.current_company_value - self.reference_value
        self.deviation_percentage = (self.deviation / self.reference_value) * 100

        # Determina resultado
        tolerance = 0.05  # 5%
        if abs(self.deviation_percentage) <= tolerance * 100:
            self.comparison_result = ComparisonResult.AT_PAR
        elif self.deviation_percentage > 0:
            if self.deviation_percentage > 20:
                self.comparison_result = ComparisonResult.EXCELLENT
            else:
                self.comparison_result = ComparisonResult.ABOVE
        else:
            if self.deviation_percentage < -20:
                self.comparison_result = ComparisonResult.POOR
            else:
                self.comparison_result = ComparisonResult.BELOW

        # Calcula percentile rank se tiver dados de distribuição
        self._calculate_percentile_rank()

    def _calculate_percentile_rank(self) -> None:
        """Calcula em qual percentil a empresa está."""
        if self.current_company_value is None:
            self.percentile_rank = None
            return

        value = self.current_company_value

        # Estimativa simples baseada nos percentis disponíveis
        if self.percentile_25 and value <= self.percentile_25:
            self.percentile_rank = 25.0 * (value / self.percentile_25) if self.percentile_25 else 0
        elif self.median_value and value <= self.median_value:
            if self.percentile_25:
                progress = (value - self.percentile_25) / (self.median_value - self.percentile_25)
                self.percentile_rank = 25.0 + (25.0 * progress)
            else:
                self.percentile_rank = 50.0 * (value / self.median_value)
        elif self.percentile_75 and value <= self.percentile_75:
            if self.median_value:
                progress = (value - self.median_value) / (self.percentile_75 - self.median_value)
                self.percentile_rank = 50.0 + (25.0 * progress)
            else:
                self.percentile_rank = 75.0
        elif self.percentile_90 and value <= self.percentile_90:
            if self.percentile_75:
                progress = (value - self.percentile_75) / (self.percentile_90 - self.percentile_75)
                self.percentile_rank = 75.0 + (15.0 * progress)
            else:
                self.percentile_rank = 90.0
        else:
            self.percentile_rank = 95.0

    def _add_to_history(self, value: float) -> None:
        """Adiciona valor ao histórico."""
        if not self.historical_values:
            self.historical_values = []

        entry = {
            "value": value,
            "date": datetime.utcnow().isoformat(),
            "year": self.reference_year,
            "quarter": self.reference_quarter,
        }
        self.historical_values.append(entry)

        # Calcula tendência
        if len(self.historical_values) >= 2:
            prev = self.historical_values[-2]["value"]
            if prev != 0:
                change = ((value - prev) / prev) * 100
                self.year_over_year_change = change
                if change > 1:
                    self.trend = "increasing"
                elif change < -1:
                    self.trend = "decreasing"
                else:
                    self.trend = "stable"

    def set_distribution(
        self,
        minimum: float | None = None,
        percentile_25: float | None = None,
        median: float | None = None,
        percentile_75: float | None = None,
        percentile_90: float | None = None,
        maximum: float | None = None,
        average: float | None = None,
    ) -> None:
        """Define a distribuição do benchmark."""
        self.min_value = minimum
        self.percentile_25 = percentile_25
        self.median_value = median
        self.percentile_75 = percentile_75
        self.percentile_90 = percentile_90
        self.max_value = maximum
        self.average_value = average
        self._recalculate_comparison()
        self.updated_at = datetime.utcnow()

    def set_target_from_benchmark(self, percentile: int = 75, deadline: datetime | None = None) -> None:
        """Define meta baseada em percentil do benchmark."""
        if percentile == 25 and self.percentile_25:
            self.target_value = self.percentile_25
        elif percentile == 50 and self.median_value:
            self.target_value = self.median_value
        elif percentile == 75 and self.percentile_75:
            self.target_value = self.percentile_75
        elif percentile == 90 and self.percentile_90:
            self.target_value = self.percentile_90
        else:
            self.target_value = self.reference_value

        if self.current_company_value and self.target_value:
            self.improvement_target = self.target_value - self.current_company_value

        if deadline:
            self.improvement_deadline = deadline

        self.updated_at = datetime.utcnow()

    def activate(self) -> None:
        """Ativa o benchmark."""
        self.status = BenchmarkStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Desativa o benchmark."""
        self.status = BenchmarkStatus.INACTIVE
        self.updated_at = datetime.utcnow()

    def mark_outdated(self) -> None:
        """Marca como desatualizado."""
        self.status = BenchmarkStatus.OUTDATED
        self.updated_at = datetime.utcnow()

    def archive(self) -> None:
        """Arquiva o benchmark."""
        self.status = BenchmarkStatus.ARCHIVED
        self.visible_on_dashboard = False
        self.ativo = False
        self.updated_at = datetime.utcnow()

    @property
    def is_active(self) -> bool:
        """Verifica se está ativo."""
        return self.status == BenchmarkStatus.ACTIVE and self.ativo

    @property
    def is_valid(self) -> bool:
        """Verifica se ainda é válido."""
        now = datetime.utcnow()
        if self.valid_until and now > self.valid_until:
            return False
        return self.status == BenchmarkStatus.ACTIVE

    @property
    def is_above_benchmark(self) -> bool:
        """Verifica se está acima do benchmark."""
        return self.comparison_result in [ComparisonResult.ABOVE, ComparisonResult.EXCELLENT]

    @property
    def is_below_benchmark(self) -> bool:
        """Verifica se está abaixo do benchmark."""
        return self.comparison_result in [ComparisonResult.BELOW, ComparisonResult.POOR]

    @property
    def needs_improvement(self) -> bool:
        """Verifica se precisa de melhoria."""
        if self.target_value and self.current_company_value:
            return self.current_company_value < self.target_value
        return self.is_below_benchmark

    @property
    def formatted_reference(self) -> str:
        """Valor de referência formatado."""
        value = round(self.reference_value, self.decimal_places)
        if self.is_percentage:
            return f"{value}%"
        if self.is_currency and self.currency_code:
            return f"{self.currency_code} {value:,.{self.decimal_places}f}"
        if self.unit:
            return f"{value:,.{self.decimal_places}f} {self.unit}"
        return f"{value:,.{self.decimal_places}f}"

    @property
    def gap_to_target(self) -> float | None:
        """Gap para a meta."""
        if self.target_value and self.current_company_value:
            return self.target_value - self.current_company_value
        return None

    @property
    def gap_percentage(self) -> float | None:
        """Gap percentual para a meta."""
        if self.target_value and self.current_company_value and self.target_value != 0:
            return ((self.target_value - self.current_company_value) / self.target_value) * 100
        return None
