"""
ServiceCatalog Model - Catálogo de Serviços
Sprint 31: Gestão de Serviços
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.services.models.service_order import ServiceOrder
    from modules.services.models.sla_config import SLAConfig


class ServiceCategory(StrEnum):
    """Categoria do serviço."""

    SEGURANCA = "seguranca"
    PORTARIA = "portaria"
    MONITORAMENTO = "monitoramento"
    MANUTENCAO = "manutencao"
    LIMPEZA = "limpeza"
    JARDINAGEM = "jardinagem"
    ADMINISTRACAO = "administracao"
    TECNOLOGIA = "tecnologia"
    CONSULTORIA = "consultoria"
    TREINAMENTO = "treinamento"
    SUPORTE = "suporte"
    OUTROS = "outros"


class ServiceType(StrEnum):
    """Tipo do serviço."""

    RECORRENTE = "recorrente"
    AVULSO = "avulso"
    PROJETO = "projeto"
    IMPLANTACAO = "implantacao"
    EMERGENCIAL = "emergencial"
    PREVENTIVO = "preventivo"
    CORRETIVO = "corretivo"


class ServiceStatus(StrEnum):
    """Status do serviço no catálogo."""

    RASCUNHO = "rascunho"
    ATIVO = "ativo"
    INATIVO = "inativo"
    DESCONTINUADO = "descontinuado"


class ServiceCatalog(Base):
    """
    Model para catálogo de serviços.
    Representa os serviços oferecidos pela empresa.
    """

    __tablename__ = "service_catalog"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    code = Column(String(20), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    short_description = Column(String(500), nullable=True)

    # Classificação
    category = Column(
        Enum(ServiceCategory, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ServiceCategory.OUTROS,
    )
    service_type = Column(
        Enum(ServiceType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ServiceType.RECORRENTE,
    )
    status = Column(
        Enum(ServiceStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ServiceStatus.RASCUNHO,
    )

    # Precificação
    base_price = Column(Numeric(15, 2), nullable=True)
    unit_price = Column(Numeric(15, 2), nullable=True)
    price_unit = Column(String(50), nullable=True)  # hora, dia, mês, unidade
    min_price = Column(Numeric(15, 2), nullable=True)
    max_price = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), nullable=False, default="BRL")

    # Duração estimada
    estimated_duration_hours = Column(Numeric(10, 2), nullable=True)
    min_duration_hours = Column(Numeric(10, 2), nullable=True)
    max_duration_hours = Column(Numeric(10, 2), nullable=True)

    # Recursos necessários
    required_skills = Column(ARRAY(String), nullable=True)
    required_certifications = Column(ARRAY(String), nullable=True)
    required_equipment = Column(ARRAY(String), nullable=True)
    min_team_size = Column(Integer, nullable=True, default=1)
    max_team_size = Column(Integer, nullable=True)

    # SLA padrão
    default_sla_response_hours = Column(Integer, nullable=True)
    default_sla_resolution_hours = Column(Integer, nullable=True)
    default_sla_availability = Column(Numeric(5, 2), nullable=True, default=99.0)

    # Configurações
    requires_scheduling = Column(Boolean, nullable=False, default=True)
    requires_approval = Column(Boolean, nullable=False, default=False)
    allows_remote = Column(Boolean, nullable=False, default=False)
    is_emergency_available = Column(Boolean, nullable=False, default=False)
    emergency_surcharge_percent = Column(Numeric(5, 2), nullable=True)

    # Integrações
    plus_service_code = Column(String(50), nullable=True)
    external_service_code = Column(String(50), nullable=True)

    # Métricas
    total_orders = Column(Integer, nullable=False, default=0)
    completed_orders = Column(Integer, nullable=False, default=0)
    cancelled_orders = Column(Integer, nullable=False, default=0)
    avg_rating = Column(Numeric(3, 2), nullable=True)
    total_revenue = Column(Numeric(15, 2), nullable=False, default=0)

    # Metadados
    tags = Column(ARRAY(String), nullable=True)
    extra_metadata = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # Imagens/Documentos
    image_url = Column(String(500), nullable=True)
    documentation_url = Column(String(500), nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    orders: list["ServiceOrder"] = relationship("ServiceOrder", back_populates="service", lazy="dynamic")
    sla_configs: list["SLAConfig"] = relationship("SLAConfig", back_populates="service", lazy="dynamic")

    # Índices
    __table_args__ = (
        Index("ix_service_catalog_code", "code"),
        Index("ix_service_catalog_name", "name"),
        Index("ix_service_catalog_category", "category"),
        Index("ix_service_catalog_type", "service_type"),
        Index("ix_service_catalog_status", "status"),
        Index("ix_service_catalog_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<ServiceCatalog {self.code}: {self.name}>"

    def activate(self) -> None:
        """Ativa o serviço no catálogo."""
        self.status = ServiceStatus.ATIVO
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Desativa o serviço."""
        self.status = ServiceStatus.INATIVO
        self.updated_at = datetime.utcnow()

    def discontinue(self) -> None:
        """Descontinua o serviço."""
        self.status = ServiceStatus.DESCONTINUADO
        self.updated_at = datetime.utcnow()

    def update_metrics(
        self,
        orders_delta: int = 0,
        completed_delta: int = 0,
        cancelled_delta: int = 0,
        revenue_delta: Decimal = Decimal("0"),
    ) -> None:
        """Atualiza métricas do serviço."""
        self.total_orders += orders_delta
        self.completed_orders += completed_delta
        self.cancelled_orders += cancelled_delta
        self.total_revenue += revenue_delta
        self.updated_at = datetime.utcnow()

    def update_rating(self, new_rating: float) -> None:
        """Atualiza rating médio do serviço."""
        if self.avg_rating is None:
            self.avg_rating = Decimal(str(new_rating))
        else:
            total = self.completed_orders or 1
            current = float(self.avg_rating) * (total - 1)
            self.avg_rating = Decimal(str((current + new_rating) / total))
        self.updated_at = datetime.utcnow()

    def calculate_price(
        self, quantity: float = 1, duration_hours: float | None = None, is_emergency: bool = False
    ) -> Decimal:
        """Calcula preço do serviço."""
        if self.unit_price:
            base = float(self.unit_price) * quantity
        elif self.base_price:
            base = float(self.base_price)
        else:
            base = 0

        if duration_hours and self.unit_price and self.price_unit == "hora":
            base = float(self.unit_price) * duration_hours

        if is_emergency and self.emergency_surcharge_percent:
            surcharge = base * (float(self.emergency_surcharge_percent) / 100)
            base += surcharge

        return Decimal(str(round(base, 2)))

    @property
    def completion_rate(self) -> float:
        """Taxa de conclusão."""
        if self.total_orders == 0:
            return 0.0
        return (self.completed_orders / self.total_orders) * 100

    @property
    def cancellation_rate(self) -> float:
        """Taxa de cancelamento."""
        if self.total_orders == 0:
            return 0.0
        return (self.cancelled_orders / self.total_orders) * 100

    @property
    def is_available(self) -> bool:
        """Verifica se serviço está disponível."""
        return self.status == ServiceStatus.ATIVO and self.ativo
