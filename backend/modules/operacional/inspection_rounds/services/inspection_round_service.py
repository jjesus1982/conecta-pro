"""
Service de Rondas de Inspecao - Versao Async.

Author: Conecta PRO Team
Date: 2026-01-23
"""

import builtins
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    InspectionCheckpoint,
    InspectionRound,
    InspectionRoundStatus,
    InspectorRole,
)
from ..repositories import InspectionRoundRepository
from ..schemas import (
    CheckpointCreate,
    CompleteRoundRequest,
    InspectionDashboardStats,
    InspectionRoundCreate,
    InspectionRoundFilter,
    InspectionRoundUpdate,
    InspectorStats,
    StartRoundRequest,
)

logger = logging.getLogger(__name__)


class InspectionRoundNotFoundError(Exception):
    """Ronda nao encontrada."""

    pass


class InspectionRoundValidationError(Exception):
    """Erro de validacao."""

    pass


class InspectionRoundService:
    """Service para gerenciamento de Rondas de Inspecao."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = InspectionRoundRepository(db)

    # ==========================================================================
    # CRUD RONDAS
    # ==========================================================================

    async def create(self, data: InspectionRoundCreate) -> InspectionRound:
        """Cria uma nova ronda de inspecao."""
        valid_roles = [r.value for r in InspectorRole]
        if data.inspector_role not in valid_roles:
            raise InspectionRoundValidationError(f"Cargo invalido. Valores validos: {valid_roles}")

        year = datetime.utcnow().year
        sequence = await self.repository.get_next_sequence(str(data.tenant_id), year)
        code = InspectionRound.generate_code(year, sequence)

        round_data = {
            "code": code,
            "tenant_id": str(data.tenant_id),
            "inspector_id": str(data.inspector_id),
            "inspector_name": data.inspector_name,
            "inspector_role": data.inspector_role,
            "status": InspectionRoundStatus.AGENDADA.value,
            "scheduled_date": data.scheduled_date,
            "posts_to_visit": [str(p) for p in data.posts_to_visit] if data.posts_to_visit else [],
            "observations": data.observations,
            "created_by": str(data.inspector_id),
        }

        inspection_round = await self.repository.create(round_data)
        logger.info(f"Ronda criada: {code} por {data.inspector_name}")

        return inspection_round

    async def get_by_id(self, round_id: str) -> InspectionRound:
        """Busca ronda por ID."""
        inspection_round = await self.repository.get_by_id(round_id)
        if not inspection_round:
            raise InspectionRoundNotFoundError(f"Ronda {round_id} nao encontrada")
        return inspection_round

    async def get_by_code(self, code: str) -> InspectionRound:
        """Busca ronda por codigo."""
        inspection_round = await self.repository.get_by_code(code)
        if not inspection_round:
            raise InspectionRoundNotFoundError(f"Ronda {code} nao encontrada")
        return inspection_round

    async def list(
        self,
        tenant_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
        filters: InspectionRoundFilter | None = None,
    ) -> tuple[list[InspectionRound], int]:
        """Lista rondas com filtros."""
        return await self.repository.list(tenant_id, skip, limit, filters)

    async def get_rounds_by_inspector(
        self,
        inspector_id: str,
        tenant_id: str,
        limit: int = 50,
    ) -> builtins.list[InspectionRound]:
        """Lista rondas de um inspetor (mais recentes primeiro)."""
        filters = InspectionRoundFilter(inspector_id=inspector_id)
        rounds, _total = await self.repository.list(
            tenant_id=tenant_id,
            skip=0,
            limit=limit,
            filters=filters,
        )
        return rounds

    async def update(self, round_id: str, data: InspectionRoundUpdate) -> InspectionRound:
        """Atualiza uma ronda."""
        inspection_round = await self.get_by_id(round_id)

        if inspection_round.status not in [
            InspectionRoundStatus.AGENDADA.value,
            InspectionRoundStatus.PAUSADA.value,
        ]:
            raise InspectionRoundValidationError("Ronda nao pode ser editada no status atual")

        if data.scheduled_date is not None:
            inspection_round.scheduled_date = data.scheduled_date
        if data.posts_to_visit is not None:
            inspection_round.posts_to_visit = [str(p) for p in data.posts_to_visit]
        if data.observations is not None:
            inspection_round.observations = data.observations
        if data.summary is not None:
            inspection_round.summary = data.summary

        return await self.repository.update(inspection_round)

    async def delete(self, round_id: str) -> None:
        """Remove uma ronda (soft delete)."""
        inspection_round = await self.get_by_id(round_id)

        if inspection_round.status == InspectionRoundStatus.EM_ANDAMENTO.value:
            raise InspectionRoundValidationError("Nao e possivel deletar ronda em andamento")

        await self.repository.delete(inspection_round)
        logger.info(f"Ronda deletada: {inspection_round.code}")

    # ==========================================================================
    # WORKFLOW DA RONDA
    # ==========================================================================

    async def start_round(
        self,
        round_id: str,
        data: StartRoundRequest | None = None,
    ) -> InspectionRound:
        """Inicia uma ronda."""
        inspection_round = await self.get_by_id(round_id)

        if inspection_round.status not in [
            InspectionRoundStatus.AGENDADA.value,
            InspectionRoundStatus.PAUSADA.value,
        ]:
            raise InspectionRoundValidationError(f"Ronda no status '{inspection_round.status}' nao pode ser iniciada")

        latitude = data.latitude if data else None
        longitude = data.longitude if data else None

        inspection_round.start(latitude, longitude)
        await self.repository.update(inspection_round)

        logger.info(f"Ronda iniciada: {inspection_round.code}")
        return inspection_round

    async def pause_round(self, round_id: str) -> InspectionRound:
        """Pausa uma ronda."""
        inspection_round = await self.get_by_id(round_id)

        if inspection_round.status != InspectionRoundStatus.EM_ANDAMENTO.value:
            raise InspectionRoundValidationError("Ronda nao esta em andamento")

        inspection_round.pause()
        await self.repository.update(inspection_round)

        logger.info(f"Ronda pausada: {inspection_round.code}")
        return inspection_round

    async def resume_round(self, round_id: str) -> InspectionRound:
        """Retoma uma ronda pausada."""
        inspection_round = await self.get_by_id(round_id)

        if inspection_round.status != InspectionRoundStatus.PAUSADA.value:
            raise InspectionRoundValidationError("Ronda nao esta pausada")

        inspection_round.resume()
        await self.repository.update(inspection_round)

        logger.info(f"Ronda retomada: {inspection_round.code}")
        return inspection_round

    async def complete_round(
        self,
        round_id: str,
        data: CompleteRoundRequest | None = None,
    ) -> InspectionRound:
        """Conclui uma ronda."""
        inspection_round = await self.get_by_id(round_id)

        if inspection_round.status != InspectionRoundStatus.EM_ANDAMENTO.value:
            raise InspectionRoundValidationError("Ronda nao esta em andamento")

        summary = data.summary if data else None
        latitude = data.latitude if data else None
        longitude = data.longitude if data else None

        inspection_round.complete(summary, latitude, longitude)

        checkpoints = await self.repository.get_checkpoints_by_round(round_id)
        inspection_round.total_checkpoints = len(checkpoints)

        await self.repository.update(inspection_round)

        logger.info(f"Ronda concluida: {inspection_round.code} - {inspection_round.total_occurrences} ocorrencias")
        return inspection_round

    async def cancel_round(self, round_id: str, reason: str | None = None) -> InspectionRound:
        """Cancela uma ronda."""
        inspection_round = await self.get_by_id(round_id)

        if inspection_round.status == InspectionRoundStatus.CONCLUIDA.value:
            raise InspectionRoundValidationError("Ronda ja concluida nao pode ser cancelada")

        inspection_round.cancel(reason)
        await self.repository.update(inspection_round)

        logger.info(f"Ronda cancelada: {inspection_round.code}")
        return inspection_round

    # ==========================================================================
    # CHECKPOINTS
    # ==========================================================================

    async def create_checkpoint(
        self,
        round_id: str,
        data: CheckpointCreate,
    ) -> InspectionCheckpoint:
        """Cria um checkpoint durante a ronda."""
        inspection_round = await self.get_by_id(round_id)

        if inspection_round.status != InspectionRoundStatus.EM_ANDAMENTO.value:
            raise InspectionRoundValidationError("Ronda nao esta em andamento")

        sequence = await self.repository.get_next_checkpoint_sequence(round_id)

        checkpoint_data = {
            "inspection_round_id": round_id,
            "post_id": str(data.post_id) if data.post_id else None,
            "post_name": data.post_name,
            "checkpoint_type": data.checkpoint_type,
            "status": data.status,
            "employee_id": str(data.employee_id) if data.employee_id else None,
            "employee_name": data.employee_name,
            "title": data.title,
            "description": data.description,
            "observations": data.observations,
            "photos": data.photos or [],
            "latitude": data.latitude,
            "longitude": data.longitude,
            "sequence": sequence,
            "created_by": inspection_round.inspector_id,
        }

        checkpoint = await self.repository.create_checkpoint(checkpoint_data)

        inspection_round.total_checkpoints += 1
        if data.post_id:
            inspection_round.add_visited_post(str(data.post_id))

        await self.repository.update(inspection_round)

        logger.info(f"Checkpoint criado na ronda {inspection_round.code}")
        return checkpoint

    async def get_checkpoints(self, round_id: str) -> builtins.list[InspectionCheckpoint]:
        """Lista checkpoints de uma ronda."""
        return await self.repository.get_checkpoints_by_round(round_id)

    # ==========================================================================
    # ESTATISTICAS
    # ==========================================================================

    async def get_dashboard_stats(self, tenant_id: str | None = None) -> InspectionDashboardStats:
        """Retorna estatisticas do dashboard."""
        status_counts = await self.repository.count_by_status(tenant_id)
        in_progress = await self.repository.get_rounds_in_progress(tenant_id)
        scheduled_today = await self.repository.get_rounds_scheduled_today(tenant_id)

        total = sum(status_counts.values())
        completed = status_counts.get(InspectionRoundStatus.CONCLUIDA.value, 0)
        scheduled = status_counts.get(InspectionRoundStatus.AGENDADA.value, 0)

        return InspectionDashboardStats(
            total_rounds=total,
            rounds_in_progress=len(in_progress),
            rounds_completed=completed,
            rounds_scheduled=scheduled,
            total_occurrences=0,
            occurrences_pending=0,
            occurrences_resolved=0,
            total_disciplinary_actions=0,
            warnings_count=0,
            suspensions_count=0,
            rounds_today=len(scheduled_today),
            rounds_this_week=0,
            rounds_this_month=total,
            top_inspectors=[],
            most_visited_posts=[],
            top_infraction_categories=[],
        )

    async def get_inspector_stats(self, tenant_id: str, limit: int = 10) -> builtins.list[InspectorStats]:
        """Retorna estatisticas por inspetor."""
        stats = await self.repository.get_stats_by_inspector(tenant_id, limit)
        return [InspectorStats(**s) for s in stats]
