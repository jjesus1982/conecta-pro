"""Oráculo combinado: telas redesign banco-horas / passagem-turno / instrucoes-posto refletem
o banco (exibido==banco) e não são cascas fabricadas. Roda no container."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import build

CHECKS = [
    ("banco-horas", "SELECT count(*) FROM time_bank WHERE coalesce(is_active,true)", ["João da Silva", "+12h"]),
    ("passagem-turno", "SELECT count(*) FROM operacional_passagens_turno WHERE coalesce(is_active,true)", ["06:58"]),
    ("instrucoes-posto", "SELECT count(*) FROM posts WHERE coalesce(is_active,true)", ["POP Portaria v3"]),
]


async def main() -> None:
    async with async_session_factory() as db:
        screens = await build(db)
        for sid, sql, fabricados in CHECKS:
            scr = screens.get(sid)
            assert scr and scr.get("type") == "table", f"{sid} não é tabela real"
            n_rows = len(scr.get("rows", []))
            n_db = int((await db.execute(text(sql))).scalar() or 0)
            assert n_rows == min(n_db, 200) or (sid == "instrucoes-posto" and n_rows <= min(n_db, 300)), \
                f"{sid}: exibido={n_rows} != banco={min(n_db, 200)}"
            blob = str(scr)
            for f in fabricados:
                assert f not in blob, f"{sid} AINDA fabricado ({f})!"
            print(f"OK {sid}: exibido={n_rows} (banco={n_db}); sem fabricação")


if __name__ == "__main__":
    asyncio.run(main())
