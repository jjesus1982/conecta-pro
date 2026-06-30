"""TaskExecution Model - Histórico de Execuções.

Sprint 35 - Task Scheduler.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class ExecutionStatus(StrEnum):
    """Status da execução."""

    PENDING = "pending"  # Aguardando início
    QUEUED = "queued"  # Na fila
    RUNNING = "running"  # Em execução
    SUCCESS = "success"  # Sucesso
    FAILED = "failed"  # Falhou
    TIMEOUT = "timeout"  # Timeout
    CANCELLED = "cancelled"  # Cancelado
    SKIPPED = "skipped"  # Pulado (overlap, condição não atendida)
    RETRY = "retry"  # Aguardando retry


class TaskExecution(Base):
    """Modelo de execução de tarefa."""

    __tablename__ = "scheduler_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Relacionamento com tarefa
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scheduler_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identificação
    execution_number = Column(Integer, nullable=False)  # Sequencial por tarefa
    run_id = Column(String(50), unique=True, index=True)  # ID único da execução

    # Status
    status = Column(
        Enum(ExecutionStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExecutionStatus.PENDING,
    )

    # Worker
    worker_id = Column(UUID(as_uuid=True), ForeignKey("scheduler_workers.id"))
    worker_hostname = Column(String(200))
    worker_pid = Column(Integer)

    # Timing
    scheduled_at = Column(DateTime)  # Quando deveria executar
    queued_at = Column(DateTime)  # Quando entrou na fila
    started_at = Column(DateTime)  # Quando iniciou
    completed_at = Column(DateTime)  # Quando completou
    duration_seconds = Column(Float)

    # Retries
    attempt_number = Column(Integer, default=1)  # Tentativa atual
    max_attempts = Column(Integer, default=3)
    retry_at = Column(DateTime)  # Próximo retry
    retry_count = Column(Integer, default=0)

    # Input/Output
    input_args = Column(JSONB)  # Args da execução
    input_kwargs = Column(JSONB)  # Kwargs da execução
    output_result = Column(JSONB)  # Resultado
    output_artifacts = Column(JSONB)  # Artefatos gerados (arquivos, etc)

    # Erro
    error_type = Column(String(200))  # Tipo do erro
    error_message = Column(Text)  # Mensagem de erro
    error_traceback = Column(Text)  # Traceback completo
    error_code = Column(String(50))  # Código de erro

    # Recursos utilizados
    memory_used_mb = Column(Float)
    cpu_used_percent = Column(Float)
    disk_read_mb = Column(Float)
    disk_write_mb = Column(Float)

    # Logs
    log_output = Column(Text)  # Output do log
    log_level = Column(String(20))  # Nível máximo de log
    log_lines_count = Column(Integer)

    # Progresso
    progress_percent = Column(Float, default=0)
    progress_message = Column(String(500))
    progress_data = Column(JSONB)

    # Trigger info
    trigger_type = Column(String(50))  # cron, manual, api, dependency, event
    triggered_by = Column(UUID(as_uuid=True))  # Usuário que triggou (se manual)
    trigger_event = Column(String(200))  # Evento que triggou

    # Metadados
    extra_data = Column(JSONB, default=dict)
    tags = Column(JSONB, default=list)

    # Checkpoints (para resumir execuções longas)
    checkpoint_data = Column(JSONB)
    checkpoint_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    task = relationship("ScheduledTask", back_populates="executions")
    worker = relationship("TaskWorker", back_populates="executions")
    logs = relationship("TaskExecutionLog", back_populates="execution", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<TaskExecution {self.run_id} ({self.status.value})>"

    @property
    def is_running(self) -> bool:
        """Verifica se está em execução."""
        return self.status == ExecutionStatus.RUNNING

    @property
    def is_finished(self) -> bool:
        """Verifica se terminou."""
        return self.status in [
            ExecutionStatus.SUCCESS,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.SKIPPED,
        ]

    @property
    def can_retry(self) -> bool:
        """Verifica se pode tentar novamente."""
        if self.status not in [ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT]:
            return False
        return self.attempt_number < self.max_attempts

    @property
    def wait_time_seconds(self) -> float | None:
        """Tempo de espera na fila."""
        if self.queued_at and self.started_at:
            return (self.started_at - self.queued_at).total_seconds()
        return None


class TaskExecutionLog(Base):
    """Log detalhado de execução."""

    __tablename__ = "scheduler_execution_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey("scheduler_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Log entry
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String(20), nullable=False)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message = Column(Text, nullable=False)
    logger_name = Column(String(200))

    # Contexto
    context = Column(JSONB)
    extra_data = Column(JSONB)

    # Stack trace (para erros)
    exc_info = Column(Text)

    # Relacionamento
    execution = relationship("TaskExecution", back_populates="logs")

    def __repr__(self) -> str:
        return f"<TaskExecutionLog {self.level} at {self.timestamp}>"
