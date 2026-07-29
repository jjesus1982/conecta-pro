"""Ação redesign: /action/medida-administrativa cria linha REAL em disciplinary_actions.
Chama a função do router diretamente (sem HTTP) com um current_user fake e confere no banco."""
import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import rd_action_medida_administrativa


async def main() -> None:
    async with async_session_factory() as db:
        emp = (await db.execute(text(
            "SELECT id, nome FROM employees WHERE coalesce(status,'')='ativo' "
            "AND length(regexp_replace(coalesce(cpf,''), '\\D', '', 'g')) >= 11 LIMIT 1"))).first()
        assert emp, "sem employee ativo com CPF p/ testar"
        user = SimpleNamespace(id=uuid.uuid4(), condominio_id=None, tenant_id=None)
        payload = {"action_type": "advertencia_escrita", "employee_id": str(emp[0]),
                   "reason_category": "atraso",
                   "reason_description": "Atraso reiterado — teste oráculo redesign",
                   "incident_date": date.today().isoformat()}
        res = await rd_action_medida_administrativa(current_user=user, payload=payload, db=db)
        assert res.get("ok") and res.get("id"), f"ação não retornou ok/id: {res}"
        row = (await db.execute(
            text("SELECT employee_name, status::text FROM disciplinary_actions WHERE id::text=:i"),
            {"i": str(res["id"])})).first()
        assert row and row[0] == (emp[1] or "—"), f"linha não persistiu com nome real: {row}"
        print(f"OK ação: criou disciplinary_action id={res['id']} nome={row[0]} status={row[1]}")


if __name__ == "__main__":
    asyncio.run(main())
