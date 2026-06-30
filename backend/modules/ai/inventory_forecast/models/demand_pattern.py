"""
Demand Pattern Models - AI Inventory Forecasting

Models para padroes de demanda identificados pela IA.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from core.database import Base


class PatternType(StrEnum):
    """Tipo de padrao de demanda."""

    CONSTANT = "constant"  # Demanda estavel
    TRENDING = "trending"  # Tendencia crescente ou decrescente
    SEASONAL = "seasonal"  # Padrao sazonal
    CYCLICAL = "cyclical"  # Ciclos longos
    IRREGULAR = "irregular"  # Demanda irregular
    INTERMITTENT = "intermittent"  # Demanda esporadica


class SeasonalityType(StrEnum):
    """Tipo de sazonalidade."""

    NONE = "none"
    WEEKLY = "weekly"  # Padrao semanal
    MONTHLY = "monthly"  # Padrao mensal
    QUARTERLY = "quarterly"  # Padrao trimestral
    YEARLY = "yearly"  # Padrao anual
    CUSTOM = "custom"  # Periodo personalizado


class TrendDirection(StrEnum):
    """Direcao da tendencia."""

    STABLE = "stable"
    INCREASING = "increasing"
    DECREASING = "decreasing"
    VOLATILE = "volatile"


class DemandPattern(Base):
    """
    Model para padroes de demanda identificados.

    Armazena analises de padroes para produtos.
    """

    __tablename__ = "inventory_demand_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Produto relacionado
    product_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    product_code = Column(String(50), nullable=False)
    product_name = Column(String(200), nullable=False)

    # Periodo analisado
    analysis_start_date = Column(Date, nullable=False)
    analysis_end_date = Column(Date, nullable=False)
    total_data_points = Column(Integer, default=0)

    # Classificacao do padrao
    pattern_type = Column(
        Enum(PatternType, values_callable=lambda x: [e.value for e in x]), default=PatternType.CONSTANT, nullable=False
    )
    pattern_confidence = Column(Float, default=0)  # 0-100

    # Sazonalidade
    seasonality_type = Column(
        Enum(SeasonalityType, values_callable=lambda x: [e.value for e in x]),
        default=SeasonalityType.NONE,
        nullable=False,
    )
    seasonality_strength = Column(Float, default=0)  # 0-1
    seasonal_periods = Column(ARRAY(Integer))  # Ex: [7, 30, 365]
    peak_periods = Column(JSONB, default=list)  # Periodos de pico

    # Tendencia
    trend_direction = Column(
        Enum(TrendDirection, values_callable=lambda x: [e.value for e in x]),
        default=TrendDirection.STABLE,
        nullable=False,
    )
    trend_slope = Column(Float, default=0)  # Taxa de variacao
    trend_strength = Column(Float, default=0)  # 0-1

    # Estatisticas de demanda
    avg_demand = Column(Float, default=0)
    std_demand = Column(Float, default=0)  # Desvio padrao
    cv_demand = Column(Float, default=0)  # Coeficiente de variacao
    median_demand = Column(Float, default=0)
    min_demand = Column(Float, default=0)
    max_demand = Column(Float, default=0)

    # Analise de variabilidade
    volatility_index = Column(Float, default=0)  # 0-100
    predictability_score = Column(Float, default=0)  # 0-100

    # Deteccao de anomalias
    anomalies_detected = Column(Integer, default=0)
    anomaly_dates = Column(JSONB, default=list)
    anomaly_impact = Column(Float, default=0)  # Impacto percentual

    # Ciclos identificados
    cycle_length_days = Column(Integer)
    cycle_amplitude = Column(Float)

    # Dias da semana com maior demanda
    weekday_distribution = Column(JSONB, default=dict)
    # Ex: {"monday": 0.12, "tuesday": 0.15, ...}

    # Meses com maior demanda
    monthly_distribution = Column(JSONB, default=dict)
    # Ex: {"january": 0.08, "february": 0.07, ...}

    # Recomendacoes baseadas no padrao
    recommended_model = Column(String(50))  # Modelo recomendado para previsao
    recommended_safety_stock_days = Column(Integer)
    recommended_review_period_days = Column(Integer)

    # Metadados
    analyzed_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Flags
    is_active = Column(Boolean, default=True, nullable=False)
    needs_update = Column(Boolean, default=False)
    last_validation_date = Column(Date)

    # Notas
    notes = Column(Text)
    insights = Column(JSONB, default=list)  # Lista de insights gerados

    def __repr__(self) -> str:
        return f"<DemandPattern {self.product_code}: {self.pattern_type.value}>"

    @property
    def is_predictable(self) -> bool:
        """Retorna se a demanda e previsivel."""
        return self.predictability_score >= 60

    @property
    def is_seasonal(self) -> bool:
        """Retorna se ha sazonalidade significativa."""
        return self.seasonality_type != SeasonalityType.NONE and self.seasonality_strength >= 0.3

    @property
    def is_trending(self) -> bool:
        """Retorna se ha tendencia significativa."""
        return self.trend_direction != TrendDirection.STABLE and self.trend_strength >= 0.3
