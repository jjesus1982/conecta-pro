"""
Alert Manager Service - Sprint 45

Servico para gerenciamento de alertas de fraude.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from modules.ai.fraud_detection.models.fraud_alert import (
    AlertSeverity,
    AlertStatus,
    FraudAlert,
    FraudCategory,
)
from modules.ai.fraud_detection.models.fraud_pattern import FraudPattern
from modules.ai.fraud_detection.models.fraud_rule import FraudRule
from modules.ai.fraud_detection.models.risk_profile import EntityType, RiskProfile

logger = logging.getLogger(__name__)


class AlertManager:
    """Gerenciador de alertas de fraude."""

    # Configuracoes de SLA por severidade (em horas)
    SLA_CONFIG = {
        AlertSeverity.CRITICAL: 1,
        AlertSeverity.HIGH: 4,
        AlertSeverity.MEDIUM: 24,
        AlertSeverity.LOW: 72,
    }

    # Canais de notificacao por severidade
    NOTIFICATION_CHANNELS = {
        AlertSeverity.CRITICAL: ["sms", "email", "push", "slack"],
        AlertSeverity.HIGH: ["email", "push", "slack"],
        AlertSeverity.MEDIUM: ["email", "push"],
        AlertSeverity.LOW: ["email"],
    }

    def __init__(self, db: Session):
        """Inicializa o gerenciador."""
        self.db = db

    async def create_alert(
        self,
        category: FraudCategory,
        severity: AlertSeverity,
        title: str,
        entity_type: str,
        entity_id: UUID,
        description: str | None = None,
        transaction_id: UUID | None = None,
        transaction_value: float | None = None,
        rule_id: UUID | None = None,
        pattern_id: UUID | None = None,
        risk_score: float = 0,
        confidence_score: float | None = None,
        evidence: list[dict[str, Any]] | None = None,
        indicators: list[str] | None = None,
        ip_address: str | None = None,
        device_id: str | None = None,
        location: str | None = None,
        potential_loss: float | None = None,
        requires_immediate_action: bool = False,
    ) -> FraudAlert:
        """
        Cria um novo alerta de fraude.

        Returns:
            Alerta criado
        """
        try:
            # Verificar se ja existe alerta similar recente
            existing = await self._check_duplicate_alert(entity_type, entity_id, category, transaction_id)
            if existing:
                logger.info(f"Alerta similar ja existe: {existing.alert_number}")
                return existing

            # Criar alerta (alert_number e NOT NULL e nao tem default no DB — gerar aqui,
            # mesmo padrao usado em FraudRepository.create_alert)
            alert_count = self.db.query(FraudAlert).count()
            alert_number = f"FRD-{datetime.utcnow().strftime('%Y%m')}-{alert_count + 1:05d}"

            alert = FraudAlert(
                alert_number=alert_number,
                category=category,
                severity=severity,
                title=title,
                description=description,
                entity_type=entity_type,
                entity_id=entity_id,
                transaction_id=transaction_id,
                transaction_value=transaction_value,
                rule_id=rule_id,
                pattern_id=pattern_id,
                risk_score=risk_score,
                confidence_score=confidence_score,
                evidence=evidence or [],
                indicators=indicators or [],
                ip_address=ip_address,
                device_id=device_id,
                location=location,
                potential_loss=potential_loss,
                requires_immediate_action=requires_immediate_action,
                detected_at=datetime.utcnow(),
            )

            # Gerar sumario automatico
            alert.summary = await self._generate_summary(alert)

            # Definir SLA
            sla_hours = self.SLA_CONFIG.get(severity, 24)
            alert.sla_deadline = datetime.utcnow() + timedelta(hours=sla_hours)

            self.db.add(alert)
            self.db.commit()
            self.db.refresh(alert)

            logger.info(f"Alerta criado: {alert.alert_number} - {title} - Severity: {severity.value}")

            # Enviar notificacoes
            await self._send_notifications(alert)

            # Atualizar perfil de risco
            await self._update_risk_profile(entity_type, entity_id)

            # Atualizar estatisticas de regra/padrao
            if rule_id:
                await self._update_rule_stats(rule_id)
            if pattern_id:
                await self._update_pattern_stats(pattern_id)

            return alert

        except Exception as e:
            logger.error(f"Erro ao criar alerta: {e}")
            self.db.rollback()
            raise

    async def assign_alert(
        self,
        alert_id: UUID,
        assigned_to: UUID,
        assigned_by: UUID | None = None,
    ) -> FraudAlert:
        """Atribui alerta a um analista."""
        alert = self.db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alerta nao encontrado: {alert_id}")

        alert.assign(assigned_to)

        # Registrar acao (FraudAlert nao tem coluna actions_log; investigation_findings
        # e o JSONB real do model para trilha de investigacao).
        alert.investigation_findings = (alert.investigation_findings or []) + [
            {
                "action": "assigned",
                "assigned_to": str(assigned_to),
                "assigned_by": str(assigned_by) if assigned_by else None,
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]

        self.db.commit()
        logger.info(f"Alerta {alert.alert_number} atribuido a {assigned_to}")

        return alert

    async def resolve_alert(
        self,
        alert_id: UUID,
        resolved_by: UUID,
        resolution_type: str,
        resolution_notes: str | None = None,
        actions_taken: list[dict[str, Any]] | None = None,
        actual_loss: float | None = None,
        recovered_amount: float | None = None,
    ) -> FraudAlert:
        """Resolve um alerta."""
        alert = self.db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alerta nao encontrado: {alert_id}")

        # FraudAlert.resolve(user_id, resolution_type, notes=, actions=) — o model
        # espera user_id (nao resolved_by=); actions_taken vai para o JSONB real
        # resolution_actions via o parametro actions= (nao um actions_log inexistente).
        alert.resolve(
            user_id=resolved_by,
            resolution_type=resolution_type,
            notes=resolution_notes,
            actions=actions_taken,
        )

        if actual_loss is not None:
            alert.actual_loss = actual_loss
        if recovered_amount is not None:
            alert.recovered_amount = recovered_amount

        self.db.commit()
        logger.info(f"Alerta {alert.alert_number} resolvido: {resolution_type}")

        return alert

    async def confirm_fraud(
        self,
        alert_id: UUID,
        confirmed_by: UUID,
        notes: str | None = None,
        actual_loss: float | None = None,
    ) -> FraudAlert:
        """Confirma alerta como fraude verdadeira."""
        alert = self.db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alerta nao encontrado: {alert_id}")

        # FraudAlert.confirm(user_id, notes=) — user_id obrigatorio.
        alert.confirm(user_id=confirmed_by, notes=notes)

        if actual_loss is not None:
            alert.actual_loss = actual_loss

        self.db.commit()
        logger.info(f"Alerta {alert.alert_number} confirmado como fraude")

        # Atualizar perfil com fraude confirmada
        await self._record_confirmed_fraud(alert.entity_type, alert.entity_id, alert_id)

        # Atualizar precisao da regra/padrao
        if alert.rule_id:
            await self._record_rule_true_positive(alert.rule_id)
        if alert.pattern_id:
            await self._record_pattern_confirmed(alert.pattern_id)

        return alert

    async def mark_false_positive(
        self,
        alert_id: UUID,
        _marked_by: UUID,
        notes: str | None = None,
    ) -> FraudAlert:
        """Marca alerta como falso positivo."""
        alert = self.db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alerta nao encontrado: {alert_id}")

        # FraudAlert.mark_false_positive(user_id, notes=) — user_id obrigatorio.
        alert.mark_false_positive(user_id=_marked_by, notes=notes)

        self.db.commit()
        logger.info(f"Alerta {alert.alert_number} marcado como falso positivo")

        # Atualizar estatisticas
        if alert.rule_id:
            await self._record_rule_false_positive(alert.rule_id)
        if alert.pattern_id:
            await self._record_pattern_false_positive(alert.pattern_id)

        return alert

    async def escalate_alert(
        self,
        alert_id: UUID,
        escalate_to: UUID,
        reason: str,
        escalated_by: UUID | None = None,
    ) -> FraudAlert:
        """Escala alerta para nivel superior."""
        alert = self.db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alerta nao encontrado: {alert_id}")

        alert.escalate(escalate_to, reason=reason)

        # Registrar escalonamento (investigation_findings e o JSONB real do model)
        alert.investigation_findings = (alert.investigation_findings or []) + [
            {
                "action": "escalated",
                "escalate_to": str(escalate_to),
                "reason": reason,
                "escalated_by": str(escalated_by) if escalated_by else None,
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]

        # Aumentar severidade se necessario
        if alert.severity in [AlertSeverity.LOW, AlertSeverity.MEDIUM]:
            alert.severity = AlertSeverity.HIGH

        self.db.commit()
        logger.info(f"Alerta {alert.alert_number} escalado: {reason}")

        # Notificar
        await self._send_escalation_notification(alert, escalate_to, reason)

        return alert

    async def add_feedback(
        self,
        alert_id: UUID,
        is_correct: bool,
        feedback_by: UUID,
        notes: str | None = None,
    ) -> FraudAlert:
        """Adiciona feedback ao alerta."""
        alert = self.db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
        if not alert:
            raise ValueError(f"Alerta nao encontrado: {alert_id}")

        # feedback_correct e a coluna real (Boolean); nao existe feedback_status.
        alert.feedback_correct = is_correct
        alert.feedback_notes = notes
        alert.feedback_by = feedback_by
        alert.feedback_at = datetime.utcnow()

        # Registrar no log (investigation_findings e o JSONB real do model)
        alert.investigation_findings = (alert.investigation_findings or []) + [
            {
                "action": "feedback",
                "is_correct": is_correct,
                "notes": notes,
                "by": str(feedback_by),
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]

        self.db.commit()
        logger.info(f"Feedback adicionado ao alerta {alert.alert_number}: {'correto' if is_correct else 'incorreto'}")

        return alert

    async def get_dashboard_stats(self) -> dict[str, Any]:
        """Obtem estatisticas para dashboard."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)

        # Contagens por status
        status_counts = dict(
            self.db.query(FraudAlert.status, func.count(FraudAlert.id))
            .filter(FraudAlert.is_active)
            .group_by(FraudAlert.status)
            .all()
        )

        # Contagens por severidade
        severity_counts = dict(
            self.db.query(FraudAlert.severity, func.count(FraudAlert.id))
            .filter(
                FraudAlert.is_active,
                FraudAlert.status.in_(
                    [
                        AlertStatus.PENDING,
                        AlertStatus.INVESTIGATING,
                    ]
                ),
            )
            .group_by(FraudAlert.severity)
            .all()
        )

        # Contagens por categoria
        category_counts = dict(
            self.db.query(FraudAlert.category, func.count(FraudAlert.id))
            .filter(FraudAlert.created_at >= month_start)
            .group_by(FraudAlert.category)
            .all()
        )

        # Alertas por periodo
        today_count = (
            self.db.query(func.count(FraudAlert.id)).filter(FraudAlert.created_at >= today_start).scalar() or 0
        )
        week_count = self.db.query(func.count(FraudAlert.id)).filter(FraudAlert.created_at >= week_start).scalar() or 0
        month_count = (
            self.db.query(func.count(FraudAlert.id)).filter(FraudAlert.created_at >= month_start).scalar() or 0
        )

        # Tempo medio de resolucao
        resolved_alerts = (
            self.db.query(FraudAlert)
            .filter(
                FraudAlert.resolved_at.isnot(None),
                FraudAlert.created_at >= month_start,
            )
            .all()
        )

        avg_resolution_hours = 0
        if resolved_alerts:
            total_hours = sum((a.resolved_at - a.created_at).total_seconds() / 3600 for a in resolved_alerts)
            avg_resolution_hours = total_hours / len(resolved_alerts)

        # Perdas
        total_potential_loss = (
            self.db.query(func.sum(FraudAlert.potential_loss)).filter(FraudAlert.created_at >= month_start).scalar()
            or 0
        )
        total_actual_loss = (
            self.db.query(func.sum(FraudAlert.actual_loss)).filter(FraudAlert.created_at >= month_start).scalar() or 0
        )
        total_recovered = (
            self.db.query(func.sum(FraudAlert.recovered_amount)).filter(FraudAlert.created_at >= month_start).scalar()
            or 0
        )

        loss_prevented = total_potential_loss - total_actual_loss

        # Taxa de falsos positivos
        confirmed = (
            self.db.query(func.count(FraudAlert.id))
            .filter(
                FraudAlert.status == AlertStatus.CONFIRMED,
                FraudAlert.created_at >= month_start,
            )
            .scalar()
            or 0
        )
        false_positives = (
            self.db.query(func.count(FraudAlert.id))
            .filter(
                FraudAlert.status == AlertStatus.FALSE_POSITIVE,
                FraudAlert.created_at >= month_start,
            )
            .scalar()
            or 0
        )

        total_reviewed = confirmed + false_positives
        false_positive_rate = (false_positives / total_reviewed * 100) if total_reviewed > 0 else 0

        # Alertas vencidos (SLA)
        overdue_count = (
            self.db.query(func.count(FraudAlert.id))
            .filter(
                FraudAlert.status.in_(
                    [
                        AlertStatus.PENDING,
                        AlertStatus.INVESTIGATING,
                    ]
                ),
                FraudAlert.sla_deadline < now,
            )
            .scalar()
            or 0
        )

        # Escalados
        escalated_count = (
            self.db.query(func.count(FraudAlert.id))
            .filter(
                FraudAlert.is_escalated,
                FraudAlert.status.in_(
                    [
                        AlertStatus.PENDING,
                        AlertStatus.INVESTIGATING,
                    ]
                ),
            )
            .scalar()
            or 0
        )

        return {
            "alerts_summary": {
                "total_pending": status_counts.get(AlertStatus.PENDING, 0),
                "total_investigating": status_counts.get(AlertStatus.INVESTIGATING, 0),
                "total_confirmed": status_counts.get(AlertStatus.CONFIRMED, 0),
                "total_resolved": status_counts.get(AlertStatus.RESOLVED, 0),
                "total_false_positives": status_counts.get(AlertStatus.FALSE_POSITIVE, 0),
                "by_severity": {s.value: c for s, c in severity_counts.items()},
                "by_category": {c.value: cnt for c, cnt in category_counts.items()},
                "avg_resolution_time_hours": round(avg_resolution_hours, 1),
                "escalated_count": escalated_count,
                "overdue_count": overdue_count,
            },
            "total_detections_today": today_count,
            "total_detections_week": week_count,
            "total_detections_month": month_count,
            "total_loss_prevented": float(loss_prevented),
            "actual_losses": float(total_actual_loss),
            "recovered_amount": float(total_recovered),
            "recovery_rate": ((total_recovered / total_actual_loss * 100) if total_actual_loss > 0 else 0),
            "false_positive_rate": round(false_positive_rate, 1),
        }

    async def get_pending_alerts(
        self,
        severity: AlertSeverity | None = None,
        category: FraudCategory | None = None,
        limit: int = 50,
    ) -> list[FraudAlert]:
        """Obtem alertas pendentes."""
        query = self.db.query(FraudAlert).filter(
            FraudAlert.status == AlertStatus.PENDING,
            FraudAlert.is_active,
        )

        if severity:
            query = query.filter(FraudAlert.severity == severity)
        if category:
            query = query.filter(FraudAlert.category == category)

        return (
            query.order_by(
                FraudAlert.severity.desc(),
                FraudAlert.created_at.asc(),
            )
            .limit(limit)
            .all()
        )

    async def get_overdue_alerts(self) -> list[FraudAlert]:
        """Obtem alertas que excederam SLA."""
        return (
            self.db.query(FraudAlert)
            .filter(
                FraudAlert.status.in_(
                    [
                        AlertStatus.PENDING,
                        AlertStatus.INVESTIGATING,
                    ]
                ),
                FraudAlert.sla_deadline < datetime.utcnow(),
            )
            .order_by(FraudAlert.sla_deadline.asc())
            .all()
        )

    async def auto_assign_alerts(
        self,
        analysts: list[UUID],
        max_per_analyst: int = 10,
    ) -> dict[str, Any]:
        """Distribui alertas automaticamente entre analistas."""
        pending = await self.get_pending_alerts()
        assignments = {str(a): 0 for a in analysts}
        assigned_count = 0

        for alert in pending:
            if alert.assigned_to:
                continue

            # Encontrar analista com menos alertas
            min_analyst = min(
                analysts,
                key=lambda a: assignments.get(str(a), 0),
            )

            if assignments[str(min_analyst)] >= max_per_analyst:
                break

            await self.assign_alert(alert.id, min_analyst)
            assignments[str(min_analyst)] += 1
            assigned_count += 1

        return {
            "total_assigned": assigned_count,
            "assignments": assignments,
        }

    async def _check_duplicate_alert(
        self,
        entity_type: str,
        entity_id: UUID,
        category: FraudCategory,
        transaction_id: UUID | None,
    ) -> FraudAlert | None:
        """Verifica se existe alerta duplicado recente."""
        cutoff = datetime.utcnow() - timedelta(hours=1)

        query = self.db.query(FraudAlert).filter(
            FraudAlert.entity_type == entity_type,
            FraudAlert.entity_id == entity_id,
            FraudAlert.category == category,
            FraudAlert.created_at >= cutoff,
            # AlertStatus.PENDING nao existe no enum real; NEW e o status inicial
            # equivalente ("pendente de investigacao").
            FraudAlert.status.in_(
                [
                    AlertStatus.NEW,
                    AlertStatus.INVESTIGATING,
                ]
            ),
        )

        if transaction_id:
            query = query.filter(FraudAlert.transaction_id == transaction_id)

        return query.first()

    async def _generate_summary(self, alert: FraudAlert) -> str:
        """Gera sumario automatico do alerta."""
        parts = [
            f"Alerta {alert.severity.value.upper()}:",
            alert.title,
        ]

        if alert.risk_score > 0:
            parts.append(f"Risk Score: {alert.risk_score:.0f}")

        if alert.transaction_value:
            parts.append(f"Valor: R${alert.transaction_value:,.2f}")

        if alert.indicators:
            parts.append(f"Indicadores: {', '.join(alert.indicators[:3])}")

        return " | ".join(parts)

    async def _send_notifications(self, alert: FraudAlert) -> None:
        """Envia notificacoes para o alerta."""
        channels = self.NOTIFICATION_CHANNELS.get(alert.severity, ["email"])

        logger.info(f"Enviando notificacoes para alerta {alert.alert_number} via {channels}")
        # Implementacao real integraria com servico de notificacoes

    async def _send_escalation_notification(
        self,
        alert: FraudAlert,
        escalate_to: UUID,
        reason: str,
    ) -> None:
        """Envia notificacao de escalonamento."""
        logger.info(f"Notificacao de escalonamento: Alerta {alert.alert_number} escalado para {escalate_to}: {reason}")

    async def _update_risk_profile(
        self,
        entity_type: str,
        entity_id: UUID,
    ) -> None:
        """Atualiza perfil de risco com novo alerta."""
        try:
            entity_type_enum = EntityType(entity_type)
        except ValueError:
            return

        profile = (
            self.db.query(RiskProfile)
            .filter(
                RiskProfile.entity_type == entity_type_enum,
                RiskProfile.entity_id == entity_id,
            )
            .first()
        )

        if profile:
            profile.total_alerts = (profile.total_alerts or 0) + 1
            self.db.commit()

    async def _record_confirmed_fraud(
        self,
        entity_type: str,
        entity_id: UUID,
        alert_id: UUID,
    ) -> None:
        """Registra fraude confirmada no perfil."""
        try:
            entity_type_enum = EntityType(entity_type)
        except ValueError:
            return

        profile = (
            self.db.query(RiskProfile)
            .filter(
                RiskProfile.entity_type == entity_type_enum,
                RiskProfile.entity_id == entity_id,
            )
            .first()
        )

        if profile:
            profile.confirmed_frauds = (profile.confirmed_frauds or 0) + 1
            # RiskProfile.add_risk_factor(factor, weight=, score=) — a assinatura real
            # nao aceita uma descricao textual como 2o posicional.
            profile.add_risk_factor("previous_fraud", score=40)
            self.db.commit()

    async def _update_rule_stats(self, rule_id: UUID) -> None:
        """Atualiza estatisticas da regra."""
        rule = self.db.query(FraudRule).filter(FraudRule.id == rule_id).first()
        if rule:
            rule.increment_trigger()
            self.db.commit()

    async def _update_pattern_stats(self, pattern_id: UUID) -> None:
        """Atualiza estatisticas do padrao."""
        pattern = self.db.query(FraudPattern).filter(FraudPattern.id == pattern_id).first()
        if pattern:
            # FraudPattern.record_detection(confirmed=, ...) — nao is_confirmed=.
            pattern.record_detection(confirmed=False)
            self.db.commit()

    async def _record_rule_true_positive(self, rule_id: UUID) -> None:
        """Registra verdadeiro positivo na regra."""
        rule = self.db.query(FraudRule).filter(FraudRule.id == rule_id).first()
        if rule:
            rule.true_positives = (rule.true_positives or 0) + 1
            self.db.commit()

    async def _record_rule_false_positive(self, rule_id: UUID) -> None:
        """Registra falso positivo na regra."""
        rule = self.db.query(FraudRule).filter(FraudRule.id == rule_id).first()
        if rule:
            rule.false_positives = (rule.false_positives or 0) + 1
            self.db.commit()

    async def _record_pattern_confirmed(self, pattern_id: UUID) -> None:
        """Registra caso confirmado no padrao."""
        pattern = self.db.query(FraudPattern).filter(FraudPattern.id == pattern_id).first()
        if pattern:
            # FraudPattern.record_detection(confirmed=, ...) — nao is_confirmed=.
            pattern.record_detection(confirmed=True)
            self.db.commit()

    async def _record_pattern_false_positive(self, pattern_id: UUID) -> None:
        """Registra falso positivo no padrao."""
        pattern = self.db.query(FraudPattern).filter(FraudPattern.id == pattern_id).first()
        if pattern:
            pattern.false_positives = (pattern.false_positives or 0) + 1
            self.db.commit()
