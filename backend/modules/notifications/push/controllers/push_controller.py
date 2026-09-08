"""PushController - API REST para Push Notifications.

Sprint 37 - Push Notifications Mobile.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db  # noqa: F401
from core.database.session import get_sync_db_dependency
from modules.notifications.push.services.push_service import PushService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["Push Notifications"])


def get_push_service(
    db: Session = Depends(get_sync_db_dependency),
    current_user: CurrentActiveUser = None,
) -> PushService:
    """Dependency para PushService."""
    from uuid import UUID as _UUID

    tenant_id = getattr(current_user, "tenant_id", None) or _UUID("00000000-0000-0000-0000-000000000001")
    return PushService(db, tenant_id)


# ============================================================================
# Device Endpoints
# ============================================================================


# ============================================================================
# Topic Endpoints
# ============================================================================


# ============================================================================
# Notification Endpoints
# ============================================================================


# ============================================================================
# Campaign Endpoints
# ============================================================================


# ============================================================================
# Segment Endpoints
# ============================================================================


# ============================================================================
# Analytics Endpoints
# ============================================================================


