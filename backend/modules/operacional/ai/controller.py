"""Operacional AI Controller — command center e performance overview (dado real)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

ai_router = APIRouter(prefix="/ai", tags=["Operacional - AI"])

_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


async def _coverage(db: AsyncSession) -> dict:
    # Semantica padronizada (mesma regra de posts/stats e da home operacional):
    # total = postos ATIVOS (status='active' AND is_active) e cobertura = cobertos/ativos.
    total = (
        await db.execute(text("SELECT count(*) FROM posts WHERE status = 'active' AND is_active = true"))
    ).scalar() or 0
    cobertos = (
        await db.execute(
            text(
                "SELECT count(DISTINCT a.post_id) FROM allocations a "
                "JOIN posts p ON p.id = a.post_id "
                "WHERE a.status = 'active' AND a.is_active = true "
                "AND p.status = 'active' AND p.is_active = true"
            )
        )
    ).scalar() or 0
    cobertura = round((cobertos / total * 100) if total else 0.0, 1)
    nivel = "baixo" if cobertura >= 90 else "medio" if cobertura >= 70 else "alto"
    return {
        "total_postos": int(total),
        "postos_cobertos": int(cobertos),
        "cobertura_atual": cobertura,
        "nivel_risco": nivel,
        "riskLevel": nivel,
    }


@ai_router.get("/command-center")
async def command_center(_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    """Command center operacional com visão de cobertura, agentes e risco semanal (dado real)."""
    hoje = datetime.now(ZoneInfo("America/Manaus")).date()
    agentes = (await db.execute(text("SELECT count(*) FROM employees WHERE status='ativo'"))).scalar() or 0
    presentes = (
        await db.execute(
            text(
                "SELECT count(DISTINCT employee_id) FROM gp_clock_punches "
                "WHERE punch_type='entrada' AND (punch_timestamp)::date = :h"
            ),
            {"h": hoje},
        )
    ).scalar() or 0
    cov = await _coverage(db)
    # mapa de risco semanal: derivado da cobertura (placeholder honesto, sem inventar evento)
    weekly = [{"dia": d, "nivel_risco": cov["nivel_risco"], "cobertura": cov["cobertura_atual"]} for d in _SEMANA]
    return {
        "overview": {
            "agentes_ativos": int(agentes),
            "agentes_presentes": int(presentes),
            "agentes_ausentes": max(0, int(agentes) - int(presentes)),
            "total_postos": cov["total_postos"],
            "cobertura_atual": cov["cobertura_atual"],
        },
        "coverage_prediction": cov,
        "weekly_risk_map": weekly,
        "agents_status": {
            "total": int(agentes),
            "presentes": int(presentes),
            "ausentes": max(0, int(agentes) - int(presentes)),
        },
    }


@ai_router.get("/performance-overview")
async def performance_overview(_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    """Resumo de performance operacional (dado real + mensagem)."""
    cov = await _coverage(db)
    alocacoes = (await db.execute(text("SELECT count(*) FROM allocations WHERE status='active'"))).scalar() or 0
    msg = (
        f"Cobertura atual de {cov['cobertura_atual']}% em {cov['total_postos']} postos "
        f"({cov['postos_cobertos']} cobertos, {alocacoes} alocações ativas). Risco {cov['nivel_risco']}."
    )
    return {
        "message": msg,
        "cobertura_atual": cov["cobertura_atual"],
        "total_postos": cov["total_postos"],
        "alocacoes_ativas": int(alocacoes),
        "nivel_risco": cov["nivel_risco"],
    }
