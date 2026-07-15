"""
Dependências de autenticação para FastAPI - VERSÃO OTIMIZADA.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db

from .jwt import TokenError, verify_access_token, verify_token_not_blacklisted

if TYPE_CHECKING:
    from core.models import User

security = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> str:
    """
    Extrai e valida o user_id do token JWT.
    Verifica também se o token foi revogado (blacklist).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = verify_access_token(credentials.credentials)

        # Verificar se token foi revogado
        await verify_token_not_blacklisted(payload)

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: subject não encontrado",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user_id

    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# Type alias para uso nos endpoints
CurrentUserId = Annotated[str, Depends(get_current_user_id)]


async def get_current_user(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),  # Usar dependência correta
) -> User:
    """
    Busca o usuario atual no banco de dados.
    """
    # Import local APENAS quando necessário
    from core.models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario nao encontrado",
        )

    return user


async def get_current_active_user(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),  # Usar dependência correta
) -> User:
    """
    Busca o usuario atual e verifica se esta ativo.
    """
    # Import local APENAS quando necessário
    from core.models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario nao encontrado",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inativo",
        )

    return user


# Type aliases otimizados
CurrentUser = Annotated["User", Depends(get_current_user)]
CurrentActiveUser = Annotated["User", Depends(get_current_active_user)]


def require_permission(permission: str):
    """
    Dependency factory que verifica se o usuario tem uma permissao especifica.

    Uso:
        @router.get("/admin", dependencies=[Depends(require_permission("admin"))])
        async def admin_endpoint(): ...
    """

    async def permission_checker(
        user_id: CurrentUserId,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from core.models import User

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario nao encontrado",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inativo",
            )

        # Admin tem todas as permissoes
        if user.role == "admin":
            return user

        # Verificar permissao especifica
        user_permissions = getattr(user, "permissions", []) or []
        if permission not in user_permissions and "*" not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissao '{permission}' requerida",
            )

        return user

    return permission_checker


# Alias para compatibilidade (plural)
require_permissions = require_permission


def require_roles(*roles: str):
    """
    Dependency factory que verifica se o usuario tem uma das roles especificadas.

    Uso:
        @router.get("/admin", dependencies=[Depends(require_roles("admin", "manager"))])
        async def admin_endpoint(): ...
    """
    # Aceita tanto require_roles("admin","rh") quanto require_roles(["admin","rh"]): vários
    # controllers (time-tracking do DP) passam a LISTA num único arg → sem o flatten,
    # `role not in roles` falhava sempre e `', '.join(roles)` quebrava (500 em 16 rotas).
    _flat: list[str] = []
    for r in roles:
        if isinstance(r, (list, tuple, set)):
            _flat.extend(str(x) for x in r)
        else:
            _flat.append(str(r))
    roles = tuple(_flat)

    async def role_checker(
        user_id: CurrentUserId,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from core.models import User

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario nao encontrado",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inativo",
            )

        # Verificar se o usuario tem uma das roles
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role requerida: {', '.join(roles)}",
            )

        return user

    return role_checker


# Alias para compatibilidade
require_role = require_roles


def require_any_permission(*permissions: str):
    """
    Dependency factory que verifica se o usuario tem pelo menos uma das permissoes.
    """

    async def permission_checker(
        user_id: CurrentUserId,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from core.models import User

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario nao encontrado",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inativo",
            )

        # Admin tem todas as permissoes
        if user.role == "admin":
            return user

        # Verificar se tem alguma das permissoes
        user_permissions = getattr(user, "permissions", []) or []
        if "*" in user_permissions:
            return user

        if not any(p in user_permissions for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Uma das permissoes requeridas: {', '.join(permissions)}",
            )

        return user

    return permission_checker
