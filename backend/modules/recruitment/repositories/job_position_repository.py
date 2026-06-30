"""Repository para JobPosition."""

import logging
from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from modules.recruitment.models.job_position import (
    Department,
    JobPosition,
    PositionStatus,
)
from modules.recruitment.schemas.job_position import (
    JobPositionCreate,
    JobPositionFilter,
    JobPositionUpdate,
)

logger = logging.getLogger(__name__)


class JobPositionRepository:
    """Repository para operações de JobPosition."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, data: JobPositionCreate) -> JobPosition:
        """Cria uma nova vaga."""
        # Gera código
        sequence = await self._get_next_sequence()
        code = JobPosition.generate_code(sequence)

        position = JobPosition(
            code=code,
            **data.model_dump(),
        )
        self.session.add(position)
        await self.session.flush()
        return position

    async def get_by_id(self, position_id: str) -> JobPosition | None:
        """Busca vaga por ID."""
        result = await self.session.execute(
            select(JobPosition).where(
                and_(
                    JobPosition.id == position_id,
                    JobPosition.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> JobPosition | None:
        """Busca vaga por código."""
        result = await self.session.execute(
            select(JobPosition).where(
                and_(
                    JobPosition.code == code,
                    JobPosition.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def update(self, position_id: str, data: JobPositionUpdate) -> JobPosition | None:
        """Atualiza uma vaga."""
        position = await self.get_by_id(position_id)
        if not position:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(position, field, value)

        await self.session.flush()
        return position

    async def soft_delete(self, position_id: str) -> bool:
        """Soft delete de vaga."""
        position = await self.get_by_id(position_id)
        if not position:
            return False

        position.is_deleted = True
        position.is_active = False
        await self.session.flush()
        return True

    async def list_with_filters(  # pylint: disable=too-many-branches
        self,
        filters: JobPositionFilter | None = None,
        skip: int = 0,
        limit: int = 20,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> tuple[list[JobPosition], int]:
        """Lista vagas com filtros e paginação."""
        query = select(JobPosition).where(JobPosition.is_deleted.is_(False))

        if filters:
            if filters.status:
                query = query.where(JobPosition.status == filters.status)
            if filters.position_type:
                query = query.where(JobPosition.position_type == filters.position_type)
            if filters.position_level:
                query = query.where(JobPosition.position_level == filters.position_level)
            if filters.department:
                query = query.where(JobPosition.department == filters.department)
            if filters.work_model:
                query = query.where(JobPosition.work_model == filters.work_model)
            if filters.city:
                query = query.where(JobPosition.city.ilike(f"%{filters.city}%"))
            if filters.state:
                query = query.where(JobPosition.state == filters.state)
            if filters.salary_min:
                query = query.where(JobPosition.salary_min >= filters.salary_min)
            if filters.salary_max:
                query = query.where(JobPosition.salary_max <= filters.salary_max)
            if filters.condominium_id:
                query = query.where(JobPosition.condominio_id == filters.condominium_id)
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.where(
                    or_(
                        JobPosition.title.ilike(search_term),
                        JobPosition.description.ilike(search_term),
                        JobPosition.code.ilike(search_term),
                    )
                )

        # Contagem total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenação
        _valid_order_column_cols = {c.key for c in sa_inspect(JobPosition).mapper.column_attrs}
        order_column = getattr(JobPosition, order_by if order_by in _valid_order_column_cols else "created_at")
        if order_desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        # Paginação
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        positions = result.scalars().all()

        return list(positions), total

    async def get_open_positions(self, condominium_id: str = None, skip: int = 0, limit: int = 20) -> list[JobPosition]:
        """Retorna vagas abertas."""
        query = select(JobPosition).where(
            and_(
                JobPosition.status == PositionStatus.ABERTA,
                JobPosition.is_deleted.is_(False),
            )
        )
        if condominium_id:
            query = query.where(JobPosition.condominio_id == condominium_id)

        query = query.order_by(JobPosition.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_department(self, department: Department, status: PositionStatus = None) -> list[JobPosition]:
        """Retorna vagas por departamento."""
        query = select(JobPosition).where(
            and_(
                JobPosition.department == department,
                JobPosition.is_deleted.is_(False),
            )
        )
        if status:
            query = query.where(JobPosition.status == status)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_expiring_soon(self, days: int = 7) -> list[JobPosition]:
        """Retorna vagas próximas da expiração."""
        deadline = date.today()
        deadline_limit = date.today()
        from datetime import timedelta  # pylint: disable=import-outside-toplevel

        deadline_limit = deadline + timedelta(days=days)

        query = select(JobPosition).where(
            and_(
                JobPosition.status == PositionStatus.ABERTA,
                JobPosition.deadline.isnot(None),
                JobPosition.deadline <= deadline_limit,
                JobPosition.deadline >= deadline,
                JobPosition.is_deleted.is_(False),
            )
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def increment_view(self, position_id: str) -> None:
        """Incrementa visualizacao (noop — coluna nao existe no DB)."""

    async def increment_application(self, position_id: str) -> None:
        """Incrementa candidaturas (noop — coluna nao existe no DB)."""

    async def fill_vacancy(self, position_id: str) -> JobPosition | None:
        """Preenche uma vaga."""
        position = await self.get_by_id(position_id)
        if position:
            position.filled_count = (position.filled_count or 0) + 1
            await self.session.flush()
        return position

    async def get_stats(self, condominium_id: str = None) -> dict:
        """Retorna estatísticas."""
        query = select(JobPosition).where(JobPosition.is_deleted.is_(False))
        if condominium_id:
            query = query.where(JobPosition.condominio_id == condominium_id)

        result = await self.session.execute(query)
        positions = result.scalars().all()

        stats = {
            "total_positions": len(positions),
            "open_positions": 0,
            "closed_positions": 0,
            "filled_positions": 0,
            "total_vacancies": 0,
            "filled_vacancies": 0,
            "total_applications": 0,
            "by_status": {},
            "by_department": {},
            "by_level": {},
            "by_type": {},
        }

        for pos in positions:
            stats["total_vacancies"] += pos.vacancies or 0
            stats["filled_vacancies"] += pos.filled_count or 0

            if pos.status == PositionStatus.ABERTA:
                stats["open_positions"] += 1
            elif pos.status == PositionStatus.FECHADA:
                stats["closed_positions"] += 1
            elif pos.status == PositionStatus.PREENCHIDA:
                stats["filled_positions"] += 1

            status_key = pos.status if isinstance(pos.status, str) else pos.status.value
            stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1

            if pos.department:
                dept_key = pos.department if isinstance(pos.department, str) else pos.department.value
                stats["by_department"][dept_key] = stats["by_department"].get(dept_key, 0) + 1

            if pos.position_level:
                level_key = pos.position_level if isinstance(pos.position_level, str) else pos.position_level.value
                stats["by_level"][level_key] = stats["by_level"].get(level_key, 0) + 1

            if pos.position_type:
                type_key = pos.position_type if isinstance(pos.position_type, str) else pos.position_type.value
                stats["by_type"][type_key] = stats["by_type"].get(type_key, 0) + 1

        return stats

    async def _get_next_sequence(self) -> int:
        """Retorna próximo número de sequência."""
        year = date.today().year
        prefix = f"VAG-{year}-"

        result = await self.session.execute(
            select(func.count()).select_from(JobPosition).where(JobPosition.code.like(f"{prefix}%"))
        )
        count = result.scalar() or 0
        return count + 1
