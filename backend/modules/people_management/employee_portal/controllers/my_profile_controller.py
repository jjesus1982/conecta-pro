"""
My Profile Controller — Perfil e contrato do funcionario.

Endpoints:
- GET /portal/perfil (dados pessoais, cargo, admissao, escala)
- GET /portal/contrato (tipo vinculo, carga horaria, local)
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

router = APIRouter(tags=["Portal - Perfil"])


@router.get("/perfil")
async def get_meu_perfil(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna perfil completo do funcionario autenticado."""
    eid = str(employee_id)

    # Tentar cache primeiro (TTL 5 min)
    cached = await portal_cache_get(eid, "perfil")
    if cached is not None:
        return cached

    result_data: dict[str, Any] = {"employee_id": eid, "nome": "Funcionario", "status": "ativo"}

    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        emp = result.scalar_one_or_none()

        if emp:
            result_data = {
                "employee_id": str(emp.id),
                "nome": emp.nome,
                "cargo": getattr(emp, "cargo", None),
                "data_admissao": str(getattr(emp, "data_admissao", "")),
                "escala": getattr(emp, "escala_padrao", None),
                "turno": getattr(emp, "turno_padrao", None),
                "posto": getattr(emp, "posto_atual_nome", None),
                "departamento": getattr(emp, "departamento", None),
                "email": getattr(emp, "email", None),
                "telefone": getattr(emp, "telefone", None),
                "status": getattr(emp, "status", "ativo"),
                "matricula": getattr(emp, "matricula", None),
            }
    except ImportError:
        pass

    await portal_cache_set(eid, "perfil", result_data, ttl=CACHE_TTLS["perfil"])
    return result_data


@router.get("/contrato")
async def get_meu_contrato(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna dados contratuais do funcionario."""
    eid = str(employee_id)

    # Tentar cache primeiro (TTL 5 min)
    cached = await portal_cache_get(eid, "contrato")
    if cached is not None:
        return cached

    result_data: dict[str, Any] = {"employee_id": eid, "tipo_contrato": "CLT"}

    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        emp = result.scalar_one_or_none()

        if emp:
            salario = float(getattr(emp, "salario_base", 0) or 0)
            cargo = getattr(emp, "cargo", "") or ""

            # Validar contra piso CCT
            piso_info: dict[str, Any] = {}
            try:
                from modules.cct.validators.salary_validator import SalaryValidator

                piso_info = SalaryValidator.validar_salario(cargo, salario)
            except ImportError:
                pass

            result_data = {
                "employee_id": str(emp.id),
                "tipo_contrato": getattr(emp, "tipo_contrato", "CLT"),
                "regime_trabalho": getattr(emp, "regime_trabalho", None),
                "carga_horaria_semanal": getattr(emp, "carga_horaria_semanal", 44),
                "jornada": getattr(emp, "escala_padrao", None) or getattr(emp, "jornada_trabalho", None),
                "data_admissao": str(getattr(emp, "data_admissao", "")),
                "posto_trabalho": getattr(emp, "posto_atual_nome", None),
                "cliente": getattr(emp, "cliente_nome", None),
                "salario_base": salario,
                "salario_conforme_cct": piso_info.get("conforme", True),
                "piso_cct_cargo": piso_info.get("piso_cct", 0),
                "cct_vigente": "SINDECOMPRESTS/SINDICOND-AM 2026",
            }
    except ImportError:
        pass

    await portal_cache_set(eid, "contrato", result_data, ttl=CACHE_TTLS["contrato"])
    return result_data
