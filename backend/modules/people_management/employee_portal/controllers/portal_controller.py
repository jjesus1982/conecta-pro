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

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import (
    CurrentEmployeeId,
)
from modules.people_management.employee_portal.schemas.portal import (
    PortalDashboard,
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
