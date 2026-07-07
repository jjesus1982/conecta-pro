"""
Servico de Avaliacao 360 — persistente em banco de dados.

Implementa avaliacao 360 completa com:
- 5 tipos de avaliador: SELF, MANAGER, PEER, SUBORDINATE, CLIENT
- Pesos configuraveis por tipo
- Calculo de score ponderado
- Gestao de ciclo completo (criacao -> coleta -> calculo -> relatorio)
- Dados persistidos em evaluation_360_cycles e evaluation_360_responses
"""

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.people_management.human_resources.models.evaluation_360 import (
    Evaluation360Cycle,
    Evaluation360Response,
    EvaluationStatus,
    EvaluatorType,
)

logger = logging.getLogger(__name__)


# Pesos padrao para seguranca patrimonial
DEFAULT_WEIGHTS: dict[str, float] = {
    EvaluatorType.SELF: 0.10,
    EvaluatorType.MANAGER: 0.35,
    EvaluatorType.PEER: 0.25,
    EvaluatorType.SUBORDINATE: 0.15,
    EvaluatorType.CLIENT: 0.15,
}

# Dimensoes de avaliacao (vigilancia patrimonial)
EVALUATION_DIMENSIONS: list[dict[str, Any]] = [
    {"id": "pontualidade", "nome": "Pontualidade e Assiduidade", "peso": 0.20},
    {"id": "postura", "nome": "Postura e Apresentacao", "peso": 0.15},
    {"id": "comunicacao", "nome": "Comunicacao", "peso": 0.15},
    {"id": "proatividade", "nome": "Proatividade e Iniciativa", "peso": 0.15},
    {"id": "trabalho_equipe", "nome": "Trabalho em Equipe", "peso": 0.10},
    {"id": "conhecimento_tecnico", "nome": "Conhecimento Tecnico", "peso": 0.10},
    {"id": "seguranca", "nome": "Procedimentos de Seguranca", "peso": 0.10},
    {"id": "lideranca", "nome": "Lideranca", "peso": 0.05},
]


def _classify_score(score: float) -> str:
    """Classifica score em nivel de desempenho."""
    if score >= 9:
        return "Excepcional"
    if score >= 7.5:
        return "Acima da Expectativa"
    if score >= 6:
        return "Atende Expectativa"
    if score >= 4:
        return "Abaixo da Expectativa"
    return "Insatisfatorio"


def _weighted_score_for_response(scores: dict[str, float]) -> float:
    """Calcula score ponderado pelas dimensoes."""
    total = 0.0
    for dim in EVALUATION_DIMENSIONS:
        total += scores.get(dim["id"], 0) * dim["peso"]
    return round(total, 2)


