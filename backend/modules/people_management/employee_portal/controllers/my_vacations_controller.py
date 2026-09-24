"""09/09/2026: rotas NÃO montadas (router fora do aggregator — o hook do frontend que as chamava era morto);
as FUNÇÕES ficam porque self_service_controller as importa tarde, dentro dos handlers do meu-espaço (férias,
benefícios, treinamentos). Apagar o arquivo derrubou o portal: ModuleNotFoundError em minhas_ferias_*.


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


# 08/09/2026: restauradas — self_service_controller (meu-espaço) importa estas funções tarde, dentro do handler.
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

            # [Veracidade] Tabela-verdade: employee_vacation_periods (periodo vigente).
            # Prioriza o periodo nao-expirado (start_date mais recente); fallback = ultimo registro.
            dias_saldo = dias_direito - dias_gozados
            try:
                from sqlalchemy import text as _sqltext

                period_row = (
                    (
                        await db.execute(
                            _sqltext(
                                "SELECT total_days_entitled, days_used, days_remaining, "
                                "days_sold, absences_count, start_date, expires_at "
                                "FROM employee_vacation_periods "
                                "WHERE CAST(employee_id AS TEXT) = :e "
                                "ORDER BY is_expired ASC, start_date DESC "
                                "LIMIT 1"
                            ),
                            {"e": str(employee_id)},
                        )
                    )
                    .mappings()
                    .first()
                )

                if period_row:
                    if period_row["total_days_entitled"] is not None:
                        dias_direito = int(period_row["total_days_entitled"])
                    if period_row["days_used"] is not None:
                        dias_gozados = int(period_row["days_used"])
                    if period_row["days_remaining"] is not None:
                        dias_saldo = int(period_row["days_remaining"])
                    else:
                        dias_saldo = dias_direito - dias_gozados
                    if period_row["start_date"]:
                        periodo_inicio = str(period_row["start_date"])
                    if period_row["expires_at"]:
                        periodo_fim = str(period_row["expires_at"])
                else:
                    # Fallback: dias gozados a partir de VacationRequest aprovadas
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
                    dias_saldo = dias_direito - dias_gozados
            except (ImportError, Exception) as e:
                logger.warning(f"employee_vacation_periods indisponivel: {e}")
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
    """Solicitações de férias do funcionário autenticado — de `hr_vacation_requests`.

    24/09/2026 (DGX Y5, medido no sandbox): esta função lia
    `modules.operacional.vacations.models.VacationRequest` — a CÓPIA
    `employee_vacation_requests`, que parou em 01/04 com pedidos presos em SUBMITTED. O
    builder do portal já usava `hr_vacation_requests` e explica por quê (a autoritativa,
    `test_oraculo_ferias_autoritativa`, 13/08): a pessoa via "enviado" num pedido que o DP
    já tinha aprovado. Pior: o campo `dias` da cópia guarda texto ("15 dias") e o schema
    pede `int` — a validação estourava, o `except` engolia, e o colaborador com 3 férias
    recebia HTTP 200 com lista VAZIA. Zero não é a mesma coisa que nenhum.

    O `id` devolvido é o de `hr_vacation_requests`, que é o mesmo que as rotas
    `/self-service/minhas-ferias/{vid}/recibo|aviso/pdf` esperam.
    """
    from sqlalchemy import text as _sql

    linhas = (
        (
            await db.execute(
                _sql(
                    "SELECT id::text AS vid, start_date, end_date, days_requested AS dias, "
                    "       nullif(status::text,'') AS situacao, created_at "
                    "  FROM hr_vacation_requests WHERE employee_id = CAST(:e AS uuid) "
                    " ORDER BY start_date DESC NULLS LAST LIMIT 200"
                ),
                {"e": str(employee_id)},
            )
        )
        .mappings()
        .all()
    )
    return [
        VacationRequestResponse(
            id=r["vid"],
            data_inicio=str(r["start_date"] or ""),
            data_fim=str(r["end_date"] or ""),
            dias=r["dias"],
            status=r["situacao"],
            tipo="ferias",
            created_at=str(r["created_at"] or ""),
        )
        for r in linhas
    ]
