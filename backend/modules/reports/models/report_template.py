"""
ReportTemplate Model - Templates de Relatórios
Sprint 34: Relatórios Gerenciais
"""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class ReportCategory(str, enum.Enum):
    """Categorias de relatório."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    COMMERCIAL = "commercial"
    HR = "hr"
    EXECUTIVE = "executive"
    COMPLIANCE = "compliance"
    AUDIT = "audit"
    CUSTOM = "custom"


class ReportFormat(str, enum.Enum):
    """Formatos de saída do relatório."""

    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    HTML = "html"
    JSON = "json"
    WORD = "word"
    POWERPOINT = "powerpoint"


class ReportType(str, enum.Enum):
    """Tipos de relatório."""

    SUMMARY = "summary"
    DETAILED = "detailed"
    ANALYTICAL = "analytical"
    COMPARATIVE = "comparative"
    TREND = "trend"
    DASHBOARD = "dashboard"
    KPI = "kpi"
    CUSTOM = "custom"


class TemplateStatus(str, enum.Enum):
    """Status do template."""

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ChartType(str, enum.Enum):
    """Tipos de gráfico."""

    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    DONUT = "donut"
    AREA = "area"
    SCATTER = "scatter"
    RADAR = "radar"
    GAUGE = "gauge"
    TABLE = "table"
    HEATMAP = "heatmap"


class ReportTemplate(Base):
    """Template de relatório gerencial."""

    __tablename__ = "report_templates"

    # Identificação
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Classificação
    category = Column(Enum(ReportCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    report_type = Column(
        Enum(ReportType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=ReportType.SUMMARY
    )
    status = Column(
        Enum(TemplateStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TemplateStatus.DRAFT,
    )

    # Formatos suportados
    default_format = Column(
        Enum(ReportFormat, values_callable=lambda x: [e.value for e in x]), nullable=False, default=ReportFormat.PDF
    )
    supported_formats = Column(JSONB, nullable=True)

    # Layout e estrutura
    layout_config = Column(JSONB, nullable=True)
    header_config = Column(JSONB, nullable=True)
    footer_config = Column(JSONB, nullable=True)
    sections = Column(JSONB, nullable=True)

    # Dados e queries
    data_sources = Column(JSONB, nullable=True)
    query_template = Column(Text, nullable=True)
    parameters = Column(JSONB, nullable=True)
    filters = Column(JSONB, nullable=True)

    # Visualizações
    charts = Column(JSONB, nullable=True)
    tables = Column(JSONB, nullable=True)
    metrics = Column(JSONB, nullable=True)

    # Estilização
    theme = Column(String(50), nullable=True, default="default")
    css_styles = Column(Text, nullable=True)
    logo_url = Column(String(500), nullable=True)
    color_scheme = Column(JSONB, nullable=True)

    # Permissões
    visibility = Column(String(20), nullable=False, default="private")
    allowed_roles = Column(JSONB, nullable=True)
    allowed_users = Column(JSONB, nullable=True)

    # Versionamento
    version = Column(Integer, nullable=False, default=1)
    version_notes = Column(Text, nullable=True)
    previous_version_id = Column(UUID(as_uuid=True), nullable=True)

    # Metadados
    tags = Column(JSONB, nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    # Estatísticas
    usage_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)
    avg_generation_time = Column(Integer, nullable=True)

    # Auditoria
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)
    ativo = Column(Boolean, nullable=False, default=True)

    # Relacionamentos
    schedules = relationship("ReportSchedule", back_populates="template")
    exports = relationship("ReportExport", back_populates="template")

    __table_args__ = (
        Index("ix_report_templates_tenant_code", "tenant_id", "code", unique=True),
        Index("ix_report_templates_category", "category"),
        Index("ix_report_templates_status", "status"),
    )

    def activate(self) -> None:
        """Ativa o template."""
        self.status = TemplateStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Desativa o template."""
        self.status = TemplateStatus.INACTIVE
        self.updated_at = datetime.utcnow()

    def deprecate(self, notes: str | None = None) -> None:
        """Marca como depreciado."""
        self.status = TemplateStatus.DEPRECATED
        if notes:
            self.version_notes = notes
        self.updated_at = datetime.utcnow()

    def archive(self) -> None:
        """Arquiva o template."""
        self.status = TemplateStatus.ARCHIVED
        self.ativo = False
        self.updated_at = datetime.utcnow()

    def increment_version(self, notes: str | None = None) -> None:
        """Incrementa a versão."""
        self.previous_version_id = self.id
        self.version += 1
        self.version_notes = notes
        self.updated_at = datetime.utcnow()

    def record_usage(self, generation_time: int | None = None) -> None:
        """Registra uso do template."""
        self.usage_count += 1
        self.last_used_at = datetime.utcnow()
        if generation_time:
            if self.avg_generation_time:
                self.avg_generation_time = (
                    self.avg_generation_time * (self.usage_count - 1) + generation_time
                ) // self.usage_count
            else:
                self.avg_generation_time = generation_time

    def add_section(self, section_config: dict) -> None:
        """Adiciona uma seção ao template."""
        if not self.sections:
            self.sections = []
        self.sections.append(section_config)
        self.updated_at = datetime.utcnow()

    def add_chart(self, chart_config: dict) -> None:
        """Adiciona um gráfico ao template."""
        if not self.charts:
            self.charts = []
        self.charts.append(chart_config)
        self.updated_at = datetime.utcnow()

    def add_parameter(self, name: str, param_type: str, config: dict) -> None:
        """Adiciona um parâmetro ao template."""
        if not self.parameters:
            self.parameters = {}
        self.parameters[name] = {"type": param_type, **config}
        self.updated_at = datetime.utcnow()

    def set_visibility(self, visibility: str, roles: list[str] | None = None, users: list[str] | None = None) -> None:
        """Define visibilidade do template."""
        self.visibility = visibility
        self.allowed_roles = roles
        self.allowed_users = users
        self.updated_at = datetime.utcnow()

    @property
    def is_active(self) -> bool:
        """Verifica se está ativo."""
        return self.status == TemplateStatus.ACTIVE and self.ativo

    @property
    def is_public(self) -> bool:
        """Verifica se é público."""
        return self.visibility == "public"

    @property
    def has_charts(self) -> bool:
        """Verifica se tem gráficos."""
        return bool(self.charts)

    @property
    def has_parameters(self) -> bool:
        """Verifica se tem parâmetros."""
        return bool(self.parameters)

    @property
    def supported_format_list(self) -> list[str]:
        """Retorna lista de formatos suportados."""
        if self.supported_formats:
            return self.supported_formats
        return [self.default_format.value]
