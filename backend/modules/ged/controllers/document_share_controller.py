"""Controller para DocumentShare."""

import logging

from fastapi import APIRouter



def _uid(current_user) -> str:
    """Extrai user id de User object ou dict."""
    return str(current_user.id) if hasattr(current_user, "id") else _uid(current_user)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document-shares", tags=["GED - Compartilhamento"])


