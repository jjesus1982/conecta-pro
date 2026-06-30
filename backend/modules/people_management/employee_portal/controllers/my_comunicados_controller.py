"""
My Comunicados Controller — Comunicados e avisos do DP.

Endpoints:
- GET /portal/comunicados (avisos do DP para o funcionario)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Comunicados"])


@router.get("/comunicados")
async def get_meus_comunicados(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna comunicados e avisos do DP para o funcionario."""
    # Buscar notificacoes do tipo comunicado
    comunicados = []
    try:
        from sqlalchemy import select

        from modules.people_management.employee_portal.models.notification import (
            PortalNotification,
        )

        result = await db.execute(
            select(PortalNotification)
            .where(PortalNotification.employee_id == employee_id)
            .order_by(PortalNotification.created_at.desc())
            .limit(50)
        )
        for notif in result.scalars().all():
            comunicados.append(
                {
                    "id": str(notif.id),
                    "titulo": notif.title,
                    "mensagem": notif.message,
                    "lido": notif.is_read,
                    "data": str(notif.created_at),
                }
            )
    except (ImportError, Exception) as exc:
        logger.debug("Notificacoes nao disponiveis: %s", exc)

    # Se nao ha comunicados, retornar mensagem padrao
    if not comunicados:
        comunicados = [
            {
                "id": "default-1",
                "titulo": "Bem-vindo ao Portal do Funcionario",
                "mensagem": (
                    "Este e o seu espaco para consultar contracheques, beneficios, "
                    "escala, direitos da CCT e muito mais. Em caso de duvidas, "
                    "procure o Departamento Pessoal."
                ),
                "lido": False,
                "data": "2026-01-01",
            },
        ]

    return {"total": len(comunicados), "comunicados": comunicados}
