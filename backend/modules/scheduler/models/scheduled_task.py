"""ScheduledTask Model - Tarefas Agendadas.

Sprint 35 - Task Scheduler.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class TaskStatus(StrEnum):
    """Status da tarefa."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class TaskType(StrEnum):
    """Tipo de tarefa."""

    CRON = "cron"  # Execução baseada em cron expression
    INTERVAL = "interval"  # Execução em intervalos fixos
    ONCE = "once"  # Execução única em data específica
    EVENT = "event"  # Execução baseada em evento
    DEPENDENCY = "dependency"  # Execução após outra tarefa
    MANUAL = "manual"  # Execução manual sob demanda


class TaskCategory(StrEnum):
    """Categoria da tarefa."""

    SYSTEM = "system"  # Tarefas do sistema
    BACKUP = "backup"  # Backups
    CLEANUP = "cleanup"  # Limpeza de dados
    SYNC = "sync"  # Sincronizações
    REPORT = "report"  # Geração de relatórios
    NOTIFICATION = "notification"  # Envio de notificações
    AI = "ai"  # Processamento de IA
    INTEGRATION = "integration"  # Integrações externas
    MAINTENANCE = "maintenance"  # Manutenção
    WORKFLOW = "workflow"  # Workflows
    CUSTOM = "custom"  # Customizado


class ScheduledTask(Base):
    """Modelo de tarefa agendada."""

    __tablename__ = "scheduler_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificação
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, index=True)
    description = Column(Text)

    # Classificação
    task_type = Column(
        Enum(TaskType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TaskType.CRON
    )
    category = Column(
        Enum(TaskCategory, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TaskCategory.CUSTOM
    )
    status = Column(
        Enum(TaskStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TaskStatus.DRAFT
    )

    # Agendamento - Cron
    cron_expression = Column(String(100))  # Ex: "0 0 * * *" (meia-noite todo dia)
    timezone = Column(String(50), default="America/Sao_Paulo")

    # Agendamento - Interval
    interval_seconds = Column(Integer)  # Intervalo em segundos
    interval_type = Column(String(20))  # seconds, minutes, hours, days

    # Agendamento - Once
    scheduled_at = Column(DateTime)  # Data/hora específica para execução única

    # Agendamento - Dependency
    depends_on_task_id = Column(UUID(as_uuid=True), ForeignKey("scheduler_tasks.id"))
    dependency_condition = Column(String(20))  # success, failure, complete

    # Período de validade
    valid_from = Column(DateTime, default=datetime.utcnow)
    valid_until = Column(DateTime)  # Null = sem expiração

    # Configuração de execução
    handler = Column(String(200), nullable=False)  # Função/método a executar
    handler_module = Column(String(200))  # Módulo Python
    handler_args = Column(JSONB, default=dict)  # Argumentos
    handler_kwargs = Column(JSONB, default=dict)  # Kwargs

    # Timeout e retries
    timeout_seconds = Column(Integer, default=3600)  # 1 hora default
    max_retries = Column(Integer, default=3)
    retry_delay_seconds = Column(Integer, default=60)
    retry_backoff_multiplier = Column(Float, default=2.0)  # Exponential backoff

    # Concorrência
    max_concurrent = Column(Integer, default=1)  # Máximo de execuções simultâneas
    allow_overlap = Column(Boolean, default=False)  # Permite sobreposição

    # Prioridade
    priority = Column(Integer, default=5)  # 1 (alta) a 10 (baixa)
    queue_name = Column(String(100), default="default")

    # Recursos
    memory_limit_mb = Column(Integer)
    cpu_limit = Column(Float)  # 0.5 = 50% de 1 CPU

    # Notificações
    notify_on_success = Column(Boolean, default=False)
    notify_on_failure = Column(Boolean, default=True)
    notify_on_retry = Column(Boolean, default=False)
    notify_emails = Column(ARRAY(String))
    notify_webhook = Column(String(500))

    # Métricas
    total_executions = Column(Integer, default=0)
    successful_executions = Column(Integer, default=0)
    failed_executions = Column(Integer, default=0)
    avg_duration_seconds = Column(Float)
    last_duration_seconds = Column(Float)

    # Histórico
    last_run_at = Column(DateTime)
    last_success_at = Column(DateTime)
    last_failure_at = Column(DateTime)
    next_run_at = Column(DateTime)

    # Metadados
    tags = Column(ARRAY(String), default=list)
    extra_data = Column(JSONB, default=dict)

    # Auditoria
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = Column(Boolean, default=True)

    # Relationships
    executions = relationship("TaskExecution", back_populates="task", lazy="dynamic")
    dependent_tasks = relationship(
        "ScheduledTask",
        backref="parent_task",
        remote_side=[id],  # noqa: A003
        foreign_keys=[depends_on_task_id],
    )

    def __repr__(self) -> str:
        return f"<ScheduledTask {self.name} ({self.status.value})>"

    @property
    def success_rate(self) -> float | None:
        """Taxa de sucesso."""
        if self.total_executions == 0:
            return None
        return self.successful_executions / self.total_executions

    @property
    def is_due(self) -> bool:
        """Verifica se a tarefa está no momento de execução."""
        if self.status != TaskStatus.ACTIVE:
            return False
        if self.next_run_at is None:
            return False
        return datetime.utcnow() >= self.next_run_at

    @property
    def is_expired(self) -> bool:
        """Verifica se a tarefa expirou."""
        if self.valid_until is None:
            return False
        return datetime.utcnow() > self.valid_until
