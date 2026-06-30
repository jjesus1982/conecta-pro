"""
DataRetention Model - Políticas de Retenção de Dados
Sprint 33: Auditoria e Compliance
"""

from datetime import datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class RetentionPeriod(StrEnum):
    """Período de retenção."""

    DAYS_30 = "30_days"
    DAYS_90 = "90_days"
    DAYS_180 = "180_days"
    YEAR_1 = "1_year"
    YEARS_2 = "2_years"
    YEARS_3 = "3_years"
    YEARS_5 = "5_years"
    YEARS_7 = "7_years"
    YEARS_10 = "10_years"
    PERMANENT = "permanent"
    CUSTOM = "custom"


class RetentionAction(StrEnum):
    """Ação ao expirar."""

    DELETE = "delete"
    ARCHIVE = "archive"
    ANONYMIZE = "anonymize"
    REVIEW = "review"
    NOTIFY = "notify"


class RetentionStatus(StrEnum):
    """Status da política."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    DEPRECATED = "deprecated"


class DataCategory(StrEnum):
    """Categoria de dados."""

    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    FINANCIAL = "financial"
    HEALTH = "health"
    LEGAL = "legal"
    OPERATIONAL = "operational"
    ANALYTICS = "analytics"
    LOGS = "logs"
    BACKUP = "backup"
    TEMPORARY = "temporary"
    AUDIT = "audit"


class DataRetention(Base):
    """
    Model para políticas de retenção de dados.
    Define quanto tempo os dados são mantidos e o que fazer após expiração.
    """

    __tablename__ = "data_retention_policies"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(20), nullable=False, default="1.0")

    # Categoria e Status
    data_category = Column(Enum(DataCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    status = Column(
        Enum(RetentionStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=RetentionStatus.DRAFT,
    )

    # Período
    retention_period = Column(Enum(RetentionPeriod, values_callable=lambda x: [e.value for e in x]), nullable=False)
    retention_days = Column(Integer, nullable=True)
    grace_period_days = Column(Integer, nullable=True, default=30)

    # Ação ao expirar
    expiration_action = Column(
        Enum(RetentionAction, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=RetentionAction.DELETE,
    )
    secondary_action = Column(Enum(RetentionAction, values_callable=lambda x: [e.value for e in x]), nullable=True)
    action_delay_days = Column(Integer, nullable=True, default=0)

    # Escopo
    entity_types = Column(JSONB, nullable=True)
    table_names = Column(JSONB, nullable=True)
    field_patterns = Column(JSONB, nullable=True)
    excluded_entities = Column(JSONB, nullable=True)

    # Condições
    condition_query = Column(Text, nullable=True)
    condition_field = Column(String(100), nullable=True)
    condition_operator = Column(String(20), nullable=True)
    condition_value = Column(String(200), nullable=True)

    # Compliance
    compliance_framework = Column(String(100), nullable=True)
    compliance_reference = Column(String(200), nullable=True)
    legal_basis = Column(Text, nullable=True)
    legal_hold_enabled = Column(Boolean, nullable=False, default=False)

    # Anonimização
    anonymize_fields = Column(JSONB, nullable=True)
    anonymization_method = Column(String(50), nullable=True)
    preserve_statistics = Column(Boolean, nullable=False, default=False)

    # Arquivamento
    archive_location = Column(String(500), nullable=True)
    archive_format = Column(String(50), nullable=True)
    archive_encrypted = Column(Boolean, nullable=False, default=True)
    archive_compressed = Column(Boolean, nullable=False, default=True)

    # Notificações
    notify_before_days = Column(Integer, nullable=True, default=7)
    notify_recipients = Column(JSONB, nullable=True)
    notify_on_execution = Column(Boolean, nullable=False, default=True)
    require_approval = Column(Boolean, nullable=False, default=False)

    # Agendamento
    schedule_enabled = Column(Boolean, nullable=False, default=True)
    schedule_cron = Column(String(100), nullable=True)
    last_execution_at = Column(DateTime, nullable=True)
    next_execution_at = Column(DateTime, nullable=True)

    # Métricas
    total_executions = Column(Integer, nullable=False, default=0)
    records_processed = Column(Integer, nullable=False, default=0)
    records_deleted = Column(Integer, nullable=False, default=0)
    records_archived = Column(Integer, nullable=False, default=0)
    records_anonymized = Column(Integer, nullable=False, default=0)
    last_records_affected = Column(Integer, nullable=True)
    storage_freed_bytes = Column(Integer, nullable=False, default=0)

    # Erros
    last_error_at = Column(DateTime, nullable=True)
    last_error_message = Column(Text, nullable=True)
    consecutive_errors = Column(Integer, nullable=False, default=0)

    # Aprovação
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)

    # Validade
    effective_from = Column(DateTime, nullable=True)
    effective_until = Column(DateTime, nullable=True)
    review_date = Column(DateTime, nullable=True)

    # Metadados
    extra_metadata = Column(JSONB, nullable=True)
    tags = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Índices
    __table_args__ = (
        Index("ix_data_retention_code", "code"),
        Index("ix_data_retention_data_category", "data_category"),
        Index("ix_data_retention_status", "status"),
        Index("ix_data_retention_retention_period", "retention_period"),
        Index("ix_data_retention_expiration_action", "expiration_action"),
        Index("ix_data_retention_next_execution_at", "next_execution_at"),
        Index("ix_data_retention_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<DataRetention {self.code} ({self.retention_period.value})>"

    def get_retention_days(self) -> int | None:
        """Retorna dias de retenção."""
        if self.retention_days:
            return self.retention_days

        period_days = {
            RetentionPeriod.DAYS_30: 30,
            RetentionPeriod.DAYS_90: 90,
            RetentionPeriod.DAYS_180: 180,
            RetentionPeriod.YEAR_1: 365,
            RetentionPeriod.YEARS_2: 730,
            RetentionPeriod.YEARS_3: 1095,
            RetentionPeriod.YEARS_5: 1825,
            RetentionPeriod.YEARS_7: 2555,
            RetentionPeriod.YEARS_10: 3650,
            RetentionPeriod.PERMANENT: None,
            RetentionPeriod.CUSTOM: self.retention_days,
        }
        return period_days.get(self.retention_period)

    def activate(self) -> None:
        """Ativa a política."""
        self.status = RetentionStatus.ACTIVE
        if not self.effective_from:
            self.effective_from = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def pause(self, reason: str | None = None) -> None:
        """Pausa a política."""
        self.status = RetentionStatus.PAUSED
        if reason:
            self.notes = f"Pausada: {reason}"
        self.updated_at = datetime.utcnow()

    def deprecate(self, replacement_code: str | None = None) -> None:
        """Deprecia a política."""
        self.status = RetentionStatus.DEPRECATED
        if replacement_code:
            self.metadata = self.metadata or {}
            self.metadata["replaced_by"] = replacement_code
        self.updated_at = datetime.utcnow()

    def approve(self, approver_id: str, notes: str | None = None) -> None:
        """Aprova a política."""
        self.approved_by = approver_id
        self.approved_at = datetime.utcnow()
        if notes:
            self.approval_notes = notes
        self.updated_at = datetime.utcnow()

    def record_execution(
        self, records_affected: int, deleted: int = 0, archived: int = 0, anonymized: int = 0, storage_freed: int = 0
    ) -> None:
        """Registra execução."""
        self.total_executions += 1
        self.last_execution_at = datetime.utcnow()
        self.last_records_affected = records_affected
        self.records_processed += records_affected
        self.records_deleted += deleted
        self.records_archived += archived
        self.records_anonymized += anonymized
        self.storage_freed_bytes += storage_freed
        self.consecutive_errors = 0
        self._schedule_next_execution()
        self.updated_at = datetime.utcnow()

    def record_error(self, error_message: str) -> None:
        """Registra erro."""
        self.last_error_at = datetime.utcnow()
        self.last_error_message = error_message
        self.consecutive_errors += 1
        self.updated_at = datetime.utcnow()

    def _schedule_next_execution(self) -> None:
        """Agenda próxima execução."""
        if not self.schedule_enabled:
            self.next_execution_at = None
            return
        self.next_execution_at = datetime.utcnow() + timedelta(days=1)

    def enable_legal_hold(self, reason: str) -> None:
        """Habilita legal hold."""
        self.legal_hold_enabled = True
        self.metadata = self.metadata or {}
        self.metadata["legal_hold_reason"] = reason
        self.metadata["legal_hold_date"] = datetime.utcnow().isoformat()
        self.updated_at = datetime.utcnow()

    def disable_legal_hold(self, released_by: str) -> None:
        """Desabilita legal hold."""
        self.legal_hold_enabled = False
        self.metadata = self.metadata or {}
        self.metadata["legal_hold_released_by"] = released_by
        self.metadata["legal_hold_released_date"] = datetime.utcnow().isoformat()
        self.updated_at = datetime.utcnow()

    @property
    def is_effective(self) -> bool:
        """Verifica se está em vigor."""
        now = datetime.utcnow()
        if self.status != RetentionStatus.ACTIVE:
            return False
        if self.effective_from and now < self.effective_from:
            return False
        if self.effective_until and now > self.effective_until:
            return False
        return True

    @property
    def is_due(self) -> bool:
        """Verifica se está no momento de executar."""
        if not self.schedule_enabled or not self.next_execution_at:
            return False
        return datetime.utcnow() >= self.next_execution_at

    @property
    def is_permanent(self) -> bool:
        """Verifica se é retenção permanente."""
        return self.retention_period == RetentionPeriod.PERMANENT

    @property
    def has_errors(self) -> bool:
        """Verifica se tem erros consecutivos."""
        return self.consecutive_errors >= 3
