"""
Controller de Clima Organizacional para RH.

Fornece dashboard com indicadores de clima e absenteismo,
preparado para receber dados de pesquisas futuras.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/climate", tags=["RH - Clima"])


PARTICIPACAO_MINIMA_PCT = 30.0
SCORE_MINIMO_ALERTA = 6.0


