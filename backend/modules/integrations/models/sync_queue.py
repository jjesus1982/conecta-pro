"""
SyncQueue Model - Fila de Sincronização
Sprint 32: API Gateway / Integrações
"""

from datetime import datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class SyncDirection(StrEnum):
    """Direção da sincronização."""

    INBOUND = "inbound"  # Sistema externo -> ERP
    OUTBOUND = "outbound"  # ERP -> Sistema externo
    BIDIRECTIONAL = "bidirectional"


class SyncPriority(StrEnum):
    """Prioridade de sincronização."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BATCH = "batch"


class SyncStatus(StrEnum):
    """Status da sincronização."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    PARTIAL = "partial"


class SyncEntityType(StrEnum):
    """Tipo de entidade sendo sincronizada."""

    CLIENT = "client"
    SERVICE = "service"
    SERVICE_ORDER = "service_order"
    INVOICE = "invoice"
    PAYMENT = "payment"
    DOCUMENT = "document"
    PRODUCT = "product"
    INVENTORY = "inventory"
    USER = "user"
    LEAD = "lead"
    PROPOSAL = "proposal"
    CONTRACT = "contract"


class SyncOperationType(StrEnum):
    """Tipo de operação."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    UPSERT = "upsert"
    FULL_SYNC = "full_sync"
    DELTA_SYNC = "delta_sync"


class ExternalSystem(StrEnum):
    """Sistema externo de integração."""

    SAP = "sap"
    TOTVS = "totvs"
    OMIE = "omie"
    BLING = "bling"
    TINY = "tiny"
    NETSUITE = "netsuite"
    SALESFORCE = "salesforce"
    HUBSPOT = "hubspot"
    PIPEDRIVE = "pipedrive"
    CUSTOM = "custom"


class SyncQueue(Base):
    """
    Model para fila de sincronização.
    Gerencia sincronização assíncrona entre sistemas.
    """

    __tablename__ = "sync_queue"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    correlation_id = Column(String(50), nullable=True)
    batch_id = Column(UUID(as_uuid=True), nullable=True)  # Agrupamento

    # Sistema
    external_system = Column(
        Enum(ExternalSystem, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExternalSystem.CUSTOM,
    )
    external_system_config_id = Column(UUID(as_uuid=True), nullable=True)
    direction = Column(
        Enum(SyncDirection, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SyncDirection.OUTBOUND,
    )

    # Entidade
    entity_type = Column(Enum(SyncEntityType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    external_id = Column(String(200), nullable=True)
    operation = Column(
        Enum(SyncOperationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SyncOperationType.UPSERT,
    )

    # Dados
    payload = Column(JSONB, nullable=True)
    payload_hash = Column(String(64), nullable=True)  # Para detectar mudanças
    previous_payload = Column(JSONB, nullable=True)  # Para rollback
    transformed_payload = Column(JSONB, nullable=True)  # Após transformação

    # Status
    status = Column(
        Enum(SyncStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SyncStatus.PENDING,
    )
    priority = Column(
        Enum(SyncPriority, values_callable=lambda x: [e.value for e in x]), nullable=False, default=SyncPriority.NORMAL
    )

    # Agendamento
    scheduled_at = Column(DateTime, nullable=True)
    not_before = Column(DateTime, nullable=True)  # Não processar antes
    not_after = Column(DateTime, nullable=True)  # Não processar depois

    # Processamento
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    processed_by = Column(String(100), nullable=True)  # Worker ID

    # Retry
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(DateTime, nullable=True)
    retry_delay_seconds = Column(Integer, nullable=False, default=60)
    retry_backoff_multiplier = Column(Integer, nullable=False, default=2)

    # Erro
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)
    last_error_at = Column(DateTime, nullable=True)

    # Resposta do sistema externo
    external_response = Column(JSONB, nullable=True)
    external_status_code = Column(Integer, nullable=True)

    # Dependências
    depends_on = Column(JSONB, nullable=True)  # IDs de itens que devem ser processados antes
    blocks = Column(JSONB, nullable=True)  # IDs de itens que dependem deste

    # Callbacks
    callback_url = Column(String(500), nullable=True)
    callback_on_success = Column(Boolean, nullable=False, default=False)
    callback_on_failure = Column(Boolean, nullable=False, default=False)

    # Validação
    validation_errors = Column(JSONB, nullable=True)
    requires_review = Column(Boolean, nullable=False, default=False)
    reviewed_by = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    # Metadados
    extra_metadata = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)
    tags = Column(JSONB, nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Índices
    __table_args__ = (
        Index("ix_sync_queue_status", "status"),
        Index("ix_sync_queue_priority", "priority"),
        Index("ix_sync_queue_entity_type", "entity_type"),
        Index("ix_sync_queue_entity_id", "entity_id"),
        Index("ix_sync_queue_external_system", "external_system"),
        Index("ix_sync_queue_external_id", "external_id"),
        Index("ix_sync_queue_direction", "direction"),
        Index("ix_sync_queue_batch_id", "batch_id"),
        Index("ix_sync_queue_correlation_id", "correlation_id"),
        Index("ix_sync_queue_scheduled_at", "scheduled_at"),
        Index("ix_sync_queue_next_retry_at", "next_retry_at"),
        Index("ix_sync_queue_status_priority_scheduled", "status", "priority", "scheduled_at"),
        Index("ix_sync_queue_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<SyncQueue {self.entity_type.value} {self.status.value}>"

    def start_processing(self, worker_id: str) -> None:
        """Inicia processamento."""
        self.status = SyncStatus.PROCESSING
        self.started_at = datetime.utcnow()
        self.processed_by = worker_id
        self.updated_at = datetime.utcnow()

    def complete_success(self, external_id: str | None = None, response: dict | None = None) -> None:
        """Marca como completado com sucesso."""
        self.status = SyncStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.processing_time_ms = int(delta.total_seconds() * 1000)
        if external_id:
            self.external_id = external_id
        if response:
            self.external_response = response
        self.error_code = None
        self.error_message = None
        self.updated_at = datetime.utcnow()

    def complete_failure(
        self, error_code: str, error_message: str, error_details: dict | None = None, status_code: int | None = None
    ) -> None:
        """Marca como falha."""
        self.last_error_at = datetime.utcnow()
        self.error_code = error_code
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        if status_code:
            self.external_status_code = status_code

        if self.retry_count < self.max_retries:
            self.status = SyncStatus.RETRYING
            delay = self.retry_delay_seconds * (self.retry_backoff_multiplier**self.retry_count)
            self.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
            self.retry_count += 1
        else:
            self.status = SyncStatus.FAILED
            self.completed_at = datetime.utcnow()

        if self.started_at:
            delta = datetime.utcnow() - self.started_at
            self.processing_time_ms = int(delta.total_seconds() * 1000)

        self.updated_at = datetime.utcnow()

    def complete_partial(self, processed_count: int, total_count: int, errors: list | None = None) -> None:
        """Marca como parcialmente completado."""
        self.status = SyncStatus.PARTIAL
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.processing_time_ms = int(delta.total_seconds() * 1000)
        self.metadata = self.metadata or {}
        self.metadata["processed_count"] = processed_count
        self.metadata["total_count"] = total_count
        if errors:
            self.validation_errors = errors
        self.updated_at = datetime.utcnow()

    def cancel(self, reason: str | None = None) -> None:
        """Cancela a sincronização."""
        self.status = SyncStatus.CANCELLED
        self.completed_at = datetime.utcnow()
        if reason:
            self.notes = f"Cancelado: {reason}"
        self.updated_at = datetime.utcnow()

    def skip(self, reason: str | None = None) -> None:
        """Pula a sincronização."""
        self.status = SyncStatus.SKIPPED
        self.completed_at = datetime.utcnow()
        if reason:
            self.notes = f"Pulado: {reason}"
        self.updated_at = datetime.utcnow()

    def reset(self) -> None:
        """Reseta para reprocessamento."""
        self.status = SyncStatus.PENDING
        self.started_at = None
        self.completed_at = None
        self.processing_time_ms = None
        self.processed_by = None
        self.retry_count = 0
        self.next_retry_at = None
        self.error_code = None
        self.error_message = None
        self.error_details = None
        self.updated_at = datetime.utcnow()

    def mark_for_review(self, errors: list) -> None:
        """Marca para revisão manual."""
        self.requires_review = True
        self.validation_errors = errors
        self.updated_at = datetime.utcnow()

    def approve_review(self, reviewer_id: str) -> None:
        """Aprova revisão."""
        self.requires_review = False
        self.reviewed_by = reviewer_id
        self.reviewed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    @property
    def is_ready_to_process(self) -> bool:
        """Verifica se está pronto para processar."""
        if self.status not in [SyncStatus.PENDING, SyncStatus.RETRYING]:
            return False
        now = datetime.utcnow()
        if self.not_before and now < self.not_before:
            return False
        if self.not_after and now > self.not_after:
            return False
        if self.status == SyncStatus.RETRYING:
            if self.next_retry_at and now < self.next_retry_at:
                return False
        if self.requires_review:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Verifica se expirou."""
        if not self.not_after:
            return False
        return datetime.utcnow() > self.not_after

    @property
    def can_retry(self) -> bool:
        """Verifica se pode fazer retry."""
        return self.retry_count < self.max_retries

    @property
    def wait_time_seconds(self) -> int | None:
        """Tempo de espera até poder processar."""
        if self.status == SyncStatus.RETRYING and self.next_retry_at:
            delta = self.next_retry_at - datetime.utcnow()
            return max(0, int(delta.total_seconds()))
        if self.not_before:
            delta = self.not_before - datetime.utcnow()
            return max(0, int(delta.total_seconds()))
        return None
