"""
Controller para o módulo de Configurações e Multi-tenant
Sprint 35: Configurações e Multi-tenant
"""
# pylint: disable=unused-argument,too-many-locals,redefined-outer-name

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from core.auth.dependencies import get_current_active_user
from core.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["Config"])


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Verifica se usuario atual é admin (mesmo padrão de api/v1/endpoints/users.py).

    HARDENING pré-autocadastro: TODA escrita em /config/* (POST/PUT/PATCH/DELETE)
    e TODA leitura de tenants exigem admin — usuários 'pending'/comuns não podem
    tocar em tenants, settings, system configs, feature flags ou templates.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]


# ==================== Tenant Endpoints ====================


# ==================== TenantSettings Endpoints ====================


# ==================== SystemConfig Endpoints ====================


# ==================== FeatureFlag Endpoints ====================


# ==================== NotificationTemplate Endpoints ====================


# ==================== Dashboard Endpoints ====================


