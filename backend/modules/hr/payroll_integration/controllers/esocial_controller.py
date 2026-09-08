"""Controller para integração eSocial."""

import logging

from fastapi import APIRouter


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/esocial", tags=["eSocial"])


def _uget(user, key, default=None):
    """Acessa campo do usuário seja ele objeto User (get_current_user) ou dict
    (require_permissions). Os endpoints misturavam current_user['x'] (crashava no
    objeto User: 'User' object is not subscriptable) com current_user.x."""
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)


