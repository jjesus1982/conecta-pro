"""Celery Tasks - Módulo Analytics.

Recálculo automático dos KPIs (executive_kpis + financial_kpis) a partir do
dado real. Executado periodicamente via Celery Beat.
"""

import logging

from celery_app import app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Helper para rodar corrotinas async dentro de tasks Celery (sync)."""
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    database_url = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        engine = create_async_engine(database_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with async_session() as session:
                return await coro(session)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@app.task(name="analytics.recalcular_kpis", bind=True, max_retries=3, default_retry_delay=120)
def recalcular_kpis_task(self):
    """Recalcula os KPIs a partir das fontes reais.

    Executado via Celery Beat (horário). Idempotente: cada execução recalcula
    o current_value do dado real e reposiciona previous_value.
    """

    def run(session):
        from modules.analytics.services.kpi_recalc_service import recalcular_kpis

        return recalcular_kpis(session)

    try:
        result = _run_async(run)
        logger.info(
            "[Analytics Task] recalcular_kpis: executive=%s financial=%s",
            result.get("executive_updated"),
            result.get("financial_updated"),
        )
        return result
    except Exception as exc:
        logger.error("[Analytics Task] recalcular_kpis error: %s", exc)
        raise self.retry(exc=exc)
