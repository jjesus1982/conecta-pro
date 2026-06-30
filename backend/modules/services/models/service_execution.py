"""
ServiceExecution Model - Execução de Serviços
Sprint 31: Gestão de Serviços
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.services.models.service_order import ServiceOrder


class ExecutionStatus(StrEnum):
    """Status da execução."""

    AGENDADA = "agendada"
    EM_DESLOCAMENTO = "em_deslocamento"
    NO_LOCAL = "no_local"
    EM_EXECUCAO = "em_execucao"
    PAUSADA = "pausada"
    AGUARDANDO_MATERIAL = "aguardando_material"
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"
    FINALIZADA = "finalizada"
    CANCELADA = "cancelada"


class ServiceExecution(Base):
    """
    Model para execução de serviços.
    Registra cada etapa da execução de uma ordem.
    """

    __tablename__ = "service_executions"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign key
    order_id = Column(UUID(as_uuid=True), ForeignKey("service_orders.id", ondelete="CASCADE"), nullable=False)

    # Identificação
    execution_number = Column(String(30), nullable=False)
    sequence = Column(Integer, nullable=False, default=1)

    # Status
    status = Column(
        Enum(ExecutionStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExecutionStatus.AGENDADA,
    )

    # Técnico/Equipe
    technician_id = Column(UUID(as_uuid=True), nullable=True)
    technician_name = Column(String(200), nullable=True)
    team_members = Column(JSONB, nullable=True)

    # Tempos
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    travel_start = Column(DateTime, nullable=True)
    travel_end = Column(DateTime, nullable=True)
    arrival_time = Column(DateTime, nullable=True)
    departure_time = Column(DateTime, nullable=True)

    # Durações calculadas
    travel_duration_minutes = Column(Integer, nullable=True)
    execution_duration_minutes = Column(Integer, nullable=True)
    waiting_duration_minutes = Column(Integer, nullable=True)
    total_duration_minutes = Column(Integer, nullable=True)

    # Localização
    start_latitude = Column(Numeric(10, 8), nullable=True)
    start_longitude = Column(Numeric(11, 8), nullable=True)
    end_latitude = Column(Numeric(10, 8), nullable=True)
    end_longitude = Column(Numeric(11, 8), nullable=True)

    # Checklist
    checklist_items = Column(JSONB, nullable=True)
    checklist_completed = Column(Boolean, nullable=False, default=False)
    checklist_completion_percent = Column(Numeric(5, 2), nullable=True)

    # Materiais
    materials_used = Column(JSONB, nullable=True)
    materials_cost = Column(Numeric(15, 2), nullable=True, default=0)

    # Descrição do trabalho
    work_description = Column(Text, nullable=True)
    findings = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)
    issues_found = Column(Text, nullable=True)

    # Assinaturas
    client_signature = Column(Text, nullable=True)  # Base64
    client_signature_name = Column(String(200), nullable=True)
    client_signature_date = Column(DateTime, nullable=True)
    technician_signature = Column(Text, nullable=True)
    technician_signature_date = Column(DateTime, nullable=True)

    # Fotos/Anexos
    photos_before = Column(JSONB, nullable=True)
    photos_after = Column(JSONB, nullable=True)
    attachments = Column(JSONB, nullable=True)

    # Custos
    labor_cost = Column(Numeric(15, 2), nullable=True, default=0)
    travel_cost = Column(Numeric(15, 2), nullable=True, default=0)
    other_costs = Column(Numeric(15, 2), nullable=True, default=0)
    total_cost = Column(Numeric(15, 2), nullable=True, default=0)

    # Pausas
    pause_count = Column(Integer, nullable=False, default=0)
    pause_history = Column(JSONB, nullable=True)

    # Notas
    internal_notes = Column(Text, nullable=True)
    client_notes = Column(Text, nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    order: "ServiceOrder" = relationship("ServiceOrder", back_populates="executions")

    # Índices
    __table_args__ = (
        Index("ix_service_executions_order_id", "order_id"),
        Index("ix_service_executions_technician_id", "technician_id"),
        Index("ix_service_executions_status", "status"),
        Index("ix_service_executions_scheduled_start", "scheduled_start"),
        Index("ix_service_executions_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<ServiceExecution {self.execution_number}>"

    def start_travel(self) -> None:
        """Inicia deslocamento."""
        self.status = ExecutionStatus.EM_DESLOCAMENTO
        self.travel_start = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def arrive_at_location(self, latitude: float | None = None, longitude: float | None = None) -> None:
        """Registra chegada no local."""
        self.status = ExecutionStatus.NO_LOCAL
        self.travel_end = datetime.utcnow()
        self.arrival_time = datetime.utcnow()
        if self.travel_start:
            delta = self.arrival_time - self.travel_start
            self.travel_duration_minutes = int(delta.total_seconds() / 60)
        if latitude:
            self.start_latitude = Decimal(str(latitude))
        if longitude:
            self.start_longitude = Decimal(str(longitude))
        self.updated_at = datetime.utcnow()

    def start_execution(self) -> None:
        """Inicia execução do serviço."""
        self.status = ExecutionStatus.EM_EXECUCAO
        self.actual_start = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def pause_execution(self, reason: str) -> None:
        """Pausa a execução."""
        self.status = ExecutionStatus.PAUSADA
        self.pause_count += 1
        pause_entry = {"pause_number": self.pause_count, "paused_at": datetime.utcnow().isoformat(), "reason": reason}
        if self.pause_history is None:
            self.pause_history = []
        self.pause_history.append(pause_entry)
        self.updated_at = datetime.utcnow()

    def resume_execution(self) -> None:
        """Retoma a execução."""
        self.status = ExecutionStatus.EM_EXECUCAO
        if self.pause_history and len(self.pause_history) > 0:
            self.pause_history[-1]["resumed_at"] = datetime.utcnow().isoformat()
        self.updated_at = datetime.utcnow()

    def wait_for_material(self, material_description: str) -> None:
        """Aguarda material."""
        self.status = ExecutionStatus.AGUARDANDO_MATERIAL
        self.internal_notes = (f"{self.internal_notes or ''}\n[AGUARDANDO MATERIAL]: {material_description}").strip()
        self.updated_at = datetime.utcnow()

    def finish_execution(
        self, work_description: str, latitude: float | None = None, longitude: float | None = None
    ) -> None:
        """Finaliza a execução."""
        self.status = ExecutionStatus.FINALIZADA
        self.actual_end = datetime.utcnow()
        self.departure_time = datetime.utcnow()
        self.work_description = work_description
        if self.actual_start:
            delta = self.actual_end - self.actual_start
            self.execution_duration_minutes = int(delta.total_seconds() / 60)
        if latitude:
            self.end_latitude = Decimal(str(latitude))
        if longitude:
            self.end_longitude = Decimal(str(longitude))
        self._calculate_total_duration()
        self._calculate_total_cost()
        self.updated_at = datetime.utcnow()

    def cancel_execution(self, reason: str) -> None:
        """Cancela a execução."""
        self.status = ExecutionStatus.CANCELADA
        self.internal_notes = (f"{self.internal_notes or ''}\n[CANCELADA]: {reason}").strip()
        self.updated_at = datetime.utcnow()

    def add_material(self, name: str, quantity: float, unit_cost: float) -> None:
        """Adiciona material utilizado."""
        if self.materials_used is None:
            self.materials_used = []
        self.materials_used.append(
            {"name": name, "quantity": quantity, "unit_cost": unit_cost, "total_cost": quantity * unit_cost}
        )
        self.materials_cost = Decimal(str(sum(m["total_cost"] for m in self.materials_used)))
        self._calculate_total_cost()
        self.updated_at = datetime.utcnow()

    def update_checklist_item(self, item_id: str, completed: bool) -> None:
        """Atualiza item do checklist."""
        if self.checklist_items:
            for item in self.checklist_items:
                if item.get("id") == item_id:
                    item["completed"] = completed
                    item["completed_at"] = datetime.utcnow().isoformat() if completed else None
                    break
            completed_count = sum(1 for item in self.checklist_items if item.get("completed"))
            total_count = len(self.checklist_items)
            self.checklist_completion_percent = Decimal(str(round((completed_count / total_count) * 100, 2)))
            self.checklist_completed = completed_count == total_count
        self.updated_at = datetime.utcnow()

    def add_signature(self, signature_type: str, signature: str, name: str) -> None:
        """Adiciona assinatura."""
        now = datetime.utcnow()
        if signature_type == "client":
            self.client_signature = signature
            self.client_signature_name = name
            self.client_signature_date = now
        elif signature_type == "technician":
            self.technician_signature = signature
            self.technician_signature_date = now
        self.updated_at = datetime.utcnow()

    def _calculate_total_duration(self) -> None:
        """Calcula duração total."""
        travel = self.travel_duration_minutes or 0
        execution = self.execution_duration_minutes or 0
        waiting = self.waiting_duration_minutes or 0
        self.total_duration_minutes = travel + execution + waiting

    def _calculate_total_cost(self) -> None:
        """Calcula custo total."""
        materials = float(self.materials_cost or 0)
        labor = float(self.labor_cost or 0)
        travel = float(self.travel_cost or 0)
        other = float(self.other_costs or 0)
        self.total_cost = Decimal(str(materials + labor + travel + other))

    @property
    def is_finished(self) -> bool:
        """Verifica se execução está finalizada."""
        return self.status == ExecutionStatus.FINALIZADA

    @property
    def has_signatures(self) -> bool:
        """Verifica se tem assinaturas."""
        return bool(self.client_signature and self.technician_signature)
