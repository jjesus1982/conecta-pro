"""Parede de EQUIPE operacional: supervisor/gerente só aplica medida / aprova férias de
colaborador alocado a posto ativo; admin age sobre todos. Testa 403 (bloqueio) sem mutar,
e o caminho permitido cria+limpa."""
import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import rd_action_medida_administrativa

SUPER = SimpleNamespace(id=uuid.uuid4(), name="Supervisor Op", email="s@conectamais.pro",
                        role="supervisor", permissions=["module:operacional", "module:dp"],
                        condominio_id=None, tenant_id=None)
ADMIN = SimpleNamespace(id=uuid.uuid4(), name="Jordan", email="j@conectamais.pro",
                        role="admin", permissions=["*"], condominio_id=None, tenant_id=None)


async def main() -> None:
    async with async_session_factory() as db:
        tid = (await db.execute(text("SELECT tenant_id FROM disciplinary_templates WHERE coalesce(is_active,true) LIMIT 1"))).scalar()
        SUPER.tenant_id = str(tid) if tid else None
        ADMIN.tenant_id = str(tid) if tid else None
        op = (await db.execute(text(
            "SELECT e.id, e.nome, coalesce(e.cpf,'00000000000') FROM employees e "
            "JOIN allocations a ON a.employee_id=e.id JOIN posts p ON p.id=a.post_id "
            "WHERE coalesce(a.is_active,true) AND coalesce(p.is_active,true) "
            "AND length(regexp_replace(coalesce(e.cpf,''),'\\D','','g'))>=11 LIMIT 1"))).first()
        nop = (await db.execute(text(
            "SELECT e.id, e.nome, coalesce(e.cpf,'00000000000') FROM employees e "
            "WHERE coalesce(e.status,'')='ativo' AND length(regexp_replace(coalesce(e.cpf,''),'\\D','','g'))>=11 "
            "AND NOT EXISTS (SELECT 1 FROM allocations a JOIN posts p ON p.id=a.post_id "
            "  WHERE a.employee_id=e.id AND coalesce(a.is_active,true) AND coalesce(p.is_active,true)) LIMIT 1"))).first()
        assert op and nop, f"faltou emp operacional({bool(op)}) ou não-operacional({bool(nop)})"

        def _pl(emp):
            return {"employee_id": str(emp[0]), "employee_name": emp[1], "employee_cpf": str(emp[2]),
                    "action_type": "advertencia_escrita", "reason_category": "atraso",
                    "reason_description": "Teste escopo equipe operacional — apagar",
                    "incident_date": date.today().isoformat()}

        # 1) supervisor + NÃO-operacional → 403 (parede), sem mutar
        try:
            await rd_action_medida_administrativa(current_user=SUPER, payload=_pl(nop), db=db)
            raise AssertionError("deveria ter bloqueado não-operacional (403)")
        except HTTPException as e:
            assert e.status_code == 403, f"esperava 403, veio {e.status_code}"
        await db.rollback()
        print(f"OK bloqueio: supervisor NÃO aplica medida a não-operacional ({nop[1]}) → 403")

        # 2) supervisor + operacional → passa a parede (cria) → limpa
        r = await rd_action_medida_administrativa(current_user=SUPER, payload=_pl(op), db=db)
        assert r.get("ok") and r.get("id"), f"deveria criar p/ operacional: {r}"
        await db.execute(text("DELETE FROM disciplinary_actions WHERE id::text=:i"), {"i": r["id"]})
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:medida%'"))
        await db.commit()
        print(f"OK permitido: supervisor aplica medida a operacional ({op[1]}) → criada+limpa")

        # 3) admin + não-operacional → passa (ignora parede) → limpa
        r2 = await rd_action_medida_administrativa(current_user=ADMIN, payload=_pl(nop), db=db)
        assert r2.get("ok") and r2.get("id"), f"admin deveria criar p/ qualquer um: {r2}"
        await db.execute(text("DELETE FROM disciplinary_actions WHERE id::text=:i"), {"i": r2["id"]})
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:medida%'"))
        await db.commit()
        print(f"OK admin: aplica medida a NÃO-operacional ({nop[1]}) → passa a parede (criada+limpa)")


if __name__ == "__main__":
    asyncio.run(main())
