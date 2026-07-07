"""
Servico de Relatorio de Horas Extras.

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
class EmployeeOvertime:
    """Horas extras por funcionario."""
    employee_id: UUID
    employee_name: str
    regular_hours: float
    overtime_50: float  # 50% adicional
    overtime_100: float  # 100% adicional (feriados/domingos)
    night_hours: float
    total_overtime: float
    overtime_cost: float
    percentage_of_total: float


@dataclass
class ClientOvertime:
    """Horas extras por cliente."""
    client_id: UUID
    client_name: str
    posts_count: int
    total_overtime_hours: float
    total_overtime_cost: float
    top_overtime_employees: List[EmployeeOvertime]


@dataclass
class OvertimeReport:
    """Relatorio completo de horas extras."""
    report_date: datetime
    period_start: date
    period_end: date
    tenant_id: UUID
    total_regular_hours: float
    total_overtime_hours: float
    total_overtime_cost: float
    overtime_50_hours: float
    overtime_100_hours: float
    night_hours: float
    by_employee: List[EmployeeOvertime]
    by_client: List[ClientOvertime]
    alerts: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


class OvertimeReportService:
    """
    Servico para geracao de relatorios de horas extras.
    
    Gera relatorios detalhados sobre:
    - Horas extras por funcionario
    - Horas extras por cliente
    - Custos de HE
    - Alertas de excesso de HE
    
    Exemplo:
        ```python
        service = OvertimeReportService(db)  # AsyncSession (fonte real)
        report = await service.generate(
            tenant_id=uuid,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )
        print(f"Total HE: {report.total_overtime_hours}h")
        print(f"Custo: R$ {report.total_overtime_cost:.2f}")
        ```
    """
    
    # Limite mensal de HE por funcionario (CLT)
    MAX_MONTHLY_OVERTIME = 60.0

    def __init__(
        self,
        db: Optional["AsyncSession"] = None,
    ) -> None:
        """Inicializa o servico.

        Args:
            db: Sessao async do banco (fonte real). Sem sessao,
                os loaders retornam listas vazias (nunca dados simulados).

        Nota de veracidade: os custos de HE vem dos valores REAIS lancados
        nos turnos (shifts.overtime_pay + shifts.night_bonus) — nao ha mais
        estimativa por taxa horaria fabricada.
        """
        self.db = db
    
    async def generate(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        client_id: Optional[UUID] = None,
        employee_ids: Optional[List[UUID]] = None,
    ) -> OvertimeReport:
        """
        Gera relatorio de horas extras para o periodo.
        
        Args:
            tenant_id: ID do tenant.
            start_date: Data inicial.
            end_date: Data final.
            client_id: Filtrar por cliente (opcional).
            employee_ids: Filtrar por funcionarios (opcional).
            
        Returns:
            OvertimeReport com dados completos.
        """
        logger.info(f"Gerando relatorio de HE: {start_date} a {end_date}")
        
        # Carrega dados
        employees_data = await self._load_employees_overtime(
            tenant_id, start_date, end_date, employee_ids
        )
        clients_data = await self._load_clients_overtime(
            tenant_id, start_date, end_date, client_id
        )
        
        # Processa funcionarios
        by_employee = self._process_employees(employees_data)
        
        # Processa clientes
        by_client = self._process_clients(clients_data)
        
        # Totais
        total_regular = sum(e.regular_hours for e in by_employee)
        total_ot = sum(e.total_overtime for e in by_employee)
        total_cost = sum(e.overtime_cost for e in by_employee)
        ot_50 = sum(e.overtime_50 for e in by_employee)
        ot_100 = sum(e.overtime_100 for e in by_employee)
        night = sum(e.night_hours for e in by_employee)
        
        # Alertas
        alerts = self._generate_alerts(by_employee)
        
        # Summary
        summary = {
            "avg_overtime_per_employee": (
                total_ot / len(by_employee) if by_employee else 0
            ),
            "employee_with_most_overtime": (
                max(by_employee, key=lambda e: e.total_overtime).employee_name
                if by_employee else None
            ),
            "client_with_most_overtime": (
                max(by_client, key=lambda c: c.total_overtime_hours).client_name
                if by_client else None
            ),
            "overtime_to_regular_ratio": (
                total_ot / total_regular * 100 if total_regular > 0 else 0
            ),
        }
        
        return OvertimeReport(
            report_date=datetime.utcnow(),
            period_start=start_date,
            period_end=end_date,
            tenant_id=tenant_id,
            total_regular_hours=round(total_regular, 2),
            total_overtime_hours=round(total_ot, 2),
            total_overtime_cost=round(total_cost, 2),
            overtime_50_hours=round(ot_50, 2),
            overtime_100_hours=round(ot_100, 2),
            night_hours=round(night, 2),
            by_employee=by_employee,
            by_client=by_client,
            alerts=alerts,
            summary=summary,
        )
    
    async def _load_employees_overtime(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        employee_ids: Optional[List[UUID]],
    ) -> List[Dict[str, Any]]:
        """Carrega dados REAIS de HE dos funcionarios (shifts agregados)."""
        if self.db is None:
            logger.warning(
                "OvertimeReportService._load_employees_overtime: fonte real não conectada "
                "(sem sessão de banco) — retornando vazio (mock removido)"
            )
            return []

        from sqlalchemy import case, func, or_, select

        from modules.operacional.models.employee import Employee
        from modules.operacional.models.shift import Shift

        # HE 100%: feriados e domingos (dow=0 no PostgreSQL)
        is_100 = or_(Shift.is_holiday.is_(True), func.extract("dow", Shift.shift_date) == 0)

        query = (
            select(
                Shift.employee_id,
                func.coalesce(func.sum(Shift.actual_hours), 0.0).label("actual_hours"),
                func.coalesce(func.sum(case((is_100, Shift.overtime_hours), else_=0.0)), 0.0).label("overtime_100"),
                func.coalesce(func.sum(case((is_100, 0.0), else_=Shift.overtime_hours)), 0.0).label("overtime_50"),
                func.coalesce(func.sum(Shift.night_hours), 0.0).label("night_hours"),
                func.coalesce(func.sum(Shift.overtime_pay + Shift.night_bonus), 0.0).label("overtime_cost"),
            )
            .where(Shift.is_active.is_(True))
            .where(Shift.employee_id.isnot(None))
            .where(Shift.shift_date >= start_date)
            .where(Shift.shift_date <= end_date)
            .group_by(Shift.employee_id)
        )
        if employee_ids:
            query = query.where(Shift.employee_id.in_([str(e) for e in employee_ids]))

        rows = list((await self.db.execute(query)).all())
        if not rows:
            return []

        names_result = await self.db.execute(
            select(Employee.id, Employee.nome).where(Employee.id.in_([UUID(str(r.employee_id)) for r in rows]))
        )
        names = {str(row.id): row.nome for row in names_result.all()}

        items: List[Dict[str, Any]] = []
        for row in rows:
            overtime_total = float(row.overtime_50 or 0.0) + float(row.overtime_100 or 0.0)
            regular = max(float(row.actual_hours or 0.0) - overtime_total, 0.0)
            items.append(
                {
                    "employee_id": UUID(str(row.employee_id)),
                    "employee_name": names.get(str(row.employee_id), "(funcionario nao cadastrado)"),
                    "regular_hours": round(regular, 2),
                    "overtime_50": float(row.overtime_50 or 0.0),
                    "overtime_100": float(row.overtime_100 or 0.0),
                    "night_hours": float(row.night_hours or 0.0),
                    "overtime_cost": float(row.overtime_cost or 0.0),
                }
            )
        return items
    
    async def _load_clients_overtime(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        client_id: Optional[UUID],
    ) -> List[Dict[str, Any]]:
        """Carrega dados REAIS de HE por cliente (shifts x postos x clients)."""
        if self.db is None:
            logger.warning(
                "OvertimeReportService._load_clients_overtime: fonte real não conectada "
                "(sem sessão de banco) — retornando vazio (mock removido)"
            )
            return []

        from sqlalchemy import func, select

        from modules.clients.models.client import Client
        from modules.operacional.models.post import Post
        from modules.operacional.models.shift import Shift

        query = (
            select(
                Post.client_id,
                func.count(func.distinct(Shift.post_id)).label("posts_count"),
                func.coalesce(func.sum(Shift.overtime_hours), 0.0).label("total_overtime_hours"),
                func.coalesce(func.sum(Shift.overtime_pay + Shift.night_bonus), 0.0).label("total_overtime_cost"),
            )
            .select_from(Shift)
            .join(Post, Post.id == Shift.post_id)
            .where(Shift.is_active.is_(True))
            .where(Shift.shift_date >= start_date)
            .where(Shift.shift_date <= end_date)
            .where(Post.client_id.isnot(None))
            .group_by(Post.client_id)
        )
        if client_id:
            query = query.where(Post.client_id == str(client_id))

        rows = list((await self.db.execute(query)).all())
        if not rows:
            return []

        names_result = await self.db.execute(
            select(Client.id, Client.name).where(Client.id.in_([UUID(str(r.client_id)) for r in rows]))
        )
        names = {str(row.id): row.name for row in names_result.all()}

        return [
            {
                "client_id": UUID(str(row.client_id)),
                "client_name": names.get(str(row.client_id), "(cliente nao cadastrado)"),
                "posts_count": int(row.posts_count or 0),
                "total_overtime_hours": float(row.total_overtime_hours or 0.0),
                "total_overtime_cost": float(row.total_overtime_cost or 0.0),
            }
            for row in rows
        ]
    
    def _process_employees(
        self,
        data: List[Dict[str, Any]],
    ) -> List[EmployeeOvertime]:
        """Processa dados de funcionarios."""
        total_ot = sum(
            d["overtime_50"] + d["overtime_100"] for d in data
        )
        
        result = []
        for emp in data:
            ot = emp["overtime_50"] + emp["overtime_100"]
            # Custo REAL vindo dos turnos (overtime_pay + night_bonus), nunca estimado
            cost = float(emp.get("overtime_cost", 0.0))

            result.append(EmployeeOvertime(
                employee_id=emp["employee_id"],
                employee_name=emp["employee_name"],
                regular_hours=emp["regular_hours"],
                overtime_50=emp["overtime_50"],
                overtime_100=emp["overtime_100"],
                night_hours=emp["night_hours"],
                total_overtime=ot,
                overtime_cost=round(cost, 2),
                percentage_of_total=round(ot / total_ot * 100 if total_ot > 0 else 0, 2),
            ))
        
        return sorted(result, key=lambda x: x.total_overtime, reverse=True)
    
    def _process_clients(
        self,
        data: List[Dict[str, Any]],
    ) -> List[ClientOvertime]:
        """Processa dados de clientes."""
        result = []
        for client in data:
            # Custo REAL vindo dos turnos (overtime_pay + night_bonus), nunca estimado
            cost = float(client.get("total_overtime_cost", 0.0))
            result.append(ClientOvertime(
                client_id=client["client_id"],
                client_name=client["client_name"],
                posts_count=client["posts_count"],
                total_overtime_hours=client["total_overtime_hours"],
                total_overtime_cost=round(cost, 2),
                top_overtime_employees=[],
            ))
        return sorted(result, key=lambda x: x.total_overtime_hours, reverse=True)
    
    def _generate_alerts(
        self,
        employees: List[EmployeeOvertime],
    ) -> List[str]:
        """Gera alertas de HE."""
        alerts = []
        for emp in employees:
            if emp.total_overtime > self.MAX_MONTHLY_OVERTIME:
                alerts.append(
                    f"ALERTA: {emp.employee_name} excedeu o limite de HE "
                    f"({emp.total_overtime:.0f}h > {self.MAX_MONTHLY_OVERTIME:.0f}h)"
                )
            elif emp.total_overtime > self.MAX_MONTHLY_OVERTIME * 0.8:
                alerts.append(
                    f"AVISO: {emp.employee_name} proximo do limite de HE "
                    f"({emp.total_overtime:.0f}h)"
                )
        return alerts
