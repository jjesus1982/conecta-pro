"""PushAnalytics Model - Metricas e Analytics de Push.

Sprint 37 - Push Notifications Mobile.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.models.base import Base


class MetricPeriod(StrEnum):
    """Periodo da metrica."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class PushMetric(Base):
    """Modelo de metricas agregadas de push."""

    __tablename__ = "push_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Periodo
    period = Column(Enum(MetricPeriod, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False)

    # Dimensoes (opcional - para drill-down)
    platform = Column(String(20), index=True)  # ios, android, web
    campaign_id = Column(UUID(as_uuid=True), index=True)
    app_id = Column(String(200), index=True)
    category = Column(String(50), index=True)

    # Metricas de envio
    total_targeted = Column(Integer, default=0)
    total_sent = Column(Integer, default=0)
    total_delivered = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    total_expired = Column(Integer, default=0)
    total_unregistered = Column(Integer, default=0)

    # Metricas de engajamento
    total_opened = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    total_dismissed = Column(Integer, default=0)
    total_converted = Column(Integer, default=0)

    # Metricas de dispositivos
    total_devices_active = Column(Integer, default=0)
    new_devices_registered = Column(Integer, default=0)
    devices_unregistered = Column(Integer, default=0)

    # Taxas
    delivery_rate = Column(Float)  # delivered / sent * 100
    open_rate = Column(Float)  # opened / delivered * 100
    click_rate = Column(Float)  # clicked / delivered * 100
    conversion_rate = Column(Float)  # converted / opened * 100
    dismiss_rate = Column(Float)  # dismissed / delivered * 100
    failure_rate = Column(Float)  # failed / sent * 100

    # Metricas de tempo
    avg_time_to_deliver_ms = Column(Integer)
    avg_time_to_open_seconds = Column(Integer)
    p50_time_to_open_seconds = Column(Integer)
    p95_time_to_open_seconds = Column(Integer)

    # Metricas por hora do dia (para DAILY)
    hourly_distribution = Column(JSONB, default={})
    # {"00": {sent: 10, opened: 5}, "01": {...}, ...}

    # Metricas por plataforma (quando nao filtrado)
    platform_breakdown = Column(JSONB, default={})
    # {"ios": {sent: 100, opened: 50}, "android": {...}}

    # Metricas de erro
    error_breakdown = Column(JSONB, default={})
    # {"InvalidToken": 10, "QuotaExceeded": 5, ...}

    # Top performers
    top_campaigns = Column(JSONB, default=[])
    # [{id, name, open_rate, click_rate}, ...]

    # Controle
    calculated_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<PushMetric {self.period.value} {self.period_start}>"

    def calculate_rates(self) -> None:
        """Calcula todas as taxas."""
        if self.total_sent > 0:
            self.delivery_rate = (self.total_delivered / self.total_sent) * 100
            self.failure_rate = (self.total_failed / self.total_sent) * 100

        if self.total_delivered > 0:
            self.open_rate = (self.total_opened / self.total_delivered) * 100
            self.click_rate = (self.total_clicked / self.total_delivered) * 100
            self.dismiss_rate = (self.total_dismissed / self.total_delivered) * 100

        if self.total_opened > 0:
            self.conversion_rate = (self.total_converted / self.total_opened) * 100


class PushABTestResult(Base):
    """Modelo de resultado de teste A/B."""

    __tablename__ = "push_ab_test_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Teste
    test_name = Column(String(200), nullable=False)
    test_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Variantes
    control_campaign_id = Column(UUID(as_uuid=True), nullable=False)
    variant_campaign_id = Column(UUID(as_uuid=True), nullable=False)

    # Configuracao
    traffic_split = Column(Integer, default=50)  # % para variante
    winner_metric = Column(String(50), default="open_rate")
    confidence_threshold = Column(Float, default=95.0)  # %

    # Metricas - Controle
    control_sent = Column(Integer, default=0)
    control_delivered = Column(Integer, default=0)
    control_opened = Column(Integer, default=0)
    control_clicked = Column(Integer, default=0)
    control_converted = Column(Integer, default=0)
    control_open_rate = Column(Float)
    control_click_rate = Column(Float)
    control_conversion_rate = Column(Float)

    # Metricas - Variante
    variant_sent = Column(Integer, default=0)
    variant_delivered = Column(Integer, default=0)
    variant_opened = Column(Integer, default=0)
    variant_clicked = Column(Integer, default=0)
    variant_converted = Column(Integer, default=0)
    variant_open_rate = Column(Float)
    variant_click_rate = Column(Float)
    variant_conversion_rate = Column(Float)

    # Resultado estatistico
    statistical_significance = Column(Float)  # %
    p_value = Column(Float)
    confidence_interval_lower = Column(Float)
    confidence_interval_upper = Column(Float)
    lift_percentage = Column(Float)  # % de melhoria da variante

    # Vencedor
    winner = Column(String(20))  # control, variant, inconclusive
    winner_declared_at = Column(DateTime)
    auto_applied = Column(Boolean, default=False)

    # Status
    status = Column(String(20), default="running")  # running, completed, stopped
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime)

    # Controle
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PushABTestResult {self.test_name}>"

    def calculate_winner(self) -> str:
        """Calcula o vencedor baseado na metrica."""
        control_value = getattr(self, f"control_{self.winner_metric}", 0) or 0
        variant_value = getattr(self, f"variant_{self.winner_metric}", 0) or 0

        if self.statistical_significance and self.statistical_significance >= self.confidence_threshold:
            if variant_value > control_value:
                self.winner = "variant"
                self.lift_percentage = ((variant_value - control_value) / control_value) * 100 if control_value else 0
            else:
                self.winner = "control"
                self.lift_percentage = ((control_value - variant_value) / variant_value) * 100 if variant_value else 0
        else:
            self.winner = "inconclusive"

        return self.winner


