"""
Controller de Onboarding para RH.

Fornece dashboard com colaboradores em periodo de experiencia
e vencimentos proximos, baseados na tabela employees.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["RH - Onboarding"])


@router.get("/pendencias")
async def pendencias(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Itens vencidos ou proximos do vencimento."""
    try:
        vencidos = (
            (
                await db.execute(
                    text(
                        "SELECT c.id, e.nome, c.titulo, c.responsavel, c.prazo_data, "
                        "CURRENT_DATE - c.prazo_data as dias_atraso "
                        "FROM rh_onboarding_checklist c "
                        "JOIN employees e ON e.id = c.employee_id "
                        "WHERE c.concluido = FALSE AND c.prazo_data < CURRENT_DATE "
                        "ORDER BY c.prazo_data"
                    )
                )
            )
            .mappings()
            .all()
        )
        proximos = (
            (
                await db.execute(
                    text(
                        "SELECT c.id, e.nome, c.titulo, c.responsavel, c.prazo_data "
                        "FROM rh_onboarding_checklist c "
                        "JOIN employees e ON e.id = c.employee_id "
                        "WHERE c.concluido = FALSE "
                        "AND c.prazo_data BETWEEN CURRENT_DATE AND CURRENT_DATE + 7 "
                        "ORDER BY c.prazo_data"
                    )
                )
            )
            .mappings()
            .all()
        )
        return {
            "vencidos": [dict(r) for r in vencidos],
            "proximos_7_dias": [dict(r) for r in proximos],
            "total_vencidos": len(vencidos),
            "total_proximos": len(proximos),
        }
    except Exception as exc:
        logger.warning("Erro ao buscar pendencias: %s", exc)
        return {"vencidos": [], "proximos_7_dias": [], "total_vencidos": 0}
