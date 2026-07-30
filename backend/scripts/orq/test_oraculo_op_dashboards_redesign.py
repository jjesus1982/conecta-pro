"""Oráculo balde A: dashboards cobertura/kpi/relatorios têm KPIs REAIS (exibido==banco)."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.controllers.redesign_builders.operacional import build


def _kpi(scr, label):
    for k in scr.get("kpis", []):
        if k.get("l") == label:
            return k.get("v")
    return None


async def main() -> None:
    async with async_session_factory() as db:
        scr = await build(db)
        posts = int((await db.execute(text("SELECT count(*) FROM posts WHERE coalesce(is_active,true)"))).scalar() or 0)
        occ_ab = int((await db.execute(text("SELECT count(*) FROM occurrences WHERE lower(coalesce(status::text,''))='aberta'"))).scalar() or 0)
        col = int((await db.execute(text("SELECT count(*) FROM employees WHERE coalesce(status,'')='ativo'"))).scalar() or 0)

        cob = scr.get("cobertura")
        assert cob and cob.get("type") == "dash", "cobertura não é dash"
        assert _kpi(cob, "Postos") == str(posts), f"cobertura Postos {_kpi(cob,'Postos')} != {posts}"
        print(f"OK cobertura: Postos={posts}, taxa={_kpi(cob,'Taxa de cobertura')}")

        kpi = scr.get("kpi")
        assert kpi and kpi.get("type") == "dash", "kpi não é dash"
        assert _kpi(kpi, "Postos ativos") == str(posts), "kpi Postos ativos != banco"
        assert _kpi(kpi, "Ocorrências abertas") == str(occ_ab), "kpi Ocorrências abertas != banco"
        print(f"OK kpi: postos={posts}, occ_abertas={occ_ab}")

        rel = scr.get("relatorios")
        assert rel and rel.get("type") == "dash", "relatorios não é dash"
        assert _kpi(rel, "Colaboradores ativos") == str(col), "relatorios Colaboradores != banco"
        print(f"OK relatorios: colaboradores_ativos={col}")


if __name__ == "__main__":
    asyncio.run(main())
