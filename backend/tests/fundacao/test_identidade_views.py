"""Task 1 (Fase -1) — views de resolucao de identidade.

Roda via python direto (pytest nao esta no container): cada funcao retorna bool.
Prova: v_employee == employees; JOIN uuid x varchar via view nao estoura; e o
escritorio e classificado corretamente por v_condominio_kind.
"""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory


async def _checks():
    async with async_session_factory() as db:
        n_view = (await db.execute(text("SELECT count(*) FROM v_employee"))).scalar()
        n_emp = (await db.execute(text("SELECT count(*) FROM employees"))).scalar()
        # JOIN ponto (employee_id varchar) x v_employee (uuid) — nao pode dar erro de tipo
        n_join = (await db.execute(text(
            "SELECT count(*) FROM gp_monthly_closings c JOIN v_employee e "
            "ON e.id_text = c.employee_id"))).scalar()
        kind = (await db.execute(text(
            "SELECT kind FROM v_condominio_kind WHERE condominio_id="
            "'a1b2c3d4-e5f6-7890-abcd-ef1234567890'"))).scalar()
        n_ec = (await db.execute(text("SELECT count(*) FROM entity_client"))).scalar()
    return {
        "v_employee_igual_employees": n_view == n_emp,
        "join_uuid_x_varchar_ok": n_join >= 0,
        "escritorio_classificado": kind == "escritorio",
        "entity_client_existe": n_ec >= 0,
    }


def run():
    res = asyncio.run(_checks())
    for k, v in res.items():
        print(f"{'OK ' if v else 'FALHA'} {k}")
    return all(res.values())


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
