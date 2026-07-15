"""Repository para Overtime."""

import builtins
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.time_tracking.models import (
    CompensationType,
    Overtime,
    OvertimeStatus,
    OvertimeType,
)
from modules.hr.time_tracking.schemas import (
    OvertimeCreate,
    OvertimeFilter,
    OvertimeUpdate,
)


class OvertimeRepository:
    """Repository para operações de Overtime."""

    def __init__(self, db: AsyncSession):
        """Inicializa o repository."""
        self.db = db

    async def create(
        self,
        data: OvertimeCreate,
        created_by_id: str = None,
    ) -> Overtime:
        """Cria um novo registro de hora extra."""
        overtime = Overtime(
            **data.model_dump(exclude_unset=True),
            created_by_id=created_by_id,
        )
        self.db.add(overtime)
        await self.db.flush()
        await self.db.refresh(overtime)
        return overtime

    async def get_by_id(self, overtime_id: UUID) -> Overtime | None:
        """Busca hora extra por ID."""
        result = await self.db.execute(
            select(Overtime).where(
                Overtime.id == overtime_id,
                Overtime.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Overtime | None:
        """Busca hora extra por código."""
        result = await self.db.execute(
            select(Overtime).where(
                Overtime.code == code,
                Overtime.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        overtime: Overtime,
        data: OvertimeUpdate,
    ) -> Overtime:
        """Atualiza uma hora extra."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(overtime, field, value)
        await self.db.flush()
        await self.db.refresh(overtime)
        return overtime

    async def delete(self, overtime: Overtime) -> None:
        """Soft delete de uma hora extra."""
        overtime.soft_delete()
        await self.db.flush()

    async def list(  # pylint: disable=too-many-branches
        self,
        filters: OvertimeFilter = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Overtime], int]:
        """Lista horas extras com filtros."""
        query = select(Overtime).where(Overtime.is_deleted.is_(False))

        if filters:
            if filters.employee_id:
                query = query.where(Overtime.employee_id == filters.employee_id)
            if filters.overtime_type:
                query = query.where(Overtime.overtime_type == filters.overtime_type)
            if filters.status:
                query = query.where(Overtime.status == filters.status)
            if filters.condominium_id:
                query = query.where(Overtime.condominium_id == filters.condominium_id)
            if filters.department_id:
                query = query.where(Overtime.department_id == filters.department_id)
            if filters.date_from:
                query = query.where(Overtime.overtime_date >= filters.date_from)
            if filters.date_to:
                query = query.where(Overtime.overtime_date <= filters.date_to)
            if getattr(filters, "is_pending_approval", None) is not None:
                if filters.is_pending_approval:
                    query = query.where(Overtime.status == OvertimeStatus.PENDENTE)
                else:
                    query = query.where(Overtime.status != OvertimeStatus.PENDENTE)
            if getattr(filters, "is_pending_compensation", None) is not None:
                query = query.where(Overtime.is_compensated == (not filters.is_pending_compensation))
            if getattr(filters, "is_pending_payment", None) is not None:
                query = query.where(Overtime.is_paid == (not filters.is_pending_payment))
            if getattr(filters, "use_time_bank", None) is not None:
                query = query.where(Overtime.use_time_bank == filters.use_time_bank)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        query = query.order_by(Overtime.overtime_date.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        overtimes = result.scalars().all()

        return list(overtimes), total

    async def get_by_employee_period(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
    ) -> builtins.list[Overtime]:
        """Busca horas extras de um funcionário em um período."""
        result = await self.db.execute(
            select(Overtime)
            .where(
                Overtime.employee_id == employee_id,
                Overtime.overtime_date >= start_date,
                Overtime.overtime_date <= end_date,
                Overtime.is_deleted.is_(False),
            )
            .order_by(Overtime.overtime_date)
        )
        return list(result.scalars().all())

    async def get_pending_approval(
        self,
        condominium_id: str = None,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[Overtime]:
        """Busca horas extras pendentes de aprovação."""
        query = select(Overtime).where(
            Overtime.status.in_(
                [
                    OvertimeStatus.PENDENTE,
                    OvertimeStatus.EM_ANALISE,
                ]
            ),
            Overtime.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(Overtime.condominium_id == condominium_id)

        query = query.order_by(Overtime.overtime_date.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_pending_compensation(
        self,
        employee_id: str = None,
        condominium_id: str = None,
    ) -> builtins.list[Overtime]:
        """Busca horas extras aprovadas pendentes de compensação."""
        query = select(Overtime).where(
            Overtime.status == OvertimeStatus.APROVADA,
            Overtime.compensation_type == CompensationType.BANCO_HORAS,
            Overtime.is_compensated.is_(False),
            Overtime.is_deleted.is_(False),
        )

        if employee_id:
            query = query.where(Overtime.employee_id == employee_id)
        if condominium_id:
            query = query.where(Overtime.condominium_id == condominium_id)

        result = await self.db.execute(query.order_by(Overtime.overtime_date))
        return list(result.scalars().all())

    async def get_pending_payment(
        self,
        condominium_id: str = None,
    ) -> builtins.list[Overtime]:
        """Busca horas extras aprovadas pendentes de pagamento."""
        query = select(Overtime).where(
            Overtime.status == OvertimeStatus.APROVADA,
            Overtime.compensation_type == CompensationType.PAGAMENTO,
            Overtime.is_paid.is_(False),
            Overtime.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(Overtime.condominium_id == condominium_id)

        result = await self.db.execute(query.order_by(Overtime.overtime_date))
        return list(result.scalars().all())

    async def get_stats(  # pylint: disable=too-many-locals
        self,
        condominium_id: str = None,
        employee_id: str = None,
        date_from: date = None,
        date_to: date = None,
    ) -> dict:
        """Calcula estatísticas de horas extras."""
        base_where = [Overtime.is_deleted.is_(False)]

        if condominium_id:
            base_where.append(Overtime.condominium_id == condominium_id)
        if employee_id:
            base_where.append(Overtime.employee_id == employee_id)
        if date_from:
            base_where.append(Overtime.overtime_date >= date_from)
        if date_to:
            base_where.append(Overtime.overtime_date <= date_to)

        # Total
        total_result = await self.db.execute(select(func.count()).where(*base_where))
        total = total_result.scalar() or 0

        # Por status
        status_result = await self.db.execute(
            select(Overtime.status, func.count()).where(*base_where).group_by(Overtime.status)
        )
        by_status = {(row[0].value if hasattr(row[0],'value') else str(row[0])): row[1] for row in status_result.all()}

        # Por tipo
        type_result = await self.db.execute(
            select(Overtime.overtime_type, func.count()).where(*base_where).group_by(Overtime.overtime_type)
        )
        by_type = {(row[0].value if hasattr(row[0],'value') else str(row[0])): row[1] for row in type_result.all()}

        # Total de minutos aprovados
        approved_minutes_result = await self.db.execute(
            select(func.sum(Overtime.net_duration_minutes)).where(
                *base_where,
                Overtime.status == OvertimeStatus.APROVADA,
            )
        )
        approved_minutes = approved_minutes_result.scalar() or 0

        # Total valor
        total_value_result = await self.db.execute(
            select(func.sum(Overtime.total_value)).where(
                *base_where,
                Overtime.status == OvertimeStatus.APROVADA,
            )
        )
        total_value = total_value_result.scalar() or 0

        # Pendentes
        pending_result = await self.db.execute(
            select(func.count()).where(
                *base_where,
                Overtime.status.in_(
                    [
                        OvertimeStatus.PENDENTE,
                        OvertimeStatus.EM_ANALISE,
                    ]
                ),
            )
        )
        pending_count = pending_result.scalar() or 0

        # Por tipo de compensação
        compensation_result = await self.db.execute(
            select(Overtime.compensation_type, func.count())
            .where(
                *base_where,
                Overtime.status == OvertimeStatus.APROVADA,
            )
            .group_by(Overtime.compensation_type)
        )
        by_compensation = {row[0].value if row[0] else "indefinido": row[1] for row in compensation_result.all()}

        return {
            "total_records": total,
            "by_status": by_status,
            "by_type": by_type,
            "approved_minutes": approved_minutes,
            "approved_hours": round(approved_minutes / 60, 2),
            "total_value": float(total_value),
            "pending_count": pending_count,
            "by_compensation_type": by_compensation,
        }

    async def get_employee_summary(
        self,
        employee_id: str,
        reference_month: int,
        reference_year: int,
    ) -> dict:
        """Calcula resumo de horas extras do funcionário no mês."""
        start_date = date(reference_year, reference_month, 1)
        if reference_month == 12:
            end_date = date(reference_year + 1, 1, 1)
        else:
            end_date = date(reference_year, reference_month + 1, 1)

        base_where = [
            Overtime.employee_id == employee_id,
            Overtime.overtime_date >= start_date,
            Overtime.overtime_date < end_date,
            Overtime.is_deleted.is_(False),
        ]

        # Horas 50%
        h50_result = await self.db.execute(
            select(func.sum(Overtime.net_duration_minutes)).where(
                *base_where,
                Overtime.overtime_type == OvertimeType.HORA_EXTRA_50,
                Overtime.status == OvertimeStatus.APROVADA,
            )
        )
        h50_minutes = h50_result.scalar() or 0

        # Horas 100%
        h100_result = await self.db.execute(
            select(func.sum(Overtime.net_duration_minutes)).where(
                *base_where,
                Overtime.overtime_type == OvertimeType.HORA_EXTRA_100,
                Overtime.status == OvertimeStatus.APROVADA,
            )
        )
        h100_minutes = h100_result.scalar() or 0

        # Valor total
        value_result = await self.db.execute(
            select(func.sum(Overtime.total_value)).where(
                *base_where,
                Overtime.status == OvertimeStatus.APROVADA,
            )
        )
        total_value = value_result.scalar() or 0

        # Para banco de horas
        bank_result = await self.db.execute(
            select(func.sum(Overtime.net_duration_minutes)).where(
                *base_where,
                Overtime.status == OvertimeStatus.APROVADA,
                Overtime.compensation_type == CompensationType.BANCO_HORAS,
            )
        )
        bank_minutes = bank_result.scalar() or 0

        return {
            "reference_month": reference_month,
            "reference_year": reference_year,
            "overtime_50_minutes": h50_minutes,
            "overtime_100_minutes": h100_minutes,
            "total_overtime_minutes": h50_minutes + h100_minutes,
            "total_value": float(total_value),
            "time_bank_credits_minutes": bank_minutes,
        }
