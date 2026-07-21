"""Celery task: alertas de expiracao de documentos.

Executa diariamente via celery beat.
Verifica documentos expirando em 30, 15, 7 e 1 dia(s).
Cria notificacoes no sistema.
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:

    def shared_task(*args, **kwargs):
        def decorator(func):
            func.delay = lambda *a, **kw: func(*a, **kw)
            func.apply_async = lambda *a, **kw: func(*a, **kw)
            return func

        if args and callable(args[0]):
            return decorator(args[0])
        return decorator


ALERT_THRESHOLDS = [30, 15, 7, 1]


@shared_task(
    name="ged.check_document_expiry",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="batch",
)
def check_document_expiry(self) -> dict:
    """Verifica documentos expirando e cria alertas.

    Returns:
        Resumo com contagem por threshold.
    """
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_check_expiry_async())
    finally:
        loop.close()


async def _check_expiry_async() -> dict:
    """Logica async para verificacao de expiracao."""
    from sqlalchemy import and_, func, select

    from core.database import async_session_factory
    from modules.ged.models.document import Document, DocumentStatus

    results = {}
    total_alerts = 0

    async with async_session_factory() as db:
        try:
            today = date.today()

            for days in ALERT_THRESHOLDS:
                target_date = today + timedelta(days=days)

                # Buscar documentos que expiram exatamente nesse dia
                query = (
                    select(func.count())
                    .select_from(Document)
                    .where(
                        and_(
                            Document.valid_until == target_date,
                            Document.is_perpetual.is_(False),
                            Document.status.notin_(
                                [
                                    DocumentStatus.EXCLUIDO,
                                    DocumentStatus.EXPIRADO,
                                ]
                            ),
                        )
                    )
                )
                result = await db.execute(query)
                count = result.scalar() or 0
                results[f"expiring_in_{days}d"] = count

                if count > 0:
                    total_alerts += count
                    logger.info(
                        "GED Expiry: %d documento(s) expirando em %d dia(s) (%s)",
                        count,
                        days,
                        target_date.isoformat(),
                    )

                    # Buscar detalhes para log
                    detail_query = (
                        select(Document.id, Document.title, Document.valid_until)
                        .where(
                            and_(
                                Document.valid_until == target_date,
                                Document.is_perpetual.is_(False),
                                Document.status.notin_(
                                    [
                                        DocumentStatus.EXCLUIDO,
                                        DocumentStatus.EXPIRADO,
                                    ]
                                ),
                            )
                        )
                        .limit(10)
                    )
                    details = await db.execute(detail_query)
                    for doc_id, title, valid_until in details.fetchall():
                        logger.info(
                            "  -> [%s] %s expira em %s",
                            str(doc_id)[:8],
                            title,
                            valid_until,
                        )
                        # Fase 0 (Task 7): materializa no sino (antes só logava). Idempotente.
                        try:
                            from modules.notifications.services.alert_ingest import (
                                enqueue_alert,
                            )

                            sev = "critico" if days <= 1 else ("atencao" if days <= 7 else "info")
                            await enqueue_alert(
                                db,
                                category="documento_vencendo",
                                source_entity_type="document",
                                source_entity_id=doc_id,
                                severity=sev,
                                title=f"Documento vence em {days}d: {title}",
                                body=f"'{title}' expira em {valid_until}.",
                            )
                        except Exception as _pe:  # noqa: BLE001
                            logger.warning("GED Expiry: enqueue_alert falhou (segue): %s", _pe)

            # Persiste os alertas de vencimento materializados acima (Task 7).
            await db.commit()

            # Marcar documentos ja expirados
            expired_query = select(Document).where(
                and_(
                    Document.valid_until < today,
                    Document.is_perpetual.is_(False),
                    Document.status.notin_(
                        [
                            DocumentStatus.EXCLUIDO,
                            DocumentStatus.EXPIRADO,
                        ]
                    ),
                )
            )
            expired_result = await db.execute(expired_query)
            expired_docs = expired_result.scalars().all()
            expired_count = 0
            for doc in expired_docs:
                if doc.check_expiry():
                    expired_count += 1

            if expired_count > 0:
                await db.commit()
                logger.info("GED Expiry: %d documento(s) marcados como expirados", expired_count)

            results["newly_expired"] = expired_count
            results["total_alerts"] = total_alerts
            results["checked_at"] = today.isoformat()

        except Exception as e:
            logger.error("GED Expiry: erro na verificacao: %s", e)
            results["error"] = str(e)

    return results
