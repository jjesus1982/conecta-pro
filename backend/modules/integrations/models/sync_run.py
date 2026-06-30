"""
SyncRun Model - Histórico de Execuções de Sincronização
Sprint 33: Integration Framework
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class SyncRunStatus(StrEnum):
    """Status da execução de sync."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


class SyncRunMode(StrEnum):
    """Modo de sincronização."""

    FULL = "full"
    INCREMENTAL = "incremental"
    DELTA = "delta"
    MANUAL = "manual"
    WEBHOOK_TRIGGERED = "webhook_triggered"
    RECOVERY = "recovery"


class SyncRunTrigger(StrEnum):
    """O que disparou a sync."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    WEBHOOK = "webhook"
    API = "api"
    RETRY = "retry"
    RECOVERY = "recovery"


class SyncRun(Base):
    """
    Model para histórico de execuções de sincronização.
    Cada sync run registra métricas, erros e estado.
    """

    __tablename__ = "sync_runs"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Referências
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    account_id = Column(
        UUID(as_uuid=True), ForeignKey("integration_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Identificação
    correlation_id = Column(String(100), nullable=True, index=True)
    parent_run_id = Column(UUID(as_uuid=True), nullable=True)  # Para retries
    batch_id = Column(UUID(as_uuid=True), nullable=True)  # Agrupamento

    # Tipo e Modo
    connector_type = Column(String(50), nullable=False)
    mode = Column(
        Enum(SyncRunMode, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SyncRunMode.INCREMENTAL,
    )
    trigger = Column(
        Enum(SyncRunTrigger, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SyncRunTrigger.SCHEDULED,
    )
    triggered_by = Column(UUID(as_uuid=True), nullable=True)  # User ID se manual

    # Entidades
    entities = Column(JSONB, nullable=True)  # ["products", "clients"]
    entity_filters = Column(JSONB, nullable=True)  # Filtros aplicados

    # Status
    status = Column(
        Enum(SyncRunStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SyncRunStatus.PENDING,
    )
    status_message = Column(Text, nullable=True)

    # Timing
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    timeout_seconds = Column(Integer, nullable=False, default=3600)

    # Worker
    worker_id = Column(String(100), nullable=True)
    worker_host = Column(String(200), nullable=True)

    # Métricas de Processamento
    items_total = Column(Integer, nullable=False, default=0)
    items_processed = Column(Integer, nullable=False, default=0)
    items_created = Column(Integer, nullable=False, default=0)
    items_updated = Column(Integer, nullable=False, default=0)
    items_deleted = Column(Integer, nullable=False, default=0)
    items_skipped = Column(Integer, nullable=False, default=0)
    items_failed = Column(Integer, nullable=False, default=0)

    # Métricas de API
    api_requests_total = Column(Integer, nullable=False, default=0)
    api_requests_success = Column(Integer, nullable=False, default=0)
    api_requests_failed = Column(Integer, nullable=False, default=0)
    api_rate_limit_hits = Column(Integer, nullable=False, default=0)
    api_total_latency_ms = Column(Integer, nullable=False, default=0)

    # Paginação/Cursor
    pages_processed = Column(Integer, nullable=False, default=0)
    last_cursor = Column(String(500), nullable=True)
    last_processed_id = Column(String(200), nullable=True)
    last_processed_at = Column(DateTime, nullable=True)

    # Erros
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)
    errors_log = Column(JSONB, nullable=True)  # Lista de erros durante execução

    # Retry
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    retry_delay_seconds = Column(Integer, nullable=False, default=60)

    # Checkpoint/Recovery
    checkpoint_data = Column(JSONB, nullable=True)
    can_resume = Column(Boolean, nullable=False, default=True)

    # Resultado
    result_summary = Column(JSONB, nullable=True)  # Resumo do resultado
    warnings = Column(JSONB, nullable=True)  # Avisos não-críticos

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Índices
    __table_args__ = (
        Index("ix_sync_runs_tenant_id", "tenant_id"),
        Index("ix_sync_runs_account_id", "account_id"),
        Index("ix_sync_runs_status", "status"),
        Index("ix_sync_runs_connector_type", "connector_type"),
        Index("ix_sync_runs_correlation_id", "correlation_id"),
        Index("ix_sync_runs_started_at", "started_at"),
        Index("ix_sync_runs_completed_at", "completed_at"),
        Index("ix_sync_runs_tenant_status", "tenant_id", "status"),
        Index("ix_sync_runs_account_status", "account_id", "status"),
        Index("ix_sync_runs_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<SyncRun {self.connector_type} {self.status.value}>"

    def start(self, worker_id: str, worker_host: str | None = None) -> None:
        """Inicia a execução."""
        self.status = SyncRunStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.worker_id = worker_id
        self.worker_host = worker_host
        self.updated_at = datetime.utcnow()

    def complete_success(self, summary: dict | None = None) -> None:
        """Marca como completado com sucesso."""
        self.status = SyncRunStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
        if summary:
            self.result_summary = summary
        self.updated_at = datetime.utcnow()

    def complete_failed(self, error_code: str, error_message: str, error_details: dict | None = None) -> None:
        """Marca como falha."""
        self.status = SyncRunStatus.FAILED
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
        self.error_code = error_code
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        self.updated_at = datetime.utcnow()

    def complete_partial(self, summary: dict | None = None, warnings: list | None = None) -> None:
        """Marca como parcialmente completado."""
        self.status = SyncRunStatus.PARTIAL
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
        if summary:
            self.result_summary = summary
        if warnings:
            self.warnings = warnings
        self.updated_at = datetime.utcnow()

    def complete_timeout(self) -> None:
        """Marca como timeout."""
        self.status = SyncRunStatus.TIMEOUT
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
        self.error_code = "TIMEOUT"
        self.error_message = f"Execução excedeu {self.timeout_seconds}s"
        self.updated_at = datetime.utcnow()

    def cancel(self, reason: str | None = None) -> None:
        """Cancela a execução."""
        self.status = SyncRunStatus.CANCELLED
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
        if reason:
            self.status_message = f"Cancelado: {reason}"
        self.updated_at = datetime.utcnow()

    def increment_items(
        self,
        processed: int = 0,
        created: int = 0,
        updated: int = 0,
        deleted: int = 0,
        skipped: int = 0,
        failed: int = 0,
    ) -> None:
        """Incrementa contadores de itens."""
        self.items_processed += processed
        self.items_created += created
        self.items_updated += updated
        self.items_deleted += deleted
        self.items_skipped += skipped
        self.items_failed += failed
        self.updated_at = datetime.utcnow()

    def increment_api_metrics(
        self, requests: int = 1, success: bool = True, latency_ms: int = 0, rate_limited: bool = False
    ) -> None:
        """Incrementa métricas de API."""
        self.api_requests_total += requests
        if success:
            self.api_requests_success += requests
        else:
            self.api_requests_failed += requests
        if rate_limited:
            self.api_rate_limit_hits += 1
        self.api_total_latency_ms += latency_ms
        self.updated_at = datetime.utcnow()

    def save_checkpoint(self, cursor: str | None = None, last_id: str | None = None, data: dict | None = None) -> None:
        """Salva checkpoint para recovery."""
        if cursor:
            self.last_cursor = cursor
        if last_id:
            self.last_processed_id = last_id
        self.last_processed_at = datetime.utcnow()
        if data:
            self.checkpoint_data = data
        self.updated_at = datetime.utcnow()

    def add_error(self, error: dict) -> None:
        """Adiciona erro ao log."""
        if not self.errors_log:
            self.errors_log = []
        self.errors_log.append({**error, "timestamp": datetime.utcnow().isoformat()})
        self.updated_at = datetime.utcnow()

    def add_warning(self, warning: str) -> None:
        """Adiciona aviso."""
        if not self.warnings:
            self.warnings = []
        self.warnings.append({"message": warning, "timestamp": datetime.utcnow().isoformat()})
        self.updated_at = datetime.utcnow()

    @property
    def is_running(self) -> bool:
        """Verifica se está em execução."""
        return self.status == SyncRunStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        """Verifica se está completado (sucesso ou falha)."""
        return self.status in [
            SyncRunStatus.COMPLETED,
            SyncRunStatus.FAILED,
            SyncRunStatus.CANCELLED,
            SyncRunStatus.PARTIAL,
            SyncRunStatus.TIMEOUT,
        ]

    @property
    def success_rate(self) -> float:
        """Taxa de sucesso de itens."""
        if self.items_processed == 0:
            return 0.0
        return (self.items_processed - self.items_failed) / self.items_processed * 100

    @property
    def avg_api_latency_ms(self) -> float:
        """Latência média de API."""
        if self.api_requests_total == 0:
            return 0.0
        return self.api_total_latency_ms / self.api_requests_total

    @property
    def is_timed_out(self) -> bool:
        """Verifica se excedeu timeout."""
        if not self.started_at or self.is_completed:
            return False
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        return elapsed >= self.timeout_seconds

    def to_metrics_dict(self) -> dict:
        """Retorna dict para métricas Prometheus."""
        return {
            "connector_type": self.connector_type,
            "status": self.status.value,
            "mode": self.mode.value,
            "duration_ms": self.duration_ms or 0,
            "items_total": self.items_total,
            "items_processed": self.items_processed,
            "items_failed": self.items_failed,
            "api_requests_total": self.api_requests_total,
            "api_requests_failed": self.api_requests_failed,
            "success_rate": self.success_rate,
            "avg_api_latency_ms": self.avg_api_latency_ms,
        }
