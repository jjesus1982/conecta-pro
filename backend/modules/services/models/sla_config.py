"""
SLAConfig Model - Configuração de SLA
Sprint 31: Gestão de Serviços
"""

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.services.models.service_catalog import ServiceCatalog


class SLAMetricType(StrEnum):
    """Tipo de métrica de SLA."""

    TEMPO_RESPOSTA = "tempo_resposta"
    TEMPO_RESOLUCAO = "tempo_resolucao"
    DISPONIBILIDADE = "disponibilidade"
    UPTIME = "uptime"
    QUALIDADE = "qualidade"
    SATISFACAO = "satisfacao"
    PRIMEIRO_CONTATO = "primeiro_contato"
    REINCIDENCIA = "reincidencia"


class SLAConfig(Base):
    """
    Model para configuração de SLA.
    Define os acordos de nível de serviço.
    """

    __tablename__ = "sla_configs"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    service_id = Column(UUID(as_uuid=True), ForeignKey("service_catalog.id", ondelete="CASCADE"), nullable=True)
    client_id = Column(UUID(as_uuid=True), nullable=True)
    contract_id = Column(UUID(as_uuid=True), nullable=True)

    # Identificação
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    code = Column(String(30), nullable=True)

    # Tipo de métrica
    metric_type = Column(
        Enum(SLAMetricType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SLAMetricType.TEMPO_RESOLUCAO,
    )

    # Tempos (em minutos para maior precisão)
    response_time_minutes = Column(Integer, nullable=True)
    resolution_time_minutes = Column(Integer, nullable=True)
    first_contact_time_minutes = Column(Integer, nullable=True)

    # Percentuais
    target_availability_percent = Column(Numeric(5, 2), nullable=True, default=99.0)
    target_quality_percent = Column(Numeric(5, 2), nullable=True, default=95.0)
    target_satisfaction_percent = Column(Numeric(5, 2), nullable=True, default=90.0)

    # Limites
    max_incidents_month = Column(Integer, nullable=True)
    max_reopen_count = Column(Integer, nullable=True, default=2)
    max_escalation_count = Column(Integer, nullable=True, default=3)

    # Penalidades
    penalty_enabled = Column(Boolean, nullable=False, default=False)
    penalty_percent_per_breach = Column(Numeric(5, 2), nullable=True)
    max_penalty_percent = Column(Numeric(5, 2), nullable=True, default=30.0)
    penalty_calculation_method = Column(String(50), nullable=True)

    # Bonificações
    bonus_enabled = Column(Boolean, nullable=False, default=False)
    bonus_percent_on_exceed = Column(Numeric(5, 2), nullable=True)
    max_bonus_percent = Column(Numeric(5, 2), nullable=True, default=10.0)

    # Escalonamento
    escalation_enabled = Column(Boolean, nullable=False, default=True)
    escalation_levels = Column(JSONB, nullable=True)

    # Horário de atendimento
    business_hours_only = Column(Boolean, nullable=False, default=True)
    business_hours_start = Column(String(5), nullable=True, default="08:00")
    business_hours_end = Column(String(5), nullable=True, default="18:00")
    business_days = Column(JSONB, nullable=True)  # [1,2,3,4,5] = seg-sex
    holiday_calendar_id = Column(UUID(as_uuid=True), nullable=True)

    # Prioridades
    priority_multipliers = Column(JSONB, nullable=True)

    # Notificações
    notification_enabled = Column(Boolean, nullable=False, default=True)
    notification_thresholds = Column(JSONB, nullable=True)
    notification_recipients = Column(JSONB, nullable=True)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)

    # Vigência
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)

    # Métricas acumuladas
    total_orders = Column(Integer, nullable=False, default=0)
    orders_within_sla = Column(Integer, nullable=False, default=0)
    orders_breached = Column(Integer, nullable=False, default=0)
    current_compliance_percent = Column(Numeric(5, 2), nullable=True)

    # Metadados
    extra_metadata = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    service: Optional["ServiceCatalog"] = relationship("ServiceCatalog", back_populates="sla_configs")

    # Índices
    __table_args__ = (
        Index("ix_sla_configs_service_id", "service_id"),
        Index("ix_sla_configs_client_id", "client_id"),
        Index("ix_sla_configs_contract_id", "contract_id"),
        Index("ix_sla_configs_metric_type", "metric_type"),
        Index("ix_sla_configs_is_active", "is_active"),
        Index("ix_sla_configs_is_default", "is_default"),
        Index("ix_sla_configs_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<SLAConfig {self.name}>"

    def activate(self) -> None:
        """Ativa a configuração de SLA."""
        self.is_active = True
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Desativa a configuração de SLA."""
        self.is_active = False
        self.updated_at = datetime.utcnow()

    def set_as_default(self) -> None:
        """Define como SLA padrão."""
        self.is_default = True
        self.updated_at = datetime.utcnow()

    def update_metrics(self, within_sla: bool) -> None:
        """Atualiza métricas do SLA."""
        self.total_orders += 1
        if within_sla:
            self.orders_within_sla += 1
        else:
            self.orders_breached += 1
        if self.total_orders > 0:
            self.current_compliance_percent = Decimal(str(round((self.orders_within_sla / self.total_orders) * 100, 2)))
        self.updated_at = datetime.utcnow()

    def calculate_deadline(self, start_time: datetime, priority: str | None = None) -> datetime:
        """Calcula deadline baseado no SLA."""
        resolution_minutes = self.resolution_time_minutes or 480  # 8h padrão

        if priority and self.priority_multipliers:
            multiplier = self.priority_multipliers.get(priority, 1.0)
            resolution_minutes = int(resolution_minutes * multiplier)

        return start_time + timedelta(minutes=resolution_minutes)

    def calculate_penalty(self, breach_count: int) -> Decimal:
        """Calcula penalidade por descumprimento."""
        if not self.penalty_enabled or not self.penalty_percent_per_breach:
            return Decimal("0")

        penalty = float(self.penalty_percent_per_breach) * breach_count
        max_penalty = float(self.max_penalty_percent or 100)
        return Decimal(str(min(penalty, max_penalty)))

    def calculate_bonus(self, exceed_percent: float) -> Decimal:
        """Calcula bonificação por exceder meta."""
        if not self.bonus_enabled or not self.bonus_percent_on_exceed:
            return Decimal("0")

        bonus = (float(self.bonus_percent_on_exceed) * exceed_percent) / 100
        max_bonus = float(self.max_bonus_percent or 10)
        return Decimal(str(min(bonus, max_bonus)))

    def get_response_time_hours(self) -> float:
        """Retorna tempo de resposta em horas."""
        if self.response_time_minutes:
            return self.response_time_minutes / 60
        return 0

    def get_resolution_time_hours(self) -> float:
        """Retorna tempo de resolução em horas."""
        if self.resolution_time_minutes:
            return self.resolution_time_minutes / 60
        return 0

    def is_valid(self) -> bool:
        """Verifica se SLA está válido."""
        now = datetime.utcnow()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    @property
    def compliance_status(self) -> str:
        """Status de compliance do SLA."""
        if self.current_compliance_percent is None:
            return "sem_dados"
        compliance = float(self.current_compliance_percent)
        target = float(self.target_availability_percent or 99.0)
        if compliance >= target:
            return "dentro_meta"
        elif compliance >= target * 0.9:
            return "atencao"
        return "critico"

    @property
    def breach_rate(self) -> float:
        """Taxa de descumprimento."""
        if self.total_orders == 0:
            return 0.0
        return (self.orders_breached / self.total_orders) * 100
