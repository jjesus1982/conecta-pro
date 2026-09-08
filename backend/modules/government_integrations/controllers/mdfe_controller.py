"""
Controller REST para MDF-e (Manifesto Eletronico de Documentos Fiscais).

Endpoints para operacoes do MDF-e.
"""

import logging

from fastapi import APIRouter


from ..services.mdfe_service import (
    MDFeService,
    get_mdfe_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mdfe", tags=["MDF-e"])


def get_service() -> MDFeService:
    """Dependency para obter o service."""
    return get_mdfe_service()


