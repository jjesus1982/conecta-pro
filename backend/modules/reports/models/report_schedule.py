"""
ReportSchedule Model - Agendamento de Relatórios
Sprint 34: Relatórios Gerenciais
"""
# pylint: disable=too-many-branches

import enum
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class ScheduleFrequency(str, enum.Enum):
    """Frequência do agendamento."""

    ONCE = "once"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class ScheduleStatus(str, enum.Enum):
    """Status do agendamento."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class DeliveryMethod(str, enum.Enum):
    """Método de entrega."""

    EMAIL = "email"
    WEBHOOK = "webhook"
    FTP = "ftp"
    S3 = "s3"
    SHAREPOINT = "sharepoint"
    DOWNLOAD = "download"
    API = "api"


class ReportSchedule(Base):
    """Agendamento de geração de relatório."""

    __tablename__ = "report_schedules"

    # Identificação
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Status
    status = Column(
        Enum(ScheduleStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ScheduleStatus.ACTIVE,
    )

    # Frequência
    frequency = Column(Enum(ScheduleFrequency, values_callable=lambda x: [e.value for e in x]), nullable=False)
    cron_expression = Column(String(100), nullable=True)
    timezone = Column(String(50), nullable=False, default="America/Sao_Paulo")

    # Período de dados
    data_period = Column(String(50), nullable=True)
    data_start_offset = Column(Integer, nullable=True)
    data_end_offset = Column(Integer, nullable=True)
    relative_period = Column(Boolean, nullable=False, default=True)

    # Próxima execução
    next_execution_at = Column(DateTime, nullable=True)
    last_execution_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_failure_at = Column(DateTime, nullable=True)

    # Validade
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    max_executions = Column(Integer, nullable=True)

    # Parâmetros do relatório
    report_parameters = Column(JSONB, nullable=True)
    report_format = Column(String(20), nullable=False, default="pdf")
    report_filename_pattern = Column(String(200), nullable=True)

    # Entrega
    delivery_method = Column(
        Enum(DeliveryMethod, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DeliveryMethod.EMAIL,
    )
    delivery_config = Column(JSONB, nullable=True)
    recipients = Column(JSONB, nullable=True)
    cc_recipients = Column(JSONB, nullable=True)
    bcc_recipients = Column(JSONB, nullable=True)

    # Email
    email_subject = Column(String(500), nullable=True)
    email_body = Column(Text, nullable=True)
    email_template = Column(String(100), nullable=True)

    # Retry
    retry_enabled = Column(Boolean, nullable=False, default=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    retry_delay_minutes = Column(Integer, nullable=False, default=30)

    # Estatísticas
    execution_count = Column(Integer, nullable=False, default=0)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    avg_execution_time = Column(Integer, nullable=True)

    # Notificações
    notify_on_success = Column(Boolean, nullable=False, default=False)
    notify_on_failure = Column(Boolean, nullable=False, default=True)
    notification_recipients = Column(JSONB, nullable=True)

    # Metadados
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Auditoria
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    ativo = Column(Boolean, nullable=False, default=True)

    # Relacionamentos
    template = relationship("ReportTemplate", back_populates="schedules")
    exports = relationship("ReportExport", back_populates="schedule")

    __table_args__ = (
        Index("ix_report_schedules_tenant_status", "tenant_id", "status"),
        Index("ix_report_schedules_next_execution", "next_execution_at"),
        Index("ix_report_schedules_template", "template_id"),
    )

    def activate(self) -> None:
        """Ativa o agendamento."""
        self.status = ScheduleStatus.ACTIVE
        self.calculate_next_execution()
        self.updated_at = datetime.utcnow()

    def pause(self) -> None:
        """Pausa o agendamento."""
        self.status = ScheduleStatus.PAUSED
        self.updated_at = datetime.utcnow()

    def resume(self) -> None:
        """Retoma o agendamento."""
        self.status = ScheduleStatus.ACTIVE
        self.calculate_next_execution()
        self.updated_at = datetime.utcnow()

    def cancel(self) -> None:
        """Cancela o agendamento."""
        self.status = ScheduleStatus.CANCELLED
        self.next_execution_at = None
        self.updated_at = datetime.utcnow()

    def complete(self) -> None:
        """Marca como completo."""
        self.status = ScheduleStatus.COMPLETED
        self.next_execution_at = None
        self.updated_at = datetime.utcnow()

    def mark_expired(self) -> None:
        """Marca como expirado."""
        self.status = ScheduleStatus.EXPIRED
        self.next_execution_at = None
        self.updated_at = datetime.utcnow()

    def calculate_next_execution(self) -> None:
        """Calcula próxima execução."""
        now = datetime.utcnow()
        base_time = self.last_execution_at or now

        if self.frequency == ScheduleFrequency.ONCE:
            if not self.last_execution_at:
                self.next_execution_at = self.start_date or now
            else:
                self.next_execution_at = None
        elif self.frequency == ScheduleFrequency.HOURLY:
            self.next_execution_at = base_time + timedelta(hours=1)
        elif self.frequency == ScheduleFrequency.DAILY:
            self.next_execution_at = base_time + timedelta(days=1)
        elif self.frequency == ScheduleFrequency.WEEKLY:
            self.next_execution_at = base_time + timedelta(weeks=1)
        elif self.frequency == ScheduleFrequency.BIWEEKLY:
            self.next_execution_at = base_time + timedelta(weeks=2)
        elif self.frequency == ScheduleFrequency.MONTHLY:
            self.next_execution_at = base_time + timedelta(days=30)
        elif self.frequency == ScheduleFrequency.QUARTERLY:
            self.next_execution_at = base_time + timedelta(days=90)
        elif self.frequency == ScheduleFrequency.YEARLY:
            self.next_execution_at = base_time + timedelta(days=365)

        # Verifica expiração
        if self.end_date and self.next_execution_at:
            if self.next_execution_at > self.end_date:
                self.next_execution_at = None
                self.mark_expired()

        # Verifica máximo de execuções
        if self.max_executions and self.execution_count >= self.max_executions:
            self.next_execution_at = None
            self.complete()

    def record_execution(self, success: bool, execution_time: int | None = None) -> None:
        """Registra execução."""
        self.execution_count += 1
        self.last_execution_at = datetime.utcnow()

        if success:
            self.success_count += 1
            self.last_success_at = datetime.utcnow()
            self.retry_count = 0
        else:
            self.failure_count += 1
            self.last_failure_at = datetime.utcnow()

        if execution_time:
            if self.avg_execution_time:
                self.avg_execution_time = (
                    self.avg_execution_time * (self.execution_count - 1) + execution_time
                ) // self.execution_count
            else:
                self.avg_execution_time = execution_time

        self.calculate_next_execution()

    def record_retry(self) -> bool:
        """Registra tentativa de retry. Retorna True se pode tentar novamente."""
        if not self.retry_enabled:
            return False

        self.retry_count += 1
        if self.retry_count > self.max_retries:
            self.status = ScheduleStatus.FAILED
            return False

        # Agenda próxima tentativa
        self.next_execution_at = datetime.utcnow() + timedelta(minutes=self.retry_delay_minutes)
        return True

    def add_recipient(self, email: str, recipient_type: str = "to") -> None:
        """Adiciona destinatário."""
        if recipient_type == "to":
            if not self.recipients:
                self.recipients = []
            if email not in self.recipients:
                self.recipients.append(email)
        elif recipient_type == "cc":
            if not self.cc_recipients:
                self.cc_recipients = []
            if email not in self.cc_recipients:
                self.cc_recipients.append(email)
        elif recipient_type == "bcc":
            if not self.bcc_recipients:
                self.bcc_recipients = []
            if email not in self.bcc_recipients:
                self.bcc_recipients.append(email)
        self.updated_at = datetime.utcnow()

    def remove_recipient(self, email: str) -> None:
        """Remove destinatário de todas as listas."""
        if self.recipients and email in self.recipients:
            self.recipients.remove(email)
        if self.cc_recipients and email in self.cc_recipients:
            self.cc_recipients.remove(email)
        if self.bcc_recipients and email in self.bcc_recipients:
            self.bcc_recipients.remove(email)
        self.updated_at = datetime.utcnow()

    @property
    def is_active(self) -> bool:
        """Verifica se está ativo."""
        return self.status == ScheduleStatus.ACTIVE and self.ativo

    @property
    def is_due(self) -> bool:
        """Verifica se está na hora de executar."""
        if not self.next_execution_at:
            return False
        return datetime.utcnow() >= self.next_execution_at

    @property
    def success_rate(self) -> float:
        """Taxa de sucesso."""
        if self.execution_count == 0:
            return 0.0
        return (self.success_count / self.execution_count) * 100

    @property
    def all_recipients(self) -> list[str]:
        """Retorna todos os destinatários."""
        all_emails = []
        if self.recipients:
            all_emails.extend(self.recipients)
        if self.cc_recipients:
            all_emails.extend(self.cc_recipients)
        if self.bcc_recipients:
            all_emails.extend(self.bcc_recipients)
        return list(set(all_emails))

    @property
    def is_expired(self) -> bool:
        """Verifica se expirou."""
        if self.end_date and datetime.utcnow() > self.end_date:
            return True
        if self.max_executions and self.execution_count >= self.max_executions:
            return True
        return False
