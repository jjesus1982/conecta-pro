"""
Service de Rondas de Inspecao - Versao Async.

Author: Conecta PRO Team
Date: 2026-01-23
"""

import builtins
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CheckpointStatus,
    CheckpointType,
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


#: ponytail: relógio de celular drifta. Online, a hora do aparelho tem de bater com a do servidor
#: dentro desta folga para a foto contar como "da hora"; offline não dá para exigir (pode ser horas).
TOLERANCIA_RELOGIO = timedelta(minutes=10)


def foto_e_obrigatoria(checkpoint_type: str, flag: bool) -> bool:
    """Régua única (frente 6): o tipo FOTO exige foto; o app pode exigir para qualquer outro
    (ex.: marca `foto_obrigatoria` quando a situação é não conforme)."""
    return bool(flag) or checkpoint_type == CheckpointType.FOTO_EVIDENCIA.value


def _tem_foto_na_hora(photos: builtins.list | None) -> bool:
    """Prova válida = imagem marcada `capturada_na_hora` (câmera, não galeria)."""
    return any(bool(f.get("capturada_na_hora")) for f in (photos or []) if isinstance(f, dict))


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


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

        checkpoints = await self.repository.get_checkpoints_by_round(round_id)
        # frente 6: checkpoint de foto obrigatória sem imagem capturada na hora NÃO fecha a ronda
        sem_foto = [c for c in checkpoints if c.status == CheckpointStatus.PENDENTE_FOTO.value
                    or (c.foto_obrigatoria and not _tem_foto_na_hora(c.photos))]
        if sem_foto:
            nomes = ", ".join((c.title or c.post_name or c.checkpoint_type) for c in sem_foto[:3])
            raise InspectionRoundValidationError(
                f"{len(sem_foto)} checkpoint(s) aguardando foto obrigatória tirada na hora: {nomes}"
            )

        inspection_round.complete(summary, latitude, longitude)
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
        """Rota antiga (JSON, sem arquivo). Foto obrigatória → nasce `pendente_foto`."""
        checkpoint, _repetida = await self.create_checkpoint_completo(round_id, data, fotos=None)
        return checkpoint

    async def create_checkpoint_completo(
        self,
        round_id: str,
        data: CheckpointCreate,
        fotos: builtins.list[dict] | None,
        checkpoint_id: str | None = None,
    ) -> tuple[InspectionCheckpoint, bool]:
        """Checkpoint + fotos na MESMA transação (frente 6). Devolve (checkpoint, repetida).

        `fotos=None` é a rota antiga: sem arquivo, um checkpoint obrigatório nasce `pendente_foto`
        e só vira válido quando a foto chegar. `fotos=[]`/lista é a rota completa: obrigatório
        sem imagem capturada na hora é recusado — nunca nasce "concluído sem foto".
        """
        if data.chave_idempotente:
            existente = await self.repository.get_checkpoint_by_chave(data.chave_idempotente)
            if existente:
                return existente, True

        inspection_round = await self.get_by_id(round_id)
        if inspection_round.status != InspectionRoundStatus.EM_ANDAMENTO.value:
            raise InspectionRoundValidationError("Ronda nao esta em andamento")

        agora = datetime.now(UTC)
        hora_aparelho = _aware(data.hora_aparelho)
        obrigatoria = foto_e_obrigatoria(data.checkpoint_type, data.foto_obrigatoria)
        lista_fotos = list(fotos or []) + list(data.photos or [])
        status = data.status
        extra: dict = {}

        if obrigatoria and not _tem_foto_na_hora(lista_fotos):
            if fotos is not None:
                raise InspectionRoundValidationError(
                    "Foto obrigatória: envie ao menos uma imagem capturada pela câmera na hora"
                )
            status = CheckpointStatus.PENDENTE_FOTO.value
            extra["status_pretendido"] = data.status
        if _tem_foto_na_hora(lista_fotos):
            if hora_aparelho is None:
                raise InspectionRoundValidationError("Foto capturada na hora exige hora_aparelho")
            if not data.origem_offline and abs(agora - hora_aparelho) > TOLERANCIA_RELOGIO:
                raise InspectionRoundValidationError(
                    f"Hora do aparelho difere do servidor em {abs(agora - hora_aparelho)} — "
                    f"acima da folga de {TOLERANCIA_RELOGIO}; a foto não conta como da hora"
                )

        sequence = await self.repository.get_next_checkpoint_sequence(round_id)
        checkpoint_data = {
            "inspection_round_id": round_id,
            "post_id": str(data.post_id) if data.post_id else None,
            "post_name": data.post_name,
            "checkpoint_type": data.checkpoint_type,
            "status": status,
            "employee_id": str(data.employee_id) if data.employee_id else None,
            "employee_name": data.employee_name,
            "title": data.title,
            "description": data.description,
            "observations": data.observations,
            "photos": lista_fotos,
            "latitude": data.latitude,
            "longitude": data.longitude,
            "sequence": sequence,
            "created_by": inspection_round.inspector_id,
            "foto_obrigatoria": obrigatoria,
            "hora_aparelho": hora_aparelho,
            "hora_servidor": agora,
            "device_id": data.device_id,
            "chave_idempotente": data.chave_idempotente,
            "origem_offline": data.origem_offline,
            "extra_data": extra,
        }
        if checkpoint_id:
            checkpoint_data["id"] = checkpoint_id

        try:
            checkpoint = await self.repository.create_checkpoint(checkpoint_data)
        except IntegrityError:
            # duas retentativas da mesma chave cruzaram: a primeira venceu, devolve ela
            await self.db.rollback()
            existente = await self.repository.get_checkpoint_by_chave(data.chave_idempotente or "")
            if existente:
                return existente, True
            raise

        inspection_round.total_checkpoints += 1
        if data.post_id:
            inspection_round.add_visited_post(str(data.post_id))
        await self.repository.update(inspection_round)

        logger.info(f"Checkpoint criado na ronda {inspection_round.code} ({status}, {len(lista_fotos)} foto(s))")
        return checkpoint, False

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
