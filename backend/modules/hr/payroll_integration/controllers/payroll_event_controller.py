"""Controller para eventos de folha de pagamento."""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["Payroll Events"])




def _uget(user, key, default=None):
    """Acessa campo do usuário seja objeto User (get_current_user) ou dict — os endpoints
    usavam current_user['x'], que crashava no User ('User' object is not subscriptable)."""
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)
