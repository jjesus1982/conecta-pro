"""
My Benefits Controller — Beneficios do funcionario conforme CCT 2026.

Endpoints:
- GET /portal/my-benefits (lista beneficios ativos com valores CCT)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId
from modules.people_management.employee_portal.utils.portal_cache import (
    CACHE_TTLS,
    portal_cache_get,
    portal_cache_set,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Beneficios"])


@router.get("/my-benefits")
async def get_my_benefits(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna beneficios do funcionario com valores da CCT 2026."""
    eid = str(employee_id)

    # Tentar cache primeiro (TTL 1 hora — dados de beneficios mudam raramente)
    cached = await portal_cache_get(eid, "beneficios")
    if cached is not None:
        return cached

    from modules.cct.models.benefits import BENEFICIOS_OBRIGATORIOS_CCT

    # Buscar dados do colaborador
    salario_base = 0.0
    cargo = ""
    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        emp = result.scalar_one_or_none()
        if emp:
            salario_base = float(getattr(emp, "salario_base", 0) or 0)
            cargo = getattr(emp, "cargo", "") or ""
    except ImportError:
        pass

    # Buscar beneficios cadastrados do colaborador
    beneficios_ativos = []
    try:
        from sqlalchemy import select as sel

        from modules.people_management.hr.models.benefits import EmployeeBenefit

        result = await db.execute(
            sel(EmployeeBenefit).where(
                EmployeeBenefit.employee_id == employee_id,
                EmployeeBenefit.status == "active",
            )
        )
        for b in result.scalars().all():
            beneficios_ativos.append(
                {
                    "tipo": b.type,
                    "operadora": b.provider,
                    "plano": b.plan_name,
                    "desconto_funcionario": float(b.employee_contribution or 0),
                    "contribuicao_empresa": float(b.company_contribution or 0),
                    "status": b.status,
                }
            )
    except (ImportError, Exception) as exc:
        logger.debug("Beneficios cadastrados nao disponiveis: %s", exc)

    # Montar resposta com referencia CCT
    beneficios_cct = []
    for b in BENEFICIOS_OBRIGATORIOS_CCT:
        if not b.obrigatorio:
            continue

        desconto_calculado = None
        if b.desconto_percentual and salario_base > 0:
            desconto_calculado = round(salario_base * float(b.desconto_percentual) / 100, 2)

        beneficios_cct.append(
            {
                "tipo": b.tipo.value,
                "obrigatorio": b.obrigatorio,
                "valor_minimo_cct": float(b.valor_total) if b.valor_total else None,
                "valor_empresa_cct": float(b.valor_empresa) if b.valor_empresa else None,
                "desconto_maximo_cct": (float(b.desconto_maximo_empregado) if b.desconto_maximo_empregado else None),
                "desconto_percentual_cct": float(b.desconto_percentual) if b.desconto_percentual else None,
                "desconto_calculado": desconto_calculado,
                "observacao": b.observacao,
            }
        )

    result_data = {
        "employee_id": eid,
        "cargo": cargo,
        "salario_base": salario_base,
        "beneficios_ativos": beneficios_ativos,
        "beneficios_cct": beneficios_cct,
        "cct": "SINDECOMPRESTS/SINDICOND-AM 2026",
    }

    await portal_cache_set(eid, "beneficios", result_data, ttl=CACHE_TTLS["beneficios"])
    return result_data
