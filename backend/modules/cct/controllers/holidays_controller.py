"""
Controller de Feriados — CCT 2026.

Endpoints para consulta de feriados Manaus/AM.
"""

import logging
from typing import Any

from fastapi import APIRouter

from core.auth.dependencies import CurrentActiveUser
from modules.cct.models.holidays import (
    FERIADOS_MANAUS_2026,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feriados", tags=["CCT — Feriados"])


@router.get("")
async def get_feriados(
    current_user: CurrentActiveUser,
) -> Any:
    """Retorna todos os 16 feriados de Manaus/AM 2026."""
    return {
        "total": len(FERIADOS_MANAUS_2026),
        "ano": 2026,
        "municipio": "Manaus/AM",
        "feriados": [
            {
                "data": f.data.isoformat(),
                "nome": f.nome,
                "tipo": f.tipo,
                "dia_semana": f.data.strftime("%A"),
            }
            for f in FERIADOS_MANAUS_2026
        ],
    }


