"""
Fraud Repository - AI Fraud Detection

Repositorio para operacoes de banco de dados.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from modules.ai.fraud_detection.models.fraud_alert import (
    AlertSeverity,
    AlertStatus,
    FraudAlert,
    FraudCategory,
)
from modules.ai.fraud_detection.models.fraud_pattern import (
    FraudPattern,
    PatternStatus,
    PatternType,
)
from modules.ai.fraud_detection.models.fraud_rule import (
    FraudRule,
    RuleType,
)
from modules.ai.fraud_detection.models.risk_profile import (
    EntityType,
    RiskLevel,
    RiskProfile,
)

logger = logging.getLogger(__name__)


class FraudRepository:
    """
    Repositorio para operacoes de fraude.

    Gerencia CRUD e queries para alertas, regras,
    padroes e perfis de risco.
    """

    def __init__(self, db: Session):
        """Inicializa repositorio."""
        self.db = db

    # =========================================================================
    # Alert Operations
    # =========================================================================

    def create_alert(self, alert_data: dict[str, Any]) -> FraudAlert:
        """Cria novo alerta."""
        # Gerar numero do alerta
        count = self.db.query(FraudAlert).count()
        alert_number = f"FRD-{datetime.now().strftime('%Y%m')}-{count + 1:05d}"

        alert = FraudAlert(
            alert_number=alert_number,
            **alert_data,
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)

        logger.info(f"Alerta criado: {alert.alert_number}")
        return alert

    def get_alert(self, alert_id: UUID) -> FraudAlert | None:
        """Busca alerta por ID."""
        return self.db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()

    def get_alert_by_number(self, alert_number: str) -> FraudAlert | None:
        """Busca alerta por numero."""
        return self.db.query(FraudAlert).filter(FraudAlert.alert_number == alert_number).first()

    def get_alerts(
        self,
        category: FraudCategory | None = None,
        severity: AlertSeverity | None = None,
        status: AlertStatus | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        assigned_to: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        is_active: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FraudAlert], int]:
        """Lista alertas com filtros."""
        query = self.db.query(FraudAlert)

        if is_active is not None:
            query = query.filter(FraudAlert.is_active == is_active)

        if category:
            query = query.filter(FraudAlert.category == category)

        if severity:
            query = query.filter(FraudAlert.severity == severity)

        if status:
            query = query.filter(FraudAlert.status == status)

        if entity_type:
            query = query.filter(FraudAlert.entity_type == entity_type)

        if entity_id:
            query = query.filter(FraudAlert.entity_id == entity_id)

        if assigned_to:
            query = query.filter(FraudAlert.assigned_to == assigned_to)

        if date_from:
            query = query.filter(FraudAlert.created_at >= date_from)

        if date_to:
            query = query.filter(FraudAlert.created_at <= date_to)

        total = query.count()

        alerts = query.order_by(desc(FraudAlert.created_at)).offset((page - 1) * page_size).limit(page_size).all()

        return alerts, total

    def get_pending_alerts_count(self) -> int:
        """Conta alertas pendentes."""
        return (
            self.db.query(FraudAlert)
            .filter(
                FraudAlert.status.in_([AlertStatus.NEW, AlertStatus.INVESTIGATING]),
                FraudAlert.is_active,
            )
            .count()
        )

    def get_alerts_by_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        limit: int = 10,
    ) -> list[FraudAlert]:
        """Lista alertas de uma entidade."""
        return (
            self.db.query(FraudAlert)
            .filter(
                FraudAlert.entity_type == entity_type,
                FraudAlert.entity_id == entity_id,
                FraudAlert.is_active,
            )
            .order_by(desc(FraudAlert.created_at))
            .limit(limit)
            .all()
        )

    def update_alert(
        self,
        alert_id: UUID,
        update_data: dict[str, Any],
    ) -> FraudAlert | None:
        """Atualiza alerta."""
        alert = self.get_alert(alert_id)
        if not alert:
            return None

        for key, value in update_data.items():
            if hasattr(alert, key):
                setattr(alert, key, value)

        alert.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(alert)
        return alert

    # =========================================================================
    # Rule Operations
    # =========================================================================

    def create_rule(self, rule_data: dict[str, Any]) -> FraudRule:
        """Cria nova regra."""
        rule = FraudRule(**rule_data)
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)

        logger.info(f"Regra criada: {rule.code}")
        return rule

    def get_rule(self, rule_id: UUID) -> FraudRule | None:
        """Busca regra por ID."""
        return self.db.query(FraudRule).filter(FraudRule.id == rule_id).first()

    def get_rule_by_code(self, code: str) -> FraudRule | None:
        """Busca regra por codigo."""
        return self.db.query(FraudRule).filter(FraudRule.code == code).first()

    def get_active_rules(
        self,
        rule_type: RuleType | None = None,
        category: str | None = None,
        applies_to: str | None = None,
    ) -> list[FraudRule]:
        """Lista regras ativas."""
        query = self.db.query(FraudRule).filter(FraudRule.is_active)

        if rule_type:
            query = query.filter(FraudRule.rule_type == rule_type)

        if category:
            query = query.filter(FraudRule.category == category)

        if applies_to:
            query = query.filter(FraudRule.applies_to_entities.contains([applies_to]))

        return query.all()

    def get_rules(
        self,
        rule_type: RuleType | None = None,
        category: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FraudRule], int]:
        """Lista regras com filtros."""
        query = self.db.query(FraudRule)

        if is_active is not None:
            query = query.filter(FraudRule.is_active == is_active)

        if rule_type:
            query = query.filter(FraudRule.rule_type == rule_type)

        if category:
            query = query.filter(FraudRule.category == category)

        total = query.count()

        rules = query.order_by(FraudRule.code).offset((page - 1) * page_size).limit(page_size).all()

        return rules, total

    def update_rule(
        self,
        rule_id: UUID,
        update_data: dict[str, Any],
    ) -> FraudRule | None:
        """Atualiza regra."""
        rule = self.get_rule(rule_id)
        if not rule:
            return None

        for key, value in update_data.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        rule.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def delete_rule(self, rule_id: UUID) -> bool:
        """Exclui regra (soft delete: is_active=false). Nunca hard-delete."""
        rule = self.get_rule(rule_id)
        if not rule:
            return False

        rule.is_active = False
        rule.updated_at = datetime.utcnow()
        self.db.commit()

        logger.info(f"Regra desativada (soft delete): {rule.code}")
        return True

    # =========================================================================
    # Pattern Operations
    # =========================================================================

    def create_pattern(self, pattern_data: dict[str, Any]) -> FraudPattern:
        """Cria novo padrao."""
        pattern = FraudPattern(**pattern_data)
        self.db.add(pattern)
        self.db.commit()
        self.db.refresh(pattern)

        logger.info(f"Padrao criado: {pattern.code}")
        return pattern

    def get_pattern(self, pattern_id: UUID) -> FraudPattern | None:
        """Busca padrao por ID."""
        return self.db.query(FraudPattern).filter(FraudPattern.id == pattern_id).first()

    def get_pattern_by_code(self, code: str) -> FraudPattern | None:
        """Busca padrao por codigo."""
        return self.db.query(FraudPattern).filter(FraudPattern.code == code).first()

    def get_active_patterns(
        self,
        pattern_type: PatternType | None = None,
        category: str | None = None,
    ) -> list[FraudPattern]:
        """Lista padroes ativos."""
        query = self.db.query(FraudPattern).filter(
            FraudPattern.is_active,
            FraudPattern.status == PatternStatus.ACTIVE,
        )

        if pattern_type:
            query = query.filter(FraudPattern.pattern_type == pattern_type)

        if category:
            query = query.filter(FraudPattern.category == category)

        return query.all()

    def get_patterns(
        self,
        pattern_type: PatternType | None = None,
        status: PatternStatus | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FraudPattern], int]:
        """Lista padroes com filtros."""
        query = self.db.query(FraudPattern)

        if is_active is not None:
            query = query.filter(FraudPattern.is_active == is_active)

        if pattern_type:
            query = query.filter(FraudPattern.pattern_type == pattern_type)

        if status:
            query = query.filter(FraudPattern.status == status)

        total = query.count()

        patterns = query.order_by(FraudPattern.code).offset((page - 1) * page_size).limit(page_size).all()

        return patterns, total

    def update_pattern(
        self,
        pattern_id: UUID,
        update_data: dict[str, Any],
    ) -> FraudPattern | None:
        """Atualiza padrao."""
        pattern = self.get_pattern(pattern_id)
        if not pattern:
            return None

        for key, value in update_data.items():
            if hasattr(pattern, key):
                setattr(pattern, key, value)

        pattern.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(pattern)
        return pattern

    # =========================================================================
    # Risk Profile Operations
    # =========================================================================

    def create_profile(self, profile_data: dict[str, Any]) -> RiskProfile:
        """Cria novo perfil de risco."""
        profile = RiskProfile(**profile_data)
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)

        logger.info(f"Perfil criado: {profile.entity_type}:{profile.entity_id}")
        return profile

    def get_profile(self, profile_id: UUID) -> RiskProfile | None:
        """Busca perfil por ID."""
        return self.db.query(RiskProfile).filter(RiskProfile.id == profile_id).first()

    def get_profile_by_entity(
        self,
        entity_type: EntityType,
        entity_id: UUID,
    ) -> RiskProfile | None:
        """Busca perfil por entidade."""
        return (
            self.db.query(RiskProfile)
            .filter(
                RiskProfile.entity_type == entity_type,
                RiskProfile.entity_id == entity_id,
            )
            .first()
        )

    def get_or_create_profile(
        self,
        entity_type: EntityType,
        entity_id: UUID,
        entity_name: str | None = None,
    ) -> RiskProfile:
        """Busca ou cria perfil."""
        profile = self.get_profile_by_entity(entity_type, entity_id)
        if profile:
            return profile

        return self.create_profile(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
            }
        )

    def get_profiles(
        self,
        entity_type: EntityType | None = None,
        risk_level: RiskLevel | None = None,
        is_blocked: bool | None = None,
        is_watchlisted: bool | None = None,
        min_risk_score: float | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[RiskProfile], int]:
        """Lista perfis com filtros."""
        query = self.db.query(RiskProfile).filter(RiskProfile.is_active)

        if entity_type:
            query = query.filter(RiskProfile.entity_type == entity_type)

        if risk_level:
            query = query.filter(RiskProfile.risk_level == risk_level)

        if is_blocked is not None:
            query = query.filter(RiskProfile.is_blocked == is_blocked)

        if is_watchlisted is not None:
            query = query.filter(RiskProfile.is_watchlisted == is_watchlisted)

        if min_risk_score is not None:
            query = query.filter(RiskProfile.risk_score >= min_risk_score)

        total = query.count()

        profiles = query.order_by(desc(RiskProfile.risk_score)).offset((page - 1) * page_size).limit(page_size).all()

        return profiles, total

    def get_high_risk_profiles(self, limit: int = 50) -> list[RiskProfile]:
        """Lista perfis de alto risco."""
        return (
            self.db.query(RiskProfile)
            .filter(
                RiskProfile.is_active,
                RiskProfile.risk_level.in_(
                    [
                        RiskLevel.HIGH,
                        RiskLevel.CRITICAL,
                        RiskLevel.BLOCKED,
                    ]
                ),
            )
            .order_by(desc(RiskProfile.risk_score))
            .limit(limit)
            .all()
        )

    def update_profile(
        self,
        profile_id: UUID,
        update_data: dict[str, Any],
    ) -> RiskProfile | None:
        """Atualiza perfil."""
        profile = self.get_profile(profile_id)
        if not profile:
            return None

        for key, value in update_data.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        profile.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(profile)
        return profile

    # =========================================================================
    # Analytics
    # =========================================================================

    def get_alerts_stats(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        """Estatisticas de alertas."""
        if not date_from:
            date_from = datetime.utcnow() - timedelta(days=30)
        if not date_to:
            date_to = datetime.utcnow()

        query = self.db.query(FraudAlert).filter(
            FraudAlert.created_at >= date_from,
            FraudAlert.created_at <= date_to,
        )

        total = query.count()

        # Por status
        by_status = {}
        for status in AlertStatus:
            count = query.filter(FraudAlert.status == status).count()
            by_status[status.value] = count

        # Por severidade
        by_severity = {}
        for severity in AlertSeverity:
            count = query.filter(FraudAlert.severity == severity).count()
            by_severity[severity.value] = count

        # Por categoria
        by_category = {}
        for category in FraudCategory:
            count = query.filter(FraudAlert.category == category).count()
            if count > 0:
                by_category[category.value] = count

        # Perdas
        total_potential_loss = (
            self.db.query(func.sum(FraudAlert.potential_loss))
            .filter(
                FraudAlert.created_at >= date_from,
                FraudAlert.created_at <= date_to,
            )
            .scalar()
            or 0
        )

        total_actual_loss = (
            self.db.query(func.sum(FraudAlert.actual_loss))
            .filter(
                FraudAlert.created_at >= date_from,
                FraudAlert.created_at <= date_to,
                FraudAlert.status == AlertStatus.CONFIRMED,
            )
            .scalar()
            or 0
        )

        return {
            "total": total,
            "by_status": by_status,
            "by_severity": by_severity,
            "by_category": by_category,
            "total_potential_loss": total_potential_loss,
            "total_actual_loss": total_actual_loss,
            "loss_prevented": total_potential_loss - total_actual_loss,
        }

    def get_risk_distribution(self) -> dict[str, int]:
        """Distribuicao de risco dos perfis."""
        distribution = {}
        for level in RiskLevel:
            count = (
                self.db.query(RiskProfile)
                .filter(
                    RiskProfile.is_active,
                    RiskProfile.risk_level == level,
                )
                .count()
            )
            distribution[level.value] = count
        return distribution

    def get_top_triggered_rules(self, limit: int = 10) -> list[dict[str, Any]]:
        """Regras mais acionadas."""
        rules = (
            self.db.query(FraudRule)
            .filter(FraudRule.is_active)
            .order_by(desc(FraudRule.total_triggers))
            .limit(limit)
            .all()
        )

        return [
            {
                "id": str(r.id),
                "code": r.code,
                "name": r.name,
                "total_triggers": r.total_triggers,
                "precision_rate": r.precision_rate,
            }
            for r in rules
        ]
