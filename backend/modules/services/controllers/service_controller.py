"""
ServiceController - REST API Endpoints
Sprint 31: Gestão de Serviços
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database.session import get_sync_db_dependency
from modules.services.repositories import ServiceRepository
from modules.services.services import ServiceAIService, ServiceManagementService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["Services"])


def get_management_service(db: Session = Depends(get_sync_db_dependency)) -> ServiceManagementService:
    """Dependency para ServiceManagementService."""
    return ServiceManagementService(db)


def get_ai_service(db: Session = Depends(get_sync_db_dependency)) -> ServiceAIService:
    """Dependency para ServiceAIService."""
    return ServiceAIService(db)


def get_repository(db: Session = Depends(get_sync_db_dependency)) -> ServiceRepository:
    """Dependency para ServiceRepository."""
    return ServiceRepository(db)


# ============================================================
# SERVICE CATALOG ENDPOINTS
# ============================================================


# ============================================================
# SERVICE ORDER ENDPOINTS
# ============================================================


# ============================================================
# SERVICE EXECUTION ENDPOINTS
# ============================================================


# ============================================================
# SERVICE REPORT ENDPOINTS
# ============================================================


# ============================================================
# SLA CONFIG ENDPOINTS
# ============================================================


# ============================================================
# AI/ANALYTICS ENDPOINTS
# ============================================================


