"""Oráculo balde B: dashboards ai-command-center/agentes/consultor refletem as funções REAIS
da camada cognitiva (command_center/panorama), não casca. Roda no container."""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.ai.controller import command_center
from modules.operacional.controllers.redesign_builders.operacional import build
from modules.operacional.services import consultor_coo_service as coo


def _kpi(scr, label):
    for k in scr.get("kpis", []):
        if k.get("l") == label:
            return k.get("v")
    return None


async def main() -> None:
    async with async_session_factory() as db:
        cc = await command_center(None, db)
        pan = await coo.panorama(db)
        scr = await build(db)
        col = int((await db.execute(text("SELECT count(*) FROM employees WHERE status='ativo'"))).scalar() or 0)

        acc = scr.get("ai-command-center")
        assert acc and acc.get("type") == "dash", "ai-command-center não é dash"
        assert _kpi(acc, "Efetivo ativo") == str(cc["overview"]["agentes_ativos"]) == str(col), \
            f"AICC efetivo {_kpi(acc,'Efetivo ativo')} != cc {cc['overview']['agentes_ativos']} / banco {col}"
        print(f"OK ai-command-center: efetivo={col}, cobertura={_kpi(acc,'Cobertura')}, risco={_kpi(acc,'Nível de risco')}")

        ag = scr.get("agentes")
        assert ag and ag.get("type") == "dash", "agentes não é dash"
        assert _kpi(ag, "Total de agentes") == str(cc["agents_status"]["total"]), "agentes total != command_center"
        print(f"OK agentes: total={_kpi(ag,'Total de agentes')}, presentes={_kpi(ag,'Presentes')}")

        con = scr.get("consultor")
        assert con and con.get("type") == "dash", "consultor não é dash"
        assert _kpi(con, "Postos ativos") == str(pan["postos"]["ativos"]), "consultor postos != panorama"
        assert _kpi(con, "Ocorrências abertas") == str(pan["ocorrencias"]["abertas"]), "consultor occ != panorama"
        print(f"OK consultor: postos_ativos={_kpi(con,'Postos ativos')}, occ_abertas={_kpi(con,'Ocorrências abertas')}, cobertura={_kpi(con,'Cobertura')}")


if __name__ == "__main__":
    asyncio.run(main())
