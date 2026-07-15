"""Repository para WorkSchedule."""

import builtins
from datetime import date as _date  # noqa: F401
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.time_tracking.models import (
    ScheduleStatus,
    WorkSchedule,
)
from modules.hr.time_tracking.schemas import (
    WorkScheduleCreate,
    WorkScheduleFilter,
    WorkScheduleUpdate,
)


class WorkScheduleRepository:
    """Repository para operações de WorkSchedule."""

    def __init__(self, db: AsyncSession):
        """Inicializa o repository."""
        self.db = db

    async def create(
        self,
        data: WorkScheduleCreate,
        created_by_id: str = None,
    ) -> WorkSchedule:
        """Cria uma nova jornada."""
        schedule = WorkSchedule(
            **data.model_dump(exclude_unset=True),
            created_by_id=created_by_id,
        )
        self.db.add(schedule)
        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule

    async def get_by_id(self, schedule_id: UUID) -> WorkSchedule | None:
        """Busca jornada por ID."""
        result = await self.db.execute(
            select(WorkSchedule).where(
                WorkSchedule.id == schedule_id,
                WorkSchedule.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> WorkSchedule | None:
        """Busca jornada por código."""
        result = await self.db.execute(
            select(WorkSchedule).where(
                WorkSchedule.code == code,
                WorkSchedule.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_employee(self, employee_id: str) -> WorkSchedule | None:
        """Busca jornada ativa de um funcionário."""
        result = await self.db.execute(
            select(WorkSchedule).where(
                WorkSchedule.employee_id == employee_id,
                WorkSchedule.status == ScheduleStatus.ATIVO,
                WorkSchedule.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        schedule: WorkSchedule,
        data: WorkScheduleUpdate,
    ) -> WorkSchedule:
        """Atualiza uma jornada."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(schedule, field, value)
        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule

    async def delete(self, schedule: WorkSchedule) -> None:
        """Soft delete de uma jornada."""
        schedule.soft_delete()
        await self.db.flush()

    async def list(
        self,
        filters: WorkScheduleFilter = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[WorkSchedule], int]:
        """Lista jornadas com filtros."""
        query = select(WorkSchedule).where(WorkSchedule.is_deleted.is_(False))

        if filters:
            if filters.employee_id:
                query = query.where(WorkSchedule.employee_id == filters.employee_id)
            if filters.schedule_type:
                query = query.where(WorkSchedule.schedule_type == filters.schedule_type)
            if filters.status:
                query = query.where(WorkSchedule.status == filters.status)
            if filters.department_id:
                query = query.where(WorkSchedule.department_id == filters.department_id)
            if filters.condominium_id:
                query = query.where(WorkSchedule.condominium_id == filters.condominium_id)
            if filters.is_template is not None:
                query = query.where(WorkSchedule.is_template == filters.is_template)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        query = query.order_by(WorkSchedule.name).offset(skip).limit(limit)
        result = await self.db.execute(query)
        schedules = result.scalars().all()

        return list(schedules), total

    async def get_templates(
        self,
        condominium_id: str = None,
    ) -> builtins.list[WorkSchedule]:
        """Busca templates de jornada."""
        query = select(WorkSchedule).where(
            WorkSchedule.is_template.is_(True),
            WorkSchedule.status == ScheduleStatus.ATIVO,
            WorkSchedule.is_deleted.is_(False),
        )
        if condominium_id:
            query = query.where(WorkSchedule.condominium_id == condominium_id)

        result = await self.db.execute(query.order_by(WorkSchedule.name))
        return list(result.scalars().all())

    async def get_stats(
        self,
        condominium_id: str = None,
    ) -> dict:
        """Calcula estatísticas de jornadas."""
        base_where = [WorkSchedule.is_deleted.is_(False)]
        if condominium_id:
            base_where.append(WorkSchedule.condominium_id == condominium_id)

        total_result = await self.db.execute(select(func.count()).where(*base_where))
        total = total_result.scalar() or 0

        active_result = await self.db.execute(
            select(func.count()).where(
                *base_where,
                WorkSchedule.status == ScheduleStatus.ATIVO,
            )
        )
        active = active_result.scalar() or 0

        template_result = await self.db.execute(
            select(func.count()).where(
                *base_where,
                WorkSchedule.is_template.is_(True),
            )
        )
        templates = template_result.scalar() or 0

        type_result = await self.db.execute(
            select(WorkSchedule.schedule_type, func.count()).where(*base_where).group_by(WorkSchedule.schedule_type)
        )
        by_type = {(row[0].value if hasattr(row[0],'value') else str(row[0])): row[1] for row in type_result.all()}

        return {
            "total_schedules": total,
            "active_schedules": active,
            "template_schedules": templates,
            "by_type": by_type,
        }
