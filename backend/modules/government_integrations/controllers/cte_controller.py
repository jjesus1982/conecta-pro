"""
Controller REST para CT-e (Conhecimento de Transporte Eletronico).

Endpoints para operacoes do CT-e.
"""

import logging

from fastapi import APIRouter


from ..services.cte_service import (
    CTeService,
    get_cte_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cte", tags=["CT-e"])


def get_service() -> CTeService:
    """Dependency para obter o service."""
    return get_cte_service()