class Evaluation360Service:
    """Servico completo de Avaliacao 360 com persistencia em banco."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_cycle(
        self,
        employee_id: str,
        employee_name: str,
        period_start: date,
        period_end: date,
        custom_weights: dict[str, float] | None = None,
    ) -> Evaluation360Cycle:
        """Cria um novo ciclo de avaliacao 360."""
        weights = custom_weights or dict(DEFAULT_WEIGHTS)

        total_weight = sum(weights.values())
        if abs(total_weight - 1.0) > 0.01:
            msg = f"Soma dos pesos deve ser 1.0, recebido: {total_weight:.2f}"
            raise ValueError(msg)

        cycle = Evaluation360Cycle(
            employee_id=employee_id,
            employee_name=employee_name,
            period_start=period_start,
            period_end=period_end,
            weights=weights,
            status=EvaluationStatus.DRAFT,
        )
        self.db.add(cycle)
        await self.db.flush()
        logger.info("Ciclo 360 criado: %s para %s", str(cycle.id)[:8], employee_name)
        return cycle

    async def start_collecting(self, cycle_id: str) -> Evaluation360Cycle:
        """Inicia a coleta de avaliacoes."""
        cycle = await self._get_cycle(cycle_id)
        if cycle.status != EvaluationStatus.DRAFT:
            msg = f"Ciclo deve estar em DRAFT para iniciar coleta, atual: {cycle.status}"
            raise ValueError(msg)
        cycle.status = EvaluationStatus.COLLECTING
        await self.db.flush()
        return cycle

    async def submit_response(
        self,
        cycle_id: str,
        evaluator_id: str,
        evaluator_type: EvaluatorType | str,
        evaluator_name: str,
        scores: dict[str, float],
        comments: dict[str, str] | None = None,
    ) -> Evaluation360Response:
        """Submete uma avaliacao individual."""
        cycle = await self._get_cycle(cycle_id)
        if cycle.status != EvaluationStatus.COLLECTING:
            msg = f"Ciclo deve estar COLLECTING para receber respostas, atual: {cycle.status}"
            raise ValueError(msg)

        for dim_id, score in scores.items():
            if not 0 <= score <= 10:
                msg = f"Score para '{dim_id}' deve ser entre 0 e 10, recebido: {score}"
                raise ValueError(msg)

        if isinstance(evaluator_type, str):
            evaluator_type = EvaluatorType(evaluator_type)

        # Um avaliador responde uma unica vez por ciclo
        existing = await self.db.execute(
            select(Evaluation360Response.id).where(
                Evaluation360Response.cycle_id == cycle.id,
                Evaluation360Response.evaluator_id == str(evaluator_id),
            )
        )
        if existing.scalar_one_or_none():
            msg = f"Avaliador {evaluator_name} ja respondeu este ciclo"
            raise ValueError(msg)

        response = Evaluation360Response(
            cycle_id=cycle.id,
            evaluator_id=evaluator_id,
            evaluator_type=evaluator_type,
            evaluator_name=evaluator_name,
            scores=scores,
            comments=comments or {},
            submitted_at=datetime.now(UTC),
        )
        self.db.add(response)
        await self.db.flush()
        logger.info(
            "Resposta 360 recebida: avaliador %s (%s) para ciclo %s",
            evaluator_name,
            evaluator_type.value,
            str(cycle.id)[:8],
        )
        return response

    async def calculate_final_score(self, cycle_id: str) -> dict[str, Any]:
        """Calcula score final ponderado da avaliacao 360."""
        cycle = await self._get_cycle_with_responses(cycle_id)
        if not cycle.responses:
            msg = "Ciclo nao tem respostas para calcular"
            raise ValueError(msg)

        cycle.status = EvaluationStatus.CALCULATING

        by_type: dict[str, list[Evaluation360Response]] = {}
        for resp in cycle.responses:
            by_type.setdefault(resp.evaluator_type.value, []).append(resp)

        type_scores: dict[str, dict[str, Any]] = {}
        active_weights: dict[str, float] = {}

        for eval_type, responses in by_type.items():
            dim_scores: dict[str, float] = {}
            for dim in EVALUATION_DIMENSIONS:
                dim_id = dim["id"]
                values = [r.scores.get(dim_id, 0) for r in responses if dim_id in r.scores]
                dim_scores[dim_id] = sum(values) / len(values) if values else 0

            weighted = sum(dim_scores[d["id"]] * d["peso"] for d in EVALUATION_DIMENSIONS)
            type_scores[eval_type] = {
                "score": round(weighted, 2),
                "count": len(responses),
                "dimensions": {k: round(v, 2) for k, v in dim_scores.items()},
            }
            active_weights[eval_type] = (cycle.weights or {}).get(eval_type, 0)

        total_active = sum(active_weights.values())
        if total_active > 0:
            normalized = {k: v / total_active for k, v in active_weights.items()}
        else:
            normalized = {k: 1.0 / len(active_weights) for k in active_weights}

        final_score = sum(normalized.get(t, 0) * data["score"] for t, data in type_scores.items())
        final_score = round(final_score, 2)

        dimension_totals: dict[str, list[float]] = {}
        for resp in cycle.responses:
            for dim_id, score in resp.scores.items():
                dimension_totals.setdefault(dim_id, []).append(score)

        dimension_averages = {dim_id: round(sum(vals) / len(vals), 2) for dim_id, vals in dimension_totals.items()}

        classification = _classify_score(final_score)

        cycle.final_score = final_score
        cycle.status = EvaluationStatus.COMPLETED
        cycle.completed_at = datetime.now(UTC)

        result = {
            "cycle_id": str(cycle.id),
            "employee_id": str(cycle.employee_id),
            "employee_name": cycle.employee_name,
            "final_score": final_score,
            "classification": classification,
            "total_responses": len(cycle.responses),
            "by_evaluator_type": type_scores,
            "by_dimension": dimension_averages,
            "weights_used": {k: round(v, 2) for k, v in normalized.items()},
            "period": f"{cycle.period_start} a {cycle.period_end}",
            "completed_at": cycle.completed_at.isoformat(),
        }

        cycle.result_data = result
        await self.db.flush()

        logger.info(
            "Avaliacao 360 finalizada: %s, score=%.2f (%s), %d respostas",
            cycle.employee_name,
            final_score,
            classification,
            len(cycle.responses),
        )
        return result

    async def generate_report(self, cycle_id: str) -> dict[str, Any]:
        """Gera relatorio completo da avaliacao 360."""
        cycle = await self._get_cycle_with_responses(cycle_id)
        if cycle.status != EvaluationStatus.COMPLETED:
            msg = "Ciclo deve estar COMPLETED para gerar relatorio"
            raise ValueError(msg)

        if cycle.result_data:
            final_data = cycle.result_data
        else:
            final_data = await self.calculate_final_score(cycle_id)

        dim_scores = final_data["by_dimension"]
        sorted_dims = sorted(dim_scores.items(), key=lambda x: x[1], reverse=True)
        strengths = sorted_dims[:3]
        improvements = sorted_dims[-3:]

        all_comments: dict[str, list[str]] = {}
        for resp in cycle.responses:
            for dim_id, comment in (resp.comments or {}).items():
                if comment.strip():
                    all_comments.setdefault(dim_id, []).append(f"[{resp.evaluator_type.value}] {comment}")

        dim_names = {d["id"]: d["nome"] for d in EVALUATION_DIMENSIONS}

        return {
            **final_data,
            "pontos_fortes": [{"dimensao": dim_names.get(d, d), "score": s} for d, s in strengths],
            "pontos_melhoria": [{"dimensao": dim_names.get(d, d), "score": s} for d, s in improvements],
            "comentarios": {dim_names.get(k, k): v for k, v in all_comments.items()},
            "dimensoes_avaliadas": [
                {"id": d["id"], "nome": d["nome"], "peso": d["peso"]} for d in EVALUATION_DIMENSIONS
            ],
        }

    async def get_cycle(self, cycle_id: str) -> Evaluation360Cycle | None:
        """Retorna ciclo por ID ou None."""
        stmt = select(Evaluation360Cycle).where(
            Evaluation360Cycle.id == cycle_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_cycles(
        self,
        employee_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista ciclos, opcionalmente filtrados por funcionario."""
        stmt = select(Evaluation360Cycle).options(
            selectinload(Evaluation360Cycle.responses),
        )
        if employee_id:
            stmt = stmt.where(Evaluation360Cycle.employee_id == employee_id)
        result = await self.db.execute(stmt)
        cycles = result.scalars().all()
        return [
            {
                "id": str(c.id),
                "employee_id": str(c.employee_id),
                "employee_name": c.employee_name,
                "status": c.status.value,
                "final_score": c.final_score,
                "responses_count": len(c.responses),
                "period": f"{c.period_start} a {c.period_end}",
            }
            for c in cycles
        ]

    async def list_pending_for_evaluator(self, evaluator_ids: list[str]) -> list[dict[str, Any]]:
        """Ciclos em coleta que o avaliador (por qualquer um de seus IDs) ainda nao respondeu."""
        ids = [str(i) for i in evaluator_ids if i]
        stmt = (
            select(Evaluation360Cycle)
            .options(selectinload(Evaluation360Cycle.responses))
            .where(Evaluation360Cycle.status == EvaluationStatus.COLLECTING)
        )
        result = await self.db.execute(stmt)
        cycles = result.scalars().all()

        pending = []
        for c in cycles:
            answered = {str(r.evaluator_id) for r in c.responses}
            if answered.intersection(ids):
                continue
            pending.append(
                {
                    "cycle_id": str(c.id),
                    "employee_id": str(c.employee_id),
                    "employee_name": c.employee_name,
                    "period": f"{c.period_start} a {c.period_end}",
                    "responses_count": len(c.responses),
                    "dimensoes": [
                        {"id": d["id"], "nome": d["nome"], "peso": d["peso"]} for d in EVALUATION_DIMENSIONS
                    ],
                }
            )
        return pending

    async def aggregate_results(self) -> dict[str, Any]:
        """Resultados agregados por avaliado, calculados ao vivo das respostas reais.

        Nao muda o status dos ciclos; ciclos sem resposta aparecem como
        "aguardando respostas" — nunca com nota fabricada.
        """
        stmt = select(Evaluation360Cycle).options(selectinload(Evaluation360Cycle.responses))
        result = await self.db.execute(stmt)
        cycles = result.scalars().all()

        por_avaliado: dict[str, dict[str, Any]] = {}
        for c in cycles:
            emp_id = str(c.employee_id)
            entry = por_avaliado.setdefault(
                emp_id,
                {"employee_id": emp_id, "employee_name": c.employee_name, "ciclos": []},
            )
            if c.responses:
                scores_ponderados = [_weighted_score_for_response(r.scores or {}) for r in c.responses]
                media_parcial = round(sum(scores_ponderados) / len(scores_ponderados), 2)
                por_tipo: dict[str, int] = {}
                for r in c.responses:
                    por_tipo[r.evaluator_type.value] = por_tipo.get(r.evaluator_type.value, 0) + 1
                entry["ciclos"].append(
                    {
                        "cycle_id": str(c.id),
                        "status": c.status.value,
                        "period": f"{c.period_start} a {c.period_end}",
                        "responses_count": len(c.responses),
                        "respostas_por_tipo": por_tipo,
                        "media_parcial": media_parcial,
                        "final_score": c.final_score,
                        "classification": _classify_score(c.final_score) if c.final_score is not None else None,
                    }
                )
            else:
                entry["ciclos"].append(
                    {
                        "cycle_id": str(c.id),
                        "status": c.status.value,
                        "period": f"{c.period_start} a {c.period_end}",
                        "responses_count": 0,
                        "media_parcial": None,
                        "final_score": None,
                        "nota": "aguardando respostas reais",
                    }
                )

        avaliados = list(por_avaliado.values())
        total_respostas = sum(cc["responses_count"] for a in avaliados for cc in a["ciclos"])
        return {
            "avaliados": avaliados,
            "total_ciclos": len(cycles),
            "total_respostas": total_respostas,
            "nota": (
                None
                if total_respostas
                else "Nenhuma resposta 360 registrada ainda — resultados aparecerao quando os avaliadores responderem."
            ),
        }

    async def _get_cycle(self, cycle_id: str) -> Evaluation360Cycle:
        """Busca ciclo ou levanta erro."""
        stmt = select(Evaluation360Cycle).where(
            Evaluation360Cycle.id == cycle_id,
        )
        result = await self.db.execute(stmt)
        cycle = result.scalar_one_or_none()
        if not cycle:
            msg = f"Ciclo {cycle_id} nao encontrado"
            raise ValueError(msg)
        return cycle

    async def _get_cycle_with_responses(self, cycle_id: str) -> Evaluation360Cycle:
        """Busca ciclo com responses carregadas."""
        stmt = (
            select(Evaluation360Cycle)
            .options(selectinload(Evaluation360Cycle.responses))
            .where(Evaluation360Cycle.id == cycle_id)
        )
        result = await self.db.execute(stmt)
        cycle = result.scalar_one_or_none()
        if not cycle:
            msg = f"Ciclo {cycle_id} nao encontrado"
            raise ValueError(msg)
        return cycle
