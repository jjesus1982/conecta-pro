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
    "funcionario": {
        "label": "Funcionário (self-service)",
        "descricao": "Área do funcionário (self-service): meus documentos a assinar, "
        "holerite, férias, ponto e benefícios. SEM acesso a módulos de gestão. "
        "Exige vínculo com funcionário (employee_id).",
        "role": "funcionario",
        "permissions": ["self:portal"],
        "somente_ceo": False,
        "requer_employee_id": True,
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


class UserAprovarBody(BaseModel):
    """Body do POST /users/{id}/aprovar."""

    perfil: str
    employee_id: UUID | None = None


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

    # ⭐ APROVOU → A PESSOA RECEBE AS INSTRUÇÕES. Pedido do Jordan, 26/09/2026: *"tem que passar
    # a ela as mesmas instruções que mandou ao jair, e isso tem que ser automático no sistema,
    # aprovei, eles recebem as instruções"*.
    #
    # Hoje o ciclo morria aqui: a conta era liberada e ninguém contava à pessoa COMO entrar nem
    # que não existe app. O Jair ficou parado em "Cadastro em análise" sem saber o que fazer, o
    # Wisley recebeu do agente a orientação de instalar o TANGERINO (desligado desde 13/09), e a
    # Thayná trabalhou o dia inteiro sem acesso. Três pessoas, o mesmo silêncio.
    #
    # ⚠️ BEST-EFFORT DE PROPÓSITO: a aprovação já está COMMITADA acima. Se o WhatsApp falhar, o
    # acesso continua liberado — falha de mensagem não pode desfazer a liberação nem devolver
    # 500 para quem aprovou. O erro vai para o log e a pessoa pode ser avisada à mão.
    #
    # ⚠️ O destinatário sai do CADASTRO, nunca de um número digitado: `enviar_guia` delega a
    # `whatsapp.destinatario`, que recusa nome ambíguo e telefone malformado. Eu mandei o guia do
    # Jair para o Antonio Carlos justamente por digitar número.
    if user.employee_id:
        try:
            from modules.people_management.ponto.guia_primeiro_acesso import enviar_guia

            envio = await enviar_guia(db, nome_ou_id=str(user.employee_id))
            logger.info("aprovar_user: guia de primeiro acesso → %s", envio)
        except Exception as exc:  # noqa: BLE001
            logger.error("aprovar_user: acesso LIBERADO mas o guia NÃO saiu para %s — %s",
                         user.email, exc, exc_info=True)

    return UserListItem.from_user(user)


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


