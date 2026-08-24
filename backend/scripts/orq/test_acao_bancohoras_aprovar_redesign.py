"""Aprovação de banco de horas via redesign: aprovar reusa TimeBankRepository.approve via gate.
Cria um lançamento DESCARTÁVEL, aprova, confere status e DELETA."""
import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import rd_action_banco_horas_aprovar
from modules.operacional.repositories.time_bank_repository import TimeBankRepository
from modules.operacional.schemas.time_bank import TimeBankCreate


async def main() -> None:
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM time_bank WHERE coalesce(reason,'') LIKE ANY (ARRAY['%ZZteste oraculo bh aprovar%', '%teste oraculo bh aprovar%'])  -- ZZ novo + marca antiga varrida junto"))
        await db.commit()
        emp = (await db.execute(text("SELECT id FROM employees WHERE coalesce(status,'')='ativo' LIMIT 1"))).scalar()
        assert emp, "sem employee"
        u = SimpleNamespace(id=uuid.uuid4(), name="Teste", email="t@conectapro.com.br")
        entry = await TimeBankRepository(db).create(TimeBankCreate(
            employee_id=str(emp), entry_type="credit", hours=8, reference_date=date.today().isoformat(),
            reason="ZZteste oraculo bh aprovar"))
        eid = str(entry.id)
        try:
            st0 = (await db.execute(text("SELECT status FROM time_bank WHERE id::text=:i"), {"i": eid})).scalar()
            assert st0 == "pending", f"status inicial {st0} != pending"
            apr = await rd_action_banco_horas_aprovar(current_user=u, payload={"entry_id": eid, "notes": "ok"}, db=db)
            assert apr["ok"] and apr["status"] == "approved", f"aprovar: {apr}"
            st = (await db.execute(text("SELECT status FROM time_bank WHERE id::text=:i"), {"i": eid})).scalar()
            assert st == "approved", f"banco: {st}"
            print(f"OK aprovar banco-horas: {eid} pending→approved (exibido==banco)")
        finally:
            await db.execute(text("DELETE FROM time_bank WHERE id::text=:i"), {"i": eid})
            await db.commit()
            print("limpo (lançamento descartável removido)")


if __name__ == "__main__":
    asyncio.run(main())
