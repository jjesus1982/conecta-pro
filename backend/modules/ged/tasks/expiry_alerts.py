"""Celery task: alertas de expiracao de documentos.

Executa diariamente via celery beat.
Verifica documentos expirando em 30, 15, 7 e 1 dia(s).
Cria notificacoes no sistema.
"""

import logging
from datetime import date

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
    queue="gov.batch",  # era "batch": fila sem consumidor (27/09)
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
    """Certidões vencendo ou vencidas → uma linha no sino por certidão.

    Reescrita em 27/09/2026. A versão anterior varria `ged_documents` (o DMS genérico,
    aposentado em 08/09 e com ZERO linhas) e só casava vencimento que caísse EXATAMENTE em
    30/15/7/1 dias. Rodava todo dia, devolvia «0» todo dia, e era verdade sobre a tabela
    errada: enquanto isso a CND municipal da Eletrônica venceu em 01/09, o CRF em 17/09, a
    estadual em 18/09, e o CRF/FGTS da Patrimonial chegou a 7 dias do vencimento sem uma
    linha no sino. (E a task nem chegava a rodar: ia para uma fila sem consumidor — commit
    e54cc8083.) Fila certa com régua errada é o mesmo silêncio.

    Fonte agora: `ged_certidoes`, que é onde as certidões reais vivem, filtrada pelos CNPJs
    do grupo (`empresas`, como o gate); CRF de cliente fica de fora porque o CNPJ não é nosso. Janela, não dia exato: tudo que vence em até 30 dias, e o que JÁ venceu.
    `enqueue_alert` é idempotente por (categoria, entidade) — uma certidão gera uma linha,
    que se atualiza conforme o prazo encurta. Categoria `documento_vencendo` não está entre
    as cortadas do sino.
    """
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    hoje = date.today()
    results = {f"expiring_in_{d}d": 0 for d in ALERT_THRESHOLDS}
    results["newly_expired"] = 0
    total_alerts = 0
    async with async_session_factory() as db:
        try:
            rows = (
                await db.execute(
                    text(
                        "SELECT id::text, document_type, coalesce(issuing_body,''), coalesce(cnpj,''), "
                        "       expiry_date, (expiry_date - CAST(:hoje AS date)) AS dias "
                        "  FROM ged_certidoes "
                        # Só os CNPJs DO GRUPO (tabela `empresas`), como o gate faz. `alerta_ativo`
                        # não serve de régua: medido em 27/09, as certidões da PATRIMONIAL — a
                        # empresa cujo CRF o contratante cobra — estavam com alerta_ativo=false,
                        # e a 1ª versão desta consulta as deixou de fora. CRF de cliente (que o
                        # kit consulta) fica fora porque o CNPJ não é nosso, não por flag.
                        " WHERE regexp_replace(coalesce(cnpj,''),'\\D','','g') IN "
                        "       (SELECT regexp_replace(coalesce(e.cnpj,''),'\\D','','g') FROM empresas e) "
                        "   AND expiry_date IS NOT NULL "
                        "   AND expiry_date <= CAST(:hoje AS date) + 30 "
                        " ORDER BY expiry_date"
                    ),
                    {"hoje": hoje},
                )
            ).all()
            from modules.notifications.services.alert_ingest import enqueue_alert  # noqa: PLC0415

            for cid, tipo, orgao, cnpj, venc, dias in rows:
                dias = int(dias)
                if dias < 0:
                    results["newly_expired"] += 1
                    sev, quando = "critico", f"VENCIDA há {-dias} dia(s)"
                else:
                    faixa = next((d for d in sorted(ALERT_THRESHOLDS) if dias <= d), None)
                    if faixa is None:
                        continue
                    results[f"expiring_in_{faixa}d"] += 1
                    sev = "critico" if dias <= 1 else ("atencao" if dias <= 7 else "info")
                    quando = f"vence em {dias} dia(s)"
                total_alerts += 1
                logger.info("GED Expiry: %s %s (%s) %s — %s", tipo, cnpj, orgao, quando, venc)
                try:
                    await enqueue_alert(
                        db,
                        category="documento_vencendo",
                        source_entity_type="certidao",
                        source_entity_id=cid,
                        severity=sev,
                        title=f"Certidão {tipo.replace('_', ' ')} — CNPJ {cnpj}: {quando}",
                        body=f"{orgao or 'emissor não informado'} · validade {venc:%d/%m/%Y}. "
                        + (
                            "Renovar AGORA: sem ela o contratante segura a fatura e a licitação recusa."
                            if dias <= 7
                            else "Programar a renovação."
                        ),
                    )
                except Exception as _pe:  # noqa: BLE001
                    logger.warning("GED Expiry: enqueue_alert falhou (segue): %s", _pe)
            await db.commit()
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            logger.error("GED Expiry: falha na verificação: %s", e)
            raise
    results["total_alerts"] = total_alerts
    results["checked_at"] = hoje.isoformat()
    return results
