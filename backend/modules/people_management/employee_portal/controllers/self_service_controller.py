"""
Self-Service do Funcionário (login Google / JWT principal).

Diferente do Portal do Funcionário clássico (login por CPF, audience
'employee_portal'), este router atende o funcionário que entra com a CONTA
GOOGLE — o MESMO fluxo dos gestores. A conta é um `User` (role='funcionario',
permissions=['self:portal']) vinculado a um `employees.id` via users.employee_id
(gravado na aprovação de perfil pelo Jordan).

Todos os endpoints resolvem o employee_id a partir de users.employee_id do
usuário autenticado (CurrentActiveUser). O funcionário só enxerga/baixa o que é
DELE — nunca documento/holerite de outro, nunca módulo de gestão.

Reusa integralmente a lógica já provada do portal clássico (payslips, ponto,
férias, benefícios): importa as funções dos controllers `my_*` e as chama com o
employee_id resolvido, sem duplicar regra de negócio.

Montado sob /portal (aggregator) → prefixo final /portal/self-service/*.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from core.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/self-service", tags=["Self-Service do Funcionário"])


def _employee_id(current_user: User) -> str:
    """Resolve o employee_id vinculado à conta, ou 400 se não vinculada."""
    if not current_user.employee_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Sua conta não está vinculada a um funcionário (employee_id ausente). "
            "Peça a um administrador para aprovar seu acesso com o perfil 'Funcionário'.",
        )
    return str(current_user.employee_id)


@router.get(
    "/me",
    summary="Meu resumo (funcionário logado)",
    description="Dados básicos + dashboard do funcionário vinculado à conta Google.",
)
async def meu_resumo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.services.portal_service import (
        PortalService,
    )

    svc = PortalService(db)
    try:
        dashboard = await svc.get_dashboard(UUID(emp))
    except Exception as e:  # noqa: BLE001
        logger.warning("self-service dashboard indisponível p/ %s: %s", emp, e)
        dashboard = {}
    return {
        "employee_id": emp,
        "nome": current_user.name,
        "email": current_user.email,
        "dashboard": dashboard,
    }


@router.get(
    "/meus-holerites",
    summary="Meus holerites",
    description="Lista os holerites do funcionário logado (por ano).",
)
async def meus_holerites(
    year: int | None = Query(default=None, ge=2020, le=2030),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_payslips_controller import (
        get_my_payslips,
    )

    return await get_my_payslips(employee_id=emp, year=year, db=db)


@router.get(
    "/meus-holerites/{month}/{year}",
    summary="Holerite por mês/ano",
)
async def meu_holerite_mes(
    month: int,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_payslips_controller import (
        get_payslip_by_month,
    )

    return await get_payslip_by_month(employee_id=emp, month=month, year=year, db=db)


@router.get(
    "/meus-holerites/{month}/{year}/pdf",
    summary="Baixar PDF do holerite",
)
async def meu_holerite_pdf(
    month: int,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_payslips_controller import (
        get_payslip_pdf,
    )

    return await get_payslip_pdf(employee_id=emp, month=month, year=year, db=db)


@router.get(
    "/minhas-ferias/saldo",
    summary="Meu saldo de férias",
)
async def minhas_ferias_saldo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_vacations_controller import (
        get_vacation_balance,
    )

    return await get_vacation_balance(employee_id=emp, db=db)


@router.get(
    "/minhas-ferias/solicitacoes",
    summary="Minhas solicitações de férias",
)
async def minhas_ferias_solicitacoes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_vacations_controller import (
        get_vacation_requests,
    )

    return await get_vacation_requests(employee_id=emp, db=db)


@router.get(
    "/meu-ponto",
    summary="Meu espelho de ponto",
)
async def meu_ponto(
    mes: int | None = Query(default=None, ge=1, le=12),
    ano: int | None = Query(default=None, ge=2020, le=2030),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_ponto_controller import (
        get_ponto_historico,
    )

    return await get_ponto_historico(employee_id=emp, mes=mes, ano=ano, db=db)


@router.get(
    "/meus-beneficios",
    summary="Meus benefícios",
)
async def meus_beneficios(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_benefits_controller import (
        get_my_benefits,
    )

    return await get_my_benefits(employee_id=emp, db=db)


@router.get(
    "/meus-documentos-a-assinar",
    summary="Meus documentos pendentes de assinatura",
    description="Atalho self-service para as assinaturas pendentes do funcionário "
    "logado (mesma fonte de GET /signatures/meus-pendentes).",
)
async def meus_documentos_a_assinar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.signatures.services.universal_signature_service import (
        UniversalSignatureService,
    )

    svc = UniversalSignatureService(db)
    pendentes = await svc.pendentes_do_funcionario(UUID(emp))
    return {"employee_id": emp, "total": len(pendentes), "pendentes": pendentes}
