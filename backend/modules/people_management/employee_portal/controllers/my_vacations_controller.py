"""
My Vacations Controller — Consulta de ferias do funcionario.

Endpoints:
- GET /portal/my-vacations/balance
- GET /portal/my-vacations/requests
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Ferias"])


class VacationBalanceResponse(BaseModel):
    """Saldo de ferias do funcionario."""

    dias_direito: int = 30
    dias_gozados: int = 0
    dias_saldo: int = 30
    total_bruto_ferias: float = 0.0
    periodo_aquisitivo_inicio: str | None = None
    periodo_aquisitivo_fim: str | None = None

    model_config = ConfigDict(from_attributes=True)


class VacationRequestResponse(BaseModel):
    """Solicitacao de ferias do funcionario."""

    id: str | None = None
    data_inicio: str | None = None
    data_fim: str | None = None
    dias: int | None = None
    status: str | None = None
    tipo: str | None = None
    created_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


@router.get(
    "/my-vacations/balance",
    response_model=VacationBalanceResponse,
    summary="Saldo de ferias",
    description="Retorna o saldo de ferias do funcionario logado.",
)
async def get_vacation_balance(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna saldo de ferias do funcionario autenticado."""
    try:
        from sqlalchemy import select

        from modules.operacional.models.employee import Employee

        result = await db.execute(select(Employee).where(Employee.id == employee_id))
        employee = result.scalar_one_or_none()

        if employee:
            data_admissao = getattr(employee, "data_admissao", None)
            salario_base = getattr(employee, "salario_base", None)

            # Calcular periodo aquisitivo
            dias_direito = 30
            dias_gozados = 0
            total_bruto = 0.0
            periodo_inicio = None
            periodo_fim = None

            if data_admissao:
                today = date.today()
                # Periodo aquisitivo atual
                anos_trabalhados = (today - data_admissao).days // 365
                if anos_trabalhados >= 1:
                    periodo_inicio = str(data_admissao.replace(year=data_admissao.year + anos_trabalhados))
                    periodo_fim = str(data_admissao.replace(year=data_admissao.year + anos_trabalhados + 1))
                else:
                    periodo_inicio = str(data_admissao)
                    periodo_fim = str(data_admissao.replace(year=data_admissao.year + 1))

            # Tentar buscar dias gozados de VacationRequest
            try:
                from modules.operacional.vacations.models import VacationRequest

                vac_result = await db.execute(
                    select(VacationRequest).where(
                        VacationRequest.employee_id == str(employee_id),
                        VacationRequest.status == "approved",
                    )
                )
                vacations = vac_result.scalars().all()
                for v in vacations:
                    dias = getattr(v, "dias", None) or getattr(v, "days", 0)
                    if dias:
                        dias_gozados += dias
            except (ImportError, Exception) as e:
                logger.warning(f"VacationRequest nao disponivel: {e}")

            dias_saldo = dias_direito - dias_gozados

            # Calcular valor bruto das ferias via clt_calculator
            if salario_base:
                try:
                    from modules.people_management.common.utils.clt_calculator import (
                        calcular_ferias,
                    )

                    resultado = calcular_ferias(
                        salario_base=Decimal(str(salario_base)),
                        dias_gozo=dias_saldo,
                    )
                    total_bruto = float(resultado.get("total_bruto", 0))
                except (ImportError, Exception) as e:
                    logger.warning(f"Erro ao calcular ferias via clt_calculator: {e}")
                    # Fallback: salario + 1/3
                    total_bruto = float(salario_base) + float(salario_base) / 3

            return VacationBalanceResponse(
                dias_direito=dias_direito,
                dias_gozados=dias_gozados,
                dias_saldo=dias_saldo,
                total_bruto_ferias=total_bruto,
                periodo_aquisitivo_inicio=periodo_inicio,
                periodo_aquisitivo_fim=periodo_fim,
            )

    except (ImportError, Exception) as e:
        logger.warning(f"Erro ao buscar saldo de ferias do funcionario {employee_id}: {e}")

    return VacationBalanceResponse()


@router.get(
    "/my-vacations/requests",
    response_model=list[VacationRequestResponse],
    summary="Minhas solicitacoes de ferias",
    description="Retorna lista de solicitacoes de ferias do funcionario.",
)
async def get_vacation_requests(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna solicitacoes de ferias do funcionario autenticado."""
    try:
        from sqlalchemy import select

        from modules.operacional.vacations.models import VacationRequest

        result = await db.execute(
            select(VacationRequest).where(
                VacationRequest.employee_id == str(employee_id),
            )
        )
        vacations = result.scalars().all()

        return [
            VacationRequestResponse(
                id=str(getattr(v, "id", None)),
                data_inicio=str(getattr(v, "start_date", None) or getattr(v, "data_inicio", "")),
                data_fim=str(getattr(v, "end_date", None) or getattr(v, "data_fim", "")),
                dias=getattr(v, "dias", None) or getattr(v, "days", None),
                status=getattr(v, "status", None),
                tipo=getattr(v, "tipo", None) or getattr(v, "type", "ferias"),
                created_at=str(getattr(v, "created_at", "")),
            )
            for v in vacations
        ]

    except (ImportError, Exception) as e:
        logger.warning(f"Erro ao buscar solicitacoes de ferias do funcionario {employee_id}: {e}")

    return []
