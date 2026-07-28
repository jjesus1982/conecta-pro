"""
Fraud Detection Controller - Sprint 45

Endpoints da API de deteccao de fraudes.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.ai.fraud_detection.models.fraud_alert import (
    AlertSeverity,
    AlertStatus,
    FraudCategory,
)
from modules.ai.fraud_detection.models.fraud_pattern import PatternStatus, PatternType
from modules.ai.fraud_detection.models.fraud_rule import RuleType
from modules.ai.fraud_detection.models.risk_profile import EntityType, RiskLevel
from modules.ai.fraud_detection.repositories.fraud_repository import FraudRepository
from modules.ai.fraud_detection.schemas.fraud_schemas import (
    AccessCheckRequest,
    AccessCheckResponse,
    AlertAssignRequest,
    AlertEscalateRequest,
    AlertFeedbackRequest,
    AlertListResponse,
    AlertResolveRequest,
    # Detection schemas
    DetectionRequest,
    DetectionResponse,
    # Alert schemas
    FraudAlertCreate,
    FraudAlertResponse,
    FraudAlertUpdate,
    # Dashboard
    FraudDashboardStats,
    # Pattern schemas
    FraudPatternCreate,
    FraudPatternResponse,
    FraudPatternUpdate,
    # Rule schemas
    FraudRuleCreate,
    FraudRuleResponse,
    FraudRuleUpdate,
    PatternMatchRequest,
    PatternMatchResponse,
    # Risk Profile schemas
    RiskProfileCreate,
    RiskProfileResponse,
    RiskProfileUpdate,
    RiskScoreRequest,
    RiskScoreResponse,
    RuleTestRequest,
    RuleTestResponse,
    TransactionCheckRequest,
    TransactionCheckResponse,
)
from modules.ai.fraud_detection.services.alert_manager import AlertManager
from modules.ai.fraud_detection.services.fraud_detector import FraudDetector
from modules.ai.fraud_detection.services.pattern_analyzer import PatternAnalyzer
from modules.ai.fraud_detection.services.risk_scorer import RiskScorer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fraud", tags=["Fraud Detection"])


# =============================================================================
# Detection Endpoints
# =============================================================================


@router.post(
    "/detect",
    response_model=DetectionResponse,
    summary="Detectar fraude generica",
)
async def detect_fraud(
    request: DetectionRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> DetectionResponse:
    """Executa deteccao de fraude para evento generico."""
    detector = FraudDetector(db)
    start_time = datetime.utcnow()

    try:
        # Executar deteccao baseado no tipo de evento
        # NOTA: check_transaction/check_access sao metodos SINCRONOS do FraudDetector (sem await).
        if request.event_type in ["transaction", "payment", "transfer"]:
            result = detector.check_transaction(
                transaction_id=request.entity_id,
                transaction_type=request.event_type,
                amount=request.event_data.get("amount", 0),
                payer_id=request.entity_id,
                payer_type=request.entity_type,
                metadata=request.event_data,
            )
        else:
            result = detector.check_access(
                user_id=request.entity_id,
                ip_address=request.event_data.get("ip_address", ""),
                action=request.event_type,
                device_id=request.event_data.get("device_id"),
                user_agent=request.event_data.get("user_agent"),
                location=request.event_data.get("location"),
            )

        processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return DetectionResponse(
            is_fraudulent=result.get("risk_level") in ["high", "critical"],
            risk_score=result.get("risk_score", 0),
            risk_level=RiskLevel(result.get("risk_level", "low")),
            alerts_generated=len(result.get("alerts_generated", [])),
            alert_ids=result.get("alerts_generated", []),
            matched_rules=result.get("matched_rules", []),
            matched_patterns=result.get("matched_patterns", []),
            recommendations=result.get("recommendations", []),
            processing_time_ms=processing_time,
        )

    except Exception as e:
        logger.error(f"Erro na deteccao: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/check/transaction",
    response_model=TransactionCheckResponse,
    summary="Verificar transacao",
)
async def check_transaction(
    request: TransactionCheckRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> TransactionCheckResponse:
    """Verifica uma transacao para fraude."""
    detector = FraudDetector(db)
    start_time = datetime.utcnow()

    try:
        # detector.check_transaction nao aceita payer_account/payee_account (nao existem no metodo real)
        # e e sincrono (sem await).
        result = detector.check_transaction(
            transaction_id=request.transaction_id,
            transaction_type=request.transaction_type,
            amount=request.amount,
            payer_id=request.payer_id,
            payer_type=request.payer_type,
            payee_id=request.payee_id,
            payee_type=request.payee_type,
            ip_address=request.ip_address,
            device_id=request.device_id,
            location=request.location,
            metadata=request.metadata,
        )

        processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return TransactionCheckResponse(
            transaction_id=request.transaction_id,
            is_allowed=result.get("decision") in ["approve", "review"],
            risk_score=result.get("risk_score", 0),
            risk_level=RiskLevel(result.get("risk_level", "low")),
            decision=result.get("decision", "approve"),
            decision_reasons=result.get("decision_reasons", []),
            matched_rules=result.get("matched_rules", []),
            matched_patterns=result.get("matched_patterns", []),
            alerts_generated=result.get("alerts_generated", []),
            recommendations=result.get("recommendations", []),
            required_actions=result.get("required_actions", []),
            processing_time_ms=processing_time,
        )

    except Exception as e:
        logger.error(f"Erro na verificacao de transacao: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/check/access",
    response_model=AccessCheckResponse,
    summary="Verificar acesso",
)
async def check_access(
    request: AccessCheckRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> AccessCheckResponse:
    """Verifica um acesso para fraude."""
    detector = FraudDetector(db)
    analyzer = PatternAnalyzer(db)
    start_time = datetime.utcnow()

    try:
        # Verificar acesso (detector.check_access e sincrono, sem await)
        result = detector.check_access(
            user_id=request.user_id,
            ip_address=request.ip_address,
            action=request.action,
            session_id=request.session_id,
            device_id=request.device_id,
            user_agent=request.user_agent,
            location=request.location,
            geo_coordinates=request.geo_coordinates,
            metadata=request.metadata,
        )

        # Analisar padroes de acesso
        access_analysis = await analyzer.analyze_access_patterns(
            user_id=request.user_id,
            access_data={
                "ip_address": request.ip_address,
                "device_id": request.device_id,
                "location": request.location,
                "geo_coordinates": request.geo_coordinates,
            },
        )

        processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return AccessCheckResponse(
            user_id=request.user_id,
            is_allowed=result.get("decision") in ["allow", "challenge"],
            risk_score=result.get("risk_score", 0),
            risk_level=RiskLevel(result.get("risk_level", "low")),
            decision=result.get("decision", "allow"),
            challenge_type=result.get("challenge_type"),
            anomalies_detected=access_analysis.get("anomalies", []),
            risk_factors=result.get("risk_factors", []),
            is_new_device=access_analysis.get("is_new_device", False),
            is_new_location=access_analysis.get("is_new_location", False),
            is_unusual_time=access_analysis.get("is_unusual_time", False),
            alerts_generated=result.get("alerts_generated", []),
            processing_time_ms=processing_time,
        )

    except Exception as e:
        logger.error(f"Erro na verificacao de acesso: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# =============================================================================
# Alert Endpoints
# =============================================================================


@router.get(
    "/alerts",
    response_model=AlertListResponse,
    summary="Listar alertas",
)
async def list_alerts(
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
    status_filter: AlertStatus | None = Query(None, alias="status"),
    severity: AlertSeverity | None = None,
    category: FraudCategory | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AlertListResponse:
    """Lista alertas com filtros."""
    repo = FraudRepository(db)

    # repo.get_alerts e sincrono e recebe os filtros nomeados diretamente
    # (nao filters=/skip=/limit=).
    alerts, total = repo.get_alerts(
        category=category,
        severity=severity,
        status=status_filter,
        entity_type=entity_type,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    pages = (total + page_size - 1) // page_size

    return AlertListResponse(
        items=[FraudAlertResponse.model_validate(a) for a in alerts],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/alerts/{alert_id}",
    response_model=FraudAlertResponse,
    summary="Obter alerta",
)
async def get_alert(
    alert_id: UUID,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudAlertResponse:
    """Obtem detalhes de um alerta."""
    repo = FraudRepository(db)
    alert = repo.get_alert(alert_id)

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta nao encontrado",
        )

    return FraudAlertResponse.model_validate(alert)


@router.post(
    "/alerts",
    response_model=FraudAlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar alerta manual",
)
async def create_alert(
    data: FraudAlertCreate,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudAlertResponse:
    """Cria alerta manualmente."""
    manager = AlertManager(db)

    alert = await manager.create_alert(
        category=data.category,
        severity=data.severity,
        title=data.title,
        description=data.description,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        transaction_id=data.transaction_id,
        transaction_value=data.transaction_value,
        rule_id=data.rule_id,
        pattern_id=data.pattern_id,
        risk_score=data.risk_score,
        confidence_score=data.confidence_score,
        evidence=data.evidence,
        indicators=data.indicators,
        ip_address=data.ip_address,
        location=data.location,
        potential_loss=data.potential_loss,
        requires_immediate_action=data.requires_immediate_action,
    )

    return FraudAlertResponse.model_validate(alert)


@router.patch(
    "/alerts/{alert_id}",
    response_model=FraudAlertResponse,
    summary="Atualizar alerta",
)
async def update_alert(
    alert_id: UUID,
    data: FraudAlertUpdate,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudAlertResponse:
    """Atualiza um alerta."""
    repo = FraudRepository(db)
    alert = repo.update_alert(alert_id, data.model_dump(exclude_unset=True))

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alerta nao encontrado",
        )

    return FraudAlertResponse.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/assign",
    response_model=FraudAlertResponse,
    summary="Atribuir alerta",
)
async def assign_alert(
    alert_id: UUID,
    data: AlertAssignRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudAlertResponse:
    """Atribui alerta a um analista."""
    manager = AlertManager(db)

    alert = await manager.assign_alert(
        alert_id=alert_id,
        assigned_to=data.assigned_to,
        assigned_by=UUID(current_user.id),
    )

    return FraudAlertResponse.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=FraudAlertResponse,
    summary="Resolver alerta",
)
async def resolve_alert(
    alert_id: UUID,
    data: AlertResolveRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudAlertResponse:
    """Resolve um alerta."""
    manager = AlertManager(db)

    alert = await manager.resolve_alert(
        alert_id=alert_id,
        resolved_by=UUID(current_user.id),
        resolution_type=data.resolution_type,
        resolution_notes=data.resolution_notes,
        actions_taken=data.actions_taken,
        actual_loss=data.actual_loss,
        recovered_amount=data.recovered_amount,
    )

    return FraudAlertResponse.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/confirm",
    response_model=FraudAlertResponse,
    summary="Confirmar fraude",
)
async def confirm_fraud(
    alert_id: UUID,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
    notes: str | None = None,
    actual_loss: float | None = None,
) -> FraudAlertResponse:
    """Confirma alerta como fraude verdadeira."""
    manager = AlertManager(db)

    alert = await manager.confirm_fraud(
        alert_id=alert_id,
        confirmed_by=UUID(current_user.id),
        notes=notes,
        actual_loss=actual_loss,
    )

    return FraudAlertResponse.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/false-positive",
    response_model=FraudAlertResponse,
    summary="Marcar falso positivo",
)
async def mark_false_positive(
    alert_id: UUID,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
    notes: str | None = None,
) -> FraudAlertResponse:
    """Marca alerta como falso positivo."""
    manager = AlertManager(db)

    alert = await manager.mark_false_positive(
        alert_id=alert_id,
        _marked_by=UUID(current_user.id),
        notes=notes,
    )

    return FraudAlertResponse.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/escalate",
    response_model=FraudAlertResponse,
    summary="Escalar alerta",
)
async def escalate_alert(
    alert_id: UUID,
    data: AlertEscalateRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudAlertResponse:
    """Escala alerta para nivel superior."""
    manager = AlertManager(db)

    alert = await manager.escalate_alert(
        alert_id=alert_id,
        escalate_to=data.escalate_to,
        reason=data.reason,
        escalated_by=UUID(current_user.id),
    )

    return FraudAlertResponse.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/feedback", response_model=FraudAlertResponse, summary="Adicionar feedback", status_code=201
)
async def add_feedback(
    alert_id: UUID,
    data: AlertFeedbackRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudAlertResponse:
    """Adiciona feedback ao alerta."""
    manager = AlertManager(db)

    alert = await manager.add_feedback(
        alert_id=alert_id,
        is_correct=data.is_correct,
        feedback_by=UUID(current_user.id),
        notes=data.notes,
    )

    return FraudAlertResponse.model_validate(alert)


# =============================================================================
# Rule Endpoints
# =============================================================================


@router.get(
    "/rules",
    response_model=list[FraudRuleResponse],
    summary="Listar regras",
)
async def list_rules(
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
    rule_type: RuleType | None = None,
    category: str | None = None,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[FraudRuleResponse]:
    """Lista regras de deteccao."""
    repo = FraudRepository(db)

    # repo.get_rules e sincrono e usa paginacao page/page_size (nao filters=/skip=/limit=)
    page_size = max(limit, 1)
    page = (skip // page_size) + 1

    rules, _total = repo.get_rules(
        rule_type=rule_type,
        category=category,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )

    return [FraudRuleResponse.model_validate(r) for r in rules]


@router.get(
    "/rules/{rule_id}",
    response_model=FraudRuleResponse,
    summary="Obter regra",
)
async def get_rule(
    rule_id: UUID,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudRuleResponse:
    """Obtem detalhes de uma regra."""
    repo = FraudRepository(db)
    rule = repo.get_rule(rule_id)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra nao encontrada",
        )

    return FraudRuleResponse.model_validate(rule)


@router.post(
    "/rules",
    response_model=FraudRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar regra",
)
async def create_rule(
    data: FraudRuleCreate,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudRuleResponse:
    """Cria nova regra de deteccao."""
    repo = FraudRepository(db)

    # Converter condicoes
    conditions = [c.model_dump() for c in data.conditions]

    # repo.create_rule espera um dict (rule_data), nao kwargs soltos.
    rule_data = {
        "code": data.code,
        "name": data.name,
        "description": data.description,
        "rule_type": data.rule_type,
        "category": data.category,
        "subcategory": data.subcategory,
        "default_severity": data.default_severity,
        "risk_weight": data.risk_weight,
        "conditions": conditions,
        "threshold_value": data.threshold_value,
        "threshold_count": data.threshold_count,
        "threshold_period_minutes": data.threshold_period_minutes,
        "velocity_count": data.velocity_count,
        "velocity_period_minutes": data.velocity_period_minutes,
        "velocity_field": data.velocity_field,
        "primary_action": data.primary_action,
        "secondary_actions": data.secondary_actions,
        "notify_channels": data.notify_channels,
        "applies_to_entities": data.applies_to_entities,
        "applies_to_transactions": data.applies_to_transactions,
        "is_active": data.is_active,
        "is_test_mode": data.is_test_mode,
    }

    rule = repo.create_rule(rule_data)

    return FraudRuleResponse.model_validate(rule)


@router.patch(
    "/rules/{rule_id}",
    response_model=FraudRuleResponse,
    summary="Atualizar regra",
)
async def update_rule(
    rule_id: UUID,
    data: FraudRuleUpdate,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudRuleResponse:
    """Atualiza uma regra."""
    repo = FraudRepository(db)

    update_data = data.model_dump(exclude_unset=True)
    if "conditions" in update_data and update_data["conditions"]:
        update_data["conditions"] = [c.model_dump() for c in data.conditions]

    rule = repo.update_rule(rule_id, update_data)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra nao encontrada",
        )

    return FraudRuleResponse.model_validate(rule)


@router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir regra",
)
async def delete_rule(
    rule_id: UUID,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> None:
    """Exclui uma regra (soft delete)."""
    repo = FraudRepository(db)
    success = repo.delete_rule(rule_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra nao encontrada",
        )


@router.post(
    "/rules/test",
    response_model=RuleTestResponse,
    summary="Testar regra",
)
async def test_rule(
    data: RuleTestRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> RuleTestResponse:
    """Testa uma regra com dados de exemplo."""
    repo = FraudRepository(db)
    rule = repo.get_rule(data.rule_id)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regra nao encontrada",
        )

    # rule.evaluate() (model) retorna tupla (matched, score, reasons), nao dict.
    matched, score, reasons = rule.evaluate(data.test_data)

    return RuleTestResponse(
        matched=matched,
        score=score,
        reasons=reasons,
        conditions_evaluated=len(rule.conditions or []),
        conditions_matched=len(reasons),
    )


# =============================================================================
# Pattern Endpoints
# =============================================================================


@router.get(
    "/patterns",
    response_model=list[FraudPatternResponse],
    summary="Listar padroes",
)
async def list_patterns(
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
    pattern_type: PatternType | None = None,
    category: str | None = None,
    status_filter: PatternStatus | None = Query(None, alias="status"),
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[FraudPatternResponse]:
    """Lista padroes de fraude."""
    repo = FraudRepository(db)

    # repo.get_patterns e sincrono e usa page/page_size (nao filters=/skip=/limit=)
    page_size = max(limit, 1)
    page = (skip // page_size) + 1

    patterns, _total = repo.get_patterns(
        pattern_type=pattern_type,
        status=status_filter,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    if category:
        patterns = [p for p in patterns if p.category == category]

    return [FraudPatternResponse.model_validate(p) for p in patterns]


@router.get(
    "/patterns/{pattern_id}",
    response_model=FraudPatternResponse,
    summary="Obter padrao",
)
async def get_pattern(
    pattern_id: UUID,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudPatternResponse:
    """Obtem detalhes de um padrao."""
    repo = FraudRepository(db)
    pattern = repo.get_pattern(pattern_id)

    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Padrao nao encontrado",
        )

    return FraudPatternResponse.model_validate(pattern)


@router.post(
    "/patterns",
    response_model=FraudPatternResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar padrao",
)
async def create_pattern(
    data: FraudPatternCreate,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudPatternResponse:
    """Cria novo padrao de fraude."""
    repo = FraudRepository(db)

    # repo.create_pattern espera um dict (pattern_data), nao kwargs soltos.
    pattern_data = {
        "code": data.code,
        "name": data.name,
        "description": data.description,
        "pattern_type": data.pattern_type,
        "category": data.category,
        "subcategory": data.subcategory,
        "severity": data.severity,
        "risk_score": data.risk_score,
        "pattern_definition": data.pattern_definition,
        "features": data.features,
        "indicators": data.indicators,
        "detection_threshold": data.detection_threshold,
        "confidence_threshold": data.confidence_threshold,
        "prevention_tips": data.prevention_tips,
        "recommended_actions": data.recommended_actions,
        "is_active": data.is_active,
        "is_ml_based": data.is_ml_based,
    }

    pattern = repo.create_pattern(pattern_data)

    return FraudPatternResponse.model_validate(pattern)


@router.patch(
    "/patterns/{pattern_id}",
    response_model=FraudPatternResponse,
    summary="Atualizar padrao",
)
async def update_pattern(
    pattern_id: UUID,
    data: FraudPatternUpdate,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudPatternResponse:
    """Atualiza um padrao."""
    repo = FraudRepository(db)
    pattern = repo.update_pattern(pattern_id, data.model_dump(exclude_unset=True))

    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Padrao nao encontrado",
        )

    return FraudPatternResponse.model_validate(pattern)


@router.post(
    "/patterns/match",
    response_model=PatternMatchResponse,
    summary="Verificar match de padrao",
)
async def match_pattern(
    data: PatternMatchRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> PatternMatchResponse:
    """Verifica se dados correspondem a um padrao."""
    # pattern.match(data: dict) e sincrono e recebe UM dict (nao data + indicators
    # separados); os indicadores vao embutidos em data["indicators"]. Retorna
    # tupla (matched, confidence, indicators_found), nao dict.
    match_data = {**data.data, "indicators": data.indicators}

    if data.pattern_id:
        # Verificar padrao especifico
        repo = FraudRepository(db)
        pattern = repo.get_pattern(data.pattern_id)

        if not pattern:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Padrao nao encontrado",
            )

        matched, confidence, indicators_found = pattern.match(match_data)

        return PatternMatchResponse(
            matched=matched,
            pattern_id=data.pattern_id,
            pattern_name=pattern.name,
            confidence=confidence,
            indicators_found=indicators_found,
            risk_score=pattern.risk_score * confidence,
        )
    else:
        # Verificar todos os padroes ativos
        repo = FraudRepository(db)
        patterns, _total = repo.get_patterns(is_active=True, status=PatternStatus.ACTIVE)

        best_match = None
        best_confidence = 0.0
        best_indicators: list[str] = []

        for pattern in patterns:
            matched, confidence, indicators_found = pattern.match(match_data)
            if matched and confidence > best_confidence:
                best_match = pattern
                best_confidence = confidence
                best_indicators = indicators_found

        if best_match:
            return PatternMatchResponse(
                matched=True,
                pattern_id=best_match.id,
                pattern_name=best_match.name,
                confidence=best_confidence,
                indicators_found=best_indicators,
                risk_score=best_match.risk_score * best_confidence,
            )

        return PatternMatchResponse(
            matched=False,
            confidence=0,
            indicators_found=[],
            risk_score=0,
        )


# =============================================================================
# Risk Profile Endpoints
# =============================================================================


@router.get(
    "/profiles",
    response_model=list[RiskProfileResponse],
    summary="Listar perfis de risco",
)
async def list_profiles(
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
    entity_type: EntityType | None = None,
    risk_level: RiskLevel | None = None,
    is_blocked: bool | None = None,
    is_watchlisted: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[RiskProfileResponse]:
    """Lista perfis de risco."""
    repo = FraudRepository(db)

    # repo.get_profiles e sincrono e usa page/page_size (nao filters=/skip=/limit=)
    page_size = max(limit, 1)
    page = (skip // page_size) + 1

    profiles, _total = repo.get_profiles(
        entity_type=entity_type,
        risk_level=risk_level,
        is_blocked=is_blocked,
        is_watchlisted=is_watchlisted,
        page=page,
        page_size=page_size,
    )

    return [RiskProfileResponse.model_validate(p) for p in profiles]


@router.get(
    "/profiles/{entity_type}/{entity_id}",
    response_model=RiskProfileResponse,
    summary="Obter perfil de risco",
)
async def get_profile(
    entity_type: EntityType,
    entity_id: UUID,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> RiskProfileResponse:
    """Obtem perfil de risco de uma entidade."""
    repo = FraudRepository(db)
    profile = repo.get_profile_by_entity(entity_type, entity_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado",
        )

    return RiskProfileResponse.model_validate(profile)


@router.post(
    "/profiles",
    response_model=RiskProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar perfil de risco",
)
async def create_profile(
    data: RiskProfileCreate,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> RiskProfileResponse:
    """Cria novo perfil de risco."""
    repo = FraudRepository(db)

    # Verificar se ja existe (get_profile_by_entity, nao get_profile — que busca por profile_id)
    existing = repo.get_profile_by_entity(data.entity_type, data.entity_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Perfil ja existe para esta entidade",
        )

    # repo.create_profile espera um dict (profile_data), nao kwargs soltos.
    profile_data = {
        "entity_type": data.entity_type,
        "entity_id": data.entity_id,
        "entity_identifier": data.entity_identifier,
        "entity_name": data.entity_name,
        "risk_level": data.risk_level,
        "risk_score": data.risk_score,
        "behavior_score": data.behavior_score,
        "transaction_score": data.transaction_score,
        "risk_factors": data.risk_factors,
        "trust_indicators": data.trust_indicators,
        "transaction_limit_daily": data.transaction_limit_daily,
        "transaction_limit_monthly": data.transaction_limit_monthly,
    }

    profile = repo.create_profile(profile_data)

    return RiskProfileResponse.model_validate(profile)


@router.patch(
    "/profiles/{entity_type}/{entity_id}",
    response_model=RiskProfileResponse,
    summary="Atualizar perfil de risco",
)
async def update_profile(
    entity_type: EntityType,
    entity_id: UUID,
    data: RiskProfileUpdate,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> RiskProfileResponse:
    """Atualiza perfil de risco."""
    repo = FraudRepository(db)

    # repo.update_profile espera profile_id (nao entity_type/entity_id) + dict
    existing = repo.get_profile_by_entity(entity_type, entity_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado",
        )

    profile = repo.update_profile(existing.id, data.model_dump(exclude_unset=True))

    return RiskProfileResponse.model_validate(profile)


@router.post(
    "/profiles/score",
    response_model=RiskScoreResponse,
    summary="Calcular score de risco",
)
async def calculate_risk_score(
    data: RiskScoreRequest,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> RiskScoreResponse:
    """Calcula ou recalcula score de risco."""
    scorer = RiskScorer(db)

    result = await scorer.calculate_risk_score(
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        recalculate=data.recalculate,
    )

    return RiskScoreResponse(
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        risk_level=RiskLevel(result["risk_level"]),
        risk_score=result["risk_score"],
        previous_score=result.get("previous_score"),
        score_change=result.get("score_change", 0),
        risk_factors=result.get("risk_factors", []),
        recommendations=result.get("recommendations", []),
    )


@router.post(
    "/profiles/{entity_type}/{entity_id}/block",
    response_model=RiskProfileResponse,
    summary="Bloquear entidade",
)
async def block_entity(
    entity_type: EntityType,
    entity_id: UUID,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
    reason: str | None = None,
) -> RiskProfileResponse:
    """Bloqueia uma entidade."""
    repo = FraudRepository(db)
    profile = repo.get_profile_by_entity(entity_type, entity_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado",
        )

    # profile.block(user_id, reason) — user_id obrigatorio no model
    profile.block(UUID(current_user.id), reason or "Bloqueio administrativo")
    db.commit()

    return RiskProfileResponse.model_validate(profile)


@router.post(
    "/profiles/{entity_type}/{entity_id}/unblock",
    response_model=RiskProfileResponse,
    summary="Desbloquear entidade",
)
async def unblock_entity(
    entity_type: EntityType,
    entity_id: UUID,
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> RiskProfileResponse:
    """Desbloqueia uma entidade."""
    repo = FraudRepository(db)
    profile = repo.get_profile_by_entity(entity_type, entity_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado",
        )

    profile.unblock()
    db.commit()

    return RiskProfileResponse.model_validate(profile)


# =============================================================================
# Dashboard Endpoints
# =============================================================================


@router.get(
    "/dashboard/stats",
    response_model=FraudDashboardStats,
    summary="Estatisticas do dashboard",
)
async def get_dashboard_stats(
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> FraudDashboardStats:
    """Obtem estatisticas para dashboard de fraude."""
    manager = AlertManager(db)
    scorer = RiskScorer(db)
    repo = FraudRepository(db)

    # Estatisticas de alertas
    # NOTA: manager.get_dashboard_stats()/get_pending_alerts()/get_overdue_alerts() ainda
    # dependem de AlertStatus.PENDING (nao existe no enum) e de FraudAlert.sla_deadline/
    # is_escalated (nao sao colunas do model) — bug pre-existente fora do escopo dos 13
    # mismatches desta tarefa (nao tocado; ver relatorio).
    alert_stats = await manager.get_dashboard_stats()

    # Distribuicao de risco
    risk_summary = await scorer.get_risk_summary()

    # Regras e padroes ativos (repo.get_rules/get_patterns sao sincronos e retornam tupla)
    rules, _total_rules = repo.get_rules(is_active=True)
    patterns, _total_patterns = repo.get_patterns(is_active=True, status=PatternStatus.ACTIVE)

    # Top regras acionadas (sincrono)
    top_rules = repo.get_top_triggered_rules(limit=5)

    return FraudDashboardStats(
        alerts_summary=alert_stats["alerts_summary"],
        total_detections_today=alert_stats["total_detections_today"],
        total_detections_week=alert_stats["total_detections_week"],
        total_detections_month=alert_stats["total_detections_month"],
        total_loss_prevented=alert_stats["total_loss_prevented"],
        actual_losses=alert_stats["actual_losses"],
        recovery_rate=alert_stats.get("recovery_rate", 0),
        detection_rate=100 - alert_stats["false_positive_rate"],
        false_positive_rate=alert_stats["false_positive_rate"],
        avg_detection_time_seconds=0,
        active_rules=len(rules),
        rules_triggered_today=alert_stats["total_detections_today"],
        most_triggered_rules=top_rules,
        active_patterns=len(patterns),
        patterns_detected_today=0,
        high_risk_profiles=risk_summary["high_risk_count"],
        blocked_entities=risk_summary["blocked_count"],
        watchlisted_entities=0,
        risk_distribution=risk_summary["distribution"],
        alerts_trend=[],
        fraud_trend=[],
    )


@router.get(
    "/dashboard/alerts/pending",
    response_model=list[FraudAlertResponse],
    summary="Alertas pendentes",
)
async def get_pending_alerts(
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
    severity: AlertSeverity | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> list[FraudAlertResponse]:
    """Obtem alertas pendentes priorizados."""
    manager = AlertManager(db)
    alerts = await manager.get_pending_alerts(severity=severity, limit=limit)
    return [FraudAlertResponse.model_validate(a) for a in alerts]


@router.get(
    "/dashboard/alerts/overdue",
    response_model=list[FraudAlertResponse],
    summary="Alertas vencidos",
)
async def get_overdue_alerts(
    current_user: CurrentActiveUser = ...,  # Required
    db: Session = Depends(get_db),
) -> list[FraudAlertResponse]:
    """Obtem alertas que excederam SLA."""
    manager = AlertManager(db)
    alerts = await manager.get_overdue_alerts()
    return [FraudAlertResponse.model_validate(a) for a in alerts]
