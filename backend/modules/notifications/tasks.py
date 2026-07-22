"""Fase 0 (Task 8): reconciliação (espinha de completude) + retenção do sino.

Pré-mortem B1/B2: o event bus perde evento (at-most-once) e PIX/jurídico nem emitem.
A espinha confiável é POLLING idempotente: re-deriva as condições de alerta direto
das tabelas-fonte e materializa via enqueue_alert (upsert). Rodar de novo NÃO
duplica e fecha buracos de evento perdido. Só leitura nas fontes; nunca dispara ação.
"""
import logging

from celery_app import app

logger = logging.getLogger(__name__)


def _run_async(coro):
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    url = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        eng = create_async_engine(url, echo=False)
        session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with session() as s:
            return await coro(s)

    return asyncio.run(_inner())


@app.task(name="notifications.reconciliar_alertas", bind=True, max_retries=1)
def reconciliar_alertas_task(self):
    """Re-deriva condições de alerta das fontes e materializa no sino (idempotente)."""

    async def run(db):
        from sqlalchemy import text

        from modules.notifications.services.alert_ingest import enqueue_alert

        materializados = 0
        # Aging de recebíveis (portfolio) — re-derivado direto da fonte, imune a evento.
        row = (
            await db.execute(
                text(
                    "SELECT count(*), coalesce(sum(net_value),0) FROM receivable_accounts "
                    "WHERE due_date < current_date "
                    "AND coalesce(status::text,'') NOT ILIKE '%pag%' "
                    "AND coalesce(status::text,'') NOT ILIKE '%cancel%'"
                )
            )
        ).fetchone()
        n_venc, total = int(row[0] or 0), float(row[1] or 0)
        if n_venc > 0:
            await enqueue_alert(
                db,
                category="financeiro_aging",
                source_entity_type="portfolio",
                source_entity_id=None,
                severity="critico" if total >= 50000 else "atencao",
                title=f"{n_venc} recebível(is) vencido(s)",
                body=f"Total vencido: R$ {total:,.2f}. Re-derivado da fonte (reconciliação).",
            )
            materializados += 1

        # Fase 3 — PROATIVIDADE CRUZADA (por entidade): cliente cujo colaborador ALOCADO
        # está AFASTADO (SST). Cruza operacional (alocação) × SST × cliente — ancorado no
        # cliente (source_entity_id). É o "cutucão" cross-domínio no sino, idempotente.
        cruz = (
            await db.execute(
                text(
                    "SELECT cd.client_id, cl.name, count(DISTINCT af.employee_id) n "
                    "FROM sst_afastamentos af "
                    "JOIN employee_alocacoes a ON a.employee_id::text=af.employee_id::text AND coalesce(a.ativo,true) "
                    "JOIN condominios cd ON cd.id=a.condominio_id "
                    "JOIN clients cl ON cl.id=cd.client_id "
                    "WHERE lower(coalesce(af.status,'')) IN ('ativo','em_andamento') OR af.data_retorno IS NULL "
                    "GROUP BY cd.client_id, cl.name"
                )
            )
        ).fetchall()
        for r in cruz:
            await enqueue_alert(
                db,
                category="cliente_cobertura",
                source_entity_type="client",
                source_entity_id=str(r.client_id),
                severity="atencao",
                title=f"{r.name}: {int(r.n)} colaborador(es) afastado(s) — verificar cobertura",
                body="Cruzamento operacional×SST: há afastamento ativo em colaborador alocado neste cliente.",
            )
            materializados += 1

        await db.commit()
        return {
            "materializados": materializados,
            "recebiveis_vencidos": n_venc,
            "clientes_cobertura": len(cruz),
        }

    try:
        res = _run_async(run)
        logger.info("[Notif] reconciliar_alertas: %s", res)
        return res
    except Exception as exc:
        logger.error("[Notif] reconciliar_alertas erro: %s", exc)
        raise self.retry(exc=exc, countdown=120)


@app.task(name="notifications.purgar_notificacoes", bind=True, max_retries=1)
def purgar_notificacoes_task(self):
    """Retenção leve: expira notificações NÃO-alerta entregues há >30 dias.
    Alertas (risco_/documento_/financeiro_/sst) são retidos (histórico p/ tendência)."""

    async def run(db):
        from sqlalchemy import text

        r = await db.execute(
            text(
                "UPDATE notification_queue SET status='expired', updated_at=now() "
                "WHERE status='delivered' AND created_at < now() - interval '30 days' "
                "AND coalesce(category,'') NOT LIKE 'risco_%' "
                "AND coalesce(category,'') NOT LIKE 'documento_%' "
                "AND coalesce(category,'') NOT LIKE 'financeiro_%' "
                "AND coalesce(category,'') NOT LIKE 'sst%'"
            )
        )
        await db.commit()
        return {"expiradas": r.rowcount}

    try:
        res = _run_async(run)
        logger.info("[Notif] purgar_notificacoes: %s", res)
        return res
    except Exception as exc:
        logger.error("[Notif] purgar_notificacoes erro: %s", exc)
        return {"erro": str(exc)}
