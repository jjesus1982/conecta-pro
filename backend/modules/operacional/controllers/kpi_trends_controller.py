"""
Controller para KPI Trends - Tendências de indicadores
"""

import logging
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.models.allocation import Allocation, AllocationStatus
from modules.operacional.models.employee import Employee
from modules.operacional.models.post import Post
from modules.operacional.models.scale import Scale
from modules.operacional.occurrences.models import Occurrence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kpi-trends", tags=["Operacional - KPI Trends"])


class KPITrendsData(BaseModel):
    """Dados de tendências dos KPIs."""

    postos_ativos: list[int] = Field(default_factory=list)
    colaboradores_ativos: list[int] = Field(default_factory=list)
    escalas_em_andamento: list[int] = Field(default_factory=list)
    ocorrencias_mes: list[int] = Field(default_factory=list)
    cobertura_percentual: list[float] = Field(default_factory=list)


class KPITrendsResponse(BaseModel):
    """Resposta do endpoint de tendências."""

    period: str
    days: int
    data: KPITrendsData
    nota: str | None = None


@router.get("", response_model=KPITrendsResponse)
@router.get("/", response_model=KPITrendsResponse, include_in_schema=False)
async def get_kpi_trends(  # pylint: disable=too-many-locals
    _user: CurrentActiveUser,
    period: Literal["7d", "30d", "90d"] = Query("7d", description="Período de análise"),
    db: AsyncSession = Depends(get_db),
) -> KPITrendsResponse:
    """
    Retorna tendências de KPIs ao longo do tempo.

    Períodos:
    - 7d: últimos 7 dias
    - 30d: últimos 30 dias
    - 90d: últimos 90 dias
    """
    period_days: dict[str, int] = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
    }

    days = period_days.get(period, 7)

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        postos_ativos: list[int] = []
        colaboradores_ativos: list[int] = []
        escalas_em_andamento: list[int] = []
        ocorrencias_mes: list[int] = []
        cobertura_percentual: list[float] = []

        for i in range(days):
            current_date = start_date + timedelta(days=i)

            # Postos ativos
            result = await db.execute(
                select(func.count(Post.id)).where(Post.status == "active").where(Post.created_at <= current_date)
            )
            postos_count = result.scalar() or 0
            postos_ativos.append(int(postos_count))

            # Colaboradores ativos — status='ativo' (a flag is_active está
            # inconsistente no banco: inclui demitidos e tem NULL em ativos)
            result = await db.execute(
                select(func.count(Employee.id))
                .where(Employee.status == "ativo")
                .where(Employee.created_at <= current_date)
            )
            colab_count = result.scalar() or 0
            colaboradores_ativos.append(int(colab_count))

            # Escalas em andamento — 'active' NÃO é status válido de scales
            # (valores reais: draft, pending_approval, approved, published,
            # in_progress, completed, cancelled). Mesmo mapeamento do dashboard.
            # Filtra is_active para excluir escalas desativadas (soft-delete) —
            # mesma conta de scales/stats usada na home.
            result = await db.execute(
                select(func.count(Scale.id))
                .where(Scale.status.in_(["approved", "published", "in_progress"]))
                .where(Scale.is_active.is_(True))
                .where(Scale.created_at <= current_date)
            )
            escalas_count = result.scalar() or 0
            escalas_em_andamento.append(int(escalas_count))

            # Ocorrências no dia
            result = await db.execute(
                select(func.count(Occurrence.id)).where(func.date(Occurrence.created_at) == current_date.date())
            )
            occ_count = result.scalar() or 0
            ocorrencias_mes.append(int(occ_count))

            # Cobertura percentual: postos ATIVOS cobertos / postos ATIVOS (formula
            # padronizada — mesma conta de /reports/coverage e da home operacional).
            # Snapshot historico: postos existentes ate o dia e alocacoes vigentes
            # naquele dia (start<=dia AND (end IS NULL OR end>=dia)).
            total_posts_result = await db.execute(
                select(func.count(Post.id)).where(Post.status == "active").where(Post.created_at <= current_date)
            )
            total_posts = total_posts_result.scalar() or 0

            covered_result = await db.execute(
                select(func.count(func.distinct(Allocation.post_id)))
                .where(Allocation.status == AllocationStatus.ACTIVE.value)
                .where(Allocation.is_active.is_(True))
                .where(Allocation.start_date <= current_date.date())
                .where(
                    or_(
                        Allocation.end_date.is_(None),
                        Allocation.end_date >= current_date.date(),
                    )
                )
            )
            posts_covered = covered_result.scalar() or 0

            if total_posts > 0:
                cobertura = min(100.0, (posts_covered / total_posts) * 100)
                cobertura_percentual.append(round(float(cobertura), 2))
            else:
                cobertura_percentual.append(0.0)

        logger.info("KPI trends calculados para período %s", period)

        return KPITrendsResponse(
            period=period,
            days=days,
            data=KPITrendsData(
                postos_ativos=postos_ativos,
                colaboradores_ativos=colaboradores_ativos,
                escalas_em_andamento=escalas_em_andamento,
                ocorrencias_mes=ocorrencias_mes,
                cobertura_percentual=cobertura_percentual,
            ),
            nota=(
                "Séries de postos/colaboradores/escalas/cobertura são snapshot atual "
                "retroprojetado (filtro created_at <= dia — não há histórico diário no banco); "
                "apenas ocorrencias_mes é série histórica real."
            ),
        )

    except (RuntimeError, ValueError, OSError) as e:
        logger.error("Erro ao calcular KPI trends: %s", e)
        return KPITrendsResponse(
            period=period,
            days=days,
            data=KPITrendsData(),
        )


