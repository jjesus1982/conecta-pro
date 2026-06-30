"""
ServiceReport Model - Relatórios de Serviços
Sprint 31: Gestão de Serviços
"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.services.models.service_order import ServiceOrder


class ReportType(StrEnum):
    """Tipo de relatório."""

    EXECUCAO = "execucao"
    TECNICO = "tecnico"
    FOTOGRAFICO = "fotografico"
    MANUTENCAO = "manutencao"
    INSPECAO = "inspecao"
    AUDITORIA = "auditoria"
    INCIDENTE = "incidente"
    PREVENTIVO = "preventivo"
    CORRETIVO = "corretivo"
    FINAL = "final"


class ServiceReport(Base):
    """
    Model para relatórios de serviços.
    Documenta os serviços executados.
    """

    __tablename__ = "service_reports"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign key
    order_id = Column(UUID(as_uuid=True), ForeignKey("service_orders.id", ondelete="CASCADE"), nullable=False)

    # Identificação
    report_number = Column(String(30), nullable=False, unique=True)
    report_type = Column(
        Enum(ReportType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=ReportType.EXECUCAO
    )
    title = Column(String(200), nullable=False)

    # Conteúdo
    summary = Column(Text, nullable=True)
    introduction = Column(Text, nullable=True)
    methodology = Column(Text, nullable=True)
    findings = Column(Text, nullable=True)
    analysis = Column(Text, nullable=True)
    conclusions = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)

    # Seções customizadas
    sections = Column(JSONB, nullable=True)

    # Dados técnicos
    technical_data = Column(JSONB, nullable=True)
    measurements = Column(JSONB, nullable=True)
    test_results = Column(JSONB, nullable=True)

    # Equipamentos
    equipment_inspected = Column(JSONB, nullable=True)
    equipment_status = Column(JSONB, nullable=True)
    equipment_recommendations = Column(JSONB, nullable=True)

    # Não conformidades
    non_conformities = Column(JSONB, nullable=True)
    corrective_actions = Column(JSONB, nullable=True)
    preventive_actions = Column(JSONB, nullable=True)

    # Fotos/Anexos
    photos = Column(JSONB, nullable=True)
    attachments = Column(JSONB, nullable=True)
    documents = Column(JSONB, nullable=True)

    # Autor
    author_id = Column(UUID(as_uuid=True), nullable=True)
    author_name = Column(String(200), nullable=True)
    reviewer_id = Column(UUID(as_uuid=True), nullable=True)
    reviewer_name = Column(String(200), nullable=True)

    # Status
    is_draft = Column(Boolean, nullable=False, default=True)
    is_reviewed = Column(Boolean, nullable=False, default=False)
    is_approved = Column(Boolean, nullable=False, default=False)
    is_sent = Column(Boolean, nullable=False, default=False)

    # Datas
    reviewed_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)

    # Envio
    sent_to = Column(JSONB, nullable=True)  # Lista de emails
    sent_method = Column(String(50), nullable=True)  # email, portal, etc

    # PDF/Exportação
    pdf_url = Column(String(500), nullable=True)
    pdf_generated_at = Column(DateTime, nullable=True)

    # Versão
    version = Column(Integer, nullable=False, default=1)
    version_history = Column(JSONB, nullable=True)

    # Metadados
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Auditoria
    ativo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    # Relacionamentos
    order: "ServiceOrder" = relationship("ServiceOrder", back_populates="reports")

    # Índices
    __table_args__ = (
        Index("ix_service_reports_order_id", "order_id"),
        Index("ix_service_reports_report_number", "report_number"),
        Index("ix_service_reports_report_type", "report_type"),
        Index("ix_service_reports_author_id", "author_id"),
        Index("ix_service_reports_is_draft", "is_draft"),
        Index("ix_service_reports_ativo", "ativo"),
    )

    def __repr__(self) -> str:
        return f"<ServiceReport {self.report_number}: {self.title}>"

    def finalize(self) -> None:
        """Finaliza rascunho do relatório."""
        self.is_draft = False
        self.updated_at = datetime.utcnow()

    def review(self, reviewer_id: UUID, reviewer_name: str) -> None:
        """Marca relatório como revisado."""
        self.is_reviewed = True
        self.reviewer_id = reviewer_id
        self.reviewer_name = reviewer_name
        self.reviewed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def approve(self, approver_id: UUID) -> None:
        """Aprova o relatório."""
        self.is_approved = True
        self.approved_at = datetime.utcnow()
        self.updated_by = approver_id
        self.updated_at = datetime.utcnow()

    def send(self, recipients: list, method: str = "email") -> None:
        """Envia o relatório."""
        self.is_sent = True
        self.sent_to = recipients
        self.sent_method = method
        self.sent_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def set_pdf_url(self, url: str) -> None:
        """Define URL do PDF gerado."""
        self.pdf_url = url
        self.pdf_generated_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def create_new_version(self) -> None:
        """Cria nova versão do relatório."""
        if self.version_history is None:
            self.version_history = []
        self.version_history.append(
            {
                "version": self.version,
                "created_at": self.updated_at.isoformat() if self.updated_at else None,
                "author_id": str(self.updated_by) if self.updated_by else None,
            }
        )
        self.version += 1
        self.is_draft = True
        self.is_reviewed = False
        self.is_approved = False
        self.is_sent = False
        self.updated_at = datetime.utcnow()

    def add_section(self, title: str, content: str, order: int | None = None) -> None:
        """Adiciona seção ao relatório."""
        if self.sections is None:
            self.sections = []
        section = {"id": str(uuid4()), "title": title, "content": content, "order": order or len(self.sections) + 1}
        self.sections.append(section)
        self.updated_at = datetime.utcnow()

    def add_photo(self, url: str, caption: str, category: str | None = None) -> None:
        """Adiciona foto ao relatório."""
        if self.photos is None:
            self.photos = []
        photo = {
            "id": str(uuid4()),
            "url": url,
            "caption": caption,
            "category": category,
            "added_at": datetime.utcnow().isoformat(),
        }
        self.photos.append(photo)
        self.updated_at = datetime.utcnow()

    def add_non_conformity(self, description: str, severity: str, corrective_action: str | None = None) -> None:
        """Adiciona não conformidade."""
        if self.non_conformities is None:
            self.non_conformities = []
        nc_entry = {
            "id": str(uuid4()),
            "description": description,
            "severity": severity,
            "corrective_action": corrective_action,
            "identified_at": datetime.utcnow().isoformat(),
        }
        self.non_conformities.append(nc_entry)
        self.updated_at = datetime.utcnow()

    @property
    def is_complete(self) -> bool:
        """Verifica se relatório está completo."""
        return not self.is_draft and self.is_reviewed and self.is_approved

    @property
    def non_conformity_count(self) -> int:
        """Conta não conformidades."""
        return len(self.non_conformities) if self.non_conformities else 0

    @property
    def photo_count(self) -> int:
        """Conta fotos."""
        return len(self.photos) if self.photos else 0
