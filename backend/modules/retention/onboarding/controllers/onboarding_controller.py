"""
Controller FastAPI para o módulo de Onboarding Digital.

Este módulo define todos os endpoints da API REST para gerenciamento
do processo de onboarding de funcionários.

Routers:
    router: Router principal com todos os endpoints de onboarding
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.retention.onboarding.services import (
    OnboardingService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/retention/onboarding",
    tags=["Retention - Onboarding Digital"],
)


# =============================================================================
# DEPENDENCY HELPERS
# =============================================================================


def get_service(db: AsyncSession = Depends(get_db)) -> OnboardingService:
    """Obtém instância do service."""
    return OnboardingService(db)


# =============================================================================
# CHECKLIST ENDPOINTS
# =============================================================================


# =============================================================================
# STEP ENDPOINTS
# =============================================================================


# =============================================================================
# FUNCIONÁRIO ONBOARDING ENDPOINTS
# =============================================================================


# =============================================================================
# DASHBOARD E ALERTAS
# =============================================================================


