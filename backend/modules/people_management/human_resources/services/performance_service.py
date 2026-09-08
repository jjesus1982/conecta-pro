"""
Service para Avaliacao de Desempenho.

Implementa logica de negocio para gestao de avaliacoes:
- CRUD de avaliacoes de desempenho
- Inicio de ciclo de avaliacao para equipe/empresa
- Calculo de scores compostos
- Fluxo de aprovacao e calibracao
- Conclusao de avaliacoes
"""

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.human_resources.models.performance import (
    PerformanceReview,
    ReviewStatus,
    ReviewType,
)
from modules.people_management.human_resources.schemas.performance import (
    PerformanceReviewCreate,
    PerformanceReviewUpdate,
    ScoresBreakdown,
)

logger = logging.getLogger(__name__)

# Pesos das dimensoes de desempenho
DIMENSION_WEIGHTS: dict[str, float] = {
    "punctuality": 0.25,
    "quality": 0.25,
    "initiative": 0.20,
    "teamwork": 0.20,
    "leadership": 0.10,
}


class PerformanceService:
    """Service para operacoes de avaliacao de desempenho."""

    def __init__(self, session: AsyncSession) -> None:
        """Inicializa o service.

        Args:
            session: Sessao async do SQLAlchemy.
        """
        self.session = session

    async def create_review(self, data: PerformanceReviewCreate) -> PerformanceReview:
        """Cria uma nova avaliacao de desempenho.

        Args:
            data: Dados da avaliacao.

        Returns:
            Avaliacao criada.

        Raises:
            ValueError: Se periodo invalido.
        """
        if data.review_period_end <= data.review_period_start:
            raise ValueError("Data de fim do periodo deve ser posterior a data de inicio.")

        review_data = data.model_dump()

        # Calcular score se breakdown fornecido
        overall_score = None
        if data.scores_breakdown:
            overall_score = self.calculate_scores(data.scores_breakdown)
            review_data["scores_breakdown"] = data.scores_breakdown.model_dump()

        review = PerformanceReview(
            id=uuid.uuid4(),
            status=ReviewStatus.DRAFT,
            overall_score=overall_score,
            **{k: v for k, v in review_data.items() if k not in ("scores_breakdown", "overall_score")},
            scores_breakdown=review_data.get("scores_breakdown"),
        )
        self.session.add(review)
        await self.session.commit()
        await self.session.refresh(review)
        logger.info(f"Avaliacao criada para funcionario {data.employee_id} (ID: {review.id}, tipo: {data.type.value})")
        return review

    async def get_review(self, review_id: uuid.UUID) -> PerformanceReview | None:
        """Busca uma avaliacao por ID.

        Args:
            review_id: ID da avaliacao.

        Returns:
            Avaliacao encontrada ou None.
        """
        result = await self.session.execute(select(PerformanceReview).where(PerformanceReview.id == review_id))
        return result.scalar_one_or_none()

    async def list_reviews(
        self,
        employee_id: uuid.UUID | None = None,
        reviewer_id: uuid.UUID | None = None,
        review_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Lista avaliacoes com filtros e paginacao.

        Args:
            employee_id: Filtro por funcionario.
            reviewer_id: Filtro por avaliador.
            review_type: Filtro por tipo.
            status: Filtro por status.
            page: Numero da pagina.
            page_size: Itens por pagina.

        Returns:
            Dicionario com items, total, page e page_size.
        """
        query = select(PerformanceReview)
        count_query = select(func.count(PerformanceReview.id))

        if employee_id:
            query = query.where(PerformanceReview.employee_id == employee_id)
            count_query = count_query.where(PerformanceReview.employee_id == employee_id)
        if reviewer_id:
            query = query.where(PerformanceReview.reviewer_id == reviewer_id)
            count_query = count_query.where(PerformanceReview.reviewer_id == reviewer_id)
        if review_type:
            query = query.where(PerformanceReview.type == review_type)
            count_query = count_query.where(PerformanceReview.type == review_type)
        if status:
            query = query.where(PerformanceReview.status == status)
            count_query = count_query.where(PerformanceReview.status == status)

        total = (await self.session.execute(count_query)).scalar() or 0
        offset = (page - 1) * page_size
        query = query.order_by(PerformanceReview.review_period_end.desc()).offset(offset).limit(page_size)
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        # Batch-fetch employee names to avoid N+1 and populate employee_name/reviewer_name
        all_ids = list({str(r.employee_id) for r in items} | {str(r.reviewer_id) for r in items if r.reviewer_id})
        names: dict[str, str] = {}
        if all_ids:
            stmt = text("SELECT id::text, nome FROM employees WHERE id::text IN :ids").bindparams(
                bindparam("ids", expanding=True)
            )
            rows = await self.session.execute(stmt, {"ids": all_ids})
            names = {row[0]: row[1] for row in rows}

        enriched = []
        for r in items:
            d = {c.key: getattr(r, c.key) for c in r.__table__.columns}
            d["employee_name"] = names.get(str(r.employee_id))
            d["reviewer_name"] = names.get(str(r.reviewer_id)) if r.reviewer_id else None
            enriched.append(d)

        return {"items": enriched, "total": total, "page": page, "page_size": page_size}

    async def update_review(self, review_id: uuid.UUID, data: PerformanceReviewUpdate) -> PerformanceReview | None:
        """Atualiza uma avaliacao de desempenho.

        Args:
            review_id: ID da avaliacao.
            data: Dados para atualizacao.

        Returns:
            Avaliacao atualizada ou None.
        """
        review = await self.get_review(review_id)
        if not review:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Recalcular score se breakdown atualizado
        if data.scores_breakdown:
            update_data["overall_score"] = self.calculate_scores(data.scores_breakdown)
            update_data["scores_breakdown"] = data.scores_breakdown.model_dump()

        for field, value in update_data.items():
            setattr(review, field, value)

        await self.session.commit()
        await self.session.refresh(review)
        logger.info(f"Avaliacao atualizada (ID: {review.id})")
        return review

    async def delete_review(self, review_id: uuid.UUID) -> bool:
        """Remove uma avaliacao (apenas rascunhos).

        Args:
            review_id: ID da avaliacao.

        Returns:
            True se removida com sucesso.

        Raises:
            ValueError: Se avaliacao nao esta em rascunho.
        """
        review = await self.get_review(review_id)
        if not review:
            return False

        if review.status != ReviewStatus.DRAFT:
            raise ValueError("Somente avaliacoes em rascunho podem ser removidas.")

        await self.session.delete(review)
        await self.session.commit()
        logger.info(f"Avaliacao removida (ID: {review_id})")
        return True

    @staticmethod
    def calculate_scores(breakdown: ScoresBreakdown) -> float:
        """Calcula o score geral ponderado a partir do breakdown.

        Dimensoes e pesos:
            - punctuality: 25%
            - quality: 25%
            - initiative: 20%
            - teamwork: 20%
            - leadership: 10%

        Args:
            breakdown: Scores por dimensao.

        Returns:
            Score geral ponderado (0-100).
        """
        scores = breakdown.model_dump()
        weighted_sum = sum(scores.get(dim, 0) * weight for dim, weight in DIMENSION_WEIGHTS.items())
        return round(weighted_sum, 2)

    async def start_review_cycle(
        self,
        employee_ids: list[uuid.UUID],
        reviewer_id: uuid.UUID,
        review_type: ReviewType,
        period_start: date,
        period_end: date,
    ) -> list[PerformanceReview]:
        """Inicia um ciclo de avaliacao para multiplos funcionarios.

        Cria avaliacoes em rascunho para cada funcionario na lista.

        Args:
            employee_ids: Lista de IDs dos funcionarios.
            reviewer_id: ID do avaliador.
            review_type: Tipo de avaliacao.
            period_start: Inicio do periodo.
            period_end: Fim do periodo.

        Returns:
            Lista de avaliacoes criadas.
        """
        reviews = []
        for emp_id in employee_ids:
            review = PerformanceReview(
                id=uuid.uuid4(),
                employee_id=emp_id,
                reviewer_id=reviewer_id,
                review_period_start=period_start,
                review_period_end=period_end,
                type=review_type,
                status=ReviewStatus.DRAFT,
            )
            self.session.add(review)
            reviews.append(review)

        await self.session.commit()
        for review in reviews:
            await self.session.refresh(review)

        logger.info(f"Ciclo de avaliacao iniciado: {len(reviews)} avaliacoes ({review_type.value}) por {reviewer_id}")
        return reviews

    async def complete_review(self, review_id: uuid.UUID) -> PerformanceReview | None:
        """Conclui uma avaliacao de desempenho.

        Marca como completada e registra a data de conclusao.

        Args:
            review_id: ID da avaliacao.

        Returns:
            Avaliacao concluida ou None.

        Raises:
            ValueError: Se avaliacao sem score ou em status invalido.
        """
        review = await self.get_review(review_id)
        if not review:
            return None

        if review.status == ReviewStatus.COMPLETED:
            raise ValueError("Avaliacao ja esta concluida.")

        if review.overall_score is None:
            raise ValueError("Avaliacao deve ter um score para ser concluida.")

        review.status = ReviewStatus.COMPLETED
        review.completed_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(review)
        logger.info(f"Avaliacao concluida (ID: {review.id}, score: {review.final_score})")
        return review
