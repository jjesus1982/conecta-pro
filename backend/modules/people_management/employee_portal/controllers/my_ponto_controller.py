"""
My Ponto Controller — Ponto eletronico e banco de horas do funcionario.

Endpoints:
- GET /portal/ponto/historico (registros de ponto do mes)
- GET /portal/banco-horas (saldo atual do banco de horas)
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portal - Ponto e Banco de Horas"])


@router.get("/ponto/historico")
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
        from sqlalchemy import extract, select

        from modules.people_management.ponto.models.clock_punch import ClockPunch

        query = (
            select(ClockPunch)
            .where(
                ClockPunch.employee_id == employee_id,
                extract("month", ClockPunch.punch_time) == target_mes,
                extract("year", ClockPunch.punch_time) == target_ano,
            )
            .order_by(ClockPunch.punch_time.desc())
        )
        result = await db.execute(query)
        for punch in result.scalars().all():
            registros.append(
                {
                    "id": str(punch.id),
                    "tipo": getattr(punch, "punch_type", "entrada"),
                    "data_hora": str(punch.punch_time),
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


@router.get("/banco-horas")
async def get_banco_horas(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna saldo atual do banco de horas do funcionario."""
    saldo_horas = 0.0
    entradas = []

    try:
        from sqlalchemy import select

        from modules.operacional.models.time_bank import TimeBank

        query = (
            select(TimeBank).where(TimeBank.employee_id == employee_id).order_by(TimeBank.created_at.desc()).limit(30)
        )
        result = await db.execute(query)
        for entry in result.scalars().all():
            horas = float(getattr(entry, "hours", 0))
            saldo_horas += horas
            entradas.append(
                {
                    "data": str(entry.created_at),
                    "tipo": getattr(entry, "entry_type", ""),
                    "horas": horas,
                    "descricao": getattr(entry, "description", None),
                }
            )
    except (ImportError, Exception) as exc:
        logger.debug("TimeBank nao disponivel para banco-horas: %s", exc)

    return {
        "employee_id": employee_id,
        "saldo_horas": round(saldo_horas, 2),
        "total_entradas": len(entradas),
        "ultimas_entradas": entradas[:10],
    }
