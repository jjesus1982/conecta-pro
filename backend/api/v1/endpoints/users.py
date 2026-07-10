"""
Endpoints de gerenciamento de usuarios.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from core.logging import logger
from core.models import User
from core.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["Users"])

JORDAN_EMAIL = "jjesus@conectamais.pro"
MODULOS_VALIDOS = {
    "module:financeiro",
    "module:fiscal",
    "module:dp",
    "module:operacional",
    "module:crm",
    "module:ged",
    "module:sst",
    "module:dev",
}

# Presets de aprovação por perfil (POST /users/{id}/aprovar).
# Aprovação = 1 chamada: seta role + permissions + employee_id + is_active.
PERFIS_APROVACAO: dict[str, dict] = {
    "executivo": {
        "label": "Executivo",
        "descricao": "Acesso total ao ERP (wildcard 'all'). Concessão exclusiva do CEO.",
        "role": "admin",
        "permissions": ["all"],
        "somente_ceo": True,
        "requer_employee_id": False,
    },
    "gestao_operacional": {
        "label": "Gestão Operacional",
        "descricao": "Gerência do operacional + DP + GED + SST (Operacional, Pessoas, Kits, Saúde/Segurança).",
        "role": "gerente_operacional",
        "permissions": ["module:operacional", "module:dp", "module:ged", "module:sst"],
        "somente_ceo": False,
        "requer_employee_id": False,
    },
    "lider_posto": {
        "label": "Líder de Posto",
        "descricao": "Líder de equipe local: SST (fichas EPI/assinaturas) + escopo operacional restrito ao próprio posto (via posts.leader_id). Exige vínculo com funcionário (employee_id).",
        "role": "lider",
        "permissions": ["module:sst"],
        "somente_ceo": False,
        "requer_employee_id": True,
    },
    "sst": {
        "label": "SST",
        "descricao": "Saúde e Segurança do Trabalho: módulo SST + GED (documentos/kits).",
        "role": "operator",
        "permissions": ["module:sst", "module:ged"],
        "somente_ceo": False,
        "requer_employee_id": False,
    },
    "dp": {
        "label": "Departamento Pessoal",
        "descricao": "DP: folha, ponto, férias, admissões + GED (kits documentais).",
        "role": "operator",
        "permissions": ["module:dp", "module:ged"],
        "somente_ceo": False,
        "requer_employee_id": False,
    },
    "comercial": {
        "label": "Comercial",
        "descricao": "CRM: leads, oportunidades, propostas, contratos, comissões.",
        "role": "operator",
        "permissions": ["module:crm"],
        "somente_ceo": False,
        "requer_employee_id": False,
    },
}


class UserListItem(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    permissions: list[str]
    is_active: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, u: User) -> "UserListItem":
        return cls(
            id=u.id,
            email=u.email,
            name=u.name,
            role=u.role,
            permissions=list(u.permissions or []),
            is_active=u.is_active,
        )


class UserListItemResponse(BaseModel):
    users: list[UserListItem]
    total: int
    page: int
    per_page: int


class UserPermissionsUpdate(BaseModel):
    permissions: list[str]


# Schemas para gerenciamento de usuarios
class UserUpdateRole(BaseModel):
    """Schema para atualizar role do usuario."""

    role: str


class UserListResponse(BaseModel):
    """Schema para lista paginada de usuarios."""

    users: list[UserResponse]
    total: int
    page: int
    per_page: int


# Roles validos no sistema
VALID_ROLES = [
    # Roles gerais
    "admin",  # Acesso total ao ERP
    "gestor",  # Dashboard, relatorios, operacoes
    "operador",  # Operacoes basicas
    "operator",  # Operacoes basicas (nome usado nos presets de aprovacao e em contas existentes)
    "funcionario",  # Portal do Funcionario (ponto, escalas, docs)
    "pending",  # Aguardando aprovacao
    # Roles do modulo operacional
    "administrador",  # Poder total no operacional
    "gerente_operacional",  # Gestao completa do operacional
    "supervisor",  # Aprova escalas, coordena
    "inspetor",  # Fiscaliza, visualiza relatorios
    "lider",  # Coordena equipe local
    "agente",  # Apenas propria escala + check-in/out
]


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Verifica se usuario atual é admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )
    return current_user


@router.get("/", response_model=UserListItemResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    role: str | None = Query(None, description="Filtrar por role"),
    search: str | None = Query(None, description="Buscar por nome ou email"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserListItemResponse:
    """Lista todos os usuarios (admin only)."""
    query = select(User)
    count_query = select(func.count(User.id))

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    if search:
        search_filter = f"%{search}%"
        query = query.where((User.name.ilike(search_filter)) | (User.email.ilike(search_filter)))
        count_query = count_query.where((User.name.ilike(search_filter)) | (User.email.ilike(search_filter)))

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page).order_by(User.created_at.desc())

    result = await db.execute(query)
    users = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return UserListItemResponse(
        users=[UserListItem.from_user(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.patch("/{user_id}/permissions", response_model=UserListItem)
async def update_user_permissions(
    user_id: str,
    body: UserPermissionsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserListItem:
    """Atualiza permissões de módulos de um usuário (apenas Jordan)."""
    if current_user.email != JORDAN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas Jordan Jesus pode gerenciar permissões de módulos.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    # Jordan não pode ter suas permissões alteradas
    if user.email == JORDAN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="As permissões de Jordan Jesus não podem ser alteradas.",
        )

    # Módulo financeiro só Jordan pode ter — remover se presente
    perms_limpas = [p for p in body.permissions if p in MODULOS_VALIDOS]
    if "module:financeiro" in perms_limpas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Módulo financeiro é exclusivo de Jordan Jesus e não pode ser concedido a outros usuários.",
        )

    user.permissions = perms_limpas
    await db.commit()
    await db.refresh(user)

    logger.info("Permissões atualizadas: %s → %s (por %s)", user.email, perms_limpas, current_user.email)
    return UserListItem.from_user(user)


@router.get("/pending")
async def list_pending_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Lista usuarios aguardando aprovacao (admin only).

    UserListItem (role como str): UserResponse usa o enum UserRole, que nao
    contem 'pending' — model_validate estourava 500 aqui.
    """
    result = await db.execute(select(User).where(User.role == "pending").order_by(User.created_at.desc()))
    users = result.scalars().all()
    logger.info(f"Admin {current_user.email} listou {len(users)} usuarios pendentes")
    return [UserListItem.from_user(u) for u in users]


