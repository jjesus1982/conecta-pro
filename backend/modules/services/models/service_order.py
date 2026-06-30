"""
ServiceOrder Model - Ordens de Serviço
Sprint 31: Gestão de Serviços
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.services.models.service_catalog import ServiceCatalog
    from modules.services.models.service_execution import ServiceExecution
    from modules.services.models.service_report import ServiceReport


class OrderStatus(StrEnum):
    """Status da ordem de serviço."""

    RASCUNHO = "rascunho"
    PENDENTE = "pendente"
    APROVADA = "aprovada"
    AGENDADA = "agendada"
    EM_ANDAMENTO = "em_andamento"
    PAUSADA = "pausada"
    CONCLUIDA = "concluida"
    CANCELADA = "cancelada"
    REJEITADA = "rejeitada"


class OrderPriority(StrEnum):
    """Prioridade da ordem."""

    BAIXA = "baixa"
    NORMAL = "normal"
    ALTA = "alta"
    URGENTE = "urgente"
    EMERGENCIAL = "emergencial"


class ServiceOrder(Base):
    """
    Model para ordens de serviço.
    Representa uma solicitação de execução de serviço.
    """

    __tablename__ = "service_orders"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    order_number = Column(String(30), nullable=False, unique=True)

    # Foreign keys
    service_id = Column(UUID(as_uuid=True), ForeignKey("service_catalog.id", ondelete="RESTRICT"), nullable=False)
    client_id = Column(UUID(as_uuid=True), nullable=False)
    condominium_id = Column(UUID(as_uuid=True), nullable=True)
    contract_id = Column(UUID(as_uuid=True), nullable=True)

    # Status e prioridade
    status = Column(
        Enum(OrderStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=OrderStatus.RASCUNHO
    )
    priority = Column(
        Enum(OrderPriority, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OrderPriority.NORMAL,
    )

    # Descrição
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    special_instructions = Column(Text, nullable=True)

    # Solicitante
    requester_name = Column(String(200), nullable=True)
    requester_email = Column(String(255), nullable=True)
    requester_phone = Column(String(20), nullable=True)

    # Local
    location_address = Column(String(500), nullable=True)
    location_details = Column(Text, nullable=True)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)

    # Agendamento
    requested_date = Column(Date, nullable=True)
    requested_time_start = Column(String(5), nullable=True)  # HH:MM
    requested_time_end = Column(String(5), nullable=True)
    scheduled_date = Column(Date, nullable=True)
    scheduled_time_start = Column(String(5), nullable=True)
    scheduled_time_end = Column(String(5), nullable=True)
    is_flexible_schedule = Column(Boolean, nullable=False, default=True)

    # Execução
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    actual_duration_hours = Column(Numeric(10, 2), nullable=True)

    # Valores
    estimated_value = Column(Numeric(15, 2), nullable=True)
    final_value = Column(Numeric(15, 2), nullable=True)
    discount_value = Column(Numeric(15, 2), nullable=True, default=0)
    discount_reason = Column(String(200), nullable=True)
    additional_charges = Column(Numeric(15, 2), nullable=True, default=0)
    additional_charges_reason = Column(String(200), nullable=True)

    # Aprovação
    requires_approval = Column(Boolean, nullable=False, default=False)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    approval_notes = Column(Text, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejected_by = Column(UUID(as_uuid=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Cancelamento
    cancellation_reason = Column(Text, nullable=True)
    cancelled_by = Column(UUID(as_uuid=True), nullable=True)

    # SLA
    sla_response_deadline = Column(DateTime, nullable=True)
    sla_resolution_deadline = Column(DateTime, nullable=True)
    sla_response_met = Column(Boolean, nullable=True)
    sla_resolution_met = Column(Boolean, nullable=True)
    first_response_at = Column(DateTime, nullable=True)

    # Avaliação
    rating = Column(Integer, nullable=True)  # 1-5
    rating_comment = Column(Text, nullable=True)
    rated_at = Column(DateTime, nullable=True)

    # Equipe
    assigned_team_id = Column(UUID(as_uuid=True), nullable=True)
    assigned_technician_id = Column(UUID(as_uuid=True), nullable=True)
    assigned_technician_name = Column(String(200), nullable=True)

    # Metadados
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    service: "ServiceCatalog" = relationship("ServiceCatalog", back_populates="orders")
    executions: list["ServiceExecution"] = relationship("ServiceExecution", back_populates="order", lazy="dynamic")
    reports: list["ServiceReport"] = relationship("ServiceReport", back_populates="order", lazy="dynamic")

    # Índices
    __table_args__ = (
        Index("ix_service_orders_number", "order_number"),
        Index("ix_service_orders_service_id", "service_id"),
        Index("ix_service_orders_client_id", "client_id"),
        Index("ix_service_orders_condominium_id", "condominium_id"),
        Index("ix_service_orders_status", "status"),
        Index("ix_service_orders_priority", "priority"),
        Index("ix_service_orders_scheduled_date", "scheduled_date"),
        Index("ix_service_orders_created_at", "created_at"),
        Index("ix_service_orders_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<ServiceOrder {self.order_number}: {self.title}>"

    def submit(self) -> None:
        """Envia ordem para aprovação/agendamento."""
        self.status = OrderStatus.PENDENTE
        self.updated_at = datetime.utcnow()

    def approve(self, approved_by: UUID, notes: str | None = None) -> None:
        """Aprova a ordem."""
        self.status = OrderStatus.APROVADA
        self.approved_at = datetime.utcnow()
        self.approved_by = approved_by
        self.approval_notes = notes
        self.updated_at = datetime.utcnow()

    def reject(self, rejected_by: UUID, reason: str) -> None:
        """Rejeita a ordem."""
        self.status = OrderStatus.REJEITADA
        self.rejected_at = datetime.utcnow()
        self.rejected_by = rejected_by
        self.rejection_reason = reason
        self.updated_at = datetime.utcnow()

    def schedule(self, scheduled_date: date, time_start: str, time_end: str | None = None) -> None:
        """Agenda a ordem."""
        self.status = OrderStatus.AGENDADA
        self.scheduled_date = scheduled_date
        self.scheduled_time_start = time_start
        self.scheduled_time_end = time_end
        self.updated_at = datetime.utcnow()

    def start(self) -> None:
        """Inicia execução da ordem."""
        self.status = OrderStatus.EM_ANDAMENTO
        self.started_at = datetime.utcnow()
        if not self.first_response_at:
            self.first_response_at = datetime.utcnow()
            if self.sla_response_deadline:
                self.sla_response_met = datetime.utcnow() <= self.sla_response_deadline
        self.updated_at = datetime.utcnow()

    def pause(self, reason: str | None = None) -> None:
        """Pausa a ordem."""
        self.status = OrderStatus.PAUSADA
        if reason:
            self.internal_notes = f"{self.internal_notes or ''}\n[PAUSA]: {reason}"
        self.updated_at = datetime.utcnow()

    def resume(self) -> None:
        """Retoma a ordem."""
        self.status = OrderStatus.EM_ANDAMENTO
        self.updated_at = datetime.utcnow()

    def complete(self, final_value: Decimal | None = None) -> None:
        """Conclui a ordem."""
        self.status = OrderStatus.CONCLUIDA
        self.completed_at = datetime.utcnow()
        if final_value:
            self.final_value = final_value
        elif not self.final_value:
            self.final_value = self.estimated_value
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.actual_duration_hours = Decimal(str(round(delta.total_seconds() / 3600, 2)))
        if self.sla_resolution_deadline:
            self.sla_resolution_met = self.completed_at <= self.sla_resolution_deadline
        self.updated_at = datetime.utcnow()

    def cancel(self, cancelled_by: UUID, reason: str) -> None:
        """Cancela a ordem."""
        self.status = OrderStatus.CANCELADA
        self.cancelled_at = datetime.utcnow()
        self.cancelled_by = cancelled_by
        self.cancellation_reason = reason
        self.updated_at = datetime.utcnow()

    def rate(self, rating: int, comment: str | None = None) -> None:
        """Avalia a ordem."""
        if not 1 <= rating <= 5:
            raise ValueError("Rating deve ser entre 1 e 5")
        self.rating = rating
        self.rating_comment = comment
        self.rated_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def assign_technician(self, technician_id: UUID, technician_name: str) -> None:
        """Atribui técnico à ordem."""
        self.assigned_technician_id = technician_id
        self.assigned_technician_name = technician_name
        self.updated_at = datetime.utcnow()

    def calculate_total(self) -> Decimal:
        """Calcula valor total da ordem."""
        base = self.final_value or self.estimated_value or Decimal("0")
        discount = self.discount_value or Decimal("0")
        additional = self.additional_charges or Decimal("0")
        return base - discount + additional

    @property
    def is_overdue(self) -> bool:
        """Verifica se ordem está atrasada."""
        if self.status in [OrderStatus.CONCLUIDA, OrderStatus.CANCELADA]:
            return False
        if self.sla_resolution_deadline:
            return datetime.utcnow() > self.sla_resolution_deadline
        if self.scheduled_date:
            return date.today() > self.scheduled_date
        return False

    @property
    def is_in_progress(self) -> bool:
        """Verifica se ordem está em andamento."""
        return self.status == OrderStatus.EM_ANDAMENTO

    @property
    def can_be_edited(self) -> bool:
        """Verifica se ordem pode ser editada."""
        return self.status in [OrderStatus.RASCUNHO, OrderStatus.PENDENTE]
