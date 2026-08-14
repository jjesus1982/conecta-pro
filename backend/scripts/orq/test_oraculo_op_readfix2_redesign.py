"""Oráculo: read-fixes substituicoes/escalas-templates/escalas-grade/avaliacao-equipe/
diaristas-escala/diaristas-fechamento refletem o banco (exibido==banco). Roda no container."""
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

CHECKS = [
    ("substituicoes", "SELECT count(*) FROM substitutions WHERE coalesce(is_active,true)", 200),
    ("escalas-templates", "SELECT count(*) FROM scale_templates WHERE coalesce(is_active,true)", 200),
    ("escalas-grade", "SELECT count(DISTINCT e.nome) FROM shifts s LEFT JOIN employees e ON e.id=s.employee_id WHERE coalesce(s.is_active,true)", 300),
    ("avaliacao-equipe", "SELECT count(*) FROM operacional_avaliacoes_equipe WHERE coalesce(is_active,true)", 200),
    # "diaristas-escala" saiu: lia diarist_schedules (0 linhas) e o equivalente vivo já é
    # a aba "diarias". E "diaristas-fechamento" apontava para diarist_payments, também 0 —
    # ou seja, este oráculo passava com 0==0 sobre tabela morta. Verde que não provava nada:
    # exibido==banco só tem força quando o banco tem linha. Agora bate nos 251 pagamentos reais.
    ("diaristas-fechamento", "SELECT count(*) FROM financial_pagamentos_diaristas", 200),
]


async def main() -> None:
    async with async_session_factory() as db:
        screens = await build(db)
        for sid, sql, cap in CHECKS:
            scr = tela(screens, sid)
            assert scr and scr.get("type") == "table", f"{sid} não é tabela real"
            n_rows = len(scr.get("rows", []))
            n_db = int((await db.execute(text(sql))).scalar() or 0)
            assert n_rows == min(n_db, cap), f"{sid}: exibido={n_rows} != banco={min(n_db, cap)}"
            print(f"OK {sid}: exibido={n_rows} == banco={min(n_db, cap)}")


if __name__ == "__main__":
    asyncio.run(main())
