"""Repository para TimeSheet."""

import builtins
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.time_tracking.models import TimeSheet, TimeSheetStatus
from modules.hr.time_tracking.schemas import (
    TimeSheetCreate,
    TimeSheetFilter,
    TimeSheetUpdate,
)


class TimeSheetRepository:
    """Repository para operações de TimeSheet."""

    def __init__(self, db: AsyncSession):
        """Inicializa o repository."""
        self.db = db

    async def create(
        self,
        data: TimeSheetCreate,
        created_by_id: str = None,
    ) -> TimeSheet:
        """Cria uma nova folha de ponto."""
        sheet = TimeSheet(
            **data.model_dump(exclude_unset=True),
            created_by_id=created_by_id,
        )
        self.db.add(sheet)
        await self.db.flush()
        await self.db.refresh(sheet)
        return sheet

    async def get_by_id(self, sheet_id: UUID) -> TimeSheet | None:
        """Busca folha por ID."""
        result = await self.db.execute(
            select(TimeSheet).where(
                TimeSheet.id == sheet_id,
                TimeSheet.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> TimeSheet | None:
        """Busca folha por código."""
        result = await self.db.execute(
            select(TimeSheet).where(
                TimeSheet.code == code,
                TimeSheet.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_employee_month(
        self,
        employee_id: str,
        reference_month: int,
        reference_year: int,
    ) -> TimeSheet | None:
        """Busca folha de um funcionário em um mês específico."""
        result = await self.db.execute(
            select(TimeSheet).where(
                TimeSheet.employee_id == employee_id,
                TimeSheet.reference_month == reference_month,
                TimeSheet.reference_year == reference_year,
                TimeSheet.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        sheet: TimeSheet,
        data: TimeSheetUpdate,
    ) -> TimeSheet:
        """Atualiza uma folha de ponto."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(sheet, field, value)
        await self.db.flush()
        await self.db.refresh(sheet)
        return sheet

    async def delete(self, sheet: TimeSheet) -> None:
        """Soft delete de uma folha de ponto."""
        sheet.soft_delete()
        await self.db.flush()

    async def list(
        self,
        filters: TimeSheetFilter = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[TimeSheet], int]:
        """Lista folhas de ponto com filtros."""
        query = select(TimeSheet).where(TimeSheet.is_deleted.is_(False))

        if filters:
            if filters.employee_id:
                query = query.where(TimeSheet.employee_id == filters.employee_id)
            if filters.reference_month:
                query = query.where(TimeSheet.reference_month == filters.reference_month)
            if filters.reference_year:
                query = query.where(TimeSheet.reference_year == filters.reference_year)
            if filters.status:
                query = query.where(TimeSheet.status == filters.status)
            if filters.condominium_id:
                query = query.where(TimeSheet.condominium_id == filters.condominium_id)
            if filters.department_id:
                query = query.where(TimeSheet.department_id == filters.department_id)
            if filters.has_pending_issues is not None:
                query = query.where(TimeSheet.has_pending_issues == filters.has_pending_issues)
            if filters.is_fully_approved is not None:
                if filters.is_fully_approved:
                    query = query.where(
                        TimeSheet.approved_by_employee.is_(True),
                        TimeSheet.approved_by_manager.is_(True),
                        TimeSheet.approved_by_hr.is_(True),
                    )
                else:
                    query = query.where(
                        ~and_(
                            TimeSheet.approved_by_employee.is_(True),
                            TimeSheet.approved_by_manager.is_(True),
                            TimeSheet.approved_by_hr.is_(True),
                        )
                    )

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        query = (
            query.order_by(
                TimeSheet.reference_year.desc(),
                TimeSheet.reference_month.desc(),
                TimeSheet.employee_name,
            )
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        sheets = result.scalars().all()

        return list(sheets), total

    async def get_by_period(
        self,
        reference_month: int,
        reference_year: int,
        condominium_id: str = None,
        department_id: str = None,
    ) -> builtins.list[TimeSheet]:
        """Busca todas as folhas de um período."""
        query = select(TimeSheet).where(
            TimeSheet.reference_month == reference_month,
            TimeSheet.reference_year == reference_year,
            TimeSheet.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(TimeSheet.condominium_id == condominium_id)
        if department_id:
            query = query.where(TimeSheet.department_id == department_id)

        result = await self.db.execute(query.order_by(TimeSheet.employee_name))
        return list(result.scalars().all())

    async def get_pending_employee_approval(
        self,
        employee_id: str = None,
        condominium_id: str = None,
    ) -> builtins.list[TimeSheet]:
        """Busca folhas pendentes de aprovação do funcionário."""
        query = select(TimeSheet).where(
            TimeSheet.status == TimeSheetStatus.ABERTO,
            TimeSheet.approved_by_employee.is_(False),
            TimeSheet.is_deleted.is_(False),
        )

        if employee_id:
            query = query.where(TimeSheet.employee_id == employee_id)
        if condominium_id:
            query = query.where(TimeSheet.condominium_id == condominium_id)

        result = await self.db.execute(
            query.order_by(
                TimeSheet.reference_year.desc(),
                TimeSheet.reference_month.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_pending_manager_approval(
        self,
        condominium_id: str = None,
        department_id: str = None,
    ) -> builtins.list[TimeSheet]:
        """Busca folhas pendentes de aprovação do gestor."""
        query = select(TimeSheet).where(
            TimeSheet.status == TimeSheetStatus.ABERTO,
            TimeSheet.approved_by_employee.is_(True),
            TimeSheet.approved_by_manager.is_(False),
            TimeSheet.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(TimeSheet.condominium_id == condominium_id)
        if department_id:
            query = query.where(TimeSheet.department_id == department_id)

        result = await self.db.execute(
            query.order_by(
                TimeSheet.reference_year.desc(),
                TimeSheet.reference_month.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_pending_hr_approval(
        self,
        condominium_id: str = None,
    ) -> builtins.list[TimeSheet]:
        """Busca folhas pendentes de aprovação do RH."""
        query = select(TimeSheet).where(
            TimeSheet.status == TimeSheetStatus.ABERTO,
            TimeSheet.approved_by_employee.is_(True),
            TimeSheet.approved_by_manager.is_(True),
            TimeSheet.approved_by_hr.is_(False),
            TimeSheet.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(TimeSheet.condominium_id == condominium_id)

        result = await self.db.execute(
            query.order_by(
                TimeSheet.reference_year.desc(),
                TimeSheet.reference_month.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_ready_to_close(
        self,
        condominium_id: str = None,
    ) -> builtins.list[TimeSheet]:
        """Busca folhas prontas para fechamento."""
        query = select(TimeSheet).where(
            TimeSheet.status == TimeSheetStatus.ABERTO,
            TimeSheet.approved_by_employee.is_(True),
            TimeSheet.approved_by_manager.is_(True),
            TimeSheet.approved_by_hr.is_(True),
            TimeSheet.has_pending_issues.is_(False),
            TimeSheet.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(TimeSheet.condominium_id == condominium_id)

        result = await self.db.execute(
            query.order_by(
                TimeSheet.reference_year.desc(),
                TimeSheet.reference_month.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_closed_not_sent(
        self,
        condominium_id: str = None,
    ) -> builtins.list[TimeSheet]:
        """Busca folhas fechadas não enviadas à folha de pagamento."""
        query = select(TimeSheet).where(
            TimeSheet.status == TimeSheetStatus.FECHADO,
            TimeSheet.sent_to_payroll_at.is_(None),
            TimeSheet.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(TimeSheet.condominium_id == condominium_id)

        result = await self.db.execute(
            query.order_by(
                TimeSheet.reference_year.desc(),
                TimeSheet.reference_month.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_stats(  # pylint: disable=too-many-locals
        self,
        condominium_id: str = None,
        reference_month: int = None,
        reference_year: int = None,
    ) -> dict:
        """Calcula estatísticas de folhas de ponto."""
        base_where = [TimeSheet.is_deleted.is_(False)]

        if condominium_id:
            base_where.append(TimeSheet.condominium_id == condominium_id)
        if reference_month:
            base_where.append(TimeSheet.reference_month == reference_month)
        if reference_year:
            base_where.append(TimeSheet.reference_year == reference_year)

        # Total
        total_result = await self.db.execute(select(func.count()).where(*base_where))
        total = total_result.scalar() or 0

        # Por status
        status_result = await self.db.execute(
            select(TimeSheet.status, func.count()).where(*base_where).group_by(TimeSheet.status)
        )
        # status volta como STRING do banco (coluna não é enum nativo) → .value crashava.
        # Normaliza p/ str aceitando tanto enum quanto string.
        by_status = {
            (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
            for row in status_result.all()
        }

        # Abertas
        open_count = by_status.get(TimeSheetStatus.ABERTO.value, 0)

        # Fechadas
        closed_count = by_status.get(TimeSheetStatus.FECHADO.value, 0)

        # Enviadas à folha
        payroll_count = by_status.get(TimeSheetStatus.ENVIADO_FOLHA.value, 0)

        # Total horas extras
        overtime_result = await self.db.execute(select(func.sum(TimeSheet.overtime_total_minutes)).where(*base_where))
        overtime_minutes = overtime_result.scalar() or 0

        # Total valor horas extras
        overtime_value_result = await self.db.execute(
            select(func.sum(TimeSheet.overtime_50_value + TimeSheet.overtime_100_value)).where(*base_where)
        )
        overtime_value = overtime_value_result.scalar() or Decimal("0")

        # Total deduções
        deductions_result = await self.db.execute(select(func.sum(TimeSheet.total_deduction_value)).where(*base_where))
        deductions = deductions_result.scalar() or Decimal("0")

        # Média horas trabalhadas
        avg_hours_result = await self.db.execute(select(func.avg(TimeSheet.hours_worked_minutes)).where(*base_where))
        avg_minutes = avg_hours_result.scalar() or 0

        # Total atrasos
        late_result = await self.db.execute(select(func.sum(TimeSheet.late_count)).where(*base_where))
        late_count = late_result.scalar() or 0

        # Total faltas
        absent_result = await self.db.execute(select(func.sum(TimeSheet.absent_days)).where(*base_where))
        absent_days = absent_result.scalar() or 0

        # Pendentes aprovação
        pending_result = await self.db.execute(
            select(func.count()).where(
                *base_where,
                TimeSheet.status == TimeSheetStatus.ABERTO,
                ~and_(
                    TimeSheet.approved_by_employee.is_(True),
                    TimeSheet.approved_by_manager.is_(True),
                    TimeSheet.approved_by_hr.is_(True),
                ),
            )
        )
        pending_approval = pending_result.scalar() or 0

        return {
            "total_sheets": total,
            "by_status": by_status,
            "open_count": open_count,
            "closed_count": closed_count,
            "sent_to_payroll_count": payroll_count,
            "total_overtime_minutes": overtime_minutes,
            "total_overtime_hours": round(overtime_minutes / 60, 2),
            "total_overtime_value": float(overtime_value),
            "total_deductions_value": float(deductions),
            "average_hours_worked": round(avg_minutes / 60, 2) if avg_minutes else 0,
            "late_count_total": late_count,
            "absent_days_total": absent_days,
            "pending_approval_count": pending_approval,
        }

    async def bulk_create(
        self,
        employee_ids: builtins.list[str],
        employee_data: dict,
        reference_month: int,
        reference_year: int,
        condominium_id: str = None,
        created_by_id: str = None,
    ) -> builtins.list[TimeSheet]:
        """Cria folhas de ponto em lote para vários funcionários."""
        sheets = []

        for emp_id in employee_ids:
            existing = await self.get_by_employee_month(emp_id, reference_month, reference_year)
            if existing:
                continue

            emp_info = employee_data.get(emp_id, {})
            sheet = TimeSheet(
                employee_id=emp_id,
                employee_name=emp_info.get("name", ""),
                employee_registration=emp_info.get("registration"),
                employee_cpf=emp_info.get("cpf"),
                employee_pis=emp_info.get("pis"),
                department_id=emp_info.get("department_id"),
                department_name=emp_info.get("department_name"),
                position_name=emp_info.get("position"),
                reference_month=reference_month,
                reference_year=reference_year,
                work_schedule_id=emp_info.get("schedule_id"),
                work_schedule_name=emp_info.get("schedule_name"),
                hourly_rate=emp_info.get("hourly_rate", Decimal("0")),
                condominium_id=condominium_id,
                created_by_id=created_by_id,
            )
            self.db.add(sheet)
            sheets.append(sheet)

        if sheets:
            await self.db.flush()
            for sheet in sheets:
                await self.db.refresh(sheet)

        return sheets

    async def get_for_payroll_export(
        self,
        reference_month: int,
        reference_year: int,
        condominium_id: str = None,
    ) -> builtins.list[TimeSheet]:
        """Busca folhas fechadas para exportação à folha de pagamento."""
        query = select(TimeSheet).where(
            TimeSheet.reference_month == reference_month,
            TimeSheet.reference_year == reference_year,
            TimeSheet.status == TimeSheetStatus.FECHADO,
            TimeSheet.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(TimeSheet.condominium_id == condominium_id)

        result = await self.db.execute(query.order_by(TimeSheet.employee_name))
        return list(result.scalars().all())
