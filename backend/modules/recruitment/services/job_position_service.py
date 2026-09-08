"""Service para JobPosition."""

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from modules.recruitment.models.job_position import (
    Department,
    JobPosition,
    PositionStatus,
)
from modules.recruitment.repositories.job_position_repository import (
    JobPositionRepository,
)
from modules.recruitment.schemas.job_position import (
    JobPositionCreate,
    JobPositionFilter,
    JobPositionPublish,
    JobPositionUpdate,
)

logger = logging.getLogger(__name__)


class JobPositionService:
    """Service para operações de vagas."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.repository = JobPositionRepository(session)

    async def create(self, data: JobPositionCreate) -> JobPosition:
        """
        Cria uma nova vaga.

        Args:
            data: Dados da vaga

        Returns:
            Vaga criada
        """
        position = await self.repository.create(data)
        await self.session.commit()

        logger.info(
            f"Vaga criada: {position.code} - {position.title}",
            extra={"position_id": str(position.id)},
        )

        return position

    async def get_by_id(self, position_id: str) -> JobPosition | None:
        """Busca vaga por ID."""
        return await self.repository.get_by_id(position_id)

    async def get_by_code(self, code: str) -> JobPosition | None:
        """Busca vaga por código."""
        return await self.repository.get_by_code(code)

    async def update(self, position_id: str, data: JobPositionUpdate) -> JobPosition | None:
        """
        Atualiza uma vaga.

        Args:
            position_id: ID da vaga
            data: Dados para atualização

        Returns:
            Vaga atualizada ou None
        """
        position = await self.repository.update(position_id, data)
        if position:
            await self.session.commit()
            logger.info(
                f"Vaga atualizada: {position.code}",
                extra={"position_id": str(position.id)},
            )
        return position

    async def delete(self, position_id: str) -> bool:
        """
        Remove uma vaga (soft delete).

        Args:
            position_id: ID da vaga

        Returns:
            True se removido com sucesso
        """
        result = await self.repository.soft_delete(position_id)
        if result:
            await self.session.commit()
            logger.info(f"Vaga removida: {position_id}")
        return result

    async def list_with_filters(
        self,
        filters: JobPositionFilter | None = None,
        skip: int = 0,
        limit: int = 20,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> tuple[list[JobPosition], int]:
        """
        Lista vagas com filtros.

        Args:
            filters: Filtros opcionais
            skip: Offset para paginação
            limit: Limite de resultados
            order_by: Campo para ordenação
            order_desc: Se ordenação é descendente

        Returns:
            Tuple com lista de vagas e total
        """
        return await self.repository.list_with_filters(filters, skip, limit, order_by, order_desc)

    async def get_open_positions(self, condominium_id: str = None, skip: int = 0, limit: int = 20) -> list[JobPosition]:
        """Retorna vagas abertas."""
        return await self.repository.get_open_positions(condominium_id, skip, limit)

    async def get_by_department(self, department: Department, status: PositionStatus = None) -> list[JobPosition]:
        """Retorna vagas por departamento."""
        return await self.repository.get_by_department(department, status)

    async def get_expiring_soon(self, days: int = 7) -> list[JobPosition]:
        """Retorna vagas próximas da expiração."""
        return await self.repository.get_expiring_soon(days)

    async def publish(self, position_id: str, data: JobPositionPublish) -> JobPosition | None:
        """
        Publica uma vaga.

        Args:
            position_id: ID da vaga
            data: Dados de publicação

        Returns:
            Vaga publicada ou None
        """
        position = await self.repository.get_by_id(position_id)
        if not position:
            return None

        if position.status != PositionStatus.RASCUNHO:
            raise ValueError("Apenas vagas em rascunho podem ser publicadas")

        position.status = PositionStatus.ABERTA
        position.published_at = data.published_at or date.today()

        if data.deadline_date:
            position.deadline = data.deadline_date

        await self.session.flush()
        await self.session.commit()

        logger.info(
            f"Vaga publicada: {position.code}",
            extra={"position_id": str(position.id)},
        )

        return position

    async def pause(self, position_id: str, reason: str = None) -> JobPosition | None:
        """
        Pausa uma vaga.

        Args:
            position_id: ID da vaga
            reason: Motivo da pausa

        Returns:
            Vaga pausada ou None
        """
        position = await self.repository.get_by_id(position_id)
        if not position:
            return None

        if position.status != PositionStatus.ABERTA:
            raise ValueError("Apenas vagas abertas podem ser pausadas")

        position.status = PositionStatus.PAUSADA  # model não tem pause(): era AttributeError/500
        if reason:
            position.internal_notes = ((getattr(position, 'internal_notes', '') or '') + f'\n[pausa] {reason}').strip()
        await self.session.commit()

        logger.info(
            f"Vaga pausada: {position.code}",
            extra={"position_id": str(position.id), "reason": reason},
        )

        return position

    async def reopen(self, position_id: str) -> JobPosition | None:
        """
        Reabre uma vaga pausada.

        Args:
            position_id: ID da vaga

        Returns:
            Vaga reaberta ou None
        """
        position = await self.repository.get_by_id(position_id)
        if not position:
            return None

        if position.status != PositionStatus.PAUSADA:
            raise ValueError("Apenas vagas pausadas podem ser reabertas")

        position.status = PositionStatus.ABERTA
        await self.session.commit()

        logger.info(
            f"Vaga reaberta: {position.code}",
            extra={"position_id": str(position.id)},
        )

        return position

    async def close(self, position_id: str, reason: str = None) -> JobPosition | None:
        """
        Fecha uma vaga.

        Args:
            position_id: ID da vaga
            reason: Motivo do fechamento

        Returns:
            Vaga fechada ou None
        """
        position = await self.repository.get_by_id(position_id)
        if not position:
            return None

        from datetime import UTC, datetime as _dt
        position.status = PositionStatus.FECHADA
        if hasattr(position, 'closed_at'):
            position.closed_at = _dt.now(UTC)
        if reason:
            position.internal_notes = ((getattr(position, 'internal_notes', '') or '') + f'\n[fechamento] {reason}').strip()
        await self.session.commit()

        logger.info(
            f"Vaga fechada: {position.code}",
            extra={"position_id": str(position.id), "reason": reason},
        )

        return position

    async def fill_vacancy(self, position_id: str) -> JobPosition | None:
        """
        Preenche uma vaga.

        Args:
            position_id: ID da vaga

        Returns:
            Vaga atualizada ou None
        """
        position = await self.repository.fill_vacancy(position_id)
        if position:
            await self.session.commit()
            logger.info(
                f"Vaga preenchida: {position.code} ({position.filled_count}/{position.vacancies})",
                extra={"position_id": str(position.id)},
            )
        return position

    async def increment_view(self, position_id: str) -> None:
        """Incrementa visualização."""
        await self.repository.increment_view(position_id)
        await self.session.commit()

    async def increment_application(self, position_id: str) -> None:
        """Incrementa candidaturas."""
        await self.repository.increment_application(position_id)
        await self.session.commit()

    async def get_stats(self, condominium_id: str = None) -> dict:
        """Retorna estatísticas de vagas."""
        return await self.repository.get_stats(condominium_id)

    async def duplicate(self, position_id: str) -> JobPosition | None:
        """
        Duplica uma vaga existente.

        Args:
            position_id: ID da vaga original

        Returns:
            Nova vaga ou None
        """
        original = await self.repository.get_by_id(position_id)
        if not original:
            return None

        # Cria cópia
        data = JobPositionCreate(
            title=f"{original.title} (Cópia)",
            description=original.description,
            requirements=original.requirements,
            responsibilities=original.responsibilities,
            benefits=original.benefits,
            position_type=original.position_type,
            position_level=original.position_level,
            department=original.department,
            work_model=original.work_model,
            salary_min=original.salary_min,
            salary_max=original.salary_max,
            show_salary=original.show_salary if hasattr(original, "show_salary") else False,
            vacancies=original.vacancies,
            city=original.city,
            state=original.state,
            address=original.address,
            required_skills=original.required_skills,
            desired_skills=original.desired_skills,
            min_experience_years=original.min_experience_years,
            education_level=original.education_level,
            condominio_id=original.condominio_id,
            responsible_id=original.responsible_id,
        )

        new_position = await self.repository.create(data)
        await self.session.commit()

        logger.info(
            f"Vaga duplicada: {original.code} -> {new_position.code}",
            extra={
                "original_id": str(original.id),
                "new_id": str(new_position.id),
            },
        )

        return new_position
