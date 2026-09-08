"""Service para Candidate."""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from modules.recruitment.models.candidate import (
    Candidate,
    CandidateSource,
    CandidateStatus,
)
from modules.recruitment.repositories.candidate_repository import CandidateRepository
from modules.recruitment.schemas.candidate import (
    CandidateBlock,
    CandidateCreate,
    CandidateFilter,
    CandidateImport,
    CandidateUpdate,
)
from modules.recruitment.services.recruitment_ai_service import RecruitmentAIService

logger = logging.getLogger(__name__)


class CandidateService:
    """Service para operações de candidatos."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.repository = CandidateRepository(session)
        self.ai_service = RecruitmentAIService()

    async def create(self, data: CandidateCreate) -> Candidate:
        """
        Cria um novo candidato.

        Args:
            data: Dados do candidato

        Returns:
            Candidato criado
        """
        # Verifica duplicidade por email
        existing = await self.repository.get_by_email(data.email)
        if existing:
            raise ValueError(f"Candidato já cadastrado com email: {data.email}")

        # Verifica duplicidade por CPF
        if data.cpf:
            existing = await self.repository.get_by_cpf(data.cpf)
            if existing:
                raise ValueError(f"Candidato já cadastrado com CPF: {data.cpf}")

        candidate = await self.repository.create(data)
        await self.session.commit()

        logger.info(
            f"Candidato criado: {candidate.name}",
            extra={"candidate_id": str(candidate.id)},
        )

        return candidate

    async def get_by_id(self, candidate_id: str) -> Candidate | None:
        """Busca candidato por ID."""
        return await self.repository.get_by_id(candidate_id)

    async def get_by_id_with_relations(self, candidate_id: str) -> Candidate | None:
        """Busca candidato por ID com relacionamentos."""
        return await self.repository.get_by_id_with_relations(candidate_id)

    async def get_by_email(self, email: str) -> Candidate | None:
        """Busca candidato por email."""
        return await self.repository.get_by_email(email)

    async def get_by_cpf(self, cpf: str) -> Candidate | None:
        """Busca candidato por CPF."""
        return await self.repository.get_by_cpf(cpf)

    async def update(self, candidate_id: str, data: CandidateUpdate) -> Candidate | None:
        """
        Atualiza um candidato.

        Args:
            candidate_id: ID do candidato
            data: Dados para atualização

        Returns:
            Candidato atualizado ou None
        """
        candidate = await self.repository.update(candidate_id, data)
        if candidate:
            await self.session.commit()
            logger.info(
                f"Candidato atualizado: {candidate.name}",
                extra={"candidate_id": str(candidate.id)},
            )
        return candidate

    async def delete(self, candidate_id: str) -> bool:
        """
        Remove um candidato (soft delete).

        Args:
            candidate_id: ID do candidato

        Returns:
            True se removido com sucesso
        """
        result = await self.repository.soft_delete(candidate_id)
        if result:
            await self.session.commit()
            logger.info(f"Candidato removido: {candidate_id}")
        return result

    async def list_with_filters(
        self,
        filters: CandidateFilter | None = None,
        skip: int = 0,
        limit: int = 20,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> tuple[list[Candidate], int]:
        """
        Lista candidatos com filtros.

        Args:
            filters: Filtros opcionais
            skip: Offset para paginação
            limit: Limite de resultados
            order_by: Campo para ordenação
            order_desc: Se ordenação é descendente

        Returns:
            Tuple com lista de candidatos e total
        """
        return await self.repository.list_with_filters(filters, skip, limit, order_by, order_desc)

    async def get_active(self, skip: int = 0, limit: int = 50) -> list[Candidate]:
        """Retorna candidatos ativos."""
        return await self.repository.get_active(skip, limit)

    async def get_by_source(self, source: CandidateSource, skip: int = 0, limit: int = 50) -> list[Candidate]:
        """Retorna candidatos por fonte."""
        return await self.repository.get_by_source(source, skip, limit)

    async def get_blocked(self, skip: int = 0, limit: int = 50) -> list[Candidate]:
        """Retorna candidatos bloqueados."""
        return await self.repository.get_blocked(skip, limit)

    async def search_by_skills(self, skills: list[str], limit: int = 50) -> list[Candidate]:
        """Busca candidatos por habilidades."""
        return await self.repository.search_by_skills(skills, limit)

    async def get_recently_active(self, days: int = 30, limit: int = 50) -> list[Candidate]:
        """Retorna candidatos ativos recentemente."""
        return await self.repository.get_recently_active(days, limit)

    async def block(self, candidate_id: str, data: CandidateBlock) -> Candidate | None:
        """
        Bloqueia um candidato.

        Args:
            candidate_id: ID do candidato
            data: Dados do bloqueio

        Returns:
            Candidato bloqueado ou None
        """
        candidate = await self.repository.block(candidate_id, data.reason, "system")
        if candidate:
            await self.session.commit()
            logger.warning(
                f"Candidato bloqueado: {candidate.name}",
                extra={
                    "candidate_id": str(candidate.id),
                    "reason": data.reason,
                },
            )
        return candidate

    async def unblock(self, candidate_id: str) -> Candidate | None:
        """
        Desbloqueia um candidato.

        Args:
            candidate_id: ID do candidato

        Returns:
            Candidato desbloqueado ou None
        """
        candidate = await self.repository.unblock(candidate_id)
        if candidate:
            await self.session.commit()
            logger.info(
                f"Candidato desbloqueado: {candidate.name}",
                extra={"candidate_id": str(candidate.id)},
            )
        return candidate

    async def mark_as_hired(self, candidate_id: str) -> Candidate | None:
        """
        Marca candidato como contratado.

        Args:
            candidate_id: ID do candidato

        Returns:
            Candidato atualizado ou None
        """
        candidate = await self.repository.mark_as_hired(candidate_id)
        if candidate:
            await self.session.commit()
            logger.info(
                f"Candidato contratado: {candidate.name}",
                extra={"candidate_id": str(candidate.id)},
            )
        return candidate

    async def archive(self, candidate_id: str) -> Candidate | None:
        """
        Arquiva um candidato.

        Args:
            candidate_id: ID do candidato

        Returns:
            Candidato arquivado ou None
        """
        candidate = await self.repository.get_by_id(candidate_id)
        if candidate:
            candidate.status = CandidateStatus.ARQUIVADO
            candidate.updated_at = datetime.now(UTC)
            await self.session.commit()
            logger.info(
                f"Candidato arquivado: {candidate.name}",
                extra={"candidate_id": str(candidate.id)},
            )
        return candidate

    async def activate(self, candidate_id: str) -> Candidate | None:
        """
        Ativa um candidato.

        Args:
            candidate_id: ID do candidato

        Returns:
            Candidato ativado ou None
        """
        candidate = await self.repository.get_by_id(candidate_id)
        if candidate:
            candidate.status = CandidateStatus.ATIVO
            candidate.updated_at = datetime.now(UTC)
            await self.session.commit()
            logger.info(
                f"Candidato ativado: {candidate.name}",
                extra={"candidate_id": str(candidate.id)},
            )
        return candidate

    async def import_from_resume(self, data: CandidateImport) -> Candidate:
        """
        Importa candidato a partir do currículo.

        Args:
            data: Dados de importação com texto do currículo

        Returns:
            Candidato criado
        """
        # Extrai dados do currículo usando IA
        parsed = await self.ai_service.parse_resume(data.resume_text)

        # Cria candidato com dados extraídos
        create_data = CandidateCreate(
            name=parsed.get("name", "Candidato Importado"),
            email=parsed.get("email", f"imported_{datetime.now(UTC).timestamp()}@temp.com"),
            phone=parsed.get("phone"),
            source=data.source or CandidateSource.SITE,
            resume_text=data.resume_text,
            tags=parsed.get("skills", []),
        )

        candidate = await self.create(create_data)

        logger.info(
            f"Candidato importado do currículo: {candidate.name}",
            extra={
                "candidate_id": str(candidate.id),
                "extracted_skills": len(parsed.get("skills", [])),
            },
        )

        return candidate

    async def update_tags(self, candidate_id: str, tags: list[str]) -> Candidate | None:
        """
        Atualiza tags do candidato.

        Args:
            candidate_id: ID do candidato
            tags: Lista de tags

        Returns:
            Candidato atualizado ou None
        """
        candidate = await self.repository.get_by_id(candidate_id)
        if candidate:
            candidate.tags = tags
            candidate.updated_at = datetime.now(UTC)
            await self.session.commit()
        return candidate

    async def add_note(self, candidate_id: str, note: str, author: str) -> Candidate | None:
        """
        Adiciona nota ao candidato (armazenada em ai_analysis como workaround).

        Args:
            candidate_id: ID do candidato
            note: Texto da nota
            author: Autor da nota

        Returns:
            Candidato atualizado ou None
        """
        candidate = await self.repository.get_by_id(candidate_id)
        if candidate:
            # DB nao tem coluna 'notes' — usa ai_analysis como storage alternativo
            analysis = dict(candidate.ai_analysis or {})  # cópia: mutação in-place não é gravada
            notes_list = list(analysis.get("notes", []))
            notes_list.append(
                {
                    "text": note,
                    "author": author,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            analysis["notes"] = notes_list
            candidate.ai_analysis = analysis
            candidate.updated_at = datetime.now(UTC)
            await self.session.commit()
        return candidate

    async def get_stats(self) -> dict:
        """Retorna estatísticas de candidatos."""
        return await self.repository.get_stats()

    async def merge_duplicates(self, primary_id: str, secondary_id: str) -> Candidate | None:
        """
        Mescla candidatos duplicados.

        Args:
            primary_id: ID do candidato principal
            secondary_id: ID do candidato secundário

        Returns:
            Candidato principal atualizado
        """
        primary = await self.repository.get_by_id(primary_id)
        secondary = await self.repository.get_by_id(secondary_id)

        if not primary or not secondary:
            return None

        # Mescla dados
        if not primary.phone and secondary.phone:
            primary.phone = secondary.phone
        if not primary.resume_text and secondary.resume_text:
            primary.resume_text = secondary.resume_text
        if not primary.resume_url and secondary.resume_url:
            primary.resume_url = secondary.resume_url
        if not primary.linkedin_url and secondary.linkedin_url:
            primary.linkedin_url = secondary.linkedin_url

        # Mescla tags
        primary_tags = set(primary.tags or [])
        secondary_tags = set(secondary.tags or [])
        primary.tags = list(primary_tags.union(secondary_tags))

        # Remove secundário
        await self.repository.soft_delete(secondary_id)

        primary.updated_at = datetime.now(UTC)
        await self.session.commit()

        logger.info(
            f"Candidatos mesclados: {secondary.name} -> {primary.name}",
            extra={
                "primary_id": str(primary.id),
                "secondary_id": str(secondary.id),
            },
        )

        return primary
