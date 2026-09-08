"""
Controller de Consentimento LGPD.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database.session import get_sync_db_dependency
from modules.security_lgpd.repositories.consent_repository import ConsentRepository
from modules.security_lgpd.services.consent_service import ConsentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/consent", tags=["LGPD - Consentimento"])


def get_consent_service(db: Session = Depends(get_sync_db_dependency)) -> ConsentService:
    """Injeta um ConsentService com repository ligado a sessao de banco."""
    return ConsentService(ConsentRepository(db))


