"""
Contract Controller - AI Contract Analysis

Endpoints REST para analise de contratos.
"""

import contextlib
import logging
import time
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.ai.contract_analysis.models.contract_alert import (
    AlertPriority,
    AlertStatus,
    AlertType,
)
from modules.ai.contract_analysis.models.contract_analysis import (
    AnalysisStatus,
    ContractAnalysis,
    ContractType,
    RiskLevel,
)
from modules.ai.contract_analysis.repositories.contract_repository import (
    ContractAnalysisRepository,
)
from modules.ai.contract_analysis.schemas.contract_schemas import (
    AlertListResponse,
    ComplianceReport,
    ContractAlertCreate,
    ContractAlertResponse,
    ContractAlertUpdate,
    ContractAnalysisListResponse,
    ContractAnalysisRequest,
    ContractAnalysisResponse,
    ContractsDashboard,
    ExtractedClauseResponse,
    RiskAssessment,
)
from modules.ai.contract_analysis.services.alert_service import AlertService
from modules.ai.contract_analysis.services.clause_extractor import ClauseExtractor
from modules.ai.contract_analysis.services.compliance_checker import ComplianceChecker
from modules.ai.contract_analysis.services.risk_analyzer import RiskAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/contract-analysis",
    tags=["AI - Contract Analysis"],
)


# ============================================================
# Analysis Endpoints
# ============================================================


@router.post(
    "/analyze",
    response_model=ContractAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analisar contrato",
)
async def analyze_contract(
    request: ContractAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> ContractAnalysisResponse:
    """
    Analisa um contrato usando NLP.

    - Extrai clausulas automaticamente
    - Identifica partes e datas
    - Avalia riscos
    - Verifica conformidade
    - Gera alertas
    """
    start_time = time.time()

    repository = ContractAnalysisRepository(db)
    extractor = ClauseExtractor(db)
    risk_analyzer = RiskAnalyzer(db)
    compliance_checker = ComplianceChecker(db)
    alert_service = AlertService(db)

    # Mock de conteudo do contrato
    contract_text = request.document_content or _get_mock_contract_text()

    try:
        # 1. Criar analise
        analysis_data = {
            "contract_id": request.contract_id,
            "contract_number": request.contract_number,
            "contract_title": request.contract_title,
            "document_id": request.document_id,
            "status": AnalysisStatus.PROCESSING,
            "analyzed_by": UUID(current_user.id) if hasattr(current_user, "id") else None,
        }
        analysis = repository.create_analysis(analysis_data)

        # 2. Identificar tipo do contrato
        contract_type, type_confidence = extractor.identify_contract_type(contract_text)
        analysis.contract_type = contract_type
        analysis.contract_type_confidence = type_confidence

        # 3. Extrair partes
        parties = extractor.extract_parties(contract_text)
        analysis.contractor_name = parties.get("contractor")
        analysis.contractor_document = parties.get("contractor_document")
        analysis.contracted_name = parties.get("contracted")
        analysis.contracted_document = parties.get("contracted_document")

        # 4. Extrair clausulas
        clauses_data = []
        if request.extract_clauses:
            clauses_data = await extractor.extract_clauses(contract_text, contract_type)
            repository.add_clauses(analysis.id, clauses_data)

        # Recarregar com clausulas
        analysis = repository.get_analysis(analysis.id, include_clauses=True)

        # 5. Analisar riscos
        if request.analyze_risk:
            risk_result = risk_analyzer.analyze_risk(analysis, analysis.clauses)
            analysis.risk_level = risk_result["risk_level"]
            analysis.risk_score = risk_result["risk_score"]
            analysis.risk_factors = risk_result["risk_factors"]

        # 6. Verificar conformidade
        if request.check_compliance:
            compliance_result = compliance_checker.check_compliance(analysis, analysis.clauses)
            analysis.compliance_score = compliance_result["compliance_score"]
            analysis.compliance_issues = compliance_result["issues"]
            analysis.missing_clauses = compliance_result["missing_clauses"]

        # 7. Extrair datas (mock)
        analysis.start_date = date.today()
        analysis.end_date = date(2026, 1, 5)
        analysis.has_auto_renewal = True

        # 8. Gerar alertas
        if request.generate_alerts:
            alert_service.generate_alerts(analysis)

        # 9. Finalizar
        processing_time = time.time() - start_time
        analysis.status = AnalysisStatus.COMPLETED
        analysis.completed_at = datetime.utcnow()
        analysis.processing_time_seconds = processing_time
        analysis.total_clauses_found = len(clauses_data)
        analysis.total_words = len(contract_text.split())
        analysis.summary = _generate_summary(analysis)

        db.commit()
        db.refresh(analysis)

        # Recarregar com todos os relacionamentos
        analysis = repository.get_analysis(analysis.id, include_clauses=True, include_alerts=True)

        return ContractAnalysisResponse.model_validate(analysis)

    except Exception as e:
        logger.error(f"Erro na analise: {e}")
        if analysis:
            analysis.status = AnalysisStatus.FAILED
            analysis.error_message = str(e)
            db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na analise: {str(e)}",
        )


