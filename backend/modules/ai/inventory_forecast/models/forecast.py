"""
Forecast Models - AI Inventory Forecasting

Models para previsao de demanda e estoque.
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
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class ForecastStatus(StrEnum):
    """Status da previsao."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ForecastType(StrEnum):
    """Tipo de previsao."""

    DEMAND = "demand"  # Previsao de demanda
    REORDER = "reorder"  # Ponto de reposicao
    SEASONAL = "seasonal"  # Analise sazonal
    TREND = "trend"  # Analise de tendencia


class Forecast(Base):
    """
    Model principal de previsao de estoque.

    Armazena previsoes de demanda para produtos especificos.
    """

    __tablename__ = "inventory_forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Produto relacionado (referencia ao modulo de estoque)
    product_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    product_code = Column(String(50), nullable=False)
    product_name = Column(String(200), nullable=False)

    # Configuracao da previsao
    forecast_type = Column(
        Enum(ForecastType, values_callable=lambda x: [e.value for e in x]), default=ForecastType.DEMAND, nullable=False
    )
    status = Column(
        Enum(ForecastStatus, values_callable=lambda x: [e.value for e in x]),
        default=ForecastStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Periodo da previsao
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    horizon_days = Column(Integer, default=30)  # Dias de previsao

    # Dados de entrada
    historical_days = Column(Integer, default=365)  # Dias de historico usado
    data_points = Column(Integer, default=0)  # Quantidade de pontos de dados

    # Modelo utilizado
    model_type = Column(String(50), default="prophet")  # prophet, arima, exp_smoothing
    model_params = Column(JSONB, default=dict)

    # Metricas de qualidade
    mae = Column(Float)  # Mean Absolute Error
    mape = Column(Float)  # Mean Absolute Percentage Error
    rmse = Column(Float)  # Root Mean Square Error
    confidence_score = Column(Float)  # 0-100

    # Resultados agregados
    total_predicted_demand = Column(Float, default=0)
    avg_daily_demand = Column(Float, default=0)
    peak_demand = Column(Float, default=0)
    peak_demand_date = Column(Date)
    min_demand = Column(Float, default=0)
    min_demand_date = Column(Date)

    # Recomendacoes
    suggested_reorder_point = Column(Float)
    suggested_reorder_quantity = Column(Float)
    suggested_safety_stock = Column(Float)

    # Metadados
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)
    expires_at = Column(DateTime)

    # Flags
    is_active = Column(Boolean, default=True, nullable=False)
    is_automated = Column(Boolean, default=False)  # Gerado automaticamente

    # Notas e observacoes
    notes = Column(Text)
    error_message = Column(Text)

    # Relacionamentos
    results = relationship("ForecastResult", back_populates="forecast", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Forecast {self.product_code} ({self.start_date} - {self.end_date})>"


class ForecastResult(Base):
    """
    Resultado detalhado da previsao por periodo.

    Armazena previsao diaria/semanal/mensal.
    """

    __tablename__ = "inventory_forecast_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relacionamento com previsao
    forecast_id = Column(
        UUID(as_uuid=True), ForeignKey("inventory_forecasts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Periodo
    date = Column(Date, nullable=False, index=True)
    period_type = Column(String(20), default="daily")  # daily, weekly, monthly

    # Valores previstos
    predicted_demand = Column(Float, nullable=False)
    lower_bound = Column(Float)  # Limite inferior (intervalo de confianca)
    upper_bound = Column(Float)  # Limite superior
    confidence_level = Column(Float, default=0.95)  # 95% por padrao

    # Valores reais (preenchidos posteriormente para validacao)
    actual_demand = Column(Float)
    variance = Column(Float)  # Diferenca real vs previsto
    variance_pct = Column(Float)  # Variacao percentual

    # Componentes da previsao
    trend_component = Column(Float)
    seasonal_component = Column(Float)
    residual_component = Column(Float)

    # Flags
    is_anomaly = Column(Boolean, default=False)
    anomaly_type = Column(String(50))  # spike, drop, pattern_break

    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamento
    forecast = relationship("Forecast", back_populates="results")

    def __repr__(self) -> str:
        return f"<ForecastResult {self.date}: {self.predicted_demand}>"
