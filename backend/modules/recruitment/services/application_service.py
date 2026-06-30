"""Service para Application."""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from modules.recruitment.models.application import (
    Application,
    ApplicationStatus,
    RejectionReason,
)
from modules.recruitment.repositories.application_repository import (
    ApplicationRepository,
)
from modules.recruitment.repositories.candidate_repository import (
    CandidateRepository,
)
from modules.recruitment.repositories.job_position_repository import (
    JobPositionRepository,
)
from modules.recruitment.schemas.application import (
    ApplicationAdvance,
    ApplicationBulkAction,
    ApplicationCreate,
    ApplicationFilter,
    ApplicationHire,
    ApplicationProposal,
    ApplicationReject,
    ApplicationUpdate,
)
from modules.recruitment.services.recruitment_ai_service import RecruitmentAIService

logger = logging.getLogger(__name__)


class ApplicationService:
    """Service para operações de candidaturas."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.repository = ApplicationRepository(session)
        self.position_repo = JobPositionRepository(session)
        self.candidate_repo = CandidateRepository(session)
        self.ai_service = RecruitmentAIService()

    async def create(self, data: ApplicationCreate) -> Application:
        """
        Cria uma nova candidatura.

        Args:
            data: Dados da candidatura

        Returns:
            Candidatura criada
        """
        # Verifica se já existe candidatura
        existing = await self.repository.get_by_candidate_and_position(data.candidate_id, data.job_position_id)
        if existing:
            raise ValueError("Candidato já se candidatou a esta vaga")

        # Verifica se vaga está aberta
        position = await self.position_repo.get_by_id(data.job_position_id)
        if not position:
            raise ValueError("Vaga não encontrada")
        if str(position.status) != "aberta":
            raise ValueError("Vaga não está aberta para candidaturas")

        # Verifica se candidato existe e está ativo
        candidate = await self.candidate_repo.get_by_id(data.candidate_id)
        if not candidate:
            raise ValueError("Candidato não encontrado")
        if candidate.status == "bloqueado":
            raise ValueError("Candidato está bloqueado")

        # Cria candidatura
        application = await self.repository.create(data)

        # Incrementa contador na vaga
        await self.position_repo.increment_application(data.job_position_id)

        # Calcula score de matching
        try:
            matching = await self.ai_service.calculate_matching_score(candidate, position)
            application.ai_match_score = matching["final_score"]
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Erro ao calcular matching: %s", e)

        await self.session.commit()

        logger.info(
            f"Candidatura criada: {candidate.name} -> {position.title}",
            extra={
                "application_id": str(application.id),
                "candidate_id": str(candidate.id),
                "position_id": str(position.id),
            },
        )

        return application

    async def get_by_id(self, application_id: str) -> Application | None:
        """Busca candidatura por ID."""
        return await self.repository.get_by_id(application_id)

    async def get_by_id_with_relations(self, application_id: str) -> Application | None:
        """Busca candidatura por ID com relacionamentos."""
        return await self.repository.get_by_id_with_relations(application_id)

    async def update(self, application_id: str, data: ApplicationUpdate) -> Application | None:
        """
        Atualiza uma candidatura.

        Args:
            application_id: ID da candidatura
            data: Dados para atualização

        Returns:
            Candidatura atualizada ou None
        """
        application = await self.repository.update(application_id, data)
        if application:
            await self.session.commit()
            logger.info(
                "Candidatura atualizada",
                extra={"application_id": str(application.id)},
            )
        return application

    async def delete(self, application_id: str) -> bool:
        """
        Remove uma candidatura (soft delete).

        Args:
            application_id: ID da candidatura

        Returns:
            True se removida com sucesso
        """
        result = await self.repository.soft_delete(application_id)
        if result:
            await self.session.commit()
            logger.info(f"Candidatura removida: {application_id}")
        return result

    async def list_with_filters(
        self,
        filters: ApplicationFilter | None = None,
        skip: int = 0,
        limit: int = 20,
        order_by: str = "applied_at",
        order_desc: bool = True,
    ) -> tuple[list[Application], int]:
        """
        Lista candidaturas com filtros.

        Args:
            filters: Filtros opcionais
            skip: Offset para paginação
            limit: Limite de resultados
            order_by: Campo para ordenação
            order_desc: Se ordenação é descendente

        Returns:
            Tuple com lista de candidaturas e total
        """
        return await self.repository.list_with_filters(filters, skip, limit, order_by, order_desc)

    async def get_by_position(
        self,
        position_id: str,
        status: ApplicationStatus = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Application]:
        """Retorna candidaturas de uma vaga."""
        return await self.repository.get_by_position(position_id, status, skip, limit)

    async def get_by_candidate(self, candidate_id: str, skip: int = 0, limit: int = 50) -> list[Application]:
        """Retorna candidaturas de um candidato."""
        return await self.repository.get_by_candidate(candidate_id, skip, limit)

    async def get_active(self, position_id: str = None, skip: int = 0, limit: int = 50) -> list[Application]:
        """Retorna candidaturas ativas."""
        return await self.repository.get_active(position_id, skip, limit)

    async def get_shortlisted(self, position_id: str, skip: int = 0, limit: int = 50) -> list[Application]:
        """Retorna candidaturas na lista restrita."""
        return await self.repository.get_shortlisted(position_id, skip, limit)

    async def get_favorites(self, position_id: str = None, skip: int = 0, limit: int = 50) -> list[Application]:
        """Retorna candidaturas favoritas."""
        return await self.repository.get_favorites(position_id, skip, limit)

    async def advance_stage(self, application_id: str, data: ApplicationAdvance) -> Application | None:
        """
        Avança candidatura de estágio.

        Args:
            application_id: ID da candidatura
            data: Dados do avanço

        Returns:
            Candidatura atualizada ou None
        """
        application = await self.repository.advance_stage(application_id, data.new_status, data.notes)
        if application:
            await self.session.commit()
            logger.info(
                f"Candidatura avançada para: {data.new_status.value}",
                extra={
                    "application_id": str(application.id),
                    "new_status": data.new_status.value,
                },
            )
        return application

    async def reject(self, application_id: str, data: ApplicationReject) -> Application | None:
        """
        Rejeita candidatura.

        Args:
            application_id: ID da candidatura
            data: Dados da rejeição

        Returns:
            Candidatura rejeitada ou None
        """
        application = await self.repository.reject(application_id, data.reason, data.details)
        if application:
            await self.session.commit()
            logger.info(
                f"Candidatura rejeitada: {data.reason.value}",
                extra={
                    "application_id": str(application.id),
                    "reason": data.reason.value,
                },
            )
        return application

    async def send_proposal(self, application_id: str, data: ApplicationProposal) -> Application | None:
        """
        Envia proposta ao candidato.

        Args:
            application_id: ID da candidatura
            data: Dados da proposta

        Returns:
            Candidatura atualizada ou None
        """
        application = await self.repository.get_by_id(application_id)
        if not application:
            return None

        application.send_proposal(amount=data.amount)
        await self.session.commit()

        logger.info(
            f"Proposta enviada: R$ {data.amount}",
            extra={
                "application_id": str(application.id),
                "salary": data.amount,
            },
        )

        return application

    async def accept_proposal(self, application_id: str, start_date: datetime = None) -> Application | None:
        """
        Aceita proposta.

        Args:
            application_id: ID da candidatura
            start_date: Data de início

        Returns:
            Candidatura atualizada ou None
        """
        application = await self.repository.get_by_id(application_id)
        if not application:
            return None

        application.accept_proposal()

        await self.session.commit()

        logger.info(
            "Proposta aceita",
            extra={"application_id": str(application.id)},
        )

        return application

    async def reject_proposal(self, application_id: str, reason: str = None) -> Application | None:
        """
        Recusa proposta.

        Args:
            application_id: ID da candidatura
            reason: Motivo da recusa

        Returns:
            Candidatura atualizada ou None
        """
        application = await self.repository.get_by_id(application_id)
        if not application:
            return None

        application.reject_proposal(reason)
        await self.session.commit()

        logger.info(
            "Proposta recusada",
            extra={
                "application_id": str(application.id),
                "reason": reason,
            },
        )

        return application

    async def hire(self, application_id: str, data: ApplicationHire) -> Application | None:
        """
        Contrata candidato.

        Args:
            application_id: ID da candidatura
            data: Dados da contratação

        Returns:
            Candidatura atualizada ou None
        """
        application = await self.repository.hire(application_id, data.start_date)
        if not application:
            return None

        # Marca candidato como contratado
        await self.candidate_repo.mark_as_hired(application.candidate_id)

        # Preenche vaga
        await self.position_repo.fill_vacancy(application.job_position_id)

        await self.session.commit()

        logger.info(
            "Candidato contratado",
            extra={
                "application_id": str(application.id),
                "start_date": data.start_date.isoformat() if data.start_date else None,
            },
        )

        return application

    async def toggle_favorite(self, application_id: str) -> Application | None:
        """
        Alterna favorito.

        DB nao possui coluna is_favorite — operacao noop, retorna application.
        """
        application = await self.repository.get_by_id(application_id)
        if not application:
            return None
        # is_favorite nao existe no banco — noop
        return application

    async def toggle_shortlist(self, application_id: str) -> Application | None:
        """
        Alterna lista restrita.

        DB nao possui coluna is_shortlisted — operacao noop, retorna application.
        """
        application = await self.repository.get_by_id(application_id)
        if not application:
            return None
        # is_shortlisted nao existe no banco — noop
        return application

    async def update_score(
        self,
        application_id: str,
        interview_score: float = None,
        test_score: float = None,
        reference_score: float = None,
    ) -> Application | None:
        """
        Atualiza scores da candidatura.

        DB possui apenas rating (int) e ai_match_score (Decimal).
        Mapeia interview_score -> rating.

        Args:
            application_id: ID da candidatura
            interview_score: Score de entrevista
            test_score: Score de teste (ignorado — coluna nao existe)
            reference_score: Score de referência (ignorado — coluna nao existe)

        Returns:
            Candidatura atualizada ou None
        """
        application = await self.repository.get_by_id(application_id)
        if not application:
            return None

        if interview_score is not None:
            application.rating = int(interview_score)

        application.updated_at = datetime.utcnow()
        await self.session.commit()

        return application

    async def update_ranking(self, position_id: str) -> None:
        """
        Atualiza ranking das candidaturas de uma vaga.

        DB nao possui ranking_position — noop.
        """
        return  # Ordenação via ai_match_score no repositório

    async def bulk_action(self, data: ApplicationBulkAction) -> tuple[int, int]:
        """
        Executa ação em lote.

        Args:
            data: Dados da ação em lote

        Returns:
            Tuple com (sucessos, falhas)
        """
        success = 0
        failed = 0

        for app_id in data.application_ids:
            try:
                if data.action == "favorite":
                    result = await self.toggle_favorite(app_id)
                elif data.action == "shortlist":
                    result = await self.toggle_shortlist(app_id)
                elif data.action == "advance":
                    adv_data = ApplicationAdvance(
                        new_status=data.new_status,
                        notes=data.notes,
                    )
                    result = await self.advance_stage(app_id, adv_data)
                elif data.action == "reject":
                    rej_data = ApplicationReject(
                        reason=RejectionReason.PERFIL_INADEQUADO,
                        details=data.notes,
                    )
                    result = await self.reject(app_id, rej_data)
                else:
                    result = None

                if result:
                    success += 1
                else:
                    failed += 1
            except (ValueError, KeyError, TypeError) as e:
                logger.error("Erro em ação bulk para %s: %s", app_id, e)
                failed += 1

        await self.session.commit()

        logger.info(
            f"Ação em lote: {data.action}",
            extra={
                "action": data.action,
                "success": success,
                "failed": failed,
            },
        )

        return success, failed

    async def calculate_matching(self, application_id: str) -> dict | None:
        """
        Recalcula matching de uma candidatura.

        Args:
            application_id: ID da candidatura

        Returns:
            Resultado do matching ou None
        """
        application = await self.repository.get_by_id_with_relations(application_id)
        if not application:
            return None

        position = application.job_position
        candidate = application.candidate

        if not position or not candidate:
            return None

        result = await self.ai_service.calculate_matching_score(candidate, position)

        application.ai_match_score = result["final_score"]
        await self.session.commit()

        return result

    async def get_stats(self, position_id: str = None) -> dict:
        """Retorna estatísticas de candidaturas."""
        return await self.repository.get_stats(position_id)
