"""Ciclo de escala via redesign: submeter→aprovar→publicar reusa ScaleRepository via gate.
Cria uma escala DESCARTÁVEL (year 2099), roda o ciclo, confere status e DELETA (não toca escala real)."""
import asyncio
import uuid
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import (
    rd_action_escala_aprovar, rd_action_escala_publicar, rd_action_escala_submeter,
)
from modules.operacional.repositories.scale_repository import ScaleRepository
from modules.operacional.schemas.scale import ScaleCreate


async def main() -> None:
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM scales WHERE year=2099 AND coalesce(notes,'') LIKE '%teste oraculo escala%'"))
        await db.commit()
        post_id = (await db.execute(text("SELECT id FROM posts WHERE coalesce(is_active,true) LIMIT 1"))).scalar()
        assert post_id, "sem posto"
        u = SimpleNamespace(id=uuid.uuid4(), name="Teste", email="t@conectapro.com.br")
        scale = await ScaleRepository(db).create(
            ScaleCreate(post_id=str(post_id), scale_type="12x36", month=12, year=2099, notes="teste oraculo escala"),
            created_by=str(u.id))
        sid = str(scale.id)
        try:
            sub = await rd_action_escala_submeter(current_user=u, payload={"scale_id": sid}, db=db)
            assert sub["ok"] and sub["status"] == "pending_approval", f"submeter: {sub}"
            apr = await rd_action_escala_aprovar(current_user=u, payload={"scale_id": sid, "notes": "ok"}, db=db)
            assert apr["ok"] and apr["status"] == "approved", f"aprovar: {apr}"
            pub = await rd_action_escala_publicar(current_user=u, payload={"scale_id": sid}, db=db)
            assert pub["ok"] and pub["status"] == "published", f"publicar: {pub}"
            st = (await db.execute(text("SELECT status::text FROM scales WHERE id::text=:i"), {"i": sid})).scalar()
            assert st == "published", f"banco: {st}"
            print(f"OK ciclo escala: {sid} draft→pending→approved→published (exibido==banco)")
        finally:
            await db.execute(text("DELETE FROM shifts WHERE scale_id::text=:i"), {"i": sid})
            await db.execute(text("DELETE FROM scales WHERE id::text=:i"), {"i": sid})
            await db.commit()
            print("limpo (escala descartável removida)")


if __name__ == "__main__":
    asyncio.run(main())
