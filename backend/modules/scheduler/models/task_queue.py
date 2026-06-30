"""TaskQueue Model - Fila de Tarefas.

Sprint 35 - Task Scheduler.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.models.base import Base


class QueueStatus(StrEnum):
    """Status do item na fila."""

    PENDING = "pending"  # Aguardando processamento
    CLAIMED = "claimed"  # Reivindicado por worker
    PROCESSING = "processing"  # Em processamento
    COMPLETED = "completed"  # Processado com sucesso
    FAILED = "failed"  # Falhou
    DEAD = "dead"  # Falhou após max retries (dead letter)
    CANCELLED = "cancelled"  # Cancelado
    DEFERRED = "deferred"  # Adiado


class QueuePriority(StrEnum):
    """Prioridade na fila."""

    CRITICAL = "critical"  # Prioridade máxima (1)
    HIGH = "high"  # Alta (2)
    NORMAL = "normal"  # Normal (5)
    LOW = "low"  # Baixa (8)
    BACKGROUND = "background"  # Background (10)


PRIORITY_VALUES = {
    QueuePriority.CRITICAL: 1,
    QueuePriority.HIGH: 2,
    QueuePriority.NORMAL: 5,
    QueuePriority.LOW: 8,
    QueuePriority.BACKGROUND: 10,
}


class TaskQueue(Base):
    """Modelo de item na fila de tarefas."""

    __tablename__ = "scheduler_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificação
    queue_name = Column(String(100), nullable=False, default="default", index=True)
    message_id = Column(String(100), unique=True, index=True)

    # Relacionamentos opcionais
    task_id = Column(UUID(as_uuid=True), ForeignKey("scheduler_tasks.id"))
    execution_id = Column(UUID(as_uuid=True), ForeignKey("scheduler_executions.id"))

    # Status e prioridade
    status = Column(
        Enum(QueueStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=QueueStatus.PENDING,
        index=True,
    )
    priority = Column(Enum(QueuePriority), nullable=False, default=QueuePriority.NORMAL)
    priority_value = Column(Integer, default=5, index=True)  # Para ordenação

    # Payload
    handler = Column(String(200), nullable=False)
    handler_module = Column(String(200))
    payload = Column(JSONB, nullable=False, default=dict)
    headers = Column(JSONB, default=dict)

    # Agendamento
    scheduled_at = Column(DateTime, index=True)  # Quando deve executar
    not_before = Column(DateTime)  # Não executar antes de
    not_after = Column(DateTime)  # Não executar depois de (expira)

    # Retry
    attempt = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    retry_at = Column(DateTime)
    retry_delay_seconds = Column(Integer, default=60)
    retry_backoff = Column(Float, default=2.0)

    # Timeout
    timeout_seconds = Column(Integer, default=3600)
    visibility_timeout_seconds = Column(Integer, default=300)  # Tempo que fica invisível após claim

    # Worker
    claimed_by = Column(UUID(as_uuid=True), ForeignKey("scheduler_workers.id"))
    claimed_at = Column(DateTime)
    claim_expires_at = Column(DateTime)

    # Timing
    enqueued_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    processing_time_ms = Column(Integer)

    # Resultado
    result = Column(JSONB)
    error_message = Column(Text)
    error_code = Column(String(50))

    # Agrupamento
    group_id = Column(String(100), index=True)  # Para processar em grupo
    correlation_id = Column(String(100), index=True)  # Para correlacionar mensagens

    # Deduplicação
    deduplication_id = Column(String(200), index=True)  # ID para evitar duplicatas
    deduplication_scope = Column(String(50), default="queue")  # queue, tenant, global

    # Metadados
    source = Column(String(100))  # De onde veio (api, scheduler, workflow, etc)
    extra_data = Column(JSONB, default=dict)
    tags = Column(JSONB, default=list)

    # Auditoria
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<TaskQueue {self.message_id} ({self.status.value})>"

    @property
    def is_available(self) -> bool:
        """Verifica se está disponível para processamento."""
        if self.status != QueueStatus.PENDING:
            return False
        if self.scheduled_at and datetime.utcnow() < self.scheduled_at:
            return False
        if self.not_after and datetime.utcnow() > self.not_after:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Verifica se expirou."""
        if self.not_after is None:
            return False
        return datetime.utcnow() > self.not_after

    @property
    def can_retry(self) -> bool:
        """Verifica se pode tentar novamente."""
        return self.attempt < self.max_attempts

    @property
    def wait_time_seconds(self) -> float | None:
        """Tempo de espera na fila."""
        if self.started_at:
            return (self.started_at - self.enqueued_at).total_seconds()
        return (datetime.utcnow() - self.enqueued_at).total_seconds()

    def set_priority(self, priority: QueuePriority) -> None:
        """Define a prioridade."""
        self.priority = priority
        self.priority_value = PRIORITY_VALUES.get(priority, 5)
