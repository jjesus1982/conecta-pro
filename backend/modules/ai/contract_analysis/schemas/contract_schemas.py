"""
Contract Schemas - AI Contract Analysis

DTOs para entrada e saida da API de analise de contratos.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from modules.ai.contract_analysis.models.contract_alert import (
    AlertPriority,
    AlertStatus,
    AlertType,
)
from modules.ai.contract_analysis.models.contract_analysis import (
    AnalysisStatus,
    ContractType,
    RiskLevel,
)
from modules.ai.contract_analysis.models.extracted_clause import (
    ClauseImportance,
    ClauseType,
)

# ============================================================
# Analysis Schemas
# ============================================================


class ContractAnalysisRequest(BaseModel):
    """Request para analisar contrato."""

    contract_id: UUID = Field(..., description="ID do contrato")
    document_id: UUID | None = Field(None, description="ID do documento no GED")
    document_content: str | None = Field(None, description="Conteudo do documento")
    contract_number: str | None = Field(None, max_length=50)
    contract_title: str | None = Field(None, max_length=300)
    template_id: UUID | None = Field(None, description="Template para comparacao")
    extract_clauses: bool = Field(default=True, description="Extrair clausulas")
    analyze_risk: bool = Field(default=True, description="Analisar riscos")
    check_compliance: bool = Field(default=True, description="Verificar conformidade")
    generate_alerts: bool = Field(default=True, description="Gerar alertas")


class ExtractedClauseResponse(BaseModel):
    """Response para clausula extraida."""

    id: UUID
    analysis_id: UUID
    clause_number: str | None = None
    clause_title: str | None = None
    clause_type: ClauseType
    clause_type_confidence: float = 0
    original_text: str
    normalized_text: str | None = None
    summary: str | None = None
    page_number: int | None = None
    importance: ClauseImportance
    is_standard: bool = True
    is_custom: bool = False
    is_risky: bool = False
    entities: list[dict] | None = None
    dates_found: list[dict] | None = None
    values_found: list[dict] | None = None
    risk_score: float = 0
    risk_reasons: list[str] | None = None
    obligations: list[dict] | None = None
    has_deadline: bool = False
    has_monetary_value: bool = False
    requires_action: bool = False
    manually_reviewed: bool = False
    created_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class ContractAlertResponse(BaseModel):
    """Response para alerta de contrato."""

    id: UUID
    analysis_id: UUID
    contract_id: UUID
    contract_number: str | None = None
    alert_type: AlertType
    status: AlertStatus
    priority: AlertPriority
    title: str
    description: str | None = None
    recommendation: str | None = None
    trigger_date: date
    due_date: date | None = None
    reference_date: date | None = None
    days_before: int = 30
    days_remaining: int | None = None
    clause_id: UUID | None = None
    clause_number: str | None = None
    monetary_value: str | None = None
    assigned_to: UUID | None = None
    notification_sent: bool = False
    confidence: int = 100
    is_active: bool = True
    is_read: bool = False
    is_overdue: bool = False
    created_at: datetime
    resolved_at: datetime | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class ContractAnalysisResponse(BaseModel):
    """Response para analise de contrato."""

    id: UUID
    contract_id: UUID
    contract_number: str | None = None
    contract_title: str | None = None
    document_id: UUID | None = None
    document_name: str | None = None
    status: AnalysisStatus
    contract_type: ContractType
    contract_type_confidence: float = 0

    # Partes
    contractor_name: str | None = None
    contractor_document: str | None = None
    contracted_name: str | None = None
    contracted_document: str | None = None

    # Datas
    signature_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    renewal_date: date | None = None
    notice_period_days: int | None = None

    # Valores
    total_value: float | None = None
    monthly_value: float | None = None
    currency: str = "BRL"
    payment_terms: str | None = None
    adjustment_index: str | None = None

    # Risco
    risk_level: RiskLevel
    risk_score: float = 50
    risk_factors: list[dict] | None = None

    # Conformidade
    compliance_score: float = 0
    compliance_issues: list[dict] | None = None
    missing_clauses: list[str] | None = None

    # Estatisticas
    total_pages: int = 0
    total_words: int = 0
    total_clauses_found: int = 0
    processing_time_seconds: float | None = None

    # Resumo
    summary: str | None = None
    key_terms: list[str] | None = None
    obligations_summary: str | None = None

    # Flags
    has_auto_renewal: bool = False
    has_penalty_clause: bool = False
    has_exclusivity: bool = False
    has_confidentiality: bool = False
    has_non_compete: bool = False
    requires_review: bool = False

    # Metadados
    created_at: datetime
    completed_at: datetime | None = None
    is_active: bool = True

    # Relacionamentos (opcionais)
    clauses: list[ExtractedClauseResponse] | None = None
    alerts: list[ContractAlertResponse] | None = None

    # Propriedades calculadas
    days_until_expiry: int | None = None
    is_expiring_soon: bool = False
    is_expired: bool = False

    class Config:
        """Pydantic config."""

        from_attributes = True


class ContractAnalysisListResponse(BaseModel):
    """Response para lista de analises."""

    items: list[ContractAnalysisResponse]
    total: int
    page: int
    page_size: int
    pages: int


class AlertListResponse(BaseModel):
    """Response para lista de alertas."""

    items: list[ContractAlertResponse]
    total: int
    pending_count: int
    urgent_count: int
    overdue_count: int


# ============================================================
# Alert Management Schemas
# ============================================================


class ContractAlertCreate(BaseModel):
    """Schema para criar alerta manualmente."""

    contract_id: UUID
    alert_type: AlertType
    priority: AlertPriority = AlertPriority.MEDIUM
    title: str = Field(..., min_length=5, max_length=300)
    description: str | None = None
    recommendation: str | None = None
    trigger_date: date
    due_date: date | None = None
    reference_date: date | None = None
    days_before: int = Field(default=30, ge=0, le=365)
    assigned_to: UUID | None = None
    notify_users: list[UUID] | None = None


class ContractAlertUpdate(BaseModel):
    """Schema para atualizar alerta."""

    status: AlertStatus | None = None
    priority: AlertPriority | None = None
    assigned_to: UUID | None = None
    due_date: date | None = None
    resolution_notes: str | None = None
    is_read: bool | None = None
    snooze_until: datetime | None = None


# ============================================================
# Report Schemas
# ============================================================


class ContractSummary(BaseModel):
    """Resumo de contrato para dashboard."""

    contract_id: UUID
    contract_number: str | None = None
    contract_title: str | None = None
    contract_type: ContractType
    risk_level: RiskLevel
    risk_score: float
    compliance_score: float
    end_date: date | None = None
    days_until_expiry: int | None = None
    pending_alerts: int = 0
    status: str  # "active", "expiring", "expired", "review_required"


class RiskAssessment(BaseModel):
    """Avaliacao de risco detalhada."""

    contract_id: UUID
    overall_risk_level: RiskLevel
    overall_risk_score: float
    risk_factors: list[dict]
    # Ex: [{"factor": "no_penalty_clause", "impact": "medium", "description": "..."}]
    risky_clauses: list[dict]
    # Ex: [{"clause_number": "5.1", "type": "penalty", "risk_score": 75}]
    recommendations: list[str]
    comparison_with_template: dict | None = None


class ComplianceReport(BaseModel):
    """Relatorio de conformidade."""

    contract_id: UUID
    compliance_score: float
    status: str  # "compliant", "partially_compliant", "non_compliant"
    required_clauses: list[dict]
    # Ex: [{"type": "confidentiality", "status": "present", "compliant": true}]
    missing_clauses: list[str]
    issues: list[dict]
    # Ex: [{"severity": "high", "description": "...", "clause": "5.1"}]
    recommendations: list[str]


# ============================================================
# Bulk Operations Schemas
# ============================================================


class BulkAnalysisRequest(BaseModel):
    """Request para analise em lote."""

    contract_ids: list[UUID] = Field(..., min_length=1, max_length=50, description="Lista de IDs de contratos (max 50)")
    extract_clauses: bool = True
    analyze_risk: bool = True
    check_compliance: bool = True
    generate_alerts: bool = True


class BulkAlertActionRequest(BaseModel):
    """Request para acao em lote em alertas."""

    alert_ids: list[UUID] = Field(..., min_length=1, max_length=100, description="Lista de IDs de alertas")
    action: str = Field(..., pattern="^(acknowledge|resolve|dismiss|snooze)$")
    notes: str | None = None
    snooze_days: int | None = Field(None, ge=1, le=90)


# ============================================================
# Dashboard Schemas
# ============================================================


class ContractsDashboard(BaseModel):
    """Dashboard de contratos."""

    total_contracts_analyzed: int
    contracts_by_risk: dict[str, int]
    # Ex: {"low": 10, "medium": 25, "high": 5, "critical": 2}
    contracts_by_type: dict[str, int]
    expiring_soon: int  # Proximos 30 dias
    expired: int
    pending_alerts: int
    urgent_alerts: int
    average_compliance_score: float
    average_risk_score: float
    recent_analyses: list[ContractSummary]
