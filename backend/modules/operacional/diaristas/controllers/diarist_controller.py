"""Controller para endpoints de Diaristas."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.operacional.diaristas.services.diarist_ai_service import DiaristAIService
from modules.operacional.diaristas.services.diarist_service import DiaristService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diaristas", tags=["Diaristas"])


def get_diarist_service(db: Session = Depends(get_db)) -> DiaristService:
    """Dependency para DiaristService."""
    return DiaristService(db)


def get_ai_service(db: Session = Depends(get_db)) -> DiaristAIService:
    """Dependency para DiaristAIService."""
    return DiaristAIService(db)


# ==================== CONSULTA CPF ====================


# ==================== DIARIST ENDPOINTS (rotas literais primeiro) ====================


# ==================== ASSIGNMENT ENDPOINTS ====================


# ==================== SCHEDULE ENDPOINTS ====================


# ==================== PAYMENT ENDPOINTS ====================


# ==================== EVALUATION ENDPOINTS ====================


# ==================== AI ENDPOINTS ====================


# ==================== STATISTICS ENDPOINTS ====================


# ==================== DIARIST BY ID ENDPOINTS (devem ficar por ultimo) ====================
# IMPORTANTE: Rotas com /{diarist_id} capturam qualquer path.
# Todas as rotas literais (/available, /schedules, /payments, etc.)
# DEVEM ser declaradas ANTES deste bloco.


