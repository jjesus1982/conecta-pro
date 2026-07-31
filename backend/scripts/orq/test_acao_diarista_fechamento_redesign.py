"""Gerar fechamento de diaristas via redesign (op_write, SEM dinheiro): reusa
generate_payroll_payments. Competência 2099-12 (sem diaristas) → 0 gerados, sem mutação."""
import asyncio
import uuid
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import rd_action_diarista_fechamento


async def main() -> None:
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:diar-fech%'"))
        await db.commit()
        cond = (await db.execute(text("SELECT id FROM condominios WHERE coalesce(ativo,true) LIMIT 1"))).scalar()
        assert cond, "sem condomínio"
        u = SimpleNamespace(id=uuid.uuid4(), name="Teste", email="t@conectapro.com.br")
        res = await rd_action_diarista_fechamento(current_user=u, payload={
            "condominio_id": str(cond), "competencia": "2099-12"}, db=db)
        assert res["ok"] and res["total_gerados"] == 0, f"esperava 0 gerados (sem diaristas): {res}"
        # garante que nada foi criado nessa competência de teste
        n = (await db.execute(text("SELECT count(*) FROM diarist_payments WHERE data_referencia >= '2099-12-01'"))).scalar()
        assert (n or 0) == 0, f"criou registros inesperados: {n}"
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref LIKE 'idem:diar-fech%'"))
        await db.commit()
        print(f"OK diarista-fechamento: reusa generate_payroll_payments, {res['total_gerados']} gerados (seguro, sem dinheiro)")


if __name__ == "__main__":
    asyncio.run(main())
