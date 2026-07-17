"""Tasks Celery — Fiscal/Obrigações (puxador de guias do Drive)."""

from __future__ import annotations

import logging

from celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="fiscal.sync_guias_drive", queue="gov.batch")
def task_sync_guias_drive() -> dict:
    """Puxa o pacote mensal de guias (Portte/Onvio) da pasta do Drive.

    Roda 2×/dia via beat; idempotente (file_id registrado em observacoes).
    """
    from modules.fiscal_contabil.obrigacoes.guias_drive_service import sync_guias_drive

    rel = sync_guias_drive()
    logger.info(
        "fiscal.sync_guias_drive: ok=%s baixados=%s guias=%s anexos=%s ja=%s",
        rel.get("ok"), rel.get("baixados"), len(rel.get("guias", [])),
        len(rel.get("anexos", [])), rel.get("ja_processados"),
    )
    return rel
