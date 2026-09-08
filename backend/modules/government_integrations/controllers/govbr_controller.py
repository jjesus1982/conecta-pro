"""
Controller REST para Gov.br - Plataforma de Login Unico do Governo Federal.

Endpoints para autenticacao OAuth2/OIDC com Gov.br.
"""

import logging

from fastapi import APIRouter


from ..services.govbr_service import GovBrService, get_govbr_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/govbr", tags=["Gov.br - Autenticacao"])


def get_service() -> GovBrService:
    """Dependency para obter o service."""
    return get_govbr_service()


