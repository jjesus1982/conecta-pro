"""
Portal Controller — Autenticacao e dashboard do portal do funcionario.

Endpoints:
- POST /portal/auth/login (CPF + senha ou data_nascimento)
- POST /portal/auth/refresh
- POST /portal/auth/logout
- GET /portal/auth/me
- GET /portal/dashboard
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import (
    CurrentEmployeeId,
    _decode_portal_token,
    create_portal_access_token,
    create_portal_refresh_token,
)
from modules.people_management.employee_portal.schemas.portal import (
    PortalDashboard,
    PortalLoginRequest,
    PortalLoginResponse,
)
from modules.people_management.employee_portal.services.portal_service import PortalService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Auth"])

# ---------------------------------------------------------------------------
# PORTAL ANTIGO DESCONTINUADO (login por CPF).
# A entrada oficial agora e o login Google -> aprovacao -> Meu Espaco.
# As rotas de AUTENTICACAO abaixo estao BLOQUEADAS (HTTP 410 Gone), mas o
# corpo original foi PRESERVADO para reversao futura — basta remover o guard.
# NAO afeta as rotas self-service (/portal/self-service/*) nem os my_* — esses
# sao o backend do Meu Espaco novo e continuam funcionando.
# ---------------------------------------------------------------------------
PORTAL_DESCONTINUADO_MSG = (
    "Portal descontinuado. Acesse erp.conectamais.pro e entre com sua conta Google."
)


def _portal_descontinuado() -> None:
    """Guard: bloqueia rotas de auth do portal antigo com HTTP 410 Gone."""
    raise HTTPException(
        status_code=http_status.HTTP_410_GONE,
        detail=PORTAL_DESCONTINUADO_MSG,
    )


@router.post("/auth/login", response_model=PortalLoginResponse, status_code=201)
async def portal_login(
    request: Request,
    login_data: PortalLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Autentica funcionario por CPF + senha ou CPF + data de nascimento.

    DESCONTINUADO — retorna HTTP 410. Use o login Google -> Meu Espaco.
    """
    _portal_descontinuado()

    if not login_data.password and not login_data.data_nascimento:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Informe senha ou data de nascimento.",
        )

    service = PortalService(db)

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    result = await service.authenticate_employee(
        cpf=login_data.cpf,
        password=login_data.password,
        data_nascimento=login_data.data_nascimento,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if not result:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="CPF ou credenciais invalidas.",
        )

    employee_id = str(result["employee_id"])
    nome = result.get("nome", "")
    cargo = result.get("cargo", "")
    cpf = result.get("cpf", "")
    escala = result.get("escala", "")

    access_token = create_portal_access_token(employee_id, nome, cargo, cpf, escala)
    refresh_token = create_portal_refresh_token(employee_id)

    return PortalLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=8 * 3600,
        employee_name=nome,
        employee_id=employee_id,
    )


