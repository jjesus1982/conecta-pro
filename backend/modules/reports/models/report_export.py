"""
ReportExport Model - Exportações de Relatórios
Sprint 34: Relatórios Gerenciais
"""
# pylint: disable=unused-argument

import enum
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class ExportStatus(str, enum.Enum):
    """Status da exportação."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ExportTrigger(str, enum.Enum):
    """O que disparou a exportação."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    API = "api"
    WEBHOOK = "webhook"
    SYSTEM = "system"


class ExportFormat(str, enum.Enum):
    """Formato da exportação."""

    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    HTML = "html"
    JSON = "json"
    WORD = "word"
    POWERPOINT = "powerpoint"
    XML = "xml"


class ReportExport(Base):
    """Exportação de relatório gerado."""

    __tablename__ = "report_exports"

    # Identificação
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id"), nullable=False)
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("report_schedules.id"), nullable=True)
    export_number = Column(String(50), nullable=False, unique=True)

    # Status
    status = Column(
        Enum(ExportStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=ExportStatus.PENDING
    )
    trigger = Column(
        Enum(ExportTrigger, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExportTrigger.MANUAL,
    )

    # Formato
    format = Column(Enum(ExportFormat, values_callable=lambda x: [e.value for e in x]), nullable=False)
    filename = Column(String(500), nullable=True)
    content_type = Column(String(100), nullable=True)

    # Parâmetros usados
    parameters = Column(JSONB, nullable=True)
    filters = Column(JSONB, nullable=True)
    data_period_start = Column(DateTime, nullable=True)
    data_period_end = Column(DateTime, nullable=True)

    # Arquivo gerado
    file_path = Column(String(1000), nullable=True)
    file_url = Column(String(2000), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    file_checksum = Column(String(64), nullable=True)

    # Download
    download_token = Column(String(100), nullable=True)
    download_count = Column(Integer, nullable=False, default=0)
    max_downloads = Column(Integer, nullable=True)
    download_expires_at = Column(DateTime, nullable=True)
    last_download_at = Column(DateTime, nullable=True)

    # Processamento
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    records_processed = Column(Integer, nullable=True)
    pages_generated = Column(Integer, nullable=True)

    # Erro
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_details = Column(JSONB, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)

    # Entrega
    delivered = Column(Boolean, nullable=False, default=False)
    delivered_at = Column(DateTime, nullable=True)
    delivery_method = Column(String(50), nullable=True)
    delivery_recipient = Column(String(500), nullable=True)
    delivery_status = Column(String(50), nullable=True)

    # Metadados
    report_title = Column(String(500), nullable=True)
    report_subtitle = Column(String(500), nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Auditoria
    requested_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    ativo = Column(Boolean, nullable=False, default=True)

    # Relacionamentos
    template = relationship("ReportTemplate", back_populates="exports")
    schedule = relationship("ReportSchedule", back_populates="exports")

    __table_args__ = (
        Index("ix_report_exports_tenant_status", "tenant_id", "status"),
        Index("ix_report_exports_template", "template_id"),
        Index("ix_report_exports_schedule", "schedule_id"),
        Index("ix_report_exports_created", "created_at"),
        Index("ix_report_exports_download_token", "download_token"),
    )

    @classmethod
    def create_export(
        cls,
        template_id: str,
        export_format: ExportFormat,
        trigger: ExportTrigger = ExportTrigger.MANUAL,
        schedule_id: str | None = None,
        requested_by: str | None = None,
    ) -> "ReportExport":
        """Cria uma nova exportação."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        token = secrets.token_hex(4).upper()
        export_number = f"EXP-{timestamp}-{token}"

        return cls(
            template_id=template_id,
            schedule_id=schedule_id,
            export_number=export_number,
            format=export_format,
            trigger=trigger,
            requested_by=requested_by,
            download_token=secrets.token_urlsafe(32),
        )

    def start_processing(self) -> None:
        """Inicia o processamento."""
        self.status = ExportStatus.PROCESSING
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def complete(
        self,
        file_path: str,
        file_size: int,
        file_checksum: str | None = None,
        records: int | None = None,
        pages: int | None = None,
    ) -> None:
        """Marca como completo."""
        self.status = ExportStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.file_path = file_path
        self.file_size = file_size
        self.file_checksum = file_checksum
        self.records_processed = records
        self.pages_generated = pages

        if self.started_at:
            delta = self.completed_at - self.started_at
            self.processing_time_ms = int(delta.total_seconds() * 1000)

        # Define expiração padrão de 7 dias
        self.download_expires_at = datetime.utcnow() + timedelta(days=7)
        self.updated_at = datetime.utcnow()

    def fail(self, error_message: str, error_code: str | None = None, error_details: dict | None = None) -> None:
        """Marca como falho."""
        self.status = ExportStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        self.error_code = error_code
        self.error_details = error_details

        if self.started_at:
            delta = self.completed_at - self.started_at
            self.processing_time_ms = int(delta.total_seconds() * 1000)

        self.updated_at = datetime.utcnow()

    def cancel(self) -> None:
        """Cancela a exportação."""
        self.status = ExportStatus.CANCELLED
        self.updated_at = datetime.utcnow()

    def expire(self) -> None:
        """Marca como expirado."""
        self.status = ExportStatus.EXPIRED
        self.ativo = False
        self.updated_at = datetime.utcnow()

    def record_download(self, user_id: str | None = None) -> bool:
        """Registra download. Retorna False se não pode baixar."""
        if self.status != ExportStatus.COMPLETED:
            return False

        if self.download_expires_at and datetime.utcnow() > self.download_expires_at:
            self.expire()
            return False

        if self.max_downloads and self.download_count >= self.max_downloads:
            return False

        self.download_count += 1
        self.last_download_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        return True

    def record_delivery(self, method: str, recipient: str, status: str = "sent") -> None:
        """Registra entrega."""
        self.delivered = True
        self.delivered_at = datetime.utcnow()
        self.delivery_method = method
        self.delivery_recipient = recipient
        self.delivery_status = status
        self.updated_at = datetime.utcnow()

    def regenerate_token(self, expires_in_days: int = 7) -> str:
        """Regenera token de download."""
        self.download_token = secrets.token_urlsafe(32)
        self.download_expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        self.updated_at = datetime.utcnow()
        return self.download_token

    def extend_expiration(self, days: int) -> None:
        """Estende a expiração."""
        if self.download_expires_at:
            self.download_expires_at += timedelta(days=days)
        else:
            self.download_expires_at = datetime.utcnow() + timedelta(days=days)
        self.updated_at = datetime.utcnow()

    @property
    def is_completed(self) -> bool:
        """Verifica se está completo."""
        return self.status == ExportStatus.COMPLETED

    @property
    def is_processing(self) -> bool:
        """Verifica se está processando."""
        return self.status == ExportStatus.PROCESSING

    @property
    def is_downloadable(self) -> bool:
        """Verifica se pode ser baixado."""
        if self.status != ExportStatus.COMPLETED:
            return False
        if self.download_expires_at and datetime.utcnow() > self.download_expires_at:
            return False
        if self.max_downloads and self.download_count >= self.max_downloads:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Verifica se expirou."""
        if self.status == ExportStatus.EXPIRED:
            return True
        if self.download_expires_at and datetime.utcnow() > self.download_expires_at:
            return True
        return False

    @property
    def file_size_formatted(self) -> str:
        """Tamanho formatado."""
        if not self.file_size:
            return "0 B"
        size = self.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def processing_time_formatted(self) -> str:
        """Tempo de processamento formatado."""
        if not self.processing_time_ms:
            return "N/A"
        if self.processing_time_ms < 1000:
            return f"{self.processing_time_ms}ms"
        seconds = self.processing_time_ms / 1000
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = seconds / 60
        return f"{minutes:.1f}min"
