"""
Alert Service - AI Contract Analysis

Gerencia alertas de contratos.
"""

import logging
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from modules.ai.contract_analysis.models.contract_alert import (
    AlertPriority,
    AlertStatus,
    AlertType,
    ContractAlert,
)
from modules.ai.contract_analysis.models.contract_analysis import ContractAnalysis
from modules.ai.contract_analysis.repositories.contract_repository import (
    ContractAnalysisRepository,
)

logger = logging.getLogger(__name__)


class AlertService:
    """
    Servico de alertas de contratos.

    Gera e gerencia alertas de vencimento, renovacao,
    riscos e conformidade.
    """

    # Configuracao de alertas por tipo
    ALERT_CONFIGS = {
        AlertType.EXPIRY: {
            "days_before": [90, 60, 30, 15, 7],
            "priority_map": {90: "low", 60: "medium", 30: "high", 15: "urgent", 7: "critical"},
        },
        AlertType.RENEWAL: {
            "days_before": [60, 30, 15],
            "priority_map": {60: "medium", 30: "high", 15: "urgent"},
        },
        AlertType.ADJUSTMENT: {
            "days_before": [30, 15],
            "priority_map": {30: "medium", 15: "high"},
        },
    }

    def __init__(self, db: Session):
        """Inicializa service."""
        self.db = db
        self.repository = ContractAnalysisRepository(db)

    def generate_alerts(
        self,
        analysis: ContractAnalysis,
        check_expiry: bool = True,
        check_renewal: bool = True,
        check_adjustment: bool = True,
        check_risk: bool = True,
    ) -> list[ContractAlert]:
        """
        Gera alertas para um contrato.

        Args:
            analysis: Analise do contrato
            check_expiry: Verificar vencimento
            check_renewal: Verificar renovacao
            check_adjustment: Verificar reajuste
            check_risk: Verificar riscos

        Returns:
            Lista de alertas gerados
        """
        logger.info(f"Gerando alertas para contrato {analysis.contract_id}")

        alerts_data = []

        # 1. Alertas de vencimento
        if check_expiry and analysis.end_date:
            expiry_alerts = self._generate_expiry_alerts(analysis)
            alerts_data.extend(expiry_alerts)

        # 2. Alertas de renovacao
        if check_renewal and (analysis.renewal_date or analysis.has_auto_renewal):
            renewal_alerts = self._generate_renewal_alerts(analysis)
            alerts_data.extend(renewal_alerts)

        # 3. Alertas de reajuste
        if check_adjustment and analysis.adjustment_date:
            adjustment_alerts = self._generate_adjustment_alerts(analysis)
            alerts_data.extend(adjustment_alerts)

        # 4. Alertas de risco
        if check_risk and analysis.risk_factors:
            risk_alerts = self._generate_risk_alerts(analysis)
            alerts_data.extend(risk_alerts)

        # 5. Alertas de revisao
        if analysis.requires_review:
            review_alert = self._generate_review_alert(analysis)
            alerts_data.append(review_alert)

        # Criar alertas no banco
        created_alerts = []
        if alerts_data:
            created_alerts = self.repository.create_alerts_bulk(alerts_data)
            logger.info(f"Criados {len(created_alerts)} alertas")

        return created_alerts

    def _generate_expiry_alerts(self, analysis: ContractAnalysis) -> list[dict]:
        """Gera alertas de vencimento."""
        alerts = []
        today = date.today()
        end_date = analysis.end_date

        if not end_date or end_date < today:
            return alerts

        days_until = (end_date - today).days
        config = self.ALERT_CONFIGS[AlertType.EXPIRY]

        for days_before in config["days_before"]:
            if days_until <= days_before:
                trigger_date = end_date - timedelta(days=days_before)

                # Nao criar alerta se ja passou
                if trigger_date < today:
                    continue

                priority_str = config["priority_map"].get(days_before, "medium")
                priority = AlertPriority(priority_str)

                alerts.append(
                    {
                        "analysis_id": analysis.id,
                        "contract_id": analysis.contract_id,
                        "contract_number": analysis.contract_number,
                        "alert_type": AlertType.EXPIRY,
                        "priority": priority,
                        "title": f"Contrato vence em {days_before} dias",
                        "description": (
                            f"O contrato {analysis.contract_number or ''} vence em {end_date.strftime('%d/%m/%Y')}"
                        ),
                        "recommendation": ("Avaliar necessidade de renovacao ou encerramento"),
                        "trigger_date": trigger_date,
                        "due_date": end_date - timedelta(days=7),
                        "reference_date": end_date,
                        "days_before": days_before,
                        "days_remaining": days_until,
                    }
                )
                break  # Apenas o alerta mais proximo

        return alerts

    def _generate_renewal_alerts(self, analysis: ContractAnalysis) -> list[dict]:
        """Gera alertas de renovacao."""
        alerts = []
        today = date.today()

        renewal_date = analysis.renewal_date or analysis.end_date
        if not renewal_date or renewal_date < today:
            return alerts

        days_until = (renewal_date - today).days
        config = self.ALERT_CONFIGS[AlertType.RENEWAL]

        for days_before in config["days_before"]:
            if days_until <= days_before:
                trigger_date = renewal_date - timedelta(days=days_before)

                if trigger_date < today:
                    continue

                priority_str = config["priority_map"].get(days_before, "medium")
                priority = AlertPriority(priority_str)

                title = f"Renovacao automatica em {days_before} dias"
                if not analysis.has_auto_renewal:
                    title = f"Prazo para renovacao: {days_before} dias"

                alerts.append(
                    {
                        "analysis_id": analysis.id,
                        "contract_id": analysis.contract_id,
                        "contract_number": analysis.contract_number,
                        "alert_type": AlertType.RENEWAL,
                        "priority": priority,
                        "title": title,
                        "description": (
                            f"Data de renovacao: {renewal_date.strftime('%d/%m/%Y')}. "
                            f"{'Renovacao automatica' if analysis.has_auto_renewal else 'Avaliar renovacao'}"
                        ),
                        "recommendation": (
                            "Revisar termos antes da renovacao automatica"
                            if analysis.has_auto_renewal
                            else "Iniciar processo de renovacao"
                        ),
                        "trigger_date": trigger_date,
                        "due_date": renewal_date - timedelta(days=analysis.notice_period_days or 15),
                        "reference_date": renewal_date,
                        "days_before": days_before,
                        "days_remaining": days_until,
                    }
                )
                break

        return alerts

    def _generate_adjustment_alerts(self, analysis: ContractAnalysis) -> list[dict]:
        """Gera alertas de reajuste."""
        alerts = []
        today = date.today()

        adjustment_date = analysis.adjustment_date
        if not adjustment_date or adjustment_date < today:
            return alerts

        days_until = (adjustment_date - today).days
        config = self.ALERT_CONFIGS[AlertType.ADJUSTMENT]

        for days_before in config["days_before"]:
            if days_until <= days_before:
                trigger_date = adjustment_date - timedelta(days=days_before)

                if trigger_date < today:
                    continue

                priority_str = config["priority_map"].get(days_before, "medium")
                priority = AlertPriority(priority_str)

                alerts.append(
                    {
                        "analysis_id": analysis.id,
                        "contract_id": analysis.contract_id,
                        "contract_number": analysis.contract_number,
                        "alert_type": AlertType.ADJUSTMENT,
                        "priority": priority,
                        "title": f"Reajuste de contrato em {days_before} dias",
                        "description": (
                            f"Reajuste previsto para {adjustment_date.strftime('%d/%m/%Y')}. "
                            f"Indice: {analysis.adjustment_index or 'nao especificado'}"
                        ),
                        "recommendation": "Calcular e comunicar novo valor",
                        "trigger_date": trigger_date,
                        "due_date": adjustment_date,
                        "reference_date": adjustment_date,
                        "days_before": days_before,
                        "days_remaining": days_until,
                    }
                )
                break

        return alerts

    def _generate_risk_alerts(self, analysis: ContractAnalysis) -> list[dict]:
        """Gera alertas de risco."""
        alerts = []

        if not analysis.risk_factors:
            return alerts

        high_risk_factors = [f for f in analysis.risk_factors if f.get("impact") in ("high", "critical")]

        if high_risk_factors:
            priority = AlertPriority.CRITICAL if analysis.risk_score >= 70 else AlertPriority.HIGH

            alerts.append(
                {
                    "analysis_id": analysis.id,
                    "contract_id": analysis.contract_id,
                    "contract_number": analysis.contract_number,
                    "alert_type": AlertType.RISK,
                    "priority": priority,
                    "title": f"Contrato com risco {analysis.risk_level.value}",
                    "description": (
                        f"Identificados {len(high_risk_factors)} fatores de risco. Score: {analysis.risk_score}/100"
                    ),
                    "recommendation": "Revisar clausulas de risco com juridico",
                    "trigger_date": date.today(),
                    "due_date": date.today() + timedelta(days=7),
                    "reference_date": date.today(),
                    "days_before": 0,
                    "days_remaining": 7,
                    "confidence": int(analysis.risk_score),
                }
            )

        return alerts

    def _generate_review_alert(self, analysis: ContractAnalysis) -> dict:
        """Gera alerta de revisao necessaria."""
        return {
            "analysis_id": analysis.id,
            "contract_id": analysis.contract_id,
            "contract_number": analysis.contract_number,
            "alert_type": AlertType.REVIEW,
            "priority": AlertPriority.HIGH,
            "title": "Contrato requer revisao",
            "description": ("A analise automatica identificou que este contrato precisa de revisao manual"),
            "recommendation": "Agendar revisao com equipe juridica",
            "trigger_date": date.today(),
            "due_date": date.today() + timedelta(days=14),
            "reference_date": date.today(),
            "days_before": 0,
            "days_remaining": 14,
        }

    def get_pending_alerts(
        self,
        contract_id: UUID | None = None,
        priority: AlertPriority | None = None,
        alert_type: AlertType | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        Lista alertas pendentes.

        Returns:
            Dict com alertas e contagens
        """
        alerts, total = self.repository.get_alerts(
            contract_id=contract_id,
            status=AlertStatus.PENDING,
            priority=priority,
            alert_type=alert_type,
            is_active=True,
            page=page,
            page_size=page_size,
        )

        # Contar por prioridade
        urgent_count = len([a for a in alerts if a.priority in (AlertPriority.URGENT, AlertPriority.CRITICAL)])
        overdue_count = len([a for a in alerts if a.is_overdue])

        return {
            "items": alerts,
            "total": total,
            "pending_count": total,
            "urgent_count": urgent_count,
            "overdue_count": overdue_count,
        }

    def acknowledge_alert(
        self,
        alert_id: UUID,
        user_id: UUID,
    ) -> ContractAlert | None:
        """Reconhece um alerta."""
        alert = self.repository.get_alert(alert_id)
        if not alert:
            return None

        alert.acknowledge(user_id)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def resolve_alert(
        self,
        alert_id: UUID,
        user_id: UUID,
        notes: str | None = None,
    ) -> ContractAlert | None:
        """Resolve um alerta."""
        return self.repository.resolve_alert(alert_id, user_id, notes)

    def snooze_alert(
        self,
        alert_id: UUID,
        days: int = 7,
    ) -> ContractAlert | None:
        """Adia um alerta."""
        alert = self.repository.get_alert(alert_id)
        if not alert:
            return None

        alert.is_snoozed = True
        alert.snooze_until = datetime.utcnow() + timedelta(days=days)
        alert.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(alert)
        return alert

    def dismiss_alert(
        self,
        alert_id: UUID,
        user_id: UUID,
        reason: str | None = None,
    ) -> ContractAlert | None:
        """Dispensa um alerta."""
        alert = self.repository.get_alert(alert_id)
        if not alert:
            return None

        alert.status = AlertStatus.DISMISSED
        alert.resolved_by = user_id
        alert.resolved_at = datetime.utcnow()
        alert.resolution_notes = reason or "Dispensado pelo usuario"
        alert.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(alert)
        return alert

    def get_alerts_summary(self) -> dict:
        """Retorna resumo de alertas."""
        pending = self.repository.get_pending_alerts_count()

        # Buscar todos os alertas pendentes para contagem
        alerts, _ = self.repository.get_alerts(
            status=AlertStatus.PENDING,
            is_active=True,
            page_size=1000,
        )

        by_type = {}
        by_priority = {}
        overdue = 0

        for alert in alerts:
            # Por tipo
            type_key = alert.alert_type.value
            by_type[type_key] = by_type.get(type_key, 0) + 1

            # Por prioridade
            priority_key = alert.priority.value
            by_priority[priority_key] = by_priority.get(priority_key, 0) + 1

            # Atrasados
            if alert.is_overdue:
                overdue += 1

        return {
            "total_pending": pending,
            "overdue": overdue,
            "by_type": by_type,
            "by_priority": by_priority,
            "urgent_and_critical": by_priority.get("urgent", 0) + by_priority.get("critical", 0),
        }
