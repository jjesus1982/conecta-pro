"""op_write: write que FALHA não deve deixar poison-marker de idempotência (retry liberado);
write que sucede grava o marcador (2ª chamada com mesma chave = bloqueada)."""
import asyncio
import uuid

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_write_gate import GateError, op_write


async def main() -> None:
    key = f"testpoison:{uuid.uuid4()}"
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref = :l"), {"l": f"idem:{key}"})
        await db.commit()

        async def _falha():
            raise RuntimeError("write falhou de propósito")

        async def _ok():
            return {"ok": True}

        # 1) write falha → NÃO deve deixar marcador
        try:
            await op_write(db, real_write=_falha, idempotency_key=key)
            raise AssertionError("deveria ter propagado a falha")
        except RuntimeError:
            pass
        n = (await db.execute(text("SELECT count(*) FROM redesign_gate_otp WHERE ref=:l"), {"l": f"idem:{key}"})).scalar()
        assert n == 0, f"POISON! marcador ficou após falha (n={n})"
        print("OK sem-poison: write que falha não deixou marcador")

        # 2) retry (mesma chave) com write OK → NÃO bloqueado (poison teria bloqueado) + grava marcador
        r = await op_write(db, real_write=_ok, idempotency_key=key)
        assert r.get("ok"), f"retry deveria suceder: {r}"
        n2 = (await db.execute(text("SELECT count(*) FROM redesign_gate_otp WHERE ref=:l"), {"l": f"idem:{key}"})).scalar()
        assert n2 == 1, f"marcador deveria existir após sucesso (n={n2})"
        print("OK retry: após falha, retry com sucesso passou e gravou o marcador")

        # 3) 3ª chamada mesma chave → agora bloqueada (idempotência de verdade)
        try:
            await op_write(db, real_write=_ok, idempotency_key=key)
            raise AssertionError("deveria bloquear duplicidade")
        except GateError:
            pass
        print("OK idempotência: 2ª execução com mesma chave bloqueada")

        await db.execute(text("DELETE FROM redesign_gate_otp WHERE ref=:l"), {"l": f"idem:{key}"})
        await db.commit()
        print("limpo")


if __name__ == "__main__":
    asyncio.run(main())
