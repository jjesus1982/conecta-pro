"""
My Vacations Controller — Consulta de ferias do funcionario.

Endpoints:
- GET /portal/my-vacations/balance
- GET /portal/my-vacations/requests
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Ferias"])


class VacationBalanceResponse(BaseModel):
    """Saldo de ferias do funcionario."""

    dias_direito: int = 30
    dias_gozados: int = 0
    dias_saldo: int = 30
    total_bruto_ferias: float = 0.0
    periodo_aquisitivo_inicio: str | None = None
    periodo_aquisitivo_fim: str | None = None

    model_config = ConfigDict(from_attributes=True)


class VacationRequestResponse(BaseModel):
    """Solicitacao de ferias do funcionario."""

    id: str | None = None
    data_inicio: str | None = None
    data_fim: str | None = None
    dias: int | None = None
    status: str | None = None
    tipo: str | None = None
    created_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


