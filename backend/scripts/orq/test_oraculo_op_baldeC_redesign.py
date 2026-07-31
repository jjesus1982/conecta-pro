"""Oráculo balde C: mapa/ronda-mobile/escalas-visual/campo (tabela, exibido==banco) e
triagem (KPI==sub-função real do triage_controller)."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import build
from modules.operacional.triage.controllers.triage_controller import _ocorrencias

TAB = [
    ("mapa", "SELECT count(*) FROM posts WHERE coalesce(is_active,true)", 300),
    ("ronda-mobile", "SELECT count(*) FROM inspection_rounds WHERE lower(coalesce(status::text,'')) IN ('em_andamento','iniciada','pausada','iniciado')", 100),
    ("escalas-visual", "SELECT count(*) FROM scales WHERE coalesce(is_active,true)", 200),
    ("campo", "SELECT count(*) FROM visitas WHERE coalesce(is_active,true)", 200),
]


def _kpi(scr, label):
    for k in scr.get("kpis", []):
        if k.get("l") == label:
            return k.get("v")
    return None


async def main() -> None:
    async with async_session_factory() as db:
        scr = await build(db)
        for sid, sql, cap in TAB:
            s = scr.get(sid)
            assert s and s.get("type") == "table", f"{sid} não é tabela real"
            n_rows = len(s.get("rows", []))
            n_db = int((await db.execute(text(sql))).scalar() or 0)
            assert n_rows == min(n_db, cap), f"{sid}: exibido={n_rows} != banco={min(n_db, cap)}"
            print(f"OK {sid}: exibido={n_rows} == banco={min(n_db, cap)}")

        tri = scr.get("triagem")
        assert tri and tri.get("type") == "dash", "triagem não é dash"
        oc = await _ocorrencias(db)
        assert _kpi(tri, "Ocorrências abertas") == str(int(getattr(oc, "abertas_total", 0) or 0)), "triagem occ != sub-função"
        print(f"OK triagem: ocorrencias_abertas={_kpi(tri,'Ocorrências abertas')}, sem_escala={_kpi(tri,'Postos sem escala vigente')}")


if __name__ == "__main__":
    asyncio.run(main())
