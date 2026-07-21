"""Task 5 (Fase 0) — enqueue_alert idempotente (upsert por entidade)."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.notifications.services.alert_ingest import enqueue_alert, normalize_severity


async def _check():
    async with async_session_factory() as db:
        eid = "00000000-0000-0000-0000-0000000000aa"
        a = dict(category="teste_dedup", source_entity_type="customer",
                 source_entity_id=eid, severity="vermelho", title="X")
        id1 = await enqueue_alert(db, **a); await db.commit()
        id2 = await enqueue_alert(db, **{**a, "title": "Y"}); await db.commit()
        n = (await db.execute(text(
            "SELECT count(*) FROM notification_queue WHERE category='teste_dedup'"))).scalar()
        subj = (await db.execute(text(
            "SELECT subject FROM notification_queue WHERE category='teste_dedup'"))).scalar()
        await db.execute(text("DELETE FROM notification_queue WHERE category='teste_dedup'"))
        await db.commit()
    return id1 == id2 and n == 1 and subj == "Y"


def run():
    assert normalize_severity("x", "vermelho") == "critico"
    assert normalize_severity("x", "yellow") == "atencao"
    ok = asyncio.run(_check())
    print("PASS" if ok else "FALHA")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
