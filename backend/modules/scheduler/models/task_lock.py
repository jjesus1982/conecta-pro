"""TaskLock Model - Locks Distribuídos.

Sprint 35 - Task Scheduler.
"""

import uuid
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.models.base import Base


class LockStatus(StrEnum):
    """Status do lock."""

    ACQUIRED = "acquired"  # Lock adquirido
    RELEASED = "released"  # Lock liberado
    EXPIRED = "expired"  # Lock expirado
    STOLEN = "stolen"  # Lock roubado (por timeout)


class TaskLock(Base):
    """Modelo de lock distribuído para tarefas.

    Usado para garantir que apenas uma instância de uma tarefa
    execute por vez (distributed locking).
    """

    __tablename__ = "scheduler_locks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Lock key
    lock_key = Column(String(500), nullable=False, index=True)  # Unique per tenant
    lock_name = Column(String(200))  # Nome amigável

    # Status
    status = Column(
        Enum(LockStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=LockStatus.ACQUIRED
    )

    # Owner
    owner_id = Column(String(200), nullable=False)  # Worker ID ou processo que possui o lock
    owner_hostname = Column(String(200))
    owner_pid = Column(Integer)

    # Relacionamentos
    task_id = Column(UUID(as_uuid=True), ForeignKey("scheduler_tasks.id"))
    execution_id = Column(UUID(as_uuid=True), ForeignKey("scheduler_executions.id"))

    # Timing
    acquired_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    ttl_seconds = Column(Integer, default=3600)  # Time to live
    released_at = Column(DateTime)

    # Renovação
    renew_count = Column(Integer, default=0)
    last_renewed_at = Column(DateTime)
    max_renewals = Column(Integer, default=10)
    auto_renew = Column(Boolean, default=False)

    # Fila de espera
    waiters_count = Column(Integer, default=0)  # Quantos aguardando
    max_waiters = Column(Integer, default=100)

    # Metadados
    reason = Column(String(500))  # Motivo do lock
    extra_data = Column(JSONB, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<TaskLock {self.lock_key} ({self.status.value})>"

    @property
    def is_valid(self) -> bool:
        """Verifica se o lock ainda é válido."""
        if self.status != LockStatus.ACQUIRED:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Verifica se expirou."""
        return datetime.utcnow() > self.expires_at

    @property
    def remaining_seconds(self) -> int | None:
        """Segundos restantes do lock."""
        if not self.is_valid:
            return None
        return int((self.expires_at - datetime.utcnow()).total_seconds())

    @property
    def can_renew(self) -> bool:
        """Verifica se pode renovar."""
        if self.status != LockStatus.ACQUIRED:
            return False
        if self.max_renewals and self.renew_count >= self.max_renewals:
            return False
        return True

    def renew(self, ttl_seconds: int | None = None) -> bool:
        """Renova o lock."""
        if not self.can_renew:
            return False
        ttl = ttl_seconds or self.ttl_seconds
        self.expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        self.renew_count += 1
        self.last_renewed_at = datetime.utcnow()
        return True

    def release(self) -> None:
        """Libera o lock."""
        self.status = LockStatus.RELEASED
        self.released_at = datetime.utcnow()

    def expire(self) -> None:
        """Marca como expirado."""
        self.status = LockStatus.EXPIRED

    def steal(self, new_owner_id: str) -> None:
        """Rouba o lock (quando expirado)."""
        self.status = LockStatus.STOLEN
        self.released_at = datetime.utcnow()


class LockWaiter(Base):
    """Fila de espera para locks."""

    __tablename__ = "scheduler_lock_waiters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    lock_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scheduler_locks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Waiter info
    waiter_id = Column(String(200), nullable=False)
    waiter_hostname = Column(String(200))
    waiter_pid = Column(Integer)

    # Prioridade na fila
    priority = Column(Integer, default=5)
    position = Column(Integer)  # Posição na fila

    # Timing
    waiting_since = Column(DateTime, default=datetime.utcnow)
    timeout_at = Column(DateTime)  # Quando desiste
    notified_at = Column(DateTime)  # Quando foi notificado que o lock está disponível

    # Status
    acquired = Column(Boolean, default=False)
    cancelled = Column(Boolean, default=False)
    timed_out = Column(Boolean, default=False)

    # Metadados
    extra_data = Column(JSONB, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<LockWaiter {self.waiter_id} for lock {self.lock_id}>"

    @property
    def is_waiting(self) -> bool:
        """Verifica se ainda está esperando."""
        if self.acquired or self.cancelled or self.timed_out:
            return False
        if self.timeout_at and datetime.utcnow() > self.timeout_at:
            return False
        return True

    @property
    def wait_time_seconds(self) -> float:
        """Tempo de espera."""
        return (datetime.utcnow() - self.waiting_since).total_seconds()
