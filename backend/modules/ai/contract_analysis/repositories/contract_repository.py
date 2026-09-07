"""
Contract Analysis Repository - AI Contract Analysis

Repository para acesso a dados de analise de contratos.
"""

import logging
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from modules.ai.contract_analysis.models.contract_alert import (
    AlertPriority,
    AlertStatus,
    AlertType,
    ContractAlert,
)
from modules.ai.contract_analysis.models.contract_analysis import (
    AnalysisStatus,
    ContractAnalysis,
    ContractType,
    RiskLevel,
)
from modules.ai.contract_analysis.models.extracted_clause import (
    ClauseImportance,
    ClauseType,
    ExtractedClause,
)

logger = logging.getLogger(__name__)


class ContractAnalysisRepository:
    """Repository para analises de contratos."""

    def __init__(self, db: Session):
        """Inicializa repository."""
        self.db = db

    # ============================================================
    # Contract Analysis CRUD
    # ============================================================

    def create_analysis(self, data: dict) -> ContractAnalysis:
        """Cria nova analise."""
        analysis = ContractAnalysis(**data)
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        logger.info(f"Analise criada: {analysis.id}")
        return analysis

    def get_analysis(
        self,
        analysis_id: UUID,
        include_clauses: bool = False,
        include_alerts: bool = False,
    ) -> ContractAnalysis | None:
        """Busca analise por ID."""
        query = self.db.query(ContractAnalysis).filter(ContractAnalysis.id == analysis_id)

        if include_clauses:
            query = query.options(joinedload(ContractAnalysis.clauses))

        if include_alerts:
            query = query.options(joinedload(ContractAnalysis.alerts))

        return query.first()

    def get_analysis_by_contract(
        self,
        contract_id: UUID,
        latest_only: bool = True,
    ) -> ContractAnalysis | None:
        """Busca analise por ID do contrato."""
        query = self.db.query(ContractAnalysis).filter(
            ContractAnalysis.contract_id == contract_id,
            ContractAnalysis.is_active,
        )

        if latest_only:
            query = query.filter(ContractAnalysis.is_latest)

        return query.order_by(desc(ContractAnalysis.created_at)).first()

    def get_analyses(
        self,
        status: AnalysisStatus | None = None,
        contract_type: ContractType | None = None,
        risk_level: RiskLevel | None = None,
        expiring_in_days: int | None = None,
        requires_review: bool | None = None,
        is_active: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ContractAnalysis], int]:
        """Lista analises com filtros."""
        query = self.db.query(ContractAnalysis)

        if is_active is not None:
            query = query.filter(ContractAnalysis.is_active == is_active)

        if status:
            query = query.filter(ContractAnalysis.status == status)

        if contract_type:
            query = query.filter(ContractAnalysis.contract_type == contract_type)

        if risk_level:
            query = query.filter(ContractAnalysis.risk_level == risk_level)

        if expiring_in_days:
            expiry_date = date.today() + timedelta(days=expiring_in_days)
            query = query.filter(
                and_(
                    ContractAnalysis.end_date is not None,
                    ContractAnalysis.end_date <= expiry_date,
                    ContractAnalysis.end_date >= date.today(),
                )
            )

        if requires_review is not None:
            query = query.filter(ContractAnalysis.requires_review == requires_review)

        total = query.count()
        items = query.order_by(desc(ContractAnalysis.created_at)).offset((page - 1) * page_size).limit(page_size).all()

        return items, total

    def update_analysis(self, analysis_id: UUID, data: dict) -> ContractAnalysis | None:
        """Atualiza analise."""
        analysis = self.get_analysis(analysis_id)
        if not analysis:
            return None

        for key, value in data.items():
            if hasattr(analysis, key):
                setattr(analysis, key, value)

        analysis.updated_at = datetime.utcnow()

        if data.get("status") == AnalysisStatus.COMPLETED:
            analysis.completed_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    def delete_analysis(self, analysis_id: UUID) -> bool:
        """Deleta analise (soft delete)."""
        analysis = self.get_analysis(analysis_id)
        if not analysis:
            return False

        analysis.is_active = False
        analysis.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    # ============================================================
    # Extracted Clauses
    # ============================================================

    def add_clauses(self, analysis_id: UUID, clauses: list[dict]) -> list[ExtractedClause]:
        """Adiciona clausulas a analise."""
        extracted = []
        for clause_data in clauses:
            clause = ExtractedClause(analysis_id=analysis_id, **clause_data)
            self.db.add(clause)
            extracted.append(clause)

        self.db.commit()
        return extracted

    def get_clauses(
        self,
        analysis_id: UUID,
        clause_type: ClauseType | None = None,
        importance: ClauseImportance | None = None,
        is_risky: bool | None = None,
    ) -> list[ExtractedClause]:
        """Busca clausulas de uma analise."""
        query = self.db.query(ExtractedClause).filter(ExtractedClause.analysis_id == analysis_id)

        if clause_type:
            query = query.filter(ExtractedClause.clause_type == clause_type)

        if importance:
            query = query.filter(ExtractedClause.importance == importance)

        if is_risky is not None:
            query = query.filter(ExtractedClause.is_risky == is_risky)

        return query.order_by(ExtractedClause.page_number, ExtractedClause.start_position).all()

    def get_clause(self, clause_id: UUID) -> ExtractedClause | None:
        """Busca clausula por ID."""
        return self.db.query(ExtractedClause).filter(ExtractedClause.id == clause_id).first()

    def update_clause(self, clause_id: UUID, data: dict) -> ExtractedClause | None:
        """Atualiza clausula."""
        clause = self.get_clause(clause_id)
        if not clause:
            return None

        for key, value in data.items():
            if hasattr(clause, key):
                setattr(clause, key, value)

        clause.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(clause)
        return clause

    # ============================================================
    # Contract Alerts
    # ============================================================

    def create_alert(self, data: dict) -> ContractAlert:
        """Cria novo alerta."""
        alert = ContractAlert(**data)
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def create_alerts_bulk(self, alerts: list[dict]) -> list[ContractAlert]:
        """Cria alertas em lote."""
        created = []
        for alert_data in alerts:
            alert = ContractAlert(**alert_data)
            self.db.add(alert)
            created.append(alert)

        self.db.commit()
        return created

    def get_alert(self, alert_id: UUID) -> ContractAlert | None:
        """Busca alerta por ID."""
        return self.db.query(ContractAlert).filter(ContractAlert.id == alert_id).first()

    def get_alerts(
        self,
        contract_id: UUID | None = None,
        analysis_id: UUID | None = None,
        alert_type: AlertType | None = None,
        status: AlertStatus | None = None,
        priority: AlertPriority | None = None,
        is_active: bool = True,
        is_overdue: bool | None = None,
        assigned_to: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ContractAlert], int]:
        """Lista alertas com filtros."""
        query = self.db.query(ContractAlert)

        if is_active is not None:
            query = query.filter(ContractAlert.is_active == is_active)

        if contract_id:
            query = query.filter(ContractAlert.contract_id == contract_id)

        if analysis_id:
            query = query.filter(ContractAlert.analysis_id == analysis_id)

        if alert_type:
            query = query.filter(ContractAlert.alert_type == alert_type)

        if status:
            query = query.filter(ContractAlert.status == status)

        if priority:
            query = query.filter(ContractAlert.priority == priority)

        if assigned_to:
            query = query.filter(ContractAlert.assigned_to == assigned_to)

        if is_overdue is not None:
            if is_overdue:
                query = query.filter(
                    and_(
                        ContractAlert.due_date is not None,
                        ContractAlert.due_date < date.today(),
                        ContractAlert.status.in_(
                            [
                                AlertStatus.PENDING,
                                AlertStatus.ACKNOWLEDGED,
                                AlertStatus.IN_PROGRESS,
                            ]
                        ),
                    )
                )
            else:
                query = query.filter(
                    or_(
                        ContractAlert.due_date is None,
                        ContractAlert.due_date >= date.today(),
                    )
                )

        total = query.count()
        items = (
            query.order_by(
                desc(ContractAlert.priority),
                ContractAlert.trigger_date,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return items, total

    def update_alert(self, alert_id: UUID, data: dict) -> ContractAlert | None:
        """Atualiza alerta."""
        alert = self.get_alert(alert_id)
        if not alert:
            return None

        for key, value in data.items():
            if hasattr(alert, key):
                setattr(alert, key, value)

        alert.updated_at = datetime.utcnow()
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
        alert = self.get_alert(alert_id)
        if not alert:
            return None

        alert.resolve(user_id, notes)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def get_pending_alerts_count(self, contract_id: UUID | None = None) -> int:
        """Conta alertas pendentes."""
        query = self.db.query(func.count(ContractAlert.id)).filter(
            ContractAlert.is_active,
            ContractAlert.status.in_(
                [
                    AlertStatus.PENDING,
                    AlertStatus.ACKNOWLEDGED,
                ]
            ),
        )

        if contract_id:
            query = query.filter(ContractAlert.contract_id == contract_id)

        return query.scalar() or 0

    # ============================================================
    # Analytics
    # ============================================================

    def get_contracts_by_risk(self) -> dict:
        """Conta contratos por nivel de risco."""
        results = (
            self.db.query(
                ContractAnalysis.risk_level,
                func.count(ContractAnalysis.id).label("count"),
            )
            .filter(
                ContractAnalysis.is_active,
                ContractAnalysis.is_latest,
            )
            .group_by(ContractAnalysis.risk_level)
            .all()
        )

        return {str(r.risk_level.value): r.count for r in results}

    def get_contracts_by_type(self) -> dict:
        """Conta contratos por tipo."""
        results = (
            self.db.query(
                ContractAnalysis.contract_type,
                func.count(ContractAnalysis.id).label("count"),
            )
            .filter(
                ContractAnalysis.is_active,
                ContractAnalysis.is_latest,
            )
            .group_by(ContractAnalysis.contract_type)
            .all()
        )

        return {str(r.contract_type.value): r.count for r in results}

    def get_expiring_contracts(self, days: int = 30) -> list[ContractAnalysis]:
        """Busca contratos expirando em X dias."""
        expiry_date = date.today() + timedelta(days=days)

        return (
            self.db.query(ContractAnalysis)
            .filter(
                ContractAnalysis.is_active,
                ContractAnalysis.is_latest,
                ContractAnalysis.end_date is not None,
                ContractAnalysis.end_date <= expiry_date,
                ContractAnalysis.end_date >= date.today(),
            )
            .order_by(ContractAnalysis.end_date)
            .all()
        )

    def get_average_scores(self) -> dict:
        """Calcula scores medios."""
        result = (
            self.db.query(
                func.avg(ContractAnalysis.risk_score).label("avg_risk"),
                func.avg(ContractAnalysis.compliance_score).label("avg_compliance"),
            )
            .filter(
                ContractAnalysis.is_active,
                ContractAnalysis.status == AnalysisStatus.COMPLETED,
            )
            .first()
        )

        return {
            "average_risk_score": round(float(result.avg_risk or 0), 1),
            "average_compliance_score": round(float(result.avg_compliance or 0), 1),
        }

    def get_clause_statistics(self, analysis_id: UUID) -> dict:
        """Estatisticas de clausulas de uma analise."""
        results = (
            self.db.query(
                ExtractedClause.clause_type,
                func.count(ExtractedClause.id).label("count"),
            )
            .filter(ExtractedClause.analysis_id == analysis_id)
            .group_by(ExtractedClause.clause_type)
            .all()
        )

        return {str(r.clause_type.value): r.count for r in results}
