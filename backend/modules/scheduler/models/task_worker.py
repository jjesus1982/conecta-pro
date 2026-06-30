"""TaskWorker Model - Workers de Processamento.

Sprint 35 - Task Scheduler.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class WorkerStatus(StrEnum):
    """Status do worker."""

    STARTING = "starting"  # Iniciando
    IDLE = "idle"  # Ocioso
    BUSY = "busy"  # Processando
    PAUSED = "paused"  # Pausado
    DRAINING = "draining"  # Drenando (não aceita novas tarefas)
    STOPPING = "stopping"  # Parando
    STOPPED = "stopped"  # Parado
    OFFLINE = "offline"  # Offline
    ERROR = "error"  # Erro


class TaskWorker(Base):
    """Modelo de worker de tarefas."""

    __tablename__ = "scheduler_workers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identificação
    name = Column(String(200), nullable=False)
    worker_id = Column(String(100), unique=True, nullable=False, index=True)

    # Host
    hostname = Column(String(200), nullable=False)
    ip_address = Column(String(50))
    pid = Column(Integer)
    process_name = Column(String(100))

    # Status
    status = Column(
        Enum(WorkerStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=WorkerStatus.STARTING,
    )

    # Configuração
    queues = Column(ARRAY(String), default=["default"])  # Filas que processa
    concurrency = Column(Integer, default=4)  # Tarefas simultâneas
    prefetch_count = Column(Integer, default=1)  # Quantas pré-busca

    # Capacidades
    categories = Column(ARRAY(String))  # Categorias que pode processar
    tags = Column(ARRAY(String))  # Tags de capability
    max_memory_mb = Column(Integer)
    max_tasks_per_hour = Column(Integer)

    # Métricas de recursos
    cpu_count = Column(Integer)
    cpu_percent = Column(Float)
    memory_total_mb = Column(Float)
    memory_used_mb = Column(Float)
    memory_percent = Column(Float)
    disk_total_gb = Column(Float)
    disk_used_gb = Column(Float)
    disk_percent = Column(Float)
    load_average = Column(ARRAY(Float))  # 1, 5, 15 min

    # Métricas de execução
    total_tasks_processed = Column(Integer, default=0)
    tasks_succeeded = Column(Integer, default=0)
    tasks_failed = Column(Integer, default=0)
    tasks_in_progress = Column(Integer, default=0)
    avg_task_duration_seconds = Column(Float)

    # Rate limiting
    tasks_this_hour = Column(Integer, default=0)
    tasks_today = Column(Integer, default=0)
    hour_reset_at = Column(DateTime)
    day_reset_at = Column(DateTime)

    # Heartbeat
    heartbeat_interval_seconds = Column(Integer, default=30)
    last_heartbeat_at = Column(DateTime)
    heartbeat_missed_count = Column(Integer, default=0)
    max_missed_heartbeats = Column(Integer, default=3)

    # Versão
    version = Column(String(50))
    python_version = Column(String(20))
    platform = Column(String(100))

    # Timing
    started_at = Column(DateTime)
    last_task_at = Column(DateTime)
    last_idle_at = Column(DateTime)

    # Metadados
    extra_data = Column(JSONB, default=dict)
    labels = Column(JSONB, default=dict)

    # Timestamps
    registered_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = Column(Boolean, default=True)

    # Relationships
    executions = relationship("TaskExecution", back_populates="worker", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<TaskWorker {self.name} ({self.status.value})>"

    @property
    def is_alive(self) -> bool:
        """Verifica se o worker está vivo (heartbeat recente)."""
        if self.last_heartbeat_at is None:
            return False
        elapsed = (datetime.utcnow() - self.last_heartbeat_at).total_seconds()
        max_elapsed = self.heartbeat_interval_seconds * (self.max_missed_heartbeats + 1)
        return elapsed <= max_elapsed

    @property
    def is_available(self) -> bool:
        """Verifica se pode processar tarefas."""
        if self.status not in [WorkerStatus.IDLE, WorkerStatus.BUSY]:
            return False
        if not self.is_alive:
            return False
        if self.tasks_in_progress >= self.concurrency:
            return False
        return True

    @property
    def available_slots(self) -> int:
        """Slots disponíveis para tarefas."""
        return max(0, self.concurrency - self.tasks_in_progress)

    @property
    def success_rate(self) -> float | None:
        """Taxa de sucesso."""
        if self.total_tasks_processed == 0:
            return None
        return self.tasks_succeeded / self.total_tasks_processed

    @property
    def utilization_percent(self) -> float:
        """Utilização do worker."""
        if self.concurrency == 0:
            return 0
        return (self.tasks_in_progress / self.concurrency) * 100

    def update_heartbeat(self) -> None:
        """Atualiza o heartbeat."""
        self.last_heartbeat_at = datetime.utcnow()
        self.heartbeat_missed_count = 0

    def record_task_start(self) -> None:
        """Registra início de tarefa."""
        self.tasks_in_progress += 1
        self.last_task_at = datetime.utcnow()
        if self.status == WorkerStatus.IDLE:
            self.status = WorkerStatus.BUSY

    def record_task_complete(self, success: bool = True) -> None:
        """Registra conclusão de tarefa."""
        self.tasks_in_progress = max(0, self.tasks_in_progress - 1)
        self.total_tasks_processed += 1
        self.tasks_this_hour += 1
        self.tasks_today += 1
        if success:
            self.tasks_succeeded += 1
        else:
            self.tasks_failed += 1
        if self.tasks_in_progress == 0:
            self.status = WorkerStatus.IDLE
            self.last_idle_at = datetime.utcnow()
