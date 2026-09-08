"""
Controller de Monitoramento - Conecta PRO v3.0.0
==================================================

Endpoints para health checks, métricas e status do sistema.
"""

import logging
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# Configurar logging
logger = logging.getLogger(__name__)

# Router para monitoramento
router = APIRouter(prefix="/monitoring", tags=["System Monitoring"])

# Timestamp de quando o sistema iniciou
STARTUP_TIME = datetime.utcnow()


class HealthStatus(BaseModel):
    """Status de saúde do sistema."""

    status: str
    timestamp: datetime
    uptime: str
    version: str
    database: str
    memory_usage: float
    cpu_usage: float


class ReadinessStatus(BaseModel):
    """Status de prontidão do sistema."""

    ready: bool
    timestamp: datetime
    services: dict[str, str]
    checks_passed: int
    checks_total: int


class SystemMetrics(BaseModel):
    """Métricas do sistema."""

    timestamp: datetime
    uptime_seconds: int
    memory_usage_mb: float
    memory_percent: float
    cpu_percent: float
    disk_usage_percent: float
    active_connections: int


async def check_database_health(session: AsyncSession) -> bool:
    """Verifica se o database está respondendo."""
    try:
        result = await session.execute(text("SELECT 1"))
        return result.scalar() == 1
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Database health check failed: {e}")
        return False


async def check_campo_tables(session: AsyncSession) -> dict[str, bool]:
    """Verifica se as tabelas principais do CAMPO existem."""
    tables_to_check = [
        "public.access_logs",
        "public.equipment_status",
        "public.campo_tecnicos",
    ]

    results = {}
    for table in tables_to_check:
        try:
            schema, table_name = table.split(".")
            query = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = :schema
                    AND table_name = :table_name
                )
            """)
            result = await session.execute(query, {"schema": schema, "table_name": table_name})
            results[table] = result.scalar()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"Table check failed for {table}: {e}")
            results[table] = False

    return results


def get_uptime() -> str:
    """Calcula tempo de atividade do sistema."""
    uptime = datetime.utcnow() - STARTUP_TIME
    total_seconds = int(uptime.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


