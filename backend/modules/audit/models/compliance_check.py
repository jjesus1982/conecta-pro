"""
ComplianceCheck Model - Verificações de Compliance
Sprint 33: Auditoria e Compliance
"""

import secrets
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.database import Base


class CheckType(StrEnum):
    """Tipo de verificação."""

    AUTOMATED = "automated"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    ON_DEMAND = "on_demand"
    CONTINUOUS = "continuous"
    SAMPLE = "sample"


class CheckStatus(StrEnum):
    """Status da verificação."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class CheckResult(StrEnum):
    """Resultado da verificação."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"
    PENDING_REVIEW = "pending_review"


class ComplianceCheck(Base):
    """
    Model para verificações de compliance.
    Registra cada execução de verificação de uma regra.
    """

    __tablename__ = "compliance_checks"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Regra
    rule_id = Column(UUID(as_uuid=True), ForeignKey("compliance_rules.id"), nullable=False)

    # Identificação
    check_number = Column(String(50), nullable=False, unique=True)
    batch_id = Column(UUID(as_uuid=True), nullable=True)

    # Tipo e Status
    check_type = Column(
        Enum(CheckType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=CheckType.AUTOMATED
    )
    status = Column(
        Enum(CheckStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=CheckStatus.PENDING
    )
    result = Column(Enum(CheckResult, values_callable=lambda x: [e.value for e in x]), nullable=True)

    # Escopo da verificação
    scope_description = Column(Text, nullable=True)
    entities_checked = Column(Integer, nullable=True)
    entities_compliant = Column(Integer, nullable=True)
    entities_non_compliant = Column(Integer, nullable=True)
    sample_size = Column(Integer, nullable=True)
    sample_percentage = Column(Integer, nullable=True)

    # Detalhes da execução
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    executed_by = Column(UUID(as_uuid=True), nullable=True)
    executor_type = Column(String(50), nullable=True)

    # Evidências
    evidence_collected = Column(JSONB, nullable=True)
    evidence_files = Column(JSONB, nullable=True)
    screenshots = Column(JSONB, nullable=True)
    query_results = Column(JSONB, nullable=True)

    # Violações encontradas
    violations = Column(JSONB, nullable=True)
    violations_count = Column(Integer, nullable=False, default=0)
    critical_violations = Column(Integer, nullable=False, default=0)

    # Análise
    analysis_notes = Column(Text, nullable=True)
    risk_assessment = Column(Text, nullable=True)
    risk_score = Column(Integer, nullable=True)
    impact_assessment = Column(Text, nullable=True)

    # Remediação
    remediation_required = Column(Boolean, nullable=False, default=False)
    remediation_plan = Column(JSONB, nullable=True)
    remediation_deadline = Column(DateTime, nullable=True)
    remediation_status = Column(String(50), nullable=True)
    remediation_completed_at = Column(DateTime, nullable=True)
    remediation_verified = Column(Boolean, nullable=False, default=False)

    # Exceções
    exception_granted = Column(Boolean, nullable=False, default=False)
    exception_reason = Column(Text, nullable=True)
    exception_approved_by = Column(UUID(as_uuid=True), nullable=True)
    exception_expires_at = Column(DateTime, nullable=True)

    # Revisão
    requires_review = Column(Boolean, nullable=False, default=False)
    reviewed_by = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)
    review_decision = Column(String(50), nullable=True)

    # Aprovação
    approved = Column(Boolean, nullable=True)
    approved_by = Column(UUID(as_uuid=True), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)

    # Notificações
    notifications_sent = Column(JSONB, nullable=True)
    escalated = Column(Boolean, nullable=False, default=False)
    escalated_at = Column(DateTime, nullable=True)
    escalated_to = Column(JSONB, nullable=True)

    # Erros
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)

    # Agendamento
    scheduled_at = Column(DateTime, nullable=True)
    next_check_at = Column(DateTime, nullable=True)

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

    # Relacionamentos
    rule = relationship("ComplianceRule", backref="checks")

    # Índices
    __table_args__ = (
        Index("ix_compliance_checks_rule_id", "rule_id"),
        Index("ix_compliance_checks_check_number", "check_number"),
        Index("ix_compliance_checks_batch_id", "batch_id"),
        Index("ix_compliance_checks_status", "status"),
        Index("ix_compliance_checks_result", "result"),
        Index("ix_compliance_checks_check_type", "check_type"),
        Index("ix_compliance_checks_created_at", "created_at"),
        Index("ix_compliance_checks_requires_review", "requires_review"),
        Index("ix_compliance_checks_remediation_required", "remediation_required"),
        Index("ix_compliance_checks_ativo", "ativo"),
        Index("ix_compliance_checks_rule_result", "rule_id", "result"),
    )

    def __repr__(self) -> str:
        result_str = self.result.value if self.result else "pending"
        return f"<ComplianceCheck {self.check_number} - {result_str}>"

    @classmethod
    def create_check(
        cls, rule_id: str, check_type: CheckType = CheckType.AUTOMATED, executed_by: str | None = None
    ) -> "ComplianceCheck":
        """Cria uma nova verificação."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        token = secrets.token_hex(4).upper()
        check_number = f"CHK-{timestamp}-{token}"

        return cls(
            rule_id=rule_id,
            check_number=check_number,
            check_type=check_type,
            status=CheckStatus.PENDING,
            executed_by=executed_by,
        )

    def start(self, executor_id: str | None = None) -> None:
        """Inicia a verificação."""
        self.status = CheckStatus.RUNNING
        self.started_at = datetime.utcnow()
        if executor_id:
            self.executed_by = executor_id
        self.updated_at = datetime.utcnow()

    def complete_compliant(self, evidence: dict | None = None, notes: str | None = None) -> None:
        """Marca como conforme."""
        self.status = CheckStatus.COMPLETED
        self.result = CheckResult.COMPLIANT
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())
        if evidence:
            self.evidence_collected = evidence
        if notes:
            self.analysis_notes = notes
        self.updated_at = datetime.utcnow()

    def complete_non_compliant(
        self, violations: list, remediation_required: bool = True, remediation_deadline: datetime | None = None
    ) -> None:
        """Marca como não conforme."""
        self.status = CheckStatus.COMPLETED
        self.result = CheckResult.NON_COMPLIANT
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())
        self.violations = violations
        self.violations_count = len(violations)
        self.critical_violations = sum(1 for v in violations if v.get("severity") == "critical")
        self.remediation_required = remediation_required
        if remediation_deadline:
            self.remediation_deadline = remediation_deadline
        self.updated_at = datetime.utcnow()

    def complete_error(self, error_message: str, details: dict | None = None) -> None:
        """Marca como erro."""
        self.status = CheckStatus.FAILED
        self.result = CheckResult.ERROR
        self.completed_at = datetime.utcnow()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())
        self.error_message = error_message
        if details:
            self.error_details = details
        self.updated_at = datetime.utcnow()

    def grant_exception(self, reason: str, approver_id: str, expires_at: datetime | None = None) -> None:
        """Concede exceção."""
        self.exception_granted = True
        self.exception_reason = reason
        self.exception_approved_by = approver_id
        if expires_at:
            self.exception_expires_at = expires_at
        self.updated_at = datetime.utcnow()

    def mark_for_review(self) -> None:
        """Marca para revisão."""
        self.requires_review = True
        self.result = CheckResult.PENDING_REVIEW
        self.updated_at = datetime.utcnow()

    def complete_review(self, reviewer_id: str, decision: str, notes: str | None = None) -> None:
        """Completa a revisão."""
        self.requires_review = False
        self.reviewed_by = reviewer_id
        self.reviewed_at = datetime.utcnow()
        self.review_decision = decision
        if notes:
            self.review_notes = notes
        self.updated_at = datetime.utcnow()

    def escalate(self, escalate_to: list) -> None:
        """Escala a verificação."""
        self.escalated = True
        self.escalated_at = datetime.utcnow()
        self.escalated_to = escalate_to
        self.updated_at = datetime.utcnow()

    @property
    def compliance_percentage(self) -> float | None:
        """Percentual de conformidade."""
        if not self.entities_checked or self.entities_checked == 0:
            return None
        compliant = self.entities_compliant or 0
        return (compliant / self.entities_checked) * 100

    @property
    def is_overdue(self) -> bool:
        """Verifica se remediação está atrasada."""
        if not self.remediation_required or not self.remediation_deadline:
            return False
        if self.remediation_completed_at:
            return False
        return datetime.utcnow() > self.remediation_deadline

    @property
    def has_critical_violations(self) -> bool:
        """Verifica se tem violações críticas."""
        return self.critical_violations > 0
