"""
Repository para operações de banco de dados com Occurrence.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from modules.operacional.occurrences.models import Occurrence, OccurrenceStatus
from modules.operacional.occurrences.schemas import (
    OccurrenceCreate,
    OccurrenceFilter,
    OccurrenceResolve,
    OccurrenceStats,
    OccurrenceUpdate,
)


class OccurrenceRepository:
    """Repository para operações CRUD de Occurrence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _generate_code(self) -> str:
        """
        Gera código único para a ocorrência.

        Returns:
            Código no formato OCO-YYYY-NNNNN
        """
        year = datetime.now().year
        result = await self.db.execute(
            select(func.count(Occurrence.id)).where(func.extract("year", Occurrence.created_at) == year)
        )
        count = result.scalar() or 0
        return f"OCO-{year}-{count + 1:05d}"

    async def create(self, data: OccurrenceCreate, inspector_id: str) -> Occurrence:
        """
        Cria uma nova ocorrência disciplinar.

        Args:
            data: Dados da ocorrência
            inspector_id: ID do gestor/supervisor que está fiscalizando

        Returns:
            Occurrence criada
        """
        code = await self._generate_code()

        occurrence = Occurrence(
            id=str(uuid4()),
            code=code,
            title=data.title,
            description=data.description,
            occurrence_type=data.occurrence_type.value,
            severity=data.severity.value,
            category=data.category.value,
            status=OccurrenceStatus.ABERTA.value,
            employee_id=data.employee_id,
            inspector_id=inspector_id,
            post_id=data.post_id,
            patrol_round_id=data.patrol_round_id,
            witnesses=data.witnesses,
            # occurred_at é opcional no form rápido mobile → default: agora
            occurred_at=data.occurred_at or datetime.now(),
            reported_at=datetime.utcnow(),
            created_by=inspector_id,
        )

        self.db.add(occurrence)
        await self.db.commit()
        await self.db.refresh(occurrence)

        logger.info(f"Occurrence criada: {occurrence.id} ({occurrence.code})")
        return occurrence

    async def get_by_id(self, occurrence_id: str) -> Occurrence | None:
        """
        Busca ocorrência por ID.

        Args:
            occurrence_id: ID da ocorrência

        Returns:
            Occurrence ou None
        """
        result = await self.db.execute(
            select(Occurrence).where(
                Occurrence.id == occurrence_id,
                Occurrence.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        filters: OccurrenceFilter | None = None,
        page: int = 1,
        page_size: int = 20,
        post_ids: list[str] | None = None,
    ) -> tuple[list[Occurrence], int]:
        """
        Lista ocorrências com filtros e paginação.

        Args:
            filters: Filtros de busca
            page: Página atual
            page_size: Itens por página
            post_ids: Escopo de postos (None = todos; lista → só esses postos)

        Returns:
            Tupla (ocorrências, total)
        """
        query = select(Occurrence).where(Occurrence.is_active.is_(True))

        if post_ids is not None:
            query = query.where(Occurrence.post_id.in_(post_ids))

        if filters:
            query = self._apply_filters(query, filters)

        # Count total
        count_query = select(func.count(Occurrence.id)).where(Occurrence.is_active.is_(True))
        if post_ids is not None:
            count_query = count_query.where(Occurrence.post_id.in_(post_ids))
        if filters:
            count_query = self._apply_filters(count_query, filters)

        result_count = await self.db.execute(count_query)
        total = result_count.scalar() or 0

        # Pagination and ordering
        query = query.order_by(Occurrence.occurred_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        occurrences = list(result.scalars().all())

        return occurrences, total

    def _apply_filters(self, query, filters: OccurrenceFilter):
        """Aplica filtros na query."""
        if filters.occurrence_type:
            query = query.where(Occurrence.occurrence_type == filters.occurrence_type.value)

        if filters.severity:
            query = query.where(Occurrence.severity == filters.severity.value)

        if filters.category:
            query = query.where(Occurrence.category == filters.category.value)

        if filters.status:
            query = query.where(Occurrence.status == filters.status.value)

        if filters.employee_id:
            query = query.where(Occurrence.employee_id == filters.employee_id)

        if filters.inspector_id:
            query = query.where(Occurrence.inspector_id == filters.inspector_id)

        if filters.post_id:
            query = query.where(Occurrence.post_id == filters.post_id)

        if filters.patrol_round_id:
            query = query.where(Occurrence.patrol_round_id == filters.patrol_round_id)

        if filters.date_from:
            query = query.where(Occurrence.occurred_at >= filters.date_from)

        if filters.date_to:
            query = query.where(Occurrence.occurred_at <= filters.date_to)

        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    Occurrence.title.ilike(search_term),
                    Occurrence.description.ilike(search_term),
                    Occurrence.code.ilike(search_term),
                )
            )

        return query

    async def update(self, occurrence_id: str, data: OccurrenceUpdate) -> Occurrence | None:
        """
        Atualiza uma ocorrência.

        Args:
            occurrence_id: ID da ocorrência
            data: Dados para atualização

        Returns:
            Occurrence atualizada ou None
        """
        occurrence = await self.get_by_id(occurrence_id)
        if not occurrence:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(occurrence, field):
                # Handle enums
                if field in ["occurrence_type", "severity", "category", "status"] and value:
                    setattr(occurrence, field, value.value)
                else:
                    setattr(occurrence, field, value)

        occurrence.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(occurrence)

        logger.info(f"Occurrence atualizada: {occurrence.id}")
        return occurrence

    async def resolve(
        self,
        occurrence_id: str,
        data: OccurrenceResolve,
        resolved_by_id: str,
    ) -> Occurrence | None:
        """
        Resolve uma ocorrência.

        Args:
            occurrence_id: ID da ocorrência
            data: Dados da resolução
            resolved_by_id: ID do usuário que resolveu

        Returns:
            Occurrence resolvida ou None
        """
        occurrence = await self.get_by_id(occurrence_id)
        if not occurrence:
            return None

        occurrence.status = OccurrenceStatus.RESOLVIDA.value
        occurrence.corrective_action = data.corrective_action
        occurrence.resolution_notes = data.resolution_notes
        occurrence.resolved_at = datetime.utcnow()
        occurrence.resolved_by_id = resolved_by_id
        occurrence.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(occurrence)

        logger.info(f"Occurrence resolvida: {occurrence.id}")
        return occurrence

    async def add_attachment(
        self,
        occurrence_id: str,
        attachment: dict,
    ) -> Occurrence | None:
        """
        Adiciona anexo a uma ocorrência.

        Args:
            occurrence_id: ID da ocorrência
            attachment: Dados do anexo {type, url, name, size}

        Returns:
            Occurrence atualizada ou None
        """
        occurrence = await self.get_by_id(occurrence_id)
        if not occurrence:
            return None

        current_attachments = occurrence.attachments or {"attachments": []}
        attachments_list = current_attachments.get("attachments", [])

        attachment["uploaded_at"] = datetime.utcnow().isoformat()
        attachments_list.append(attachment)

        occurrence.attachments = {"attachments": attachments_list}
        occurrence.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(occurrence)

        logger.info(f"Anexo adicionado a Occurrence: {occurrence.id}")
        return occurrence

    async def delete(self, occurrence_id: str) -> bool:
        """
        Soft delete de ocorrência.

        Args:
            occurrence_id: ID da ocorrência

        Returns:
            True se deletada
        """
        occurrence = await self.get_by_id(occurrence_id)
        if not occurrence:
            return False

        occurrence.is_active = False
        occurrence.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(f"Occurrence deletada (soft): {occurrence.id}")
        return True

    async def get_by_post(self, post_id: str) -> list[Occurrence]:
        """
        Busca ocorrências por posto.

        Args:
            post_id: ID do posto

        Returns:
            Lista de ocorrências
        """
        result = await self.db.execute(
            select(Occurrence)
            .where(
                Occurrence.post_id == post_id,
                Occurrence.is_active.is_(True),
            )
            .order_by(Occurrence.occurred_at.desc())
        )
        return list(result.scalars().all())

    async def get_stats(self, post_ids: list[str] | None = None) -> OccurrenceStats:
        """
        Obtém estatísticas de ocorrências.

        Args:
            post_ids: Escopo de postos (None = todos; lista → só esses postos)

        Returns:
            Estatísticas
        """
        query = select(Occurrence).where(Occurrence.is_active.is_(True))
        if post_ids is not None:
            query = query.where(Occurrence.post_id.in_(post_ids))
        result = await self.db.execute(query)
        occurrences = list(result.scalars().all())

        if not occurrences:
            return OccurrenceStats()

        by_status = {}
        by_type = {}
        by_severity = {}
        by_category = {}
        by_employee = {}
        open_count = 0
        in_analysis_count = 0
        resolved_count = 0
        severe_count = 0
        resolution_times = []

        for occ in occurrences:
            by_status[occ.status] = by_status.get(occ.status, 0) + 1
            by_type[occ.occurrence_type] = by_type.get(occ.occurrence_type, 0) + 1
            by_severity[occ.severity] = by_severity.get(occ.severity, 0) + 1
            by_category[occ.category] = by_category.get(occ.category, 0) + 1

            # Contar por funcionário (para ranking) — employee_id pode ser None
            if occ.employee_id:
                by_employee[occ.employee_id] = by_employee.get(occ.employee_id, 0) + 1

            if occ.status == OccurrenceStatus.ABERTA.value:
                open_count += 1
            elif occ.status == OccurrenceStatus.EM_ANALISE.value:
                in_analysis_count += 1
            elif occ.status == OccurrenceStatus.RESOLVIDA.value:
                resolved_count += 1

            if occ.is_severe:
                severe_count += 1

            if occ.resolution_time_hours:
                resolution_times.append(occ.resolution_time_hours)

        avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else None

        return OccurrenceStats(
            total=len(occurrences),
            by_status=by_status,
            by_type=by_type,
            by_severity=by_severity,
            by_category=by_category,
            by_employee=by_employee,
            open=open_count,
            in_analysis=in_analysis_count,
            resolved=resolved_count,
            severe=severe_count,
            avg_resolution_time_hours=avg_resolution_time,
        )
