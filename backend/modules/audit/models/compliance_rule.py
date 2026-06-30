"""
ComplianceRule Model - Regras de Compliance
Sprint 33: Auditoria e Compliance
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class ComplianceFramework(StrEnum):
    """Framework de compliance."""

    LGPD = "lgpd"
    GDPR = "gdpr"
    SOX = "sox"
    ISO_27001 = "iso_27001"
    ISO_9001 = "iso_9001"
    PCI_DSS = "pci_dss"
    HIPAA = "hipaa"
    SOC2 = "soc2"
    BACEN = "bacen"
    CVM = "cvm"
    CUSTOM = "custom"


class RuleCategory(StrEnum):
    """Categoria da regra."""

    DATA_PRIVACY = "data_privacy"
    DATA_PROTECTION = "data_protection"
    ACCESS_CONTROL = "access_control"
    DATA_RETENTION = "data_retention"
    AUDIT_TRAIL = "audit_trail"
    ENCRYPTION = "encryption"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    INCIDENT_RESPONSE = "incident_response"
    BACKUP_RECOVERY = "backup_recovery"
    CHANGE_MANAGEMENT = "change_management"
    VENDOR_MANAGEMENT = "vendor_management"
    FINANCIAL_CONTROL = "financial_control"
    REPORTING = "reporting"


class RuleSeverity(StrEnum):
    """Severidade da regra."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RuleStatus(StrEnum):
    """Status da regra."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class ComplianceRule(Base):
    """
    Model para regras de compliance.
    Define requisitos regulatórios e políticas internas.
    """

    __tablename__ = "compliance_rules"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Identificação
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(20), nullable=False, default="1.0")

    # Framework
    framework = Column(Enum(ComplianceFramework, values_callable=lambda x: [e.value for e in x]), nullable=False)
    framework_reference = Column(String(100), nullable=True)
    category = Column(Enum(RuleCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)

    # Status e Severidade
    status = Column(
        Enum(RuleStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=RuleStatus.DRAFT
    )
    severity = Column(
        Enum(RuleSeverity, values_callable=lambda x: [e.value for e in x]), nullable=False, default=RuleSeverity.MEDIUM
    )

    # Requisitos
    requirement_text = Column(Text, nullable=False)
    implementation_guidance = Column(Text, nullable=True)
    evidence_required = Column(JSONB, nullable=True)
    controls_required = Column(JSONB, nullable=True)

    # Validação
    validation_query = Column(Text, nullable=True)
    validation_script = Column(Text, nullable=True)
    validation_endpoint = Column(String(500), nullable=True)
    validation_frequency_hours = Column(Integer, nullable=True, default=24)
    auto_validate = Column(Boolean, nullable=False, default=True)

    # Escopo
    applies_to_entities = Column(JSONB, nullable=True)
    applies_to_roles = Column(JSONB, nullable=True)
    applies_to_modules = Column(JSONB, nullable=True)
    excluded_entities = Column(JSONB, nullable=True)

    # Penalidades
    penalty_description = Column(Text, nullable=True)
    penalty_amount = Column(Integer, nullable=True)
    penalty_currency = Column(String(3), nullable=True, default="BRL")
    legal_reference = Column(Text, nullable=True)

    # Notificações
    notify_on_violation = Column(Boolean, nullable=False, default=True)
    notification_recipients = Column(JSONB, nullable=True)
    escalation_path = Column(JSONB, nullable=True)
    escalation_timeout_hours = Column(Integer, nullable=True, default=24)

    # Remediação
    remediation_steps = Column(JSONB, nullable=True)
    remediation_deadline_days = Column(Integer, nullable=True)
    auto_remediate = Column(Boolean, nullable=False, default=False)
    remediation_script = Column(Text, nullable=True)

    # Documentação
    documentation_url = Column(String(500), nullable=True)
    training_url = Column(String(500), nullable=True)
    related_policies = Column(JSONB, nullable=True)

    # Exceções
    exceptions_allowed = Column(Boolean, nullable=False, default=False)
    exception_approval_required = Column(Boolean, nullable=False, default=True)
    exception_max_duration_days = Column(Integer, nullable=True)

    # Métricas
    total_checks = Column(Integer, nullable=False, default=0)
    passed_checks = Column(Integer, nullable=False, default=0)
    failed_checks = Column(Integer, nullable=False, default=0)
    last_check_at = Column(DateTime, nullable=True)
    last_violation_at = Column(DateTime, nullable=True)

    # Validade
    effective_from = Column(DateTime, nullable=True)
    effective_until = Column(DateTime, nullable=True)
    review_date = Column(DateTime, nullable=True)
    next_review_date = Column(DateTime, nullable=True)

    # Aprovação
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)

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
        Index("ix_compliance_rules_code", "code"),
        Index("ix_compliance_rules_framework", "framework"),
        Index("ix_compliance_rules_category", "category"),
        Index("ix_compliance_rules_status", "status"),
        Index("ix_compliance_rules_severity", "severity"),
        Index("ix_compliance_rules_ativo", "ativo"),
        Index("ix_compliance_rules_framework_status", "framework", "status"),
    )

    def __repr__(self) -> str:
        return f"<ComplianceRule {self.code} ({self.framework.value})>"

    def activate(self) -> None:
        """Ativa a regra."""
        self.status = RuleStatus.ACTIVE
        if not self.effective_from:
            self.effective_from = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def deprecate(self, replacement_code: str | None = None) -> None:
        """Deprecia a regra."""
        self.status = RuleStatus.DEPRECATED
        if replacement_code:
            self.metadata = self.metadata or {}
            self.metadata["replaced_by"] = replacement_code
        self.updated_at = datetime.utcnow()

    def disable(self, reason: str | None = None) -> None:
        """Desabilita a regra."""
        self.status = RuleStatus.DISABLED
        if reason:
            self.notes = f"Desabilitada: {reason}"
        self.updated_at = datetime.utcnow()

    def approve(self, approver_id: str, notes: str | None = None) -> None:
        """Aprova a regra."""
        self.approved_by = approver_id
        self.approved_at = datetime.utcnow()
        if notes:
            self.approval_notes = notes
        self.updated_at = datetime.utcnow()

    def record_check(self, passed: bool) -> None:
        """Registra resultado de verificação."""
        self.total_checks += 1
        if passed:
            self.passed_checks += 1
        else:
            self.failed_checks += 1
            self.last_violation_at = datetime.utcnow()
        self.last_check_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    @property
    def compliance_rate(self) -> float:
        """Taxa de conformidade."""
        if self.total_checks == 0:
            return 100.0
        return (self.passed_checks / self.total_checks) * 100

    @property
    def is_effective(self) -> bool:
        """Verifica se está em vigor."""
        now = datetime.utcnow()
        if self.status != RuleStatus.ACTIVE:
            return False
        if self.effective_from and now < self.effective_from:
            return False
        if self.effective_until and now > self.effective_until:
            return False
        return True

    @property
    def needs_review(self) -> bool:
        """Verifica se precisa revisão."""
        if not self.next_review_date:
            return False
        return datetime.utcnow() >= self.next_review_date

    @property
    def is_critical(self) -> bool:
        """Verifica se é regra crítica."""
        return self.severity == RuleSeverity.CRITICAL
