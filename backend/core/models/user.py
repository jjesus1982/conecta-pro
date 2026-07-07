"""
Modelo de usuário com RBAC.
"""

import uuid as uuid_module
from enum import StrEnum

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel


class UserRole(StrEnum):
    """Roles disponíveis no sistema."""

    SUPER_ADMIN = "super_admin"  # Acesso total ao sistema
    ADMIN = "admin"  # Administrador de empresa
    MANAGER = "manager"  # Gerente de departamento
    SUPERVISOR = "supervisor"  # Supervisor de equipe
    OPERATOR = "operator"  # Operador/funcionário
    CLIENT = "client"  # Cliente externo
    VIEWER = "viewer"  # Apenas visualização


# Hierarquia de permissões (maior = mais permissões)
ROLE_HIERARCHY = {
    UserRole.SUPER_ADMIN: 100,
    UserRole.ADMIN: 80,
    UserRole.MANAGER: 60,
    UserRole.SUPERVISOR: 40,
    UserRole.OPERATOR: 20,
    UserRole.CLIENT: 10,
    UserRole.VIEWER: 5,
}


class User(BaseModel):
    """Modelo de usuário do sistema."""

    __tablename__ = "users"

    # Identificação
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Dados pessoais
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # RBAC
    role: Mapped[str] = mapped_column(
        String(50),
        default=UserRole.OPERATOR.value,
        nullable=False,
    )
    permissions: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        default=list,
        nullable=True,
    )

    # Multi-tenant
    condominio_id: Mapped[uuid_module.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Vínculo com funcionário (employees.id) — coluna já existe no banco.
    # Sem relationship de propósito: apenas espelho da coluna (mudança mínima).
    employee_id: Mapped[uuid_module.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )

    # OAuth providers
    google_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        index=True,
    )

    # Metadata
    last_login: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    def has_role(self, required_role: UserRole) -> bool:
        """
        Verifica se o usuário tem o role requerido ou superior.

        Args:
            required_role: Role mínimo necessário

        Returns:
            True se o usuário tem permissão
        """
        user_level = ROLE_HIERARCHY.get(UserRole(self.role), 0)
        required_level = ROLE_HIERARCHY.get(required_role, 0)
        return user_level >= required_level

    def has_permission(self, permission: str) -> bool:
        """
        Verifica se o usuário tem uma permissão específica.

        Args:
            permission: Nome da permissão

        Returns:
            True se o usuário tem a permissão
        """
        if self.role == UserRole.SUPER_ADMIN.value:
            return True

        return permission in (self.permissions or [])

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
