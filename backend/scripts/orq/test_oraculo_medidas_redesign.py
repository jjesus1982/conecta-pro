"""Oráculo: a tela redesign 'medidas-administrativas' reflete disciplinary_actions (exibido==banco),
e NÃO contém dado fabricado. Roda dentro do container (asyncpg → DB real)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# As telas do operacional foram agrupadas em abas: o slug de topo virou stub
# `{"type":"redirect","groupRef":…}` e a tela real é aba do grupo. Ler `scr[slug]`
# direto encontra o stub e acusa "não é dash/tabela/form" sobre tela que está lá.
# Foi o que derrubou 6 oráculos na varredura de 12/08 às 05:00.
from _fixtures import tela  # noqa: E402

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import build


async def main() -> None:
    async with async_session_factory() as db:
        screens = await build(db)
        scr = tela(screens, "medidas-administrativas")
        assert scr and scr.get("type") == "table", "medidas-administrativas não é tabela real"
        n_rows = len(scr.get("rows", []))
        n_db = (await db.execute(text(
            "SELECT count(*) FROM disciplinary_actions WHERE coalesce(is_active,true)"))).scalar() or 0
        assert n_rows == min(int(n_db), 200), f"linhas exibidas={n_rows} != banco={min(int(n_db),200)}"
        blob = str(scr)
        assert "Carlos Batista" not in blob and "Uniforme incompleto" not in blob, "AINDA fabricado!"
        print(f"OK medidas: exibido={n_rows} == banco(min200)={min(int(n_db),200)}; sem fabricação")


if __name__ == "__main__":
    asyncio.run(main())
