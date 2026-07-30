"""Ação redesign nova-ronda cria ronda REAL via InspectionRoundService. Cria, confere, limpa."""
import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import rd_action_nova_ronda


async def main() -> None:
    async with async_session_factory() as db:
        emp = (await db.execute(text("SELECT id, nome FROM employees WHERE coalesce(status,'')='ativo' LIMIT 1"))).first()
        assert emp, "sem employee ativo"
        # tenant real das rondas existentes — get_next_sequence é per-tenant e o code é global-unique;
        # usar o mesmo tenant faz a sequência CONTINUAR (senão colide com código de outro tenant).
        tid = (await db.execute(text("SELECT tenant_id FROM inspection_rounds ORDER BY code DESC LIMIT 1"))).scalar()
        user = SimpleNamespace(id=uuid.uuid4(), name="Teste", email="t@conectapro.com.br",
                               condominio_id=None, tenant_id=str(tid) if tid else None)
        r = await rd_action_nova_ronda(current_user=user, payload={
            "inspector_id": str(emp[0]), "scheduled_date": date.today().isoformat(),
            "observations": "ronda teste oráculo redesign"}, db=db)
        assert r.get("ok") and r.get("id"), f"nova-ronda falhou: {r}"
        chk = (await db.execute(text("SELECT inspector_name FROM inspection_rounds WHERE id::text=:i"), {"i": r["id"]})).first()
        assert chk and chk[0] == (emp[1] or "—"), "ronda não persistiu com inspetor real"
        await db.execute(text("DELETE FROM inspection_rounds WHERE id::text=:i"), {"i": r["id"]})
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:ronda:%'"))
        await db.commit()
        print(f"OK nova-ronda: id={r['id']} inspetor={chk[0]} (criada+limpa)")


if __name__ == "__main__":
    asyncio.run(main())
