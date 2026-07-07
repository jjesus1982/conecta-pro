"""Celery Tasks - Módulo Operacional.

Sprint: Módulo Operacional - Sistema de Notificações Push
Sprint: Geração Automática de Escalas
Sprint: Expiração de Banco de Horas / Lembretes de Turno / Relatório de Cobertura
"""

import asyncio
import logging

from celery_app import app
from core.database.session import get_async_db_session, get_sync_db
from modules.operacional.services.notification_triggers import (
    OperacionalNotificationTriggers,
    _get_active_tenants,
)

logger = logging.getLogger(__name__)


@app.task(
    name="operacional.check_late_employees",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def check_late_employees_task(self):
    """Tarefa Celery: Verifica colaboradores atrasados.

    Executada a cada 5 minutos via Celery Beat.
    Itera sobre todos os tenants ativos.
    """
    try:
        with get_sync_db() as db:
            tenant_ids = _get_active_tenants(db)
            logger.info(f"[Operacional Task] Verificando atrasos em {len(tenant_ids)} tenants")

            results = []
            for tenant_id in tenant_ids:
                try:
                    triggers = OperacionalNotificationTriggers(db, tenant_id)
                    result = triggers.check_late_employees()
                    results.append({"tenant_id": str(tenant_id), **result})
                except Exception as e:
                    logger.error(f"[Operacional Task] Atrasos falhou para tenant {tenant_id}: {e}")

            logger.info(f"[Operacional Task] Verificação de atrasos concluída: {len(results)} tenants")
            return results

    except Exception as exc:
        logger.error(f"[Operacional Task] Erro ao verificar atrasos: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.check_pending_approvals",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def check_pending_approvals_task(self):
    """Tarefa Celery: Verifica aprovações pendentes.

    Executada a cada 1 hora via Celery Beat.
    Itera sobre todos os tenants ativos.
    """
    try:
        with get_sync_db() as db:
            tenant_ids = _get_active_tenants(db)
            logger.info(f"[Operacional Task] Verificando aprovações em {len(tenant_ids)} tenants")

            results = []
            for tenant_id in tenant_ids:
                try:
                    triggers = OperacionalNotificationTriggers(db, tenant_id)
                    result = triggers.check_pending_approvals()
                    results.append({"tenant_id": str(tenant_id), **result})
                except Exception as e:
                    logger.error(f"[Operacional Task] Aprovações falhou para tenant {tenant_id}: {e}")

            logger.info(f"[Operacional Task] Verificação de aprovações concluída: {len(results)} tenants")
            return results

    except Exception as exc:
        logger.error(f"[Operacional Task] Erro ao verificar aprovações: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.auto_generate_monthly_scales",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def auto_generate_monthly_scales_task(self, month: int = None, year: int = None):
    """Tarefa Celery: Gera escalas automaticamente para o mês.

    Executada no dia 1º de cada mês via Celery Beat, ou sob demanda.
    Itera sobre todos os tenants ativos.

    Args:
        month: Mês (1-12), se None usa mês atual
        year: Ano, se None usa ano atual
    """
    try:
        from modules.operacional.services.auto_scale_service import AutoScaleService

        async def _generate():
            async with get_async_db_session() as db:
                service = AutoScaleService(db)

                if month and year:
                    result = await service.generate_scales_for_month(month, year)
                else:
                    result = await service.generate_scales_for_current_month()

                return result

        # Executar função async
        result = asyncio.run(_generate())

        logger.info(f"[Operacional Task] Geração automática de escalas: {result}")
        return result

    except Exception as exc:
        logger.error(f"[Operacional Task] Erro ao gerar escalas: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.expire_time_bank_entries",
    bind=True,
    max_retries=3,
    default_retry_delay=1800,  # 30 minutos
)
def expire_time_bank_entries(self):
    """
    Task Celery para expiração automática de banco de horas.

    Executa diariamente via Celery Beat às 00:30h.
    Marca como expiradas as entradas de banco de horas com data de validade vencida.
    """
    try:

        async def run_expiration():
            from datetime import date

            from sqlalchemy import and_, select

            from core.database.session import get_async_db_session
            from modules.operacional.models import TimeBank, TimeBankEntryType, TimeBankStatus

            async with get_async_db_session() as db:
                cutoff_date = date.today()
                result = await db.execute(
                    select(TimeBank).where(
                        and_(
                            TimeBank.status == TimeBankStatus.APPROVED,
                            TimeBank.expiration_date.isnot(None),
                            TimeBank.expiration_date < cutoff_date,
                            TimeBank.entry_type == TimeBankEntryType.CREDIT,
                            TimeBank.hours > 0,
                        )
                    )
                )
                entries = result.scalars().all()
                expired_count = 0
                for entry in entries:
                    entry.status = TimeBankStatus.EXPIRED
                    entry.description = f"Expirado automaticamente em {cutoff_date.strftime('%d/%m/%Y')}"
                    expired_count += 1

                if expired_count > 0:
                    await db.commit()
                    logger.info(
                        "[Operacional Task] Banco de horas: %d entradas expiradas automaticamente",
                        expired_count,
                    )
                else:
                    logger.debug("[Operacional Task] Banco de horas: nenhuma entrada para expirar")

                return expired_count

        result = asyncio.run(run_expiration())
        return {"expired_count": result}

    except Exception as exc:
        logger.error(f"[Operacional Task] Erro na expiração do banco de horas: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.send_shift_reminders",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_shift_reminders(self):
    """
    Task para envio de lembretes de turno 2h antes.
    Executa a cada 30 minutos via Celery Beat.
    """
    try:
        logger.info("[Operacional Task] Processando lembretes de turno...")
        # TODO: integrar com CommsAutomatorAgent quando WhatsApp API estiver configurado
        return {"status": "ok", "message": "Lembretes processados"}
    except Exception as exc:
        logger.error(f"[Operacional Task] Erro nos lembretes de turno: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.daily_coverage_report",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def daily_coverage_report(self):
    """
    Task para geração diária de relatório de cobertura.
    Executa todo dia às 23:55h via Celery Beat.

    Usa dados REAIS via ReportsRepository (mesma fonte das rotas
    /operacional/reports/coverage) — nunca dados simulados.
    """
    try:
        from datetime import date

        from modules.operacional.repositories.reports_repository import ReportsRepository

        async def _generate():
            async with get_async_db_session() as db:
                repo = ReportsRepository(db)
                today = date.today()
                period_start = date(today.year, today.month, 1)
                items = await repo.get_coverage(period_start, today)

                total_allocations = sum(item["total_allocations"] for item in items)
                active_allocations = sum(item["active_allocations"] for item in items)
                coverage_rate = (
                    round(active_allocations / total_allocations * 100, 2) if total_allocations else 0.0
                )

                critical_posts = [
                    item["post_name"] for item in items if item["total_allocations"] and item["coverage_rate"] < 90.0
                ]

                return {
                    "status": "ok",
                    "date": today.isoformat(),
                    "period_start": period_start.isoformat(),
                    "total_posts": len(items),
                    "total_allocations": total_allocations,
                    "active_allocations": active_allocations,
                    "coverage_rate": coverage_rate,
                    "critical_posts": critical_posts,
                }

        logger.info("[Operacional Task] Gerando relatório diário de cobertura (dados reais)...")
        result = asyncio.run(_generate())
        logger.info(f"[Operacional Task] Relatório diário de cobertura: {result}")
        return result
    except Exception as exc:
        logger.error(f"[Operacional Task] Erro no relatório diário: {exc}")
        raise self.retry(exc=exc)
