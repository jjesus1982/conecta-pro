"""
Controller EPI (NR-6) - Equipamentos de Protecao Individual
============================================================

Endpoints REST para gestao de EPIs.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database.session import get_sync_db_dependency
from modules.health_occupational.services.epi_service import EPIService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/epi", tags=["EPI - Equipamentos de Protecao (NR-6)"])


# Dependency para obter o service com DB session
def get_epi_service(db: Session = Depends(get_sync_db_dependency)) -> EPIService:
    """Retorna instancia do EPIService com DB session."""
    return EPIService(db=db)


# ==============================================================================
# EPI Catalog Endpoints
# ==============================================================================


# ==============================================================================
# Reference Data Endpoints
# ==============================================================================


# ==============================================================================
# Statistics Endpoint
# ==============================================================================


# ==============================================================================
# Inventory Endpoints
# ==============================================================================


# ==============================================================================
# EPI Delivery Endpoints
# ==============================================================================


# ==============================================================================
# Parametric {epi_id} Endpoints (MUST be last to avoid capturing specific paths)
# ==============================================================================


