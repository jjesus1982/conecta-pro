"""Service para Interview."""

import logging
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from modules.recruitment.models.interview import (
    Interview,
    InterviewStatus,
)
from modules.recruitment.repositories.application_repository import (
    ApplicationRepository,
)
from modules.recruitment.repositories.interview_repository import InterviewRepository
from modules.recruitment.schemas.interview import (
    InterviewCalendar,
    InterviewCancel,
    InterviewComplete,
    InterviewCreate,
    InterviewEvaluation,
    InterviewFilter,
    InterviewReschedule,
    InterviewSlot,
    InterviewUpdate,
)
from modules.recruitment.services.recruitment_ai_service import RecruitmentAIService

logger = logging.getLogger(__name__)


class InterviewService:
    """Service para operações de entrevistas."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.repository = InterviewRepository(session)
        self.application_repo = ApplicationRepository(session)
        self.ai_service = RecruitmentAIService()

    async def create(self, data: InterviewCreate) -> Interview:
        """
        Agenda uma nova entrevista.

        Args:
            data: Dados da entrevista

        Returns:
            Entrevista criada
        """
        # Verifica se candidatura existe
        application = await self.application_repo.get_by_id(data.application_id)
        if not application:
            raise ValueError("Candidatura não encontrada")

        # Verifica conflito de horário
        conflict = await self._check_schedule_conflict(
            data.scheduled_date,
            data.scheduled_time,
            data.duration_minutes,
            data.interviewer_ids,
        )
        if conflict:
            raise ValueError(f"Conflito de horário: {conflict}")

        interview = await self.repository.create(data)
        await self.session.commit()

        logger.info(
            f"Entrevista agendada: {interview.interview_type}",
            extra={
                "interview_id": str(interview.id),
                "application_id": str(application.id),
                "scheduled_date": str(data.scheduled_date),
            },
        )

        return interview

    async def get_by_id(self, interview_id: str) -> Interview | None:
        """Busca entrevista por ID."""
        return await self.repository.get_by_id(interview_id)

    async def get_by_id_with_relations(self, interview_id: str) -> Interview | None:
        """Busca entrevista por ID com relacionamentos."""
        return await self.repository.get_by_id_with_relations(interview_id)

    async def update(self, interview_id: str, data: InterviewUpdate) -> Interview | None:
        """
        Atualiza uma entrevista.

        Args:
            interview_id: ID da entrevista
            data: Dados para atualização

        Returns:
            Entrevista atualizada ou None
        """
        interview = await self.repository.update(interview_id, data)
        if interview:
            await self.session.commit()
            logger.info(
                "Entrevista atualizada",
                extra={"interview_id": str(interview.id)},
            )
        return interview

    async def delete(self, interview_id: str) -> bool:
        """
        Remove uma entrevista (soft delete).

        Args:
            interview_id: ID da entrevista

        Returns:
            True se removida com sucesso
        """
        result = await self.repository.soft_delete(interview_id)
        if result:
            await self.session.commit()
            logger.info(f"Entrevista removida: {interview_id}")
        return result

    async def list_with_filters(
        self,
        filters: InterviewFilter | None = None,
        skip: int = 0,
        limit: int = 20,
        order_by: str = "scheduled_at",
        order_desc: bool = False,
    ) -> tuple[list[Interview], int]:
        """
        Lista entrevistas com filtros.

        Args:
            filters: Filtros opcionais
            skip: Offset para paginação
            limit: Limite de resultados
            order_by: Campo para ordenação
            order_desc: Se ordenação é descendente

        Returns:
            Tuple com lista de entrevistas e total
        """
        # Map legacy order_by
        if order_by == "scheduled_date":
            order_by = "scheduled_at"
        return await self.repository.list_with_filters(filters, skip, limit, order_by, order_desc)

    async def get_by_application(self, application_id: str, status: InterviewStatus = None) -> list[Interview]:
        """Retorna entrevistas de uma candidatura."""
        return await self.repository.get_by_application(application_id, status)

    async def get_today(self, interviewer_id: str = None) -> list[Interview]:
        """Retorna entrevistas de hoje."""
        return await self.repository.get_today(interviewer_id)

    async def get_upcoming(self, days: int = 7, interviewer_id: str = None) -> list[Interview]:
        """Retorna próximas entrevistas."""
        return await self.repository.get_upcoming(days, interviewer_id)

    async def get_pending_confirmation(self) -> list[Interview]:
        """Retorna entrevistas pendentes de confirmação."""
        return await self.repository.get_pending_confirmation()

    async def get_pending_result(self) -> list[Interview]:
        """Retorna entrevistas pendentes de resultado."""
        return await self.repository.get_pending_result()

    async def get_by_date_range(
        self,
        start_date: date,
        end_date: date,
        interviewer_id: str = None,
    ) -> list[Interview]:
        """Retorna entrevistas em um período."""
        return await self.repository.get_by_date_range(start_date, end_date, interviewer_id)

    async def confirm_candidate(self, interview_id: str) -> Interview | None:
        """
        Confirma presença do candidato.

        DB nao possui candidate_confirmed — muda status para CONFIRMADA.
        """
        interview = await self.repository.get_by_id(interview_id)
        if not interview:
            return None

        interview.status = InterviewStatus.CONFIRMADA
        interview.updated_at = datetime.now(UTC)
        await self.session.commit()

        logger.info(
            "Candidato confirmou presença",
            extra={"interview_id": str(interview.id)},
        )

        return interview

    async def confirm_interviewer(self, interview_id: str) -> Interview | None:
        """
        Confirma presença do entrevistador.

        DB nao possui interviewer_confirmed — muda status para CONFIRMADA.
        """
        interview = await self.repository.get_by_id(interview_id)
        if not interview:
            return None

        interview.status = InterviewStatus.CONFIRMADA
        interview.updated_at = datetime.now(UTC)
        await self.session.commit()

        logger.info(
            "Entrevistador confirmou presença",
            extra={"interview_id": str(interview.id)},
        )

        return interview

    async def start(self, interview_id: str) -> Interview | None:
        """
        Inicia entrevista.

        Args:
            interview_id: ID da entrevista

        Returns:
            Entrevista atualizada ou None
        """
        interview = await self.repository.get_by_id(interview_id)
        if not interview:
            return None

        interview.start()
        await self.session.commit()

        logger.info(
            "Entrevista iniciada",
            extra={"interview_id": str(interview.id)},
        )

        return interview

    async def complete(self, interview_id: str, data: InterviewComplete) -> Interview | None:
        """
        Completa entrevista.

        Args:
            interview_id: ID da entrevista
            data: Dados da conclusão

        Returns:
            Entrevista completada ou None
        """
        interview = await self.repository.complete(
            interview_id,
            data.result,
            data.score,
            data.feedback,
        )
        if not interview:
            return None

        # Atualiza rating na candidatura
        if data.score is not None:
            application = await self.application_repo.get_by_id(interview.application_id)
            if application:
                # Calcula media de ratings das entrevistas realizadas
                interviews = await self.repository.get_by_application(interview.application_id)
                completed = [i for i in interviews if i.status == InterviewStatus.REALIZADA and i.rating]
                if completed:
                    avg_rating = sum(i.rating for i in completed) / len(completed)
                    application.rating = int(avg_rating)

        await self.session.commit()

        logger.info(
            f"Entrevista completada: {data.result.value}",
            extra={
                "interview_id": str(interview.id),
                "result": data.result.value,
                "score": data.score,
            },
        )

        return interview

    async def cancel(self, interview_id: str, data: InterviewCancel) -> Interview | None:
        """
        Cancela entrevista.

        Args:
            interview_id: ID da entrevista
            data: Dados do cancelamento

        Returns:
            Entrevista cancelada ou None
        """
        interview = await self.repository.cancel(interview_id, data.reason)
        if interview:
            await self.session.commit()
            logger.info(
                f"Entrevista cancelada: {data.reason}",
                extra={
                    "interview_id": str(interview.id),
                },
            )
        return interview

    async def reschedule(self, interview_id: str, data: InterviewReschedule) -> Interview | None:
        """
        Reagenda entrevista.

        Args:
            interview_id: ID da entrevista
            data: Dados do reagendamento

        Returns:
            Entrevista reagendada ou None
        """
        # Verifica conflito no novo horário
        interview = await self.repository.get_by_id(interview_id)
        if not interview:
            return None

        conflict = await self._check_schedule_conflict(
            data.new_date,
            data.new_time,
            interview.duration_minutes,
            interview.interviewer_ids,
            exclude_interview_id=interview_id,
        )
        if conflict:
            raise ValueError(f"Conflito de horário: {conflict}")

        # Model.reschedule expects a single datetime
        new_datetime = datetime.combine(data.new_date, data.new_time)
        interview = await self.repository.reschedule(interview_id, new_datetime)
        if interview:
            await self.session.commit()
            logger.info(
                f"Entrevista reagendada para {data.new_date}",
                extra={
                    "interview_id": str(interview.id),
                    "new_date": str(data.new_date),
                    "new_time": str(data.new_time),
                },
            )
        return interview

    async def mark_no_show(self, interview_id: str) -> Interview | None:
        """
        Marca como não compareceu.

        Args:
            interview_id: ID da entrevista

        Returns:
            Entrevista atualizada ou None
        """
        interview = await self.repository.mark_no_show(interview_id)
        if interview:
            await self.session.commit()
            logger.warning(
                "Candidato não compareceu",
                extra={"interview_id": str(interview.id)},
            )
        return interview

    async def add_evaluation(self, interview_id: str, data: InterviewEvaluation) -> Interview | None:
        """
        Adiciona avaliação de competência.

        DB possui interviewer_notes (JSONB) — usa esse campo para armazenar avaliacao.

        Args:
            interview_id: ID da entrevista
            data: Dados da avaliação

        Returns:
            Entrevista atualizada ou None
        """
        interview = await self.repository.get_by_id(interview_id)
        if not interview:
            return None

        # Armazena avaliacao em interviewer_notes (JSONB)
        notes = dict(interview.interviewer_notes or {})  # cópia: mutação in-place não é gravada
        evaluations = list(notes.get("evaluations", []))
        evaluations.append(
            {
                "competency": data.competency,
                "score": data.score,
                "notes": data.notes,
                "evaluator_id": data.evaluator_id,
                "evaluated_at": datetime.now(UTC).isoformat(),
            }
        )
        notes["evaluations"] = evaluations
        interview.interviewer_notes = notes
        interview.updated_at = datetime.now(UTC)

        await self.session.commit()

        logger.info(
            "Avaliação adicionada",
            extra={
                "interview_id": str(interview.id),
            },
        )

        return interview

    async def get_available_slots(  # pylint: disable=too-many-locals,too-many-nested-blocks
        self,
        interviewer_ids: list[str],
        start_date: date,
        end_date: date,
        duration_minutes: int = 60,
    ) -> list[InterviewSlot]:
        """
        Retorna horários disponíveis para agendamento.

        Args:
            interviewer_ids: IDs dos entrevistadores
            start_date: Data inicial
            end_date: Data final
            duration_minutes: Duração da entrevista

        Returns:
            Lista de slots disponíveis
        """
        # Busca entrevistas já agendadas
        existing = await self.repository.get_by_date_range(start_date, end_date)

        # Horários de trabalho (8h-18h)
        work_start = time(8, 0)
        work_end = time(18, 0)
        slot_duration = timedelta(minutes=duration_minutes)

        slots = []
        current_date = start_date

        while current_date <= end_date:
            # Pula fins de semana
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            current_time = datetime.combine(current_date, work_start)
            end_time_dt = datetime.combine(current_date, work_end)

            while current_time + slot_duration <= end_time_dt:
                slot_time = current_time.time()

                # Verifica conflitos
                has_conflict = False
                for interview in existing:
                    int_date = interview.scheduled_at.date() if interview.scheduled_at else None
                    if int_date != current_date:
                        continue

                    # Verifica se algum entrevistador está ocupado
                    if interview.interviewer_ids:
                        common = set(interviewer_ids) & set(interview.interviewer_ids)
                        if common:
                            int_start = interview.scheduled_at
                            int_end = int_start + timedelta(minutes=interview.duration_minutes or 60)
                            slot_end = current_time + slot_duration

                            if not (slot_end <= int_start or current_time >= int_end):
                                has_conflict = True
                                break

                if not has_conflict:
                    slots.append(
                        InterviewSlot(
                            date=current_date,
                            time=slot_time,
                            duration_minutes=duration_minutes,
                            available=True,
                        )
                    )

                current_time += slot_duration

            current_date += timedelta(days=1)

        return slots

    async def get_calendar(self, interviewer_id: str, month: int, year: int) -> InterviewCalendar:
        """
        Retorna calendário de entrevistas.

        Args:
            interviewer_id: ID do entrevistador
            month: Mês
            year: Ano

        Returns:
            Calendário com entrevistas
        """
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        interviews = await self.repository.get_by_date_range(start_date, end_date, interviewer_id)

        # Group interviews by day
        days: dict[str, list] = {}
        for interview in interviews:
            if interview.scheduled_at:
                day_key = str(interview.scheduled_at.date().day)
                if day_key not in days:
                    days[day_key] = []
                days[day_key].append(str(interview.id))

        return InterviewCalendar(
            month=month,
            year=year,
            interviewer_id=interviewer_id,
            days=days,
            total_interviews=len(interviews),
        )

    async def generate_questions(self, interview_id: str) -> list[dict] | None:
        """
        Gera sugestões de perguntas para entrevista.

        Args:
            interview_id: ID da entrevista

        Returns:
            Lista de perguntas ou None
        """
        interview = await self.repository.get_by_id_with_relations(interview_id)
        if not interview or not interview.application:
            return None

        application = interview.application

        # Busca dados do candidato e vaga
        questions = await self.ai_service.generate_interview_questions(
            application.candidate,
            application.job_position,
        )

        return questions

    async def get_stats(self, application_id: str = None) -> dict:
        """Retorna estatísticas de entrevistas."""
        return await self.repository.get_stats(application_id)

    async def _check_schedule_conflict(
        self,
        scheduled_date: date,
        scheduled_time: time,
        duration_minutes: int,
        interviewer_ids: list[str],
        exclude_interview_id: str = None,
    ) -> str | None:
        """Verifica conflito de horário."""
        if not interviewer_ids:
            return None

        existing = await self.repository.get_by_date_range(scheduled_date, scheduled_date)

        new_start = datetime.combine(scheduled_date, scheduled_time)
        new_end = new_start + timedelta(minutes=duration_minutes)

        for interview in existing:
            if exclude_interview_id and str(interview.id) == exclude_interview_id:
                continue

            if interview.status in [
                InterviewStatus.CANCELADA,
                InterviewStatus.REAGENDADA,
            ]:
                continue

            if not interview.interviewer_ids:
                continue

            common = set(interviewer_ids) & set(interview.interviewer_ids)
            if not common:
                continue

            # Use scheduled_at (datetime) — extract date/time via properties
            int_date = interview.scheduled_at.date() if interview.scheduled_at else None
            int_time = interview.scheduled_at.time() if interview.scheduled_at else None

            if not int_date or not int_time:
                continue

            int_start = datetime.combine(int_date, int_time)
            int_end = int_start + timedelta(minutes=interview.duration_minutes or 60)

            if not (new_end <= int_start or new_start >= int_end):
                return f"Conflito com entrevista {interview.id}"

        return None
