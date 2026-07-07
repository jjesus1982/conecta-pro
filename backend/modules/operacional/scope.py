"""
Escopo operacional por posto.

Define QUAIS postos um usuário pode enxergar no módulo operacional:

- LÍDER DE POSTO (employee vinculado ao user lidera >=1 post via posts.leader_id):
  escopo SEMPRE limitado aos seus postos — mesmo que o role seja admin.
- Roles gerenciais (admin, super_admin, administrador, gerente_operacional,
  supervisor, inspetor): veem TUDO (all_posts=True, is_manager=True).
- Demais usuários sem posto vinculado: sem acesso a dados de posto
  (all_posts=False e post_ids vazio → 403 via scope_post_ids_or_403).

Observação de runtime: users.employee_id e posts.leader_id EXISTEM no banco,
mas o model core User pode não ter o atributo em runtime antigo — por isso
as consultas aqui usam SQL text, nunca atributos do ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db

# Roles que enxergam todos os postos (quando NÃO são líderes de posto)
MANAGER_ROLES = {
    "admin",
    "super_admin",
    "administrador",
    "gerente_operacional",
    "supervisor",
    "inspetor",
}


@dataclass
class OperationalScope:
    """Escopo de visibilidade operacional do usuário autenticado."""

    all_posts: bool
    post_ids: list[str] = field(default_factory=list)  # vazio se all_posts
    employee_id: str | None = None
    user_id: str = ""
    user_name: str = ""
    is_manager: bool = False


async def get_operational_scope(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> OperationalScope:
    """
    FastAPI dependency: resolve o escopo operacional do usuário atual.

    Regras (nesta ordem):
    1. employee_id do usuário via SQL text (users.employee_id).
    2. Se o employee lidera >=1 post ativo (posts.leader_id) → escopado a esses
       posts (LÍDER SEMPRE ESCOPADO, mesmo com role admin).
    3. Senão, role gerencial → all_posts=True, is_manager=True.
    4. Senão → sem acesso a dados de posto (all_posts=False, post_ids=[]).
    """
    user_id = str(current_user.id)
    user_name = getattr(current_user, "name", "") or ""

    # (1) employee_id via SQL text — o atributo do model pode não existir em runtime velho
    employee_id: str | None = None
    row = (
        await db.execute(
            text("SELECT employee_id FROM users WHERE id = :uid"),
            {"uid": user_id},
        )
    ).first()
    if row and row[0]:
        employee_id = str(row[0])

    # (2) líder de posto → escopo limitado aos seus posts, SEMPRE
    if employee_id:
        rows = (
            await db.execute(
                text("SELECT id FROM posts WHERE leader_id = :emp AND is_active = TRUE"),
                {"emp": employee_id},
            )
        ).fetchall()
        led_post_ids = [str(r[0]) for r in rows]
        if led_post_ids:
            return OperationalScope(
                all_posts=False,
                post_ids=led_post_ids,
                employee_id=employee_id,
                user_id=user_id,
                user_name=user_name,
                is_manager=False,
            )

    # (3) roles gerenciais veem tudo
    if (current_user.role or "") in MANAGER_ROLES:
        return OperationalScope(
            all_posts=True,
            post_ids=[],
            employee_id=employee_id,
            user_id=user_id,
            user_name=user_name,
            is_manager=True,
        )

    # (4) sem posto vinculado → sem acesso a dados de posto
    return OperationalScope(
        all_posts=False,
        post_ids=[],
        employee_id=employee_id,
        user_id=user_id,
        user_name=user_name,
        is_manager=False,
    )


def scope_post_ids_or_403(scope: OperationalScope) -> list[str] | None:
    """
    Retorna a lista de post_ids do escopo, ou None se o usuário vê todos.

    Levanta 403 se o usuário não tem nenhum posto vinculado (vazio honesto:
    quem não é gestor nem líder não enxerga dado de posto de ninguém).
    """
    if scope.all_posts:
        return None
    if not scope.post_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem posto vinculado ao seu usuário — sem acesso a dados de posto.",
        )
    return scope.post_ids
