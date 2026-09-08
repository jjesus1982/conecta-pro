"""Scheduler Controller - REST API Endpoints.

Sprint 35 - Task Scheduler.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db  # noqa: F401
from core.database.session import get_sync_db_dependency

# Queue models used via schemas
from modules.scheduler.services.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


def get_scheduler_service(db: Session = Depends(get_sync_db_dependency)) -> SchedulerService:
    """Dependency para obter o SchedulerService."""
    return SchedulerService(db)


# ==================== Task Endpoints ====================


# ==================== Execution Endpoints ====================


# ==================== Queue Endpoints ====================


# ==================== Worker Endpoints ====================


# ==================== Lock Endpoints ====================


# ==================== Scheduler Operations ====================


