"""
Controller de Autenticacao do Portal do Cliente.

Endpoints publicos (sem autenticacao) para login, refresh e logout.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.rate_limit import limiter
from modules.client_portal.schemas.auth import (
    PortalLoginRequest,
    PortalLoginResponse,
    PortalTokenRefresh,
)
from modules.client_portal.services.auth_service import PortalAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Portal - Autenticacao"])


@router.post("/login", response_model=PortalLoginResponse)
@limiter.limit("10/minute")  # anti brute-force: o router do portal não herda o rate-limit do ERP
async def portal_login(
    data: PortalLoginRequest,
    request: Request,
    response: Response,  # exigido pelo slowapi p/ injetar os headers de rate-limit
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Autentica um cliente no portal.

    Recebe username e password, valida contra ged_clients e
    retorna um token JWT com validade de 24 horas.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    service = PortalAuthService(db)
    try:
        result = await service.login(
            username=data.username,
            password=data.password,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/refresh", response_model=PortalLoginResponse)
async def portal_refresh(
    data: PortalTokenRefresh,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Renova o token JWT do portal.

    Invalida o token atual e emite um novo com validade estendida.
    """
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    service = PortalAuthService(db)
    try:
        result = await service.refresh_token(
            current_token=data.access_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout")
async def portal_logout(
    data: PortalTokenRefresh,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Encerra a sessao do cliente no portal.

    Invalida o token JWT atual, impedindo uso futuro.
    """
    service = PortalAuthService(db)
    result = await service.logout(token=data.access_token)
    await db.commit()
    return result
