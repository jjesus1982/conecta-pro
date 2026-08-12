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


@app.task(name="fiscal.calendario_obrigacoes", queue="gov.batch")
def task_calendario_obrigacoes() -> dict:
    """Garante que cada competência FECHADA tenha suas obrigações recorrentes cadastradas.

    Existe porque o calendário dependia do PDF da guia chegar no Drive: as guias pararam em
    dez/2025 e o calendário parou junto — competências 04, 05 e 07/2026 simplesmente não
    existiam, e em 11/08 havia UMA obrigação vencendo nos 30 dias seguintes no sistema
    inteiro, com a competência de julho vencendo em nove dias.

    Obrigação existe por lei, não porque o documento chegou. Roda mensal; é idempotente,
    então rodar de novo não duplica.
    """
    import asyncio
    from datetime import date

    from core.database import async_session_factory
    from modules.fiscal_contabil.obrigacoes.calendario_service import garantir_ate_hoje

    async def _run():
        async with async_session_factory() as db:
            return await garantir_ate_hoje(db, date.today(), meses_atras=3, aplicar=True)

    try:
        r = asyncio.run(_run())
        logger.info("[calendario_obrigacoes] %s criada(s)", r.get("total"))
        return r
    except Exception as exc:  # noqa: BLE001 — falha aqui não pode derrubar o worker
        logger.error("[calendario_obrigacoes] falhou: %s", exc)
        return {"erro": str(exc)[:200]}
