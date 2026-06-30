"""Repository para Interview."""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.recruitment.models.interview import (
    Interview,
    InterviewResult,
    InterviewStatus,
)
from modules.recruitment.schemas.interview import (
    InterviewCreate,
    InterviewFilter,
    InterviewUpdate,
)

logger = logging.getLogger(__name__)


class InterviewRepository:
    """Repository para operações de Interview."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, data: InterviewCreate) -> Interview:
        """Cria uma nova entrevista."""
        create_data = data.model_dump()
        # Schema tem scheduled_date + scheduled_time, mas DB usa scheduled_at
        scheduled_date = create_data.pop("scheduled_date", None)
        scheduled_time = create_data.pop("scheduled_time", None)
        if scheduled_date and scheduled_time:
            create_data["scheduled_at"] = datetime.combine(scheduled_date, scheduled_time)
        # Remove campos que nao existem no model
        for field in list(create_data.keys()):
            if not hasattr(Interview, field) or field in (
                "timezone",
                "meeting_link",
                "meeting_platform",
                "meeting_id",
                "meeting_password",
                "interviewer_names",
                "lead_interviewer_id",
                "script",
                "questions",
                "competencies_to_assess",
                "created_by",
            ):
                create_data.pop(field, None)
        # Map meeting_link -> meeting_url if present (schema usa meeting_url; getattr defensivo —
        # data.meeting_link não existe e crashava todo CREATE de entrevista)
        if getattr(data, "meeting_link", None):
            create_data["meeting_url"] = data.meeting_link

        interview = Interview(**create_data)
        self.session.add(interview)
        await self.session.flush()
        return interview

    async def get_by_id(self, interview_id: str) -> Interview | None:
        """Busca entrevista por ID."""
        result = await self.session.execute(
            select(Interview).where(
                and_(
                    Interview.id == interview_id,
                    Interview.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_relations(self, interview_id: str) -> Interview | None:
        """Busca entrevista por ID com relacionamentos."""
        result = await self.session.execute(
            select(Interview)
            .options(selectinload(Interview.application))
            .where(
                and_(
                    Interview.id == interview_id,
                    Interview.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def update(self, interview_id: str, data: InterviewUpdate) -> Interview | None:
        """Atualiza uma entrevista."""
        interview = await self.get_by_id(interview_id)
        if not interview:
            return None

        update_data = data.model_dump(exclude_unset=True)
        # Handle scheduled_date/scheduled_time -> scheduled_at conversion
        new_date = update_data.pop("scheduled_date", None)
        new_time = update_data.pop("scheduled_time", None)
        if new_date and new_time:
            interview.scheduled_at = datetime.combine(new_date, new_time)
        elif new_date:
            old_time = interview.scheduled_at.time() if interview.scheduled_at else datetime.min.time()
            interview.scheduled_at = datetime.combine(new_date, old_time)
        elif new_time:
            old_date = interview.scheduled_at.date() if interview.scheduled_at else date.today()
            interview.scheduled_at = datetime.combine(old_date, new_time)

        # Remove campos que nao existem no model
        for field in list(update_data.keys()):
            if hasattr(interview, field):
                setattr(interview, field, update_data[field])

        interview.updated_at = datetime.utcnow()
        await self.session.flush()
        return interview

    async def soft_delete(self, interview_id: str) -> bool:
        """Soft delete de entrevista.

        interviews table has no is_deleted/is_active column.
        We cancel instead.
        """
        interview = await self.get_by_id(interview_id)
        if not interview:
            return False

        interview.cancel("Removido pelo sistema")
        await self.session.flush()
        return True

    async def list_with_filters(
        self,
        filters: InterviewFilter | None = None,
        skip: int = 0,
        limit: int = 20,
        order_by: str = "scheduled_at",
        order_desc: bool = False,
    ) -> tuple[list[Interview], int]:
        """Lista entrevistas com filtros e paginação."""
        query = select(Interview).where(Interview.is_deleted.is_(False))

        if filters:
            if filters.application_id:
                query = query.where(Interview.application_id == filters.application_id)
            if filters.interview_type:
                query = query.where(Interview.interview_type == filters.interview_type)
            if filters.status:
                query = query.where(Interview.status == filters.status)
            if filters.result:
                query = query.where(Interview.result == filters.result)
            if filters.interviewer_id:
                query = query.where(Interview.interviewer_ids.contains([filters.interviewer_id]))
            if filters.scheduled_after:
                query = query.where(func.date(Interview.scheduled_at) >= filters.scheduled_after)
            if filters.scheduled_before:
                query = query.where(func.date(Interview.scheduled_at) <= filters.scheduled_before)
            if filters.is_today:
                query = query.where(func.date(Interview.scheduled_at) == date.today())
            if filters.is_upcoming:
                upcoming_limit = date.today() + timedelta(days=7)
                query = query.where(
                    and_(
                        func.date(Interview.scheduled_at) >= date.today(),
                        func.date(Interview.scheduled_at) <= upcoming_limit,
                    )
                )

        # Contagem total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenação — map legacy order_by values
        if order_by == "scheduled_date":
            order_by = "scheduled_at"
        _valid_order_column_cols = {c.key for c in sa_inspect(Interview).mapper.column_attrs}
        order_column = getattr(Interview, order_by if order_by in _valid_order_column_cols else "scheduled_at")
        if order_desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        # Paginação
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        interviews = result.scalars().all()

        return list(interviews), total

    async def get_by_application(self, application_id: str, status: InterviewStatus = None) -> list[Interview]:
        """Retorna entrevistas de uma candidatura."""
        query = select(Interview).where(
            and_(
                Interview.application_id == application_id,
                Interview.is_deleted.is_(False),
            )
        )
        if status:
            query = query.where(Interview.status == status)

        query = query.order_by(Interview.scheduled_at)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_today(self, interviewer_id: str = None) -> list[Interview]:
        """Retorna entrevistas de hoje."""
        query = select(Interview).where(
            and_(
                func.date(Interview.scheduled_at) == date.today(),
                Interview.status.in_(
                    [
                        InterviewStatus.AGENDADA,
                        InterviewStatus.CONFIRMADA,
                        InterviewStatus.EM_ANDAMENTO,
                    ]
                ),
                Interview.is_deleted.is_(False),
            )
        )
        if interviewer_id:
            query = query.where(Interview.interviewer_ids.contains([interviewer_id]))

        query = query.order_by(Interview.scheduled_at)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_upcoming(self, days: int = 7, interviewer_id: str = None) -> list[Interview]:
        """Retorna próximas entrevistas."""
        limit_date = date.today() + timedelta(days=days)

        query = select(Interview).where(
            and_(
                func.date(Interview.scheduled_at) >= date.today(),
                func.date(Interview.scheduled_at) <= limit_date,
                Interview.status.in_(
                    [
                        InterviewStatus.AGENDADA,
                        InterviewStatus.CONFIRMADA,
                    ]
                ),
                Interview.is_deleted.is_(False),
            )
        )
        if interviewer_id:
            query = query.where(Interview.interviewer_ids.contains([interviewer_id]))

        query = query.order_by(Interview.scheduled_at)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_pending_confirmation(self) -> list[Interview]:
        """Retorna entrevistas pendentes de confirmação.

        DB nao possui candidate_confirmed/interviewer_confirmed.
        Retorna entrevistas agendadas para amanha ou antes que ainda estao AGENDADA.
        """
        tomorrow = date.today() + timedelta(days=1)

        query = (
            select(Interview)
            .where(
                and_(
                    func.date(Interview.scheduled_at) <= tomorrow,
                    Interview.status == InterviewStatus.AGENDADA,
                    Interview.is_deleted.is_(False),
                )
            )
            .order_by(Interview.scheduled_at)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_pending_result(self) -> list[Interview]:
        """Retorna entrevistas pendentes de resultado."""
        query = (
            select(Interview)
            .where(
                and_(
                    Interview.status == InterviewStatus.REALIZADA,
                    Interview.result.is_(None),
                    Interview.is_deleted.is_(False),
                )
            )
            .order_by(Interview.scheduled_at.desc())
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_date_range(self, start_date: date, end_date: date, interviewer_id: str = None) -> list[Interview]:
        """Retorna entrevistas em um período."""
        query = select(Interview).where(
            and_(
                func.date(Interview.scheduled_at) >= start_date,
                func.date(Interview.scheduled_at) <= end_date,
                Interview.is_deleted.is_(False),
            )
        )
        if interviewer_id:
            query = query.where(Interview.interviewer_ids.contains([interviewer_id]))

        query = query.order_by(Interview.scheduled_at)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def complete(
        self,
        interview_id: str,
        result: InterviewResult,
        score: int = None,
        feedback: str = None,
    ) -> Interview | None:
        """Completa entrevista."""
        interview = await self.get_by_id(interview_id)
        if interview:
            # Model.complete() accepts rating param — score property maps to rating
            interview.complete(result, rating=score, feedback=feedback)
            await self.session.flush()
        return interview

    async def cancel(self, interview_id: str, reason: str, cancelled_by: str = None) -> Interview | None:
        """Cancela entrevista."""
        interview = await self.get_by_id(interview_id)
        if interview:
            interview.cancel(reason, cancelled_by)
            await self.session.flush()
        return interview

    async def reschedule(self, interview_id: str, new_datetime: datetime) -> Interview | None:
        """Reagenda entrevista.

        Accepts a single datetime (model.reschedule expects datetime).
        """
        interview = await self.get_by_id(interview_id)
        if interview:
            interview.reschedule(new_datetime)
            await self.session.flush()
        return interview

    async def mark_no_show(self, interview_id: str) -> Interview | None:
        """Marca como não compareceu."""
        interview = await self.get_by_id(interview_id)
        if interview:
            interview.mark_no_show()
            await self.session.flush()
        return interview

    async def get_stats(  # pylint: disable=too-many-branches
        self, application_id: str = None
    ) -> dict:
        """Retorna estatísticas."""
        query = select(Interview).where(Interview.is_deleted.is_(False))
        if application_id:
            query = query.where(Interview.application_id == application_id)

        result = await self.session.execute(query)
        interviews = result.scalars().all()

        stats = {
            "total_interviews": len(interviews),
            "scheduled": 0,
            "completed": 0,
            "cancelled": 0,
            "no_show": 0,
            "by_type": {},
            "by_result": {},
            "avg_score": 0,
            "avg_duration_minutes": 0,
            "approval_rate": 0,
        }

        total_score = 0
        score_count = 0
        total_duration = 0
        duration_count = 0
        approved_count = 0
        completed_count = 0

        for interview in interviews:
            if interview.status in [InterviewStatus.AGENDADA, InterviewStatus.CONFIRMADA]:
                stats["scheduled"] += 1
            elif interview.status == InterviewStatus.REALIZADA:
                stats["completed"] += 1
                completed_count += 1
            elif interview.status == InterviewStatus.CANCELADA:
                stats["cancelled"] += 1
            elif interview.status == InterviewStatus.NO_SHOW:
                stats["no_show"] += 1

            type_key = interview.interview_type
            if hasattr(type_key, "value"):
                type_key = type_key.value
            stats["by_type"][type_key] = stats["by_type"].get(type_key, 0) + 1

            if interview.result:
                result_key = interview.result
                if hasattr(result_key, "value"):
                    result_key = result_key.value
                stats["by_result"][result_key] = stats["by_result"].get(result_key, 0) + 1

                if interview.result in [
                    InterviewResult.APROVADO,
                    InterviewResult.APROVADO_COM_RESSALVAS,
                ]:
                    approved_count += 1

            if interview.rating:
                total_score += interview.rating
                score_count += 1

            # Compute duration from started_at/ended_at if available
            if interview.started_at and interview.ended_at:
                duration = (interview.ended_at - interview.started_at).total_seconds() / 60
                total_duration += duration
                duration_count += 1

        if score_count > 0:
            stats["avg_score"] = round(total_score / score_count, 1)

        if duration_count > 0:
            stats["avg_duration_minutes"] = round(total_duration / duration_count, 0)

        if completed_count > 0:
            stats["approval_rate"] = round((approved_count / completed_count) * 100, 1)

        return stats