@router.get(
    "/analyses/{analysis_id}",
    response_model=ContractAnalysisResponse,
    summary="Buscar analise por ID",
)
async def get_analysis(
    analysis_id: UUID,
    include_clauses: bool = Query(True),
    include_alerts: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> ContractAnalysisResponse:
    """Busca analise por ID."""
    repository = ContractAnalysisRepository(db)
    analysis = repository.get_analysis(analysis_id, include_clauses, include_alerts)

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analise nao encontrada",
        )

    return ContractAnalysisResponse.model_validate(analysis)


@router.get(
    "/analyses",
    response_model=ContractAnalysisListResponse,
    summary="Listar analises",
)
async def list_analyses(
    status_filter: AnalysisStatus | None = Query(None, alias="status"),
    contract_type: ContractType | None = None,
    risk_level: RiskLevel | None = None,
    expiring_in_days: int | None = Query(None, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> ContractAnalysisListResponse:
    """Lista analises com filtros."""
    repository = ContractAnalysisRepository(db)
    items, total = repository.get_analyses(
        status=status_filter,
        contract_type=contract_type,
        risk_level=risk_level,
        expiring_in_days=expiring_in_days,
        page=page,
        page_size=page_size,
    )

    pages = (total + page_size - 1) // page_size

    return ContractAnalysisListResponse(
        items=[ContractAnalysisResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/contract/{contract_id}",
    response_model=ContractAnalysisResponse,
    summary="Buscar analise por contrato",
)
async def get_analysis_by_contract(
    contract_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> ContractAnalysisResponse:
    """Busca analise mais recente de um contrato."""
    repository = ContractAnalysisRepository(db)
    analysis = repository.get_analysis_by_contract(contract_id)

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhuma analise encontrada para este contrato",
        )

    return ContractAnalysisResponse.model_validate(analysis)


# ============================================================
# Clauses Endpoints
# ============================================================


@router.get(
    "/analyses/{analysis_id}/clauses",
    response_model=list[ExtractedClauseResponse],
    summary="Listar clausulas de uma analise",
)
async def list_clauses(
    analysis_id: UUID,
    clause_type: str | None = None,
    is_risky: bool | None = None,
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> list[ExtractedClauseResponse]:
    """Lista clausulas extraidas de uma analise."""
    repository = ContractAnalysisRepository(db)

    from modules.ai.contract_analysis.models.extracted_clause import ClauseType

    clause_type_enum = None
    if clause_type:
        with contextlib.suppress(ValueError):
            clause_type_enum = ClauseType(clause_type)

    clauses = repository.get_clauses(
        analysis_id,
        clause_type=clause_type_enum,
        is_risky=is_risky,
    )

    return [ExtractedClauseResponse.model_validate(c) for c in clauses]


# ============================================================
# Risk & Compliance Endpoints
# ============================================================


@router.get(
    "/analyses/{analysis_id}/risk",
    response_model=RiskAssessment,
    summary="Avaliacao de risco",
)
async def get_risk_assessment(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> RiskAssessment:
    """Retorna avaliacao detalhada de risco."""
    risk_analyzer = RiskAnalyzer(db)
    summary = risk_analyzer.get_risk_summary(analysis_id)

    if "error" in summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=summary["error"],
        )

    return RiskAssessment(
        contract_id=UUID(summary["contract_id"]),
        overall_risk_level=RiskLevel(summary["risk_level"]),
        overall_risk_score=summary["risk_score"],
        risk_factors=summary["risk_factors"],
        risky_clauses=summary["risky_clauses"],
        recommendations=[],
    )


@router.get(
    "/analyses/{analysis_id}/compliance",
    response_model=ComplianceReport,
    summary="Relatorio de conformidade",
)
async def get_compliance_report(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> ComplianceReport:
    """Retorna relatorio de conformidade."""
    compliance_checker = ComplianceChecker(db)
    report = compliance_checker.get_compliance_report(analysis_id)

    if "error" in report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=report["error"],
        )

    return ComplianceReport(
        contract_id=UUID(report["contract_id"]),
        compliance_score=report["compliance_score"],
        status=report["status"],
        required_clauses=[],
        missing_clauses=report["missing_clauses"],
        issues=report["issues"],
        recommendations=[],
    )


# ============================================================
# Alerts Endpoints
# ============================================================


@router.get(
    "/alerts",
    response_model=AlertListResponse,
    summary="Listar alertas",
)
async def list_alerts(
    contract_id: UUID | None = None,
    alert_type: AlertType | None = None,
    status_filter: AlertStatus | None = Query(None, alias="status"),
    priority: AlertPriority | None = None,
    is_overdue: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> AlertListResponse:
    """Lista alertas de contratos."""
    repository = ContractAnalysisRepository(db)
    items, total = repository.get_alerts(
        contract_id=contract_id,
        alert_type=alert_type,
        status=status_filter,
        priority=priority,
        is_overdue=is_overdue,
        page=page,
        page_size=page_size,
    )

    pending = len([a for a in items if a.status == AlertStatus.PENDING])
    urgent = len([a for a in items if a.priority in (AlertPriority.URGENT, AlertPriority.CRITICAL)])
    overdue = len([a for a in items if a.is_overdue])

    return AlertListResponse(
        items=[ContractAlertResponse.model_validate(a) for a in items],
        total=total,
        pending_count=pending,
        urgent_count=urgent,
        overdue_count=overdue,
    )


@router.post(
    "/alerts",
    response_model=ContractAlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar alerta manualmente",
)
async def create_alert(
    alert: ContractAlertCreate,
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> ContractAlertResponse:
    """Cria alerta manual para um contrato."""
    repository = ContractAnalysisRepository(db)

    # Buscar analise do contrato
    analysis = repository.get_analysis_by_contract(alert.contract_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analise do contrato nao encontrada",
        )

    alert_data = {
        "analysis_id": analysis.id,
        "contract_id": alert.contract_id,
        "contract_number": analysis.contract_number,
        "alert_type": alert.alert_type,
        "priority": alert.priority,
        "title": alert.title,
        "description": alert.description,
        "recommendation": alert.recommendation,
        "trigger_date": alert.trigger_date,
        "due_date": alert.due_date,
        "reference_date": alert.reference_date,
        "days_before": alert.days_before,
        "assigned_to": alert.assigned_to,
        "notify_users": alert.notify_users,
        "auto_generated": False,
    }

    created = repository.create_alert(alert_data)
    return ContractAlertResponse.model_validate(created)


@router.patch(
    "/alerts/{alert_id}",
    response_model=ContractAlertResponse,
    summary="Atualizar alerta",
)
async def update_alert(
    alert_id: UUID,
    update: ContractAlertUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> ContractAlertResponse:
    """Atualiza um alerta."""
    repository = ContractAnalysisRepository(db)
    alert = repository.update_alert(alert_id, update.model_dump(exclude_unset=True))

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta nao encontrado",
        )

    return ContractAlertResponse.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=ContractAlertResponse,
    summary="Resolver alerta",
)
async def resolve_alert(
    alert_id: UUID,
    notes: str | None = None,
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> ContractAlertResponse:
    """Resolve um alerta."""
    alert_service = AlertService(db)
    user_id = UUID(current_user.id) if hasattr(current_user, "id") else UUID(int=0)

    alert = alert_service.resolve_alert(alert_id, user_id, notes)

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta nao encontrado",
        )

    return ContractAlertResponse.model_validate(alert)


# ============================================================
# Dashboard Endpoints
# ============================================================


@router.get(
    "/dashboard",
    response_model=ContractsDashboard,
    summary="Dashboard de contratos",
)
async def get_dashboard(
    db: Session = Depends(get_db),
    current_user: CurrentActiveUser = ...,  # Required
) -> ContractsDashboard:
    """Retorna dashboard com metricas de contratos."""
    repository = ContractAnalysisRepository(db)
    alert_service = AlertService(db)

    # Buscar estatisticas
    analyses, total = repository.get_analyses(page_size=1000)

    by_risk = repository.get_contracts_by_risk()
    by_type = repository.get_contracts_by_type()
    scores = repository.get_average_scores()

    expiring = repository.get_expiring_contracts(30)
    expired = [a for a in analyses if a.is_expired]

    alerts_summary = alert_service.get_alerts_summary()

    return ContractsDashboard(
        total_contracts_analyzed=total,
        contracts_by_risk=by_risk,
        contracts_by_type=by_type,
        expiring_soon=len(expiring),
        expired=len(expired),
        pending_alerts=alerts_summary["total_pending"],
        urgent_alerts=alerts_summary["urgent_and_critical"],
        average_compliance_score=scores["average_compliance_score"],
        average_risk_score=scores["average_risk_score"],
        recent_analyses=[],
    )


# ============================================================
# Helper Functions
# ============================================================


def _get_mock_contract_text() -> str:
    """Retorna texto mock de contrato para teste."""
    return """
    CONTRATO DE PRESTACAO DE SERVICOS

    CONTRATANTE: Empresa ABC Ltda, inscrita no CNPJ sob n. 12.345.678/0001-90
    CONTRATADO: Servicos XYZ S.A., inscrita no CNPJ sob n. 98.765.432/0001-10

    CLAUSULA PRIMEIRA - DO OBJETO
    O presente contrato tem por objeto a prestacao de servicos de consultoria
    em tecnologia da informacao.

    CLAUSULA SEGUNDA - DO PRECO E FORMA DE PAGAMENTO
    Pelo servico prestado, a CONTRATANTE pagara a CONTRATADO o valor de
    R$ 10.000,00 (dez mil reais) mensais, com vencimento todo dia 10.

    CLAUSULA TERCEIRA - DA VIGENCIA
    O presente contrato tera vigencia de 12 (doze) meses, com inicio em
    01/01/2025 e termino em 31/12/2025, podendo ser renovado automaticamente.

    CLAUSULA QUARTA - DA RESCISAO
    O presente contrato podera ser rescindido por qualquer das partes,
    mediante aviso previo de 30 (trinta) dias.

    CLAUSULA QUINTA - DAS PENALIDADES
    Em caso de descumprimento, a parte infratora pagara multa de 10% sobre
    o valor total do contrato.

    CLAUSULA SEXTA - DA CONFIDENCIALIDADE
    As partes se comprometem a manter sigilo sobre todas as informacoes
    confidenciais a que tiverem acesso.

    CLAUSULA SETIMA - DO FORO
    Fica eleito o Foro da Comarca de Sao Paulo para dirimir quaisquer
    controversias oriundas deste contrato.
    """


def _generate_summary(analysis: ContractAnalysis) -> str:
    """Gera resumo do contrato."""
    parts = []

    if analysis.contract_type:
        parts.append(f"Contrato de {analysis.contract_type.value}")

    if analysis.contractor_name and analysis.contracted_name:
        parts.append(f"entre {analysis.contractor_name} e {analysis.contracted_name}")

    if analysis.total_value:
        parts.append(f"no valor de R$ {analysis.total_value:,.2f}")

    if analysis.end_date:
        parts.append(f"com vigencia ate {analysis.end_date.strftime('%d/%m/%Y')}")

    return ". ".join(parts) + "." if parts else "Contrato analisado."