@router.post("/auth/primeiro-acesso", status_code=201)
async def portal_primeiro_acesso(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Primeiro acesso ao portal: define senha usando CPF + data de nascimento.

    DESCONTINUADO — retorna HTTP 410. Use o login Google -> Meu Espaco.
    """
    _portal_descontinuado()

    from passlib.hash import bcrypt
    from sqlalchemy import select, text

    body = await request.json()
    cpf = (body.get("cpf") or "").replace(".", "").replace("-", "").strip()
    data_nasc = body.get("data_nascimento", "")
    nova_senha = body.get("nova_senha", "")
    confirmar = body.get("confirmar_senha", "")

    if not cpf or not nova_senha:
        raise HTTPException(status_code=400, detail="CPF e nova_senha sao obrigatorios.")
    if len(nova_senha) < 6:
        raise HTTPException(status_code=400, detail="Senha deve ter no minimo 6 caracteres.")
    if nova_senha != confirmar:
        raise HTTPException(status_code=400, detail="Senhas nao conferem.")

    # Buscar funcionario
    from modules.operacional.models.employee import Employee

    result = await db.execute(select(Employee).where(Employee.cpf == cpf, Employee.status == "ativo"))
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Funcionario nao encontrado com este CPF.")

    # Verificar data de nascimento (validacao de identidade)
    dt_nasc_db = str(getattr(employee, "data_nascimento", "") or "")
    if data_nasc and dt_nasc_db and dt_nasc_db != data_nasc:
        raise HTTPException(status_code=401, detail="Data de nascimento nao confere.")

    # Verificar se ja tem senha definida
    existing_hash = await db.execute(
        text("SELECT portal_password_hash FROM employees WHERE id = :eid"),
        {"eid": str(employee.id)},
    )
    current_hash = existing_hash.scalar()

    if current_hash:
        raise HTTPException(
            status_code=409,
            detail="Senha ja definida. Use o endpoint /auth/reset-senha para redefinir.",
        )

    # Definir senha
    hashed = bcrypt.hash(nova_senha)
    await db.execute(
        text(
            "UPDATE employees SET portal_password_hash = :hash, "
            "portal_password_set_at = now(), portal_first_access = false "
            "WHERE id = :eid"
        ),
        {"hash": hashed, "eid": str(employee.id)},
    )
    await db.commit()

    # Gerar token
    access_token = create_portal_access_token(str(employee.id), employee.nome, getattr(employee, "cargo", ""), cpf, "")
    refresh_token = create_portal_refresh_token(str(employee.id))

    logger.info("Primeiro acesso do portal: employee_id=%s cpf=%s***", employee.id, cpf[:3])

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 8 * 3600,
        "employee_name": employee.nome,
        "employee_id": str(employee.id),
        "message": "Senha definida com sucesso! Bem-vindo ao portal.",
    }


@router.post("/auth/reset-senha", status_code=201)
async def portal_reset_senha(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Reset de senha do portal: redefine senha usando CPF + data de nascimento.

    DESCONTINUADO — retorna HTTP 410. Use o login Google -> Meu Espaco.
    """
    _portal_descontinuado()

    from passlib.hash import bcrypt
    from sqlalchemy import select, text

    body = await request.json()
    cpf = (body.get("cpf") or "").replace(".", "").replace("-", "").strip()
    data_nasc = body.get("data_nascimento", "")
    nova_senha = body.get("nova_senha", "")
    confirmar = body.get("confirmar_senha", "")

    if not cpf or not nova_senha:
        raise HTTPException(status_code=400, detail="CPF e nova_senha sao obrigatorios.")
    if len(nova_senha) < 6:
        raise HTTPException(status_code=400, detail="Senha deve ter no minimo 6 caracteres.")
    if nova_senha != confirmar:
        raise HTTPException(status_code=400, detail="Senhas nao conferem.")

    from modules.operacional.models.employee import Employee

    result = await db.execute(select(Employee).where(Employee.cpf == cpf, Employee.status == "ativo"))
    employee = result.scalar_one_or_none()

    if not employee:
        raise HTTPException(status_code=404, detail="Funcionario nao encontrado com este CPF.")

    dt_nasc_db = str(getattr(employee, "data_nascimento", "") or "")
    if data_nasc and dt_nasc_db and dt_nasc_db != data_nasc:
        raise HTTPException(status_code=401, detail="Data de nascimento nao confere.")

    hashed = bcrypt.hash(nova_senha)
    await db.execute(
        text("UPDATE employees SET portal_password_hash = :hash, portal_password_set_at = now() WHERE id = :eid"),
        {"hash": hashed, "eid": str(employee.id)},
    )
    await db.commit()

    logger.info("Reset de senha do portal: employee_id=%s", employee.id)

    return {"message": "Senha redefinida com sucesso. Faca login com a nova senha."}


@router.post("/auth/refresh", status_code=201)
async def portal_refresh(request: Request) -> Any:
    """Renova token de acesso usando refresh token.

    DESCONTINUADO — retorna HTTP 410. Use o login Google -> Meu Espaco.
    """
    _portal_descontinuado()

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token nao fornecido.",
        )

    token = auth_header.replace("Bearer ", "").strip()
    payload = _decode_portal_token(token, "portal_refresh")

    employee_id = payload.get("sub", "")
    nome = payload.get("nome", "")
    cargo = payload.get("cargo", "")

    new_access = create_portal_access_token(employee_id, nome, cargo)
    new_refresh = create_portal_refresh_token(employee_id)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": 8 * 3600,
    }


@router.post("/auth/logout", status_code=201)
async def portal_logout(employee_id: CurrentEmployeeId) -> Any:
    """Logout do portal (invalida sessao client-side)."""
    logger.info("Portal logout: employee_id=%s", employee_id)
    return {"message": "Logout realizado com sucesso."}


@router.get("/auth/me")
async def portal_me(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna dados do funcionario autenticado."""
    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        emp = result.scalar_one_or_none()

        if emp:
            return {
                "employee_id": str(emp.id),
                "nome": emp.nome,
                "cargo": getattr(emp, "cargo", None),
                "cpf": _mask_cpf(getattr(emp, "cpf", "")),
                "data_admissao": str(getattr(emp, "data_admissao", "")),
                "status": getattr(emp, "status", "ativo"),
                "email": getattr(emp, "email", None),
                "telefone": getattr(emp, "telefone", None),
            }
    except ImportError:
        pass

    return {"employee_id": employee_id, "nome": "Funcionario"}


@router.get("/dashboard", response_model=PortalDashboard)
async def get_dashboard(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna dados do dashboard do funcionario autenticado."""
    try:
        service = PortalService(db)
        dashboard_data = await service.get_dashboard(employee_id)
        if dashboard_data:
            return PortalDashboard(**dashboard_data)
    except Exception as exc:
        logger.warning("Erro ao carregar dashboard: %s", exc)

    return PortalDashboard(
        name="Funcionario",
        position=None,
        workplace=None,
        next_shift=None,
        pending_documents=0,
        unread_notifications=0,
    )


def _mask_cpf(cpf: str) -> str:
    """Mascara CPF: 035.***.*42-38."""
    if not cpf or len(cpf) < 11:
        return "***.***.***-**"
    clean = cpf.replace(".", "").replace("-", "")
    return f"{clean[:3]}.***.*{clean[8:10]}-{clean[10:]}"
