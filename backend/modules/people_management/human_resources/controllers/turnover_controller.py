"""
Controller de Turnover para RH.

Fornece dashboard com dados reais de admissoes, desligamentos
e taxa de turnover baseados na tabela employees.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/turnover", tags=["RH - Turnover"])


@router.get("/dashboard")
async def turnover_dashboard(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard de turnover com dados reais."""
    try:
        from modules.operacional.models.employee import Employee

        total = (await db.execute(select(func.count()).select_from(Employee))).scalar() or 0

        ativos = (
            await db.execute(select(func.count()).select_from(Employee).where(func.lower(Employee.status) == "ativo"))
        ).scalar() or 0

        admitidos_90d = (
            await db.execute(
                text("SELECT count(*) FROM employees WHERE data_admissao >= CURRENT_DATE - INTERVAL '90 days'")
            )
        ).scalar() or 0

        desligados_90d = (
            await db.execute(
                text("SELECT count(*) FROM employees WHERE data_demissao >= CURRENT_DATE - INTERVAL '90 days'")
            )
        ).scalar() or 0

        media = (ativos + total) / 2 if total > 0 else 1
        taxa_turnover = round(((admitidos_90d + desligados_90d) / 2 / media) * 100, 2) if media > 0 else 0

        por_cargo = (
            (
                await db.execute(
                    text(
                        "SELECT cargo, count(*) as qtd FROM employees "
                        "WHERE status = 'ativo' GROUP BY cargo ORDER BY qtd DESC"
                    )
                )
            )
            .mappings()
            .all()
        )

        return {
            "total_colaboradores": total,
            "ativos": ativos,
            "admitidos_90_dias": admitidos_90d,
            "desligados_90_dias": desligados_90d,
            "taxa_turnover_trimestral": taxa_turnover,
            "distribuicao_cargo": [dict(r) for r in por_cargo],
        }
    except Exception as exc:
        logger.warning("Erro no dashboard turnover: %s", exc)
        return {"total_colaboradores": 0, "taxa_turnover_trimestral": 0}


@router.get("/motivos")
async def turnover_motivos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Distribuicao por motivo de desligamento nos ultimos 12 meses."""
    try:
        result = (
            (
                await db.execute(
                    text(
                        "SELECT motivo_desligamento, COUNT(*) as total "
                        "FROM employees "
                        "WHERE motivo_desligamento IS NOT NULL "
                        "AND data_demissao >= CURRENT_DATE - INTERVAL '12 months' "
                        "GROUP BY motivo_desligamento ORDER BY total DESC"
                    )
                )
            )
            .mappings()
            .all()
        )
        return {"motivos": [dict(r) for r in result], "periodo": "12_meses"}
    except Exception as exc:
        logger.warning("Erro ao buscar motivos: %s", exc)
        return {"motivos": [], "periodo": "12_meses"}
