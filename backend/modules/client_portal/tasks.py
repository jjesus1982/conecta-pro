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
