"""
Task Model - Sprint 49.

Define modelos para tarefas e dependências.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class TaskStatusEnum(StrEnum):
    """Status da tarefa."""

    BACKLOG = "BACKLOG"
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ON_HOLD = "ON_HOLD"


class TaskPriorityEnum(StrEnum):
    """Prioridade da tarefa."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class TaskTypeEnum(StrEnum):
    """Tipo de tarefa."""

    TASK = "TASK"
    BUG = "BUG"
    FEATURE = "FEATURE"
    IMPROVEMENT = "IMPROVEMENT"
    STORY = "STORY"
    EPIC = "EPIC"
    SUBTASK = "SUBTASK"
    MAINTENANCE = "MAINTENANCE"
    DOCUMENTATION = "DOCUMENTATION"
    RESEARCH = "RESEARCH"
    MEETING_ACTION = "MEETING_ACTION"
    FOLLOW_UP = "FOLLOW_UP"


class DependencyTypeEnum(StrEnum):
    """Tipo de dependência."""

    BLOCKS = "BLOCKS"
    BLOCKED_BY = "BLOCKED_BY"
    RELATES_TO = "RELATES_TO"
    DUPLICATES = "DUPLICATES"
    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"


class Task(Base):
    """Modelo de Tarefa."""

    __tablename__ = "ai_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_code = Column(String(50), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)

    # Tipo e status
    task_type = Column(
        Enum(TaskTypeEnum, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TaskTypeEnum.TASK
    )
    status = Column(
        Enum(TaskStatusEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TaskStatusEnum.TODO,
    )
    priority = Column(
        Enum(TaskPriorityEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TaskPriorityEnum.MEDIUM,
    )

    # Priorização IA
    ai_priority_score = Column(Float)  # 0-100
    ai_priority_factors = Column(JSONB, default={})
    ai_suggested_priority = Column(Enum(TaskPriorityEnum, values_callable=lambda x: [e.value for e in x]))
    priority_last_calculated = Column(DateTime)

    # Atribuição
    assignee_id = Column(UUID(as_uuid=True))
    assignee_name = Column(String(200))
    reporter_id = Column(UUID(as_uuid=True))
    reporter_name = Column(String(200))
    watchers = Column(ARRAY(UUID(as_uuid=True)), default=[])

    # Datas
    due_date = Column(DateTime)
    start_date = Column(DateTime)
    completed_at = Column(DateTime)
    ai_suggested_due_date = Column(DateTime)

    # Estimativas
    estimated_hours = Column(Float)
    actual_hours = Column(Float)
    remaining_hours = Column(Float)
    ai_estimated_hours = Column(Float)
    story_points = Column(Integer)

    # Organização
    project_id = Column(UUID(as_uuid=True))
    project_name = Column(String(200))
    sprint_id = Column(UUID(as_uuid=True))
    sprint_name = Column(String(100))
    epic_id = Column(UUID(as_uuid=True))
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey("ai_tasks.id"))

    # Relacionamento com reunião
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("ai_meetings.id"))
    meeting_action_index = Column(Integer)  # Índice do action item na reunião

    # Categorização
    tags = Column(ARRAY(String(50)), default=[])
    labels = Column(ARRAY(String(50)), default=[])
    category = Column(String(100))
    department = Column(String(100))

    # Progresso
    progress_percentage = Column(Float, default=0)
    checklist = Column(JSONB, default=[])  # Lista de subtarefas/checklist
    checklist_completed = Column(Integer, default=0)
    checklist_total = Column(Integer, default=0)

    # Bloqueios
    is_blocked = Column(Boolean, default=False)
    blocked_reason = Column(Text)
    blocked_since = Column(DateTime)

    # Contexto
    context = Column(Text)  # Contexto adicional para IA
    acceptance_criteria = Column(JSONB, default=[])
    attachments = Column(JSONB, default=[])
    links = Column(JSONB, default=[])  # Links relacionados

    # Comentários e histórico
    comments_count = Column(Integer, default=0)
    last_comment_at = Column(DateTime)
    activity_log = Column(JSONB, default=[])

    # IA e automação
    ai_generated = Column(Boolean, default=False)
    ai_generation_source = Column(String(100))  # meeting, email, etc.
    ai_suggestions = Column(JSONB, default=[])  # Sugestões da IA
    smart_notifications_enabled = Column(Boolean, default=True)

    # Recorrência
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(JSONB, default={})
    recurrence_end_date = Column(DateTime)
    parent_recurring_task_id = Column(UUID(as_uuid=True))

    # Métricas
    cycle_time_hours = Column(Float)  # Tempo do início ao fim
    lead_time_hours = Column(Float)  # Tempo da criação ao fim
    time_in_status = Column(JSONB, default={})  # Tempo em cada status

    # Metadados
    external_id = Column(String(200))  # ID em sistema externo (Jira, etc.)
    external_url = Column(String(1000))
    extra_metadata = Column(JSONB, default={})

    # Timestamps
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ativo = Column(Boolean, default=True)

    # Relationships
    subtasks = relationship("Task", backref="parent", remote_side=[id], foreign_keys=[parent_task_id])  # noqa: A003
    dependencies = relationship("TaskDependency", foreign_keys="TaskDependency.task_id", back_populates="task")

    def start_task(self):
        """Inicia a tarefa."""
        self.status = TaskStatusEnum.IN_PROGRESS
        self.start_date = datetime.utcnow()
        self._log_activity("started", "Task started")

    def complete_task(self):
        """Completa a tarefa."""
        self.status = TaskStatusEnum.COMPLETED
        self.completed_at = datetime.utcnow()
        self.progress_percentage = 100
        if self.start_date:
            self.cycle_time_hours = (self.completed_at - self.start_date).total_seconds() / 3600
        self.lead_time_hours = (self.completed_at - self.created_at).total_seconds() / 3600
        self._log_activity("completed", "Task completed")

    def block_task(self, reason: str):
        """Bloqueia a tarefa."""
        self.status = TaskStatusEnum.BLOCKED
        self.is_blocked = True
        self.blocked_reason = reason
        self.blocked_since = datetime.utcnow()
        self._log_activity("blocked", f"Task blocked: {reason}")

    def unblock_task(self):
        """Desbloqueia a tarefa."""
        self.status = TaskStatusEnum.IN_PROGRESS
        self.is_blocked = False
        self.blocked_reason = None
        self.blocked_since = None
        self._log_activity("unblocked", "Task unblocked")

    def update_progress(self, percentage: float):
        """Atualiza progresso."""
        self.progress_percentage = min(100, max(0, percentage))
        self._log_activity("progress_updated", f"Progress: {self.progress_percentage}%")

    def add_checklist_item(self, item: str):
        """Adiciona item ao checklist."""
        if self.checklist is None:
            self.checklist = []
        self.checklist.append({"item": item, "completed": False, "added_at": datetime.utcnow().isoformat()})
        self.checklist_total = len(self.checklist)
        self._update_progress_from_checklist()

    def complete_checklist_item(self, index: int):
        """Completa item do checklist."""
        if self.checklist and 0 <= index < len(self.checklist):
            self.checklist[index]["completed"] = True
            self.checklist[index]["completed_at"] = datetime.utcnow().isoformat()
            self.checklist_completed = sum(1 for item in self.checklist if item.get("completed"))
            self._update_progress_from_checklist()

    def _update_progress_from_checklist(self):
        """Atualiza progresso baseado no checklist."""
        if self.checklist_total > 0:
            self.progress_percentage = (self.checklist_completed / self.checklist_total) * 100

    def assign_to(self, user_id: uuid.UUID, user_name: str):
        """Atribui a tarefa."""
        self.assignee_id = user_id
        self.assignee_name = user_name
        self._log_activity("assigned", f"Assigned to {user_name}")

    def change_priority(self, new_priority: TaskPriorityEnum, reason: str = None):
        """Altera prioridade."""
        old_priority = self.priority
        self.priority = new_priority
        self._log_activity(
            "priority_changed", f"Priority changed from {old_priority} to {new_priority}", {"reason": reason}
        )

    def add_ai_suggestion(self, suggestion_type: str, suggestion: str, confidence: float):
        """Adiciona sugestão da IA."""
        if self.ai_suggestions is None:
            self.ai_suggestions = []
        self.ai_suggestions.append(
            {
                "type": suggestion_type,
                "suggestion": suggestion,
                "confidence": confidence,
                "created_at": datetime.utcnow().isoformat(),
                "applied": False,
            }
        )

    def _log_activity(self, action: str, description: str, extra: dict[str, Any] = None):
        """Registra atividade."""
        if self.activity_log is None:
            self.activity_log = []
        log_entry = {"action": action, "description": description, "timestamp": datetime.utcnow().isoformat()}
        if extra:
            log_entry["extra"] = extra
        self.activity_log.append(log_entry)

    def calculate_ai_priority(self):
        """Calcula prioridade sugerida pela IA."""
        score = 50  # Base score
        factors = {}

        # Fator: prazo
        if self.due_date:
            days_until_due = (self.due_date - datetime.utcnow()).days
            if days_until_due < 0:
                score += 30
                factors["overdue"] = True
            elif days_until_due <= 1:
                score += 20
                factors["due_soon"] = True
            elif days_until_due <= 7:
                score += 10
                factors["due_this_week"] = True

        # Fator: dependências
        if self.is_blocked:
            score -= 20
            factors["blocked"] = True

        # Fator: tipo
        if self.task_type == TaskTypeEnum.BUG:
            score += 15
            factors["is_bug"] = True
        elif self.task_type == TaskTypeEnum.CRITICAL:
            score += 25
            factors["is_critical"] = True

        # Fator: watchers
        if self.watchers and len(self.watchers) > 3:
            score += 10
            factors["high_visibility"] = True

        # Normaliza score
        score = min(100, max(0, score))

        # Determina prioridade sugerida
        if score >= 80:
            suggested = TaskPriorityEnum.CRITICAL
        elif score >= 60:
            suggested = TaskPriorityEnum.HIGH
        elif score >= 40:
            suggested = TaskPriorityEnum.MEDIUM
        else:
            suggested = TaskPriorityEnum.LOW

        self.ai_priority_score = score
        self.ai_priority_factors = factors
        self.ai_suggested_priority = suggested
        self.priority_last_calculated = datetime.utcnow()

        return score, suggested, factors


class TaskDependency(Base):
    """Modelo de Dependência entre Tarefas."""

    __tablename__ = "ai_task_dependencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("ai_tasks.id"), nullable=False)
    related_task_id = Column(UUID(as_uuid=True), ForeignKey("ai_tasks.id"), nullable=False)

    dependency_type = Column(
        Enum(DependencyTypeEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DependencyTypeEnum.RELATES_TO,
    )

    # Metadados
    description = Column(Text)
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    task = relationship("Task", foreign_keys=[task_id], back_populates="dependencies")
    related_task = relationship("Task", foreign_keys=[related_task_id])