@router.get("/roles")
async def list_roles(
    current_user: User = Depends(require_admin),
):
    """Lista roles disponiveis no sistema."""
    return {
        "roles": [
            # Roles gerais
            {"value": "admin", "label": "Administrador", "description": "Acesso total ao ERP"},
            {"value": "gestor", "label": "Gestor", "description": "Dashboard, relatórios, operações"},
            {"value": "operador", "label": "Operador", "description": "Operações básicas"},
            {"value": "funcionario", "label": "Funcionário", "description": "Portal do Funcionário"},
            {"value": "pending", "label": "Pendente", "description": "Aguardando aprovação"},
            # Roles do modulo operacional
            {
                "value": "administrador",
                "label": "Administrador Operacional",
                "description": "Poder total no módulo operacional",
            },
            {
                "value": "gerente_operacional",
                "label": "Gerente Operacional",
                "description": "Gestão completa do operacional",
            },
            {"value": "supervisor", "label": "Supervisor", "description": "Aprova escalas, coordena equipes"},
            {"value": "inspetor", "label": "Inspetor", "description": "Fiscaliza postos, visualiza relatórios"},
            {"value": "lider", "label": "Líder", "description": "Coordena equipe local"},
            {"value": "agente", "label": "Agente", "description": "Acesso à própria escala e check-in/out"},
        ]
    }


class UserAprovarBody(BaseModel):
    """Body do POST /users/{id}/aprovar."""

    perfil: str
    employee_id: UUID | None = None


@router.get("/perfis")
async def list_perfis(
    current_user: User = Depends(require_admin),
):
    """Catálogo dos presets de aprovação por perfil (para o frontend)."""
    return {
        "perfis": [
            {
                "value": nome,
                "label": p["label"],
                "descricao": p["descricao"],
                "role": p["role"],
                "permissions": p["permissions"],
                "somente_ceo": p["somente_ceo"],
                "requer_employee_id": p["requer_employee_id"],
            }
            for nome, p in PERFIS_APROVACAO.items()
        ]
    }


