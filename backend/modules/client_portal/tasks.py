"""Tasks agendadas do Portal do Cliente."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="portal.materializar_kits", bind=True, max_retries=1)
def materializar_kits_task(self, competencia: str | None = None):
    """Indexa os arquivos locais (ponto/solides/onvio) nos kits do portal (automação diária).

    Catch-all p/ docs que chegam fora da montagem (ex.: ponto assinado do host).
    Idempotente — só indexa o que ainda não está indexado.
    """
    from datetime import date

    from modules.client_portal.services.portal_kit_materializar_service import materializar

    comp = competencia or date.today().strftime("%Y-%m")
    try:
        stats = materializar(comp)
        logger.info("Portal materializar_kits (%s): %s", comp, stats)
        return stats
    except Exception as exc:
        logger.error("Portal materializar_kits falhou: %s", exc)
        raise self.retry(exc=exc, countdown=300)


@shared_task(name="portal.resumo_mensal_clientes", bind=True, max_retries=1)
def resumo_mensal_clientes_task(self, competencia: str | None = None):
    """Resumo mensal p/ todos os clientes do portal (dia 1º via beat, fila gov.batch).

    Caixa do portal sempre; e-mail sai quando PORTAL_NOTIFY_ENABLED=true (o worker
    celery-batch tem SMTP_* no env). Dado 100% real — seções vazias saem honestas.
    """
    import asyncio

    from core.database.session import get_async_db_session
    from modules.client_portal.services.portal_resumo_service import enviar_resumo_todos

    async def _run():
        async with get_async_db_session() as db:
            return await enviar_resumo_todos(db, competencia)

    try:
        resultado = asyncio.run(_run())
        logger.info("Portal resumo_mensal_clientes: %s", resultado)
        return resultado
    except Exception as exc:
        logger.error("Portal resumo_mensal_clientes falhou: %s", exc)
        raise self.retry(exc=exc, countdown=600)
