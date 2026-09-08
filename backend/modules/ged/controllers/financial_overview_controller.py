"""
Controller de Overview Financeiro — dados para a pagina /modulos/financeiro.

Endpoints que a pagina principal chama via hooks Orval:
- GET /bi-dashboard/bi/dashboards/stats → IFinancialOverview
- GET /payables/payables/stats → PayableStats
- GET /receivables/receivables/stats → ReceivableStats
- GET /cashflow/cashflow/dashboard → CashflowDashboard
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Financial Overview"])


