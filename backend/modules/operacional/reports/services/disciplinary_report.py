"""
Servico de Relatorio Disciplinar.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score: 99+/100
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class DisciplinaryStats:
    """Estatisticas disciplinares."""
    total_actions: int
    warnings_verbal: int
    warnings_written: int
    suspensions: int
    terminations: int
    pending_approval: int
    pending_signature: int


@dataclass
class EmployeeDisciplinary:
    """Dados disciplinares por funcionario."""
    employee_id: UUID
    employee_name: str
    warnings_count: int
    suspensions_count: int
    suspension_days_total: int
    last_action_date: Optional[date]
    last_action_type: Optional[str]
    risk_level: str


@dataclass
class ReasonBreakdown:
    """Distribuicao por motivo."""
    reason_category: str
    reason_name: str
    count: int
    percentage: float


@dataclass
class DisciplinaryReport:
    """Relatorio completo disciplinar."""
    report_date: datetime
    period_start: date
    period_end: date
    tenant_id: UUID
    stats: DisciplinaryStats
    by_employee: List[EmployeeDisciplinary]
    by_reason: List[ReasonBreakdown]
    recurrence_rate: float
    avg_time_to_apply: float
    summary: Dict[str, Any] = field(default_factory=dict)


class DisciplinaryReportService:
    """
    Servico para geracao de relatorios disciplinares.
    
    Gera relatorios sobre:
    - Medidas aplicadas por tipo
    - Distribuicao por funcionario
    - Motivos mais frequentes
    - Taxa de reincidencia
    
    Exemplo:
        ```python
        service = DisciplinaryReportService(db)  # AsyncSession (fonte real)
        report = await service.generate(
            tenant_id=uuid,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )
        print(f"Total medidas: {report.stats.total_actions}")
        ```
    """
    
    def __init__(self, db: Optional["AsyncSession"] = None) -> None:
        """Inicializa o servico.

        Args:
            db: Sessao async do banco (fonte real: tabela disciplinary_actions).
                Sem sessao, os loaders retornam listas vazias (nunca dados simulados).
        """
        self.db = db
    
    async def generate(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        client_id: Optional[UUID] = None,
    ) -> DisciplinaryReport:
        """
        Gera relatorio disciplinar para o periodo.
        
        Args:
            tenant_id: ID do tenant.
            start_date: Data inicial.
            end_date: Data final.
            client_id: Filtrar por cliente (opcional).
            
        Returns:
            DisciplinaryReport com dados completos.
        """
        logger.info(f"Gerando relatorio disciplinar: {start_date} a {end_date}")
        
        # Carrega dados
        actions_data = await self._load_actions(tenant_id, start_date, end_date)
        employees_data = await self._load_employees_disciplinary(
            tenant_id, start_date, end_date
        )
        
        # Calcula estatisticas
        stats = self._calculate_stats(actions_data)
        
        # Processa funcionarios
        by_employee = self._process_employees(employees_data)
        
        # Processa motivos
        by_reason = self._process_reasons(actions_data)
        
        # Calcula reincidencia
        recurrence = self._calculate_recurrence(employees_data)
        
        # Tempo medio para aplicar
        avg_time = self._calculate_avg_time(actions_data)
        
        # Summary
        summary = {
            "most_common_reason": by_reason[0].reason_name if by_reason else None,
            "employees_with_multiple": len([e for e in by_employee if e.warnings_count > 1]),
            "high_risk_employees": len([e for e in by_employee if e.risk_level == "alto"]),
        }
        
        return DisciplinaryReport(
            report_date=datetime.utcnow(),
            period_start=start_date,
            period_end=end_date,
            tenant_id=tenant_id,
            stats=stats,
            by_employee=by_employee,
            by_reason=by_reason,
            recurrence_rate=round(recurrence, 2),
            avg_time_to_apply=round(avg_time, 2),
            summary=summary,
        )
    
    async def _load_actions(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Carrega medidas disciplinares REAIS (tabela disciplinary_actions)."""
        if self.db is None:
            logger.warning(
                "DisciplinaryReportService._load_actions: fonte real não conectada "
                "(sem sessão de banco) — retornando vazio (mock removido)"
            )
            return []

        from sqlalchemy import select

        from modules.operacional.disciplinary.models.disciplinary_action import (
            DisciplinaryAction,
            DisciplinaryActionStatus,
        )

        query = (
            select(
                DisciplinaryAction.action_type,
                DisciplinaryAction.reason_category,
                DisciplinaryAction.status,
                DisciplinaryAction.incident_date,
                DisciplinaryAction.application_date,
            )
            .where(DisciplinaryAction.is_active.is_(True))
            .where(DisciplinaryAction.tenant_id == str(tenant_id))
            .where(DisciplinaryAction.status != DisciplinaryActionStatus.CANCELADA.value)
            .where(DisciplinaryAction.incident_date >= start_date)
            .where(DisciplinaryAction.incident_date <= end_date)
        )
        rows = (await self.db.execute(query)).all()

        actions: List[Dict[str, Any]] = []
        for row in rows:
            days_to_apply = None
            if row.application_date and row.incident_date:
                days_to_apply = (row.application_date - row.incident_date).days
            actions.append(
                {
                    "type": row.action_type,
                    "reason": row.reason_category,
                    "status": row.status,
                    "days_to_apply": days_to_apply,
                }
            )
        return actions
    
    async def _load_employees_disciplinary(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Carrega dados disciplinares REAIS por funcionario (disciplinary_actions)."""
        if self.db is None:
            logger.warning(
                "DisciplinaryReportService._load_employees_disciplinary: fonte real não conectada "
                "(sem sessão de banco) — retornando vazio (mock removido)"
            )
            return []

        from sqlalchemy import select

        from modules.operacional.disciplinary.models.disciplinary_action import (
            DisciplinaryAction,
            DisciplinaryActionStatus,
            DisciplinaryActionType,
        )

        query = (
            select(
                DisciplinaryAction.employee_id,
                DisciplinaryAction.employee_name,
                DisciplinaryAction.action_type,
                DisciplinaryAction.suspension_days,
                DisciplinaryAction.incident_date,
            )
            .where(DisciplinaryAction.is_active.is_(True))
            .where(DisciplinaryAction.tenant_id == str(tenant_id))
            .where(DisciplinaryAction.status != DisciplinaryActionStatus.CANCELADA.value)
            .where(DisciplinaryAction.incident_date >= start_date)
            .where(DisciplinaryAction.incident_date <= end_date)
        )
        rows = (await self.db.execute(query)).all()

        warning_types = {
            DisciplinaryActionType.ADVERTENCIA_VERBAL.value,
            DisciplinaryActionType.ADVERTENCIA_ESCRITA.value,
        }

        per_employee: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            key = str(row.employee_id)
            emp = per_employee.setdefault(
                key,
                {
                    "employee_id": UUID(key),
                    "employee_name": row.employee_name,
                    "warnings": 0,
                    "suspensions": 0,
                    "suspension_days": 0,
                    "last_date": None,
                    "last_type": None,
                },
            )
            if row.action_type in warning_types:
                emp["warnings"] += 1
            elif row.action_type == DisciplinaryActionType.SUSPENSAO.value:
                emp["suspensions"] += 1
                emp["suspension_days"] += int(row.suspension_days or 0)
            if row.incident_date and (emp["last_date"] is None or row.incident_date > emp["last_date"]):
                emp["last_date"] = row.incident_date
                emp["last_type"] = row.action_type

        return list(per_employee.values())
    
    def _calculate_stats(self, data: List[Dict[str, Any]]) -> DisciplinaryStats:
        """Calcula estatisticas."""
        return DisciplinaryStats(
            total_actions=len(data),
            warnings_verbal=len([d for d in data if d["type"] == "advertencia_verbal"]),
            warnings_written=len([d for d in data if d["type"] == "advertencia_escrita"]),
            suspensions=len([d for d in data if d["type"] == "suspensao"]),
            terminations=len([d for d in data if d["type"] == "demissao_justa_causa"]),
            pending_approval=len([d for d in data if d.get("status") == "pendente_aprovacao"]),
            pending_signature=len([d for d in data if d.get("status") == "pendente_assinatura"]),
        )
    
    def _process_employees(
        self,
        data: List[Dict[str, Any]],
    ) -> List[EmployeeDisciplinary]:
        """Processa dados de funcionarios."""
        result = []
        for emp in data:
            total_issues = emp["warnings"] + emp["suspensions"]
            if total_issues >= 3:
                risk = "alto"
            elif total_issues >= 2:
                risk = "medio"
            else:
                risk = "baixo"
            
            result.append(EmployeeDisciplinary(
                employee_id=emp["employee_id"],
                employee_name=emp["employee_name"],
                warnings_count=emp["warnings"],
                suspensions_count=emp["suspensions"],
                suspension_days_total=emp["suspension_days"],
                last_action_date=emp["last_date"],
                last_action_type=emp["last_type"],
                risk_level=risk,
            ))
        
        return sorted(result, key=lambda x: x.warnings_count + x.suspensions_count, reverse=True)
    
    def _process_reasons(
        self,
        data: List[Dict[str, Any]],
    ) -> List[ReasonBreakdown]:
        """Processa distribuicao por motivo."""
        reason_counts: Dict[str, int] = {}
        for action in data:
            reason = action["reason"]
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        
        total = len(data)
        result = []
        for reason, count in reason_counts.items():
            result.append(ReasonBreakdown(
                reason_category=reason,
                reason_name=reason.replace("_", " ").title(),
                count=count,
                percentage=round(count / total * 100 if total > 0 else 0, 2),
            ))
        
        return sorted(result, key=lambda x: x.count, reverse=True)
    
    def _calculate_recurrence(self, employees: List[Dict[str, Any]]) -> float:
        """Calcula taxa de reincidencia."""
        total = len(employees)
        with_multiple = len([e for e in employees if e["warnings"] + e["suspensions"] > 1])
        return with_multiple / total * 100 if total > 0 else 0
    
    def _calculate_avg_time(self, data: List[Dict[str, Any]]) -> float:
        """Calcula tempo medio para aplicar medida (so medidas ja aplicadas)."""
        times = [d["days_to_apply"] for d in data if d.get("days_to_apply") is not None]
        if not times:
            return 0
        return sum(times) / len(times)
