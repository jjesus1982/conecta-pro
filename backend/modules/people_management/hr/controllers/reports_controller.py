"""
Controller de Relatórios — Departamento Pessoal.

Endpoints de relatórios gerenciais: headcount, turnover, custo de benefícios.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["DP - Relatórios"])


