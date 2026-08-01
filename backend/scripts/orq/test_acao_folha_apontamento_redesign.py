"""Apontamento de folha (DP) via redesign: registra contest_reason+contested_at SEM mudar status.
Testa numa folha draft real, confere, e LIMPA (restaura). Não fecha, não paga."""
import asyncio
import uuid
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from core.database.session import SyncSessionLocal
from modules.operacional.controllers.redesign_builders.departamento_pessoal import (
    build, rd_action_folha_apontamento,
)


async def main() -> None:
    async with async_session_factory() as db:
        pid = (await db.execute(text(
            "SELECT CAST(id AS TEXT) FROM hr_payslips WHERE status::text='draft' AND contest_reason IS NULL LIMIT 1"))).scalar()
        assert pid, "sem folha draft sem apontamento p/ testar"
    user = SimpleNamespace(id=uuid.uuid4(), name="Eliziel Gonzaga", email="e@conectamais.pro")
    sync = SyncSessionLocal()
    try:
        res = await rd_action_folha_apontamento(current_user=user, payload={
            "payslip_id": pid, "motivo": "INSS divergente — teste oraculo apontamento"}, db=sync)
        assert res.get("ok"), f"ação falhou: {res}"
    finally:
        sync.close()
    async with async_session_factory() as db:
        row = (await db.execute(text(
            "SELECT status::text, contest_reason, contested_at FROM hr_payslips WHERE id::text=:i"), {"i": pid})).first()
        assert row[0] == "draft", f"status mudou! {row[0]} (esperado draft — não deve interferir no fechamento)"
        assert row[1] and row[1].startswith("[Eliziel Gonzaga]"), f"contest_reason sem autor: {row[1]}"
        assert row[2] is not None, "contested_at não gravado"
        scr = await build(db)
        nc = scr.get("folha-nao-conformidades")
        assert nc and nc.get("type") == "table" and len(nc.get("rows", [])) >= 1, "tela não-conformidades vazia"
        print(f"OK apontamento: folha {pid[:8]} status={row[0]} (inalterado) motivo={row[1][:40]!r}; tela NC tem {len(nc['rows'])} linha(s)")
        # LIMPA (restaura — não polui produção)
        await db.execute(text("UPDATE hr_payslips SET contest_reason=NULL, contested_at=NULL WHERE id::text=:i"), {"i": pid})
        await db.commit()
        print("limpo (apontamento de teste removido)")


if __name__ == "__main__":
    asyncio.run(main())
