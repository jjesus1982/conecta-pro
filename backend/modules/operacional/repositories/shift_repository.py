"""
Repository para operações de banco de dados com Shift.
"""

import builtins
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from modules.operacional.models.shift import Shift, ShiftStatus
from modules.operacional.schemas.shift import (
    ShiftBulkUpdateItem,
    ShiftCreate,
    ShiftFilter,
    ShiftUpdate,
)


class ShiftRepository:
    """Repository para operações CRUD de Shift."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: ShiftCreate) -> Shift:
        """
        Cria um novo turno.

        Args:
            data: Dados do turno

        Returns:
            Shift criado
        """
        shift = Shift(
            id=str(uuid4()),
            scale_id=data.scale_id,
            employee_id=data.employee_id,
            post_id=data.post_id,
            shift_date=data.shift_date,
            planned_start_time=data.planned_start_time,
            planned_end_time=data.planned_end_time,
            planned_break_minutes=data.planned_break_minutes or 60,
            status=ShiftStatus.SCHEDULED.value,
            is_holiday=data.is_holiday,
            is_night_shift=data.is_night_shift,
            is_off_day=data.is_off_day,
            planned_hours=data.planned_hours,
            notes=data.notes,
        )

        # Calcula horas se não informado
        if shift.planned_hours == 0 and not shift.is_off_day:
            shift.planned_hours = shift.calculate_hours()

        self.db.add(shift)
        await self.db.commit()
        await self.db.refresh(shift)

        logger.debug(f"Shift criado: {shift.id}")
        return shift

    async def create_bulk(self, shifts_data: list[ShiftCreate]) -> list[Shift]:
        """
        Cria múltiplos turnos.

        Args:
            shifts_data: Lista de dados dos turnos

        Returns:
            Lista de Shifts criados
        """
        shifts = []
        for data in shifts_data:
            shift = Shift(
                id=str(uuid4()),
                scale_id=data.scale_id,
                employee_id=data.employee_id,
                post_id=data.post_id,
                shift_date=data.shift_date,
                planned_start_time=data.planned_start_time,
                planned_end_time=data.planned_end_time,
                planned_break_minutes=data.planned_break_minutes or 60,
                status=ShiftStatus.SCHEDULED.value,
                is_holiday=data.is_holiday,
                is_night_shift=data.is_night_shift,
                is_off_day=data.is_off_day,
                planned_hours=data.planned_hours or 0,
                notes=data.notes,
            )

            if shift.planned_hours == 0 and not shift.is_off_day:
                shift.planned_hours = shift.calculate_hours()

            shifts.append(shift)
            self.db.add(shift)

        await self.db.commit()

        for shift in shifts:
            await self.db.refresh(shift)

        logger.info(f"Criados {len(shifts)} turnos em lote")
        return shifts

    async def get_by_id(self, shift_id: str) -> Shift | None:
        """
        Busca turno por ID.

        Args:
            shift_id: ID do turno

        Returns:
            Shift ou None
        """
        result = await self.db.execute(select(Shift).where(Shift.id == shift_id, Shift.is_active.is_(True)))
        return result.scalar_one_or_none()

    async def list(
        self,
        filters: ShiftFilter | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Shift], int]:
        """
        Lista turnos com filtros e paginação.

        Args:
            filters: Filtros de busca
            page: Página atual
            page_size: Itens por página

        Returns:
            Tupla (turnos, total)
        """
        query = select(Shift).where(Shift.is_active.is_(True))

        if filters:
            query = self._apply_filters(query, filters)

        # Count total
        count_query = select(func.count(Shift.id)).where(Shift.is_active.is_(True))
        if filters:
            count_query = self._apply_filters(count_query, filters)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(Shift.shift_date, Shift.planned_start_time)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        shifts = list(result.scalars().all())

        return shifts, total

    def _apply_filters(self, query, filters: ShiftFilter):  # pylint: disable=too-many-branches
        """Aplica filtros à query."""
        if filters.scale_id:
            query = query.where(Shift.scale_id == filters.scale_id)

        if filters.employee_id:
            query = query.where(Shift.employee_id == filters.employee_id)

        if filters.post_id:
            query = query.where(Shift.post_id == filters.post_id)

        if filters.status:
            query = query.where(Shift.status == filters.status.value)

        if filters.start_date:
            query = query.where(Shift.shift_date >= filters.start_date)

        if filters.end_date:
            query = query.where(Shift.shift_date <= filters.end_date)

        if filters.is_holiday is not None:
            query = query.where(Shift.is_holiday == filters.is_holiday)

        if filters.is_night_shift is not None:
            query = query.where(Shift.is_night_shift == filters.is_night_shift)

        if filters.is_off_day is not None:
            query = query.where(Shift.is_off_day == filters.is_off_day)

        if filters.is_filled is not None:
            if filters.is_filled:
                query = query.where(Shift.employee_id.isnot(None))
            else:
                query = query.where(Shift.employee_id.is_(None))

        if filters.needs_substitution:
            query = query.where(Shift.needs_substitution.is_(True))

        return query

    async def update(self, shift_id: str, data: ShiftUpdate) -> Shift | None:
        """
        Atualiza um turno.

        Args:
            shift_id: ID do turno
            data: Dados para atualização

        Returns:
            Shift atualizado ou None
        """
        shift = await self.get_by_id(shift_id)
        if not shift:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "status" and value:
                setattr(shift, field, value.value)
            else:
                setattr(shift, field, value)

        shift.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(shift)

        logger.debug(f"Shift atualizado: {shift.id}")
        return shift

    async def delete(self, shift_id: str) -> bool:
        """
        Soft delete de turno.

        Args:
            shift_id: ID do turno

        Returns:
            True se deletado
        """
        shift = await self.get_by_id(shift_id)
        if not shift:
            return False

        shift.is_active = False
        shift.status = ShiftStatus.CANCELLED.value
        shift.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.debug(f"Shift deletado (soft): {shift.id}")
        return True

    async def get_by_scale(self, scale_id: str) -> builtins.list[Shift]:
        """
        Lista turnos de uma escala.

        Args:
            scale_id: ID da escala

        Returns:
            Lista de turnos
        """
        result = await self.db.execute(
            select(Shift)
            .where(
                Shift.scale_id == scale_id,
                Shift.is_active.is_(True),
            )
            .order_by(Shift.shift_date, Shift.planned_start_time)
        )
        return list(result.scalars().all())

    async def get_by_employee_and_date(self, employee_id: str, shift_date: date) -> builtins.list[Shift]:
        """
        Busca turnos de um funcionário em uma data.

        Args:
            employee_id: ID do funcionário
            shift_date: Data

        Returns:
            Lista de turnos
        """
        result = await self.db.execute(
            select(Shift).where(
                Shift.employee_id == employee_id,
                Shift.shift_date == shift_date,
                Shift.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def check_in(self, shift_id: str, actual_start_time, notes: str | None = None) -> Shift | None:
        """
        Registra entrada no turno.

        Args:
            shift_id: ID do turno
            actual_start_time: Hora real de entrada
            notes: Observações

        Returns:
            Shift atualizado ou None
        """
        shift = await self.get_by_id(shift_id)
        if not shift:
            return None

        shift.actual_start_time = actual_start_time
        shift.status = ShiftStatus.IN_PROGRESS.value
        if notes:
            shift.notes = f"{shift.notes or ''}\n[Check-in] {notes}".strip()
        shift.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(shift)

        logger.info(f"Check-in registrado: {shift.id}")
        return shift

    async def check_out(
        self,
        shift_id: str,
        actual_end_time,
        actual_break_minutes: int = 0,
        notes: str | None = None,
    ) -> Shift | None:
        """
        Registra saída do turno.

        Args:
            shift_id: ID do turno
            actual_end_time: Hora real de saída
            actual_break_minutes: Intervalo em minutos
            notes: Observações

        Returns:
            Shift atualizado ou None
        """
        shift = await self.get_by_id(shift_id)
        if not shift:
            return None

        shift.actual_end_time = actual_end_time
        shift.actual_break_minutes = actual_break_minutes
        shift.status = ShiftStatus.COMPLETED.value

        # Calcular horas reais trabalhadas
        if shift.actual_start_time:
            start_time = (
                shift.actual_start_time.time()
                if isinstance(shift.actual_start_time, datetime)
                else shift.actual_start_time
            )
            end_time = actual_end_time.time() if isinstance(actual_end_time, datetime) else actual_end_time
            start = datetime.combine(shift.shift_date, start_time)
            end = datetime.combine(shift.shift_date, end_time)

            if end <= start:  # Turno noturno (cruza a meia-noite)
                # timedelta rola mês/ano corretamente; .replace(day=day+1) estourava
                # ValueError no último dia do mês (dia 30/31 → day=32) = 500 no check-out.
                end = end + timedelta(days=1)

            duration = (end - start).total_seconds() / 3600
            shift.actual_hours = max(0, duration - (actual_break_minutes / 60))

            # Calcular hora extra
            shift.overtime_hours = shift.calculate_overtime()

        if notes:
            shift.notes = f"{shift.notes or ''}\n[Check-out] {notes}".strip()
        shift.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(shift)

        logger.info(f"Check-out registrado: {shift.id}")
        return shift

    async def mark_as_missed(self, shift_id: str, reason: str | None = None) -> Shift | None:
        """
        Marca turno como falta.

        Args:
            shift_id: ID do turno
            reason: Motivo da falta

        Returns:
            Shift atualizado ou None
        """
        shift = await self.get_by_id(shift_id)
        if not shift:
            return None

        shift.status = ShiftStatus.MISSED.value
        shift.needs_substitution = True
        if reason:
            shift.notes = f"{shift.notes or ''}\n[Falta] {reason}".strip()
        shift.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(shift)

        logger.info(f"Turno marcado como falta: {shift.id}")
        return shift

    async def bulk_update(self, items: builtins.list[ShiftBulkUpdateItem]) -> dict:
        """
        Atualiza múltiplos turnos em lote.

        Args:
            items: Lista de itens com shift_id e dados para atualização

        Returns:
            Dict com:
                - success_count: quantidade de sucessos
                - error_count: quantidade de erros
                - errors: lista de erros [{"id": shift_id, "error": mensagem}]
        """
        success_count = 0
        error_count = 0
        errors = []

        for item in items:
            try:
                shift = await self.update(item.shift_id, item.data)
                if shift:
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(
                        {
                            "id": item.shift_id,
                            "error": "Turno não encontrado",
                        }
                    )
            except ValueError as e:
                # Erro de validação (horários, etc)
                error_count += 1
                errors.append(
                    {
                        "id": item.shift_id,
                        "error": str(e),
                    }
                )
                logger.warning(
                    "Erro de validação ao atualizar turno em bulk",
                    action="bulk_update_shift",
                    shift_id=item.shift_id,
                    error=str(e),
                )
            except Exception as e:  # pylint: disable=broad-except
                error_count += 1
                errors.append(
                    {
                        "id": item.shift_id,
                        "error": str(e),
                    }
                )
                logger.error(
                    "Erro ao atualizar turno em bulk",
                    action="bulk_update_shift",
                    shift_id=item.shift_id,
                    error=str(e),
                )

        logger.info(
            "Bulk update de turnos finalizado",
            action="bulk_update_shifts",
            total=len(items),
            success=success_count,
            errors=error_count,
        )

        return {
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors,
        }
