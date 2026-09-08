"""
Controller PPRA/PGR (NR-9) - Programa de Prevencao de Riscos Ambientais
=======================================================================

Endpoints REST para mapeamento de riscos ocupacionais.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database.session import get_sync_db_dependency
from modules.health_occupational.services.ppra_service import PPRAService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ppra", tags=["PPRA/PGR - Riscos Ocupacionais (NR-9)"])


# Dependency para obter o service com DB session
def get_ppra_service(db: Session = Depends(get_sync_db_dependency)) -> PPRAService:
    """Retorna instancia do PPRAService com DB session."""
    return PPRAService(db=db)


# ==============================================================================
# Risk Mapping Endpoints
# ==============================================================================


# ==============================================================================
# Risk Consultation Endpoints
# ==============================================================================


# ==============================================================================
# Control Measure Endpoints
# ==============================================================================


# ==============================================================================
# Reference Data Endpoints
# ==============================================================================


# ==============================================================================
# Statistics Endpoint
# ==============================================================================