@router.get("/performance-scores", tags=["Operacional - KPI Trends"])
async def get_performance_scores(
    _user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns performance scores for all active employees.

    Calculates a composite score (0-100) based on:
    - Time bank balance (positive = reliable)
    - Occurrence count (fewer = better)
    - Allocation status (active = reliable)

    Returns:
        Performance data for top 10 and bottom 5 employees
    """
    from sqlalchemy import text  # pylint: disable=import-outside-toplevel

    try:
        # Get employee performance metrics from DB
        result = await db.execute(
            text("""
                WITH employee_scores AS (
                    SELECT
                        e.id,
                        e.nome AS name,
                        e.cargo AS role,
                        COALESCE(
                            (SELECT SUM(t.hours)
                             FROM time_bank t
                             WHERE t.employee_id = e.id
                               AND t.status = 'approved'
                               AND t.is_active = true),
                            0
                        ) AS time_bank_balance,
                        COALESCE(
                            (SELECT COUNT(o.id)
                             FROM occurrences o
                             WHERE o.employee_id = e.id
                               AND o.created_at >= NOW() - INTERVAL '90 days'),
                            0
                        ) AS recent_occurrences,
                        -- Presença 30d REAL: turnos passados com batida (ponto) ou check-in manual
                        (SELECT COUNT(*) FROM shifts s
                          WHERE s.employee_id = e.id AND s.is_active AND s.status = 'scheduled'
                            AND NOT s.is_off_day
                            AND s.shift_date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE - 1
                        ) AS turnos_30d,
                        (SELECT COUNT(*) FROM shifts s
                          WHERE s.employee_id = e.id AND s.is_active AND s.status = 'scheduled'
                            AND NOT s.is_off_day
                            AND s.shift_date BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE - 1
                            AND (s.actual_start_time IS NOT NULL OR EXISTS (
                              SELECT 1 FROM gp_clock_punches gp
                              WHERE gp.employee_id = s.employee_id
                                AND (gp.punch_timestamp)::date = s.shift_date
                                AND COALESCE(gp.status,'') NOT IN ('rejected','cancelado')))
                        ) AS presentes_30d
                    FROM employees e
                    WHERE e.status = 'ativo'
                )
                SELECT
                    id,
                    name,
                    role,
                    time_bank_balance,
                    recent_occurrences,
                    turnos_30d,
                    presentes_30d,
                    -- Score composto REAL: 60% presença 30d (quando há turnos) + base 40
                    -- + bônus banco de horas - penalidade de ocorrências.
                    -- Sem turnos no período → score NULL (sem dados; front exibe "—").
                    CASE WHEN turnos_30d > 0 THEN
                      GREATEST(0, LEAST(100,
                          40
                          + (presentes_30d::numeric / turnos_30d) * 60
                          + LEAST(10, GREATEST(-10, time_bank_balance * 1.5))
                          - LEAST(30, recent_occurrences * 5)
                      ))
                    ELSE NULL END AS score
                FROM employee_scores
                ORDER BY score DESC NULLS LAST
            """)
        )

        rows = result.fetchall()

        if not rows:
            return {
                "top_performers": [],
                "needs_attention": [],
                "average_score": 0.0,
                "total_evaluated": 0,
            }

        employees = [
            {
                "id": str(row.id),
                "name": row.name,
                "role": row.role or "Porteiro",
                "score": round(float(row.score), 1) if row.score is not None else None,
                "time_bank_balance": float(row.time_bank_balance),
                "recent_occurrences": int(row.recent_occurrences),
                # trend omitido: sem base de periodo anterior para derivar tendencia real
            }
            for row in rows
        ]

        com_score = [e for e in employees if e["score"] is not None]
        avg_score = sum(e["score"] for e in com_score) / len(com_score) if com_score else 0

        return {
            "top_performers": employees[:10],
            "needs_attention": [e for e in reversed(employees) if e["score"] is not None and e["score"] < 60][:5],
            "average_score": round(avg_score, 1),
            "total_evaluated": len(employees),
            "distribution": {
                "excelente": len([e for e in employees if e["score"] is not None and e["score"] >= 85]),
                "bom": len([e for e in employees if e["score"] is not None and 70 <= e["score"] < 85]),
                "regular": len([e for e in employees if e["score"] is not None and 50 <= e["score"] < 70]),
                "critico": len([e for e in employees if e["score"] is not None and e["score"] < 50]),
            },
        }

    except (RuntimeError, ValueError, OSError) as e:
        logger.error("Erro ao calcular scores de performance: %s", e)
        return {
            "top_performers": [],
            "needs_attention": [],
            "average_score": 0.0,
            "total_evaluated": 0,
            "error": str(e),
        }


@router.get("/coverage-prediction")
@router.get("/coverage-prediction/", include_in_schema=False)
async def get_coverage_prediction(_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)):
    """Previsao de cobertura de postos (deriva de posts ATIVOS + alocacoes ativas).

    Formula padronizada: postos ativos com alocacao / postos ativos — a mesma
    conta de /reports/coverage e da home operacional (total_postos aqui = 8, nao 12).
    """
    from sqlalchemy import text

    total = (await db.execute(text("SELECT count(*) FROM posts WHERE status = 'active'"))).scalar() or 0
    cobertos = (
        await db.execute(
            text(
                "SELECT count(DISTINCT a.post_id) FROM allocations a "
                "JOIN posts p ON p.id = a.post_id AND p.status = 'active' "
                "WHERE a.status='active' AND a.is_active = true"
            )
        )
    ).scalar() or 0
    cobertura = round(min(100.0, (cobertos / total * 100) if total else 0.0), 1)
    nivel = "baixo" if cobertura >= 90 else "medio" if cobertura >= 70 else "alto"
    return {
        "total_postos": int(total),
        "postos_cobertos": int(cobertos),
        "cobertura_atual": cobertura,
        "nivel_risco": nivel,
        "riskLevel": nivel,
        # campo "predicoes" removido: nao ha modelo preditivo real ainda (era [] fixo)
    }
