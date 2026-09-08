"""
My Ponto Controller — Ponto eletronico e banco de horas do funcionario.

Endpoints:
- GET /portal/ponto/historico (registros de ponto do mes)
- GET /portal/banco-horas (saldo atual do banco de horas)
"""

import logging

from fastapi import APIRouter
from datetime import datetime
from typing import Any
from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Ponto e Banco de Horas"])

# 08/09/2026: rota /portal/ponto/historico apagada (redundante — meu-espaco usa /self-service/meu-ponto, que chama esta função por import)
async def get_ponto_historico(
    employee_id: CurrentEmployeeId,
    mes: int = Query(default=None, ge=1, le=12, description="Mes (1-12)"),
    ano: int = Query(default=None, ge=2020, le=2030, description="Ano"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna registros de ponto do funcionario no mes."""
    target_mes = mes or datetime.utcnow().month
    target_ano = ano or datetime.utcnow().year

    registros = []
    try:
        from sqlalchemy import func, extract, select

        # [Ponto loop] modelo real e ClockPunchModel (tabela gp_clock_punches); coluna e punch_timestamp
        from modules.people_management.ponto.models.clock_punch import ClockPunchModel as ClockPunch

        query = (
            select(ClockPunch)
            .where(
                ClockPunch.employee_id == employee_id,
                # punch_timestamp já é hora LOCAL Manaus (naive) → filtra direto
                extract("month", ClockPunch.punch_timestamp) == target_mes,
                extract("year", ClockPunch.punch_timestamp) == target_ano,
            )
            .order_by(ClockPunch.punch_timestamp.desc())
        )
        result = await db.execute(query)
        for punch in result.scalars().all():
            registros.append(
                {
                    "id": str(punch.id),
                    "tipo": getattr(punch, "punch_type", "entrada"),
                    "data_hora": str(punch.punch_timestamp),
                    "localizacao": getattr(punch, "location", None),
                    "observacao": getattr(punch, "observation", None),
                }
            )
    except (ImportError, Exception) as exc:
        logger.debug("Modelo ClockPunch nao disponivel: %s", exc)

    # Fallback: buscar do operacional (time_bank)
    if not registros:
        try:
            from sqlalchemy import extract, select

            from modules.operacional.models.time_bank import TimeBank

            query = (
                select(TimeBank)
                .where(
                    TimeBank.employee_id == employee_id,
                    extract("month", TimeBank.created_at) == target_mes,
                    extract("year", TimeBank.created_at) == target_ano,
                )
                .order_by(TimeBank.created_at.desc())
            )
            result = await db.execute(query)
            for entry in result.scalars().all():
                registros.append(
                    {
                        "id": str(entry.id),
                        "tipo": getattr(entry, "entry_type", "registro"),
                        "data_hora": str(entry.created_at),
                        "horas": float(getattr(entry, "hours", 0)),
                        "observacao": getattr(entry, "description", None),
                    }
                )
        except (ImportError, Exception) as exc:
            logger.debug("TimeBank nao disponivel: %s", exc)

    return {
        "employee_id": employee_id,
        "mes": target_mes,
        "ano": target_ano,
        "total_registros": len(registros),
        "registros": registros,
    }