# Nota: retorna UserListItem (role como str) — UserRole (enum do UserResponse) não
# contém os roles operacionais (gerente_operacional/lider) e quebraria a serialização.
@router.post("/{user_id}/aprovar", response_model=UserListItem)
async def aprovar_user(
    user_id: str,
    body: UserAprovarBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserListItem:
    """
    Aprova um usuário aplicando um preset de perfil em 1 chamada:
    seta role + permissions + employee_id (quando aplicável) + is_active=True.

    Guard: admin. Preset 'executivo' só pode ser concedido pelo CEO (Jordan).
    """
    preset = PERFIS_APROVACAO.get(body.perfil)
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Perfil inválido. Valores aceitos: {', '.join(PERFIS_APROVACAO)}",
        )

    if preset["somente_ceo"] and current_user.email != JORDAN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas Jordan Jesus (CEO) pode conceder o perfil executivo.",
        )

    if preset["requer_employee_id"] and not body.employee_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O perfil '{body.perfil}' exige employee_id (vínculo com funcionário).",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado")

    # Jordan não pode ter role/permissões alteradas por este endpoint
    if user.email == JORDAN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A conta de Jordan Jesus não pode ser alterada por aprovação de perfil.",
        )

    # Valida vínculo com funcionário quando informado (coluna sem FK — validar aqui)
    if body.employee_id:
        emp = await db.execute(
            text("SELECT 1 FROM employees WHERE id = :eid"),
            {"eid": str(body.employee_id)},
        )
        if emp.scalar() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Funcionário {body.employee_id} não encontrado.",
            )

    user.role = preset["role"]
    user.permissions = list(preset["permissions"])
    if body.employee_id:
        user.employee_id = body.employee_id
    user.is_active = True

    carimbo = (
        f"[{datetime.now(UTC).isoformat(timespec='seconds')}] "
        f"Aprovado por {current_user.email} — perfil '{body.perfil}' "
        f"(role={preset['role']}, permissions={','.join(preset['permissions'])}"
        + (f", employee_id={body.employee_id}" if body.employee_id else "")
        + ")"
    )
    user.notes = f"{user.notes}\n{carimbo}" if user.notes else carimbo

    await db.commit()
    await db.refresh(user)

    logger.info(
        f"Aprovação de perfil: {user.email} → perfil={body.perfil} "
        f"role={preset['role']} perms={preset['permissions']} (por {current_user.email})"
    )
    return UserListItem.from_user(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserResponse:
    """Obtem detalhes de um usuario (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario nao encontrado",
        )

    return UserResponse.model_validate(user)


@router.patch("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: str,
    role_data: UserUpdateRole,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserResponse:
    """Atualiza role de um usuario (admin only)."""
    if role_data.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role invalido. Valores aceitos: {', '.join(VALID_ROLES)}",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario nao encontrado",
        )

    # Nao permitir que admin remova seu proprio acesso
    if str(user.id) == str(current_user.id) and role_data.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voce nao pode remover seu proprio acesso de admin",
        )

    old_role = user.role
    user.role = role_data.role
    await db.commit()
    await db.refresh(user)

    logger.info(f"Admin {current_user.email} alterou role de {user.email}: {old_role} -> {role_data.role}")
    return UserResponse.model_validate(user)


@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserResponse:
    """Ativa um usuario (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario nao encontrado",
        )

    user.is_active = True
    await db.commit()
    await db.refresh(user)

    logger.info(f"Admin {current_user.email} ativou usuario {user.email}")
    return UserResponse.model_validate(user)


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserResponse:
    """Desativa um usuario (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario nao encontrado",
        )

    # Nao permitir que admin desative a si mesmo
    if str(user.id) == str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voce nao pode desativar sua propria conta",
        )

    user.is_active = False
    await db.commit()
    await db.refresh(user)

    logger.info(f"Admin {current_user.email} desativou usuario {user.email}")
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Exclui um usuario permanentemente (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario nao encontrado",
        )

    # Nao permitir que admin exclua a si mesmo
    if str(user.id) == str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voce nao pode excluir sua propria conta",
        )

    email = user.email
    await db.delete(user)
    await db.commit()

    logger.info(f"Admin {current_user.email} excluiu usuario {email}")
