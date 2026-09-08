"""
Controller PCMSO (NR-7) - Programa de Controle Medico de Saude Ocupacional
==========================================================================

Endpoints REST para exames medicos ocupacionais e ASO.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database.session import get_sync_db_dependency
from modules.health_occupational.services.pcmso_service import PCMSOService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pcmso", tags=["PCMSO - Exames Medicos (NR-7)"])


# Dependency para obter o service com DB session
def get_pcmso_service(db: Session = Depends(get_sync_db_dependency)) -> PCMSOService:
    """Retorna instancia do PCMSOService com DB session."""
    return PCMSOService(db=db)


# ==============================================================================
# Medical Exam Endpoints
# ==============================================================================


# ==============================================================================
# ASO Endpoints
# ==============================================================================


# ==============================================================================
# Statistics Endpoint
# ==============================================================================


