"""Repository para TimeJustification."""

import builtins
from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.time_tracking.models import (
    JustificationStatus,
    JustificationType,
    TimeJustification,
)
from modules.hr.time_tracking.schemas import (
    TimeJustificationCreate,
    TimeJustificationFilter,
    TimeJustificationUpdate,
)


class TimeJustificationRepository:
    """Repository para operações de TimeJustification."""

    def __init__(self, db: AsyncSession):
        """Inicializa o repository."""
        self.db = db

    async def create(
        self,
        data: TimeJustificationCreate,
        created_by_id: str = None,
    ) -> TimeJustification:
        """Cria uma nova justificativa."""
        justification = TimeJustification(
            **data.model_dump(exclude_unset=True),
            created_by_id=created_by_id,
        )
        self.db.add(justification)
        await self.db.flush()
        await self.db.refresh(justification)
        return justification

    async def get_by_id(self, justification_id: UUID) -> TimeJustification | None:
        """Busca justificativa por ID."""
        result = await self.db.execute(
            select(TimeJustification).where(
                TimeJustification.id == justification_id,
                TimeJustification.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> TimeJustification | None:
        """Busca justificativa por código."""
        result = await self.db.execute(
            select(TimeJustification).where(
                TimeJustification.code == code,
                TimeJustification.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        justification: TimeJustification,
        data: TimeJustificationUpdate,
    ) -> TimeJustification:
        """Atualiza uma justificativa."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(justification, field, value)
        await self.db.flush()
        await self.db.refresh(justification)
        return justification

    async def delete(self, justification: TimeJustification) -> None:
        """Soft delete de uma justificativa."""
        justification.soft_delete()
        await self.db.flush()

    async def list(  # pylint: disable=too-many-branches
        self,
        filters: TimeJustificationFilter = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[TimeJustification], int]:
        """Lista justificativas com filtros."""
        query = select(TimeJustification).where(TimeJustification.is_deleted.is_(False))

        if filters:
            if filters.employee_id:
                query = query.where(TimeJustification.employee_id == filters.employee_id)
            if filters.justification_type:
                query = query.where(TimeJustification.justification_type == filters.justification_type)
            if filters.category:
                query = query.where(TimeJustification.category == filters.category)
            if filters.status:
                query = query.where(TimeJustification.status == filters.status)
            if filters.condominium_id:
                query = query.where(TimeJustification.condominium_id == filters.condominium_id)
            if filters.department_id:
                query = query.where(TimeJustification.department_id == filters.department_id)
            if filters.date_from:
                query = query.where(TimeJustification.start_date >= filters.date_from)
            if filters.date_to:
                query = query.where(TimeJustification.end_date <= filters.date_to)
            if filters.is_pending is not None:
                if filters.is_pending:
                    query = query.where(
                        TimeJustification.status.in_(
                            [
                                JustificationStatus.RASCUNHO,
                                JustificationStatus.PENDENTE,
                                JustificationStatus.EM_ANALISE,
                            ]
                        )
                    )
                else:
                    query = query.where(
                        TimeJustification.status.in_(
                            [
                                JustificationStatus.APROVADA,
                                JustificationStatus.REJEITADA,
                            ]
                        )
                    )
            if filters.is_verified is not None:
                query = query.where(TimeJustification.is_verified == filters.is_verified)
            if filters.has_attachments is not None:
                query = query.where(TimeJustification.has_attachments == filters.has_attachments)
            if filters.is_late_submission is not None:
                query = query.where(TimeJustification.is_late_submission == filters.is_late_submission)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        query = query.order_by(TimeJustification.start_date.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        justifications = result.scalars().all()

        return list(justifications), total

    async def get_by_employee_period(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
    ) -> builtins.list[TimeJustification]:
        """Busca justificativas de um funcionário em um período."""
        result = await self.db.execute(
            select(TimeJustification)
            .where(
                TimeJustification.employee_id == employee_id,
                or_(
                    and_(
                        TimeJustification.start_date >= start_date,
                        TimeJustification.start_date <= end_date,
                    ),
                    and_(
                        TimeJustification.end_date >= start_date,
                        TimeJustification.end_date <= end_date,
                    ),
                    and_(
                        TimeJustification.start_date <= start_date,
                        TimeJustification.end_date >= end_date,
                    ),
                ),
                TimeJustification.is_deleted.is_(False),
            )
            .order_by(TimeJustification.start_date)
        )
        return list(result.scalars().all())

    async def get_pending_approval(
        self,
        condominium_id: str = None,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[TimeJustification]:
        """Busca justificativas pendentes de aprovação."""
        query = select(TimeJustification).where(
            TimeJustification.status.in_(
                [
                    JustificationStatus.PENDENTE,
                    JustificationStatus.EM_ANALISE,
                ]
            ),
            TimeJustification.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(TimeJustification.condominium_id == condominium_id)

        query = query.order_by(TimeJustification.start_date.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_pending_verification(
        self,
        condominium_id: str = None,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[TimeJustification]:
        """Busca justificativas aprovadas pendentes de verificação do RH."""
        query = select(TimeJustification).where(
            TimeJustification.status == JustificationStatus.APROVADA,
            TimeJustification.is_verified.is_(False),
            TimeJustification.is_deleted.is_(False),
        )

        if condominium_id:
            query = query.where(TimeJustification.condominium_id == condominium_id)

        query = query.order_by(TimeJustification.start_date.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_date(
        self,
        employee_id: str,
        target_date: date,
    ) -> builtins.list[TimeJustification]:
        """Busca justificativas que cobrem uma data específica."""
        result = await self.db.execute(
            select(TimeJustification).where(
                TimeJustification.employee_id == employee_id,
                TimeJustification.start_date <= target_date,
                TimeJustification.end_date >= target_date,
                TimeJustification.status == JustificationStatus.APROVADA,
                TimeJustification.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def get_medical_leaves(
        self,
        employee_id: str = None,
        condominium_id: str = None,
        date_from: date = None,
        date_to: date = None,
    ) -> builtins.list[TimeJustification]:
        """Busca atestados médicos."""
        # só membros REAIS do enum (ATESTADO_MEDICO/ATESTADO_ACOMPANHANTE/DOENCA_OCUPACIONAL
        # não existem em JustificationType → crashavam a rota)
        medical_types = [
            JustificationType.LICENCA_MEDICA,
            JustificationType.ACOMPANHAMENTO_FAMILIAR,
            JustificationType.LICENCA_MATERNIDADE,
            JustificationType.LICENCA_PATERNIDADE,
            JustificationType.ACIDENTE_TRABALHO,
            JustificationType.CONSULTA_MEDICA,
        ]

        query = select(TimeJustification).where(
            TimeJustification.justification_type.in_(medical_types),
            TimeJustification.is_deleted.is_(False),
        )

        if employee_id:
            query = query.where(TimeJustification.employee_id == employee_id)
        if condominium_id:
            query = query.where(TimeJustification.condominium_id == condominium_id)
        if date_from:
            query = query.where(TimeJustification.start_date >= date_from)
        if date_to:
            query = query.where(TimeJustification.end_date <= date_to)

        result = await self.db.execute(query.order_by(TimeJustification.start_date.desc()))
        return list(result.scalars().all())

    async def get_stats(  # pylint: disable=too-many-locals
        self,
        condominium_id: str = None,
        employee_id: str = None,
        date_from: date = None,
        date_to: date = None,
    ) -> dict:
        """Calcula estatísticas de justificativas."""
        base_where = [TimeJustification.is_deleted.is_(False)]

        if condominium_id:
            base_where.append(TimeJustification.condominium_id == condominium_id)
        if employee_id:
            base_where.append(TimeJustification.employee_id == employee_id)
        if date_from:
            base_where.append(TimeJustification.start_date >= date_from)
        if date_to:
            base_where.append(TimeJustification.end_date <= date_to)

        # Total
        total_result = await self.db.execute(select(func.count()).where(*base_where))
        total = total_result.scalar() or 0

        # Por status
        status_result = await self.db.execute(
            select(TimeJustification.status, func.count()).where(*base_where).group_by(TimeJustification.status)
        )
        by_status = {row[0].value: row[1] for row in status_result.all()}

        # Por tipo
        type_result = await self.db.execute(
            select(TimeJustification.justification_type, func.count())
            .where(*base_where)
            .group_by(TimeJustification.justification_type)
        )
        by_type = {row[0].value: row[1] for row in type_result.all()}

        # Por categoria
        category_result = await self.db.execute(
            select(TimeJustification.category, func.count()).where(*base_where).group_by(TimeJustification.category)
        )
        by_category = {row[0].value: row[1] for row in category_result.all()}

        # Total de dias justificados
        days_result = await self.db.execute(
            select(func.sum(TimeJustification.days_count)).where(
                *base_where,
                TimeJustification.status == JustificationStatus.APROVADA,
            )
        )
        total_days = days_result.scalar() or 0

        # Pendentes
        pending_result = await self.db.execute(
            select(func.count()).where(
                *base_where,
                TimeJustification.status.in_(
                    [
                        JustificationStatus.PENDENTE,
                        JustificationStatus.EM_ANALISE,
                    ]
                ),
            )
        )
        pending_count = pending_result.scalar() or 0

        # Submissões atrasadas
        late_result = await self.db.execute(
            select(func.count()).where(
                *base_where,
                TimeJustification.is_late_submission.is_(True),
            )
        )
        late_count = late_result.scalar() or 0

        # Pendentes verificação
        verification_result = await self.db.execute(
            select(func.count()).where(
                *base_where,
                TimeJustification.status == JustificationStatus.APROVADA,
                TimeJustification.is_verified.is_(False),
            )
        )
        verification_pending = verification_result.scalar() or 0

        return {
            "total_justifications": total,
            "by_status": by_status,
            "by_type": by_type,
            "by_category": by_category,
            "total_days_justified": total_days,
            "pending_count": pending_count,
            "late_submissions_count": late_count,
            "pending_verification_count": verification_pending,
        }

    async def check_overlap(
        self,
        employee_id: str,
        start_date: date,
        end_date: date,
        exclude_id: UUID = None,
    ) -> TimeJustification | None:
        """Verifica sobreposição de justificativas."""
        query = select(TimeJustification).where(
            TimeJustification.employee_id == employee_id,
            or_(
                and_(
                    TimeJustification.start_date >= start_date,
                    TimeJustification.start_date <= end_date,
                ),
                and_(
                    TimeJustification.end_date >= start_date,
                    TimeJustification.end_date <= end_date,
                ),
                and_(
                    TimeJustification.start_date <= start_date,
                    TimeJustification.end_date >= end_date,
                ),
            ),
            TimeJustification.status != JustificationStatus.REJEITADA,
            TimeJustification.is_deleted.is_(False),
        )

        if exclude_id:
            query = query.where(TimeJustification.id != exclude_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()
