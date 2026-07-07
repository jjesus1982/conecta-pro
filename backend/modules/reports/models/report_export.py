"""
ReportExport Model - Exportações de Relatórios
Sprint 34: Relatórios Gerenciais

Reconciliado com a tabela real `report_exports` (2026-07-07, Ciclo 3 item 16):
a tabela do banco é a fonte da verdade — nomes/tipos/nullable abaixo batem 1:1
com o `\\d report_exports` de produção. NÃO reintroduzir colunas fantasmas
(export_number, filename, content_type, file_url, file_checksum, max_downloads,
download_expires_at, last_download_at, records_processed, pages_generated,
error_code, retry_count, delivery_recipient, delivery_status, report_title,
report_subtitle, data_period_start/end).
"""
# pylint: disable=unused-argument

import enum
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
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
    export_id = Column(String(50), nullable=False, unique=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id"), nullable=False, index=True)
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("report_schedules.id"), nullable=True, index=True)

    # Status
    status = Column(
        Enum(ExportStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExportStatus.PENDING,
        index=True,
    )
    trigger = Column(
        Enum(ExportTrigger, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExportTrigger.MANUAL,
        index=True,
    )

    # Formato
    format = Column(Enum(ExportFormat, values_callable=lambda x: [e.value for e in x]), nullable=False)

    # Parâmetros usados
    parameters = Column(JSONB, nullable=True)
    filters = Column(JSONB, nullable=True)

    # Arquivo gerado
    file_name = Column(String(500), nullable=True)
    file_path = Column(String(1000), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    file_hash = Column(String(64), nullable=True)
    mime_type = Column(String(100), nullable=True)
    row_count = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)

    # Processamento
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)

    # Erro
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)

    # Download
    download_url = Column(String(1000), nullable=True)
    download_token = Column(String(100), nullable=True, index=True)
    download_count = Column(Integer, nullable=False, default=0)
    last_downloaded_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Entrega
    delivered = Column(Boolean, nullable=False, default=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    delivery_method = Column(String(20), nullable=True)
    delivery_details = Column(JSONB, nullable=True)

    # Auditoria / Metadados
    requested_by = Column(UUID(as_uuid=True), nullable=True, index=True)
    extra_metadata = Column(JSONB, nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)
    tenant_id = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    template = relationship("ReportTemplate", back_populates="exports")
    schedule = relationship("ReportSchedule", back_populates="exports")

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
        export_id = f"EXP-{timestamp}-{token}"

        return cls(
            template_id=template_id,
            schedule_id=schedule_id,
            export_id=export_id,
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
        self.file_hash = file_checksum
        self.row_count = records
        self.page_count = pages

        if self.started_at:
            delta = self.completed_at - self._naive(self.started_at)
            self.processing_time_ms = int(delta.total_seconds() * 1000)

        # Define expiração padrão de 7 dias
        self.expires_at = datetime.utcnow() + timedelta(days=7)
        self.updated_at = datetime.utcnow()

    def fail(self, error_message: str, error_code: str | None = None, error_details: dict | None = None) -> None:
        """Marca como falho. error_code é armazenado dentro de error_details (JSONB)."""
        self.status = ExportStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        if error_code:
            error_details = {**(error_details or {}), "error_code": error_code}
        self.error_details = error_details

        if self.started_at:
            delta = self.completed_at - self._naive(self.started_at)
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

        if self.expires_at and datetime.utcnow() > self._naive(self.expires_at):
            self.expire()
            return False

        self.download_count += 1
        self.last_downloaded_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        return True

    def record_delivery(self, method: str, recipient: str, status: str = "sent") -> None:
        """Registra entrega. Destinatário e status ficam em delivery_details (JSONB)."""
        self.delivered = True
        self.delivered_at = datetime.utcnow()
        self.delivery_method = method
        self.delivery_details = {**(self.delivery_details or {}), "recipient": recipient, "status": status}
        self.updated_at = datetime.utcnow()

    def regenerate_token(self, expires_in_days: int = 7) -> str:
        """Regenera token de download."""
        self.download_token = secrets.token_urlsafe(32)
        self.expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        self.updated_at = datetime.utcnow()
        return self.download_token

    def extend_expiration(self, days: int) -> None:
        """Estende a expiração."""
        if self.expires_at:
            self.expires_at += timedelta(days=days)
        else:
            self.expires_at = datetime.utcnow() + timedelta(days=days)
        self.updated_at = datetime.utcnow()

    @staticmethod
    def _naive(dt: datetime) -> datetime:
        """Compara com segurança datetimes vindos do banco (timestamptz) contra utcnow naive."""
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

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
        if self.expires_at and datetime.utcnow() > self._naive(self.expires_at):
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Verifica se expirou."""
        if self.status == ExportStatus.EXPIRED:
            return True
        if self.expires_at and datetime.utcnow() > self._naive(self.expires_at):
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