class PushDeliveryReport(Base):
    """Modelo de relatorio de entrega detalhado."""

    __tablename__ = "push_delivery_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Campanha
    campaign_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Periodo
    report_date = Column(DateTime, nullable=False, index=True)

    # Por plataforma
    ios_sent = Column(Integer, default=0)
    ios_delivered = Column(Integer, default=0)
    ios_failed = Column(Integer, default=0)
    ios_opened = Column(Integer, default=0)

    android_sent = Column(Integer, default=0)
    android_delivered = Column(Integer, default=0)
    android_failed = Column(Integer, default=0)
    android_opened = Column(Integer, default=0)

    web_sent = Column(Integer, default=0)
    web_delivered = Column(Integer, default=0)
    web_failed = Column(Integer, default=0)
    web_opened = Column(Integer, default=0)

    # Por provedor
    fcm_sent = Column(Integer, default=0)
    fcm_delivered = Column(Integer, default=0)
    fcm_failed = Column(Integer, default=0)

    apns_sent = Column(Integer, default=0)
    apns_delivered = Column(Integer, default=0)
    apns_failed = Column(Integer, default=0)

    # Erros detalhados
    errors_by_code = Column(JSONB, default={})
    # {"InvalidToken": 10, "Unregistered": 5, "QuotaExceeded": 2}

    # Por versao do app
    by_app_version = Column(JSONB, default={})
    # {"2.0.0": {sent: 100, opened: 50}, "2.1.0": {...}}

    # Por pais
    by_country = Column(JSONB, default={})
    # {"BR": {sent: 500, opened: 200}, "US": {...}}

    # Por hora
    by_hour = Column(JSONB, default={})
    # {"09": {sent: 50, opened: 30}, "10": {...}}

    # Latencia
    avg_delivery_latency_ms = Column(Integer)
    max_delivery_latency_ms = Column(Integer)
    min_delivery_latency_ms = Column(Integer)

    # Controle
    generated_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<PushDeliveryReport {self.campaign_id} {self.report_date}>"
