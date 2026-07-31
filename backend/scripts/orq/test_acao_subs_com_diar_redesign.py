"""Ações redesign: diarista ativar/desativar (real, restaura), alerta-ack (real, restaura),
e build() carrega todos os forms. Reuso via gate."""
import asyncio
import uuid
from types import SimpleNamespace

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import (
    build, rd_action_alerta_ack, rd_action_diarista_ativar, rd_action_diarista_desativar,
)


async def main() -> None:
    async with async_session_factory() as db:
        u = SimpleNamespace(id=uuid.uuid4(), name="Teste", email="t@conectapro.com.br")

        # 1) diarista desativar -> reativar (restaura estado)
        d = (await db.execute(text("SELECT id FROM diarists WHERE coalesce(ativo,true) LIMIT 1"))).scalar()
        assert d, "sem diarista ativo"
        off = await rd_action_diarista_desativar(current_user=u, payload={"diarist_id": str(d)}, db=db)
        assert off["ok"], f"desativar: {off}"
        a1 = (await db.execute(text("SELECT ativo FROM diarists WHERE id::text=:i"), {"i": str(d)})).scalar()
        assert a1 is False, f"ativo após desativar={a1}"
        on = await rd_action_diarista_ativar(current_user=u, payload={"diarist_id": str(d)}, db=db)
        assert on["ok"], f"ativar: {on}"
        a2 = (await db.execute(text("SELECT ativo FROM diarists WHERE id::text=:i"), {"i": str(d)})).scalar()
        assert a2 is True, f"ativo após reativar={a2}"
        print(f"OK diarista ativar/desativar: {d} desativado→reativado (estado restaurado)")

        # 2) alerta-ack em alerta real não reconhecido, depois restaura
        al = (await db.execute(text(
            "SELECT id FROM communication_alerts WHERE coalesce(is_active,true) AND acknowledged_by IS NULL LIMIT 1"))).first()
        if al:
            ackr = await rd_action_alerta_ack(current_user=u, payload={"alert_id": str(al[0])}, db=db)
            assert ackr["ok"], f"ack: {ackr}"
            acked = (await db.execute(text("SELECT acknowledged_by FROM communication_alerts WHERE id::text=:i"), {"i": str(al[0])})).scalar()
            assert acked is not None, "alerta não marcou acknowledged_by"
            await db.execute(text("UPDATE communication_alerts SET acknowledged_by=NULL WHERE id::text=:i"), {"i": str(al[0])})
            await db.commit()
            print(f"OK alerta-ack: {al[0]} reconhecido (restaurado)")
        else:
            print("SKIP alerta-ack: nenhum alerta não-reconhecido")

        # 3) build() carrega todos os forms novos (sem crash → queries válidas)
        scr = await build(db)
        for sid in ("substituicao-confirmar", "substituicao-rejeitar", "comunicado-publicar", "alerta-ack",
                    "diarista-ativar", "diarista-desativar", "diarista-avaliar"):
            assert scr.get(sid) and scr[sid].get("type") == "form", f"{sid} não é form"
        print("OK build: 7 forms de ação carregados")


if __name__ == "__main__":
    asyncio.run(main())
