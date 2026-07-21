"""Homologação (T1) — módulo NOVO (não existia builder no monólito). Dashboard da base
de homologação isolada (is_homologacao / cliente HOMOLOGACAO / batidas de teste)."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import IC, S, _scalar

SLUG = "homologacao"
EXTRA_MENU: list[dict] = []


async def build(db) -> dict:
    out: dict = {}
    try:
        n_emp = await _scalar(db, "SELECT count(*) FROM employees WHERE is_homologacao=true")
        n_punch = await _scalar(db, "SELECT count(*) FROM gp_clock_punches p JOIN employees e ON e.id=p.employee_id WHERE e.is_homologacao=true")
        emps = (await db.execute(text("SELECT nome, coalesce(cargo,'—') FROM employees WHERE is_homologacao=true ORDER BY nome LIMIT 20"))).fetchall()
        out["visao"] = {
            "title": "Homologação — base isolada", "sub": "Ambiente de homologação (isolado da produção — folha/operacional excluem)",
            "cta": "—", "type": "dash", "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_emp or 0), "l": "Colaboradores homolog", "icon": IC["users"], "color": "#0F1B3A"},
                {"v": "1", "l": "Cliente base", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": str(n_punch or 0), "l": "Batidas de teste", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": "Isolada", "l": "Status", "icon": IC["shield"], "color": "#16A34A"},
            ],
            "panels": [
                {"title": "Colaboradores em homologação", "rows": [{"left": nm, "right": cg, **S["info"]} for nm, cg in emps] or [{"left": "Base vazia", "right": "0", **S["mut"]}]},
                {"title": "Ambiente", "rows": [
                    {"left": "Cliente base", "right": "HOMOLOGACAO (Conecta Base)", **S["ok"]},
                    {"left": "Isolamento", "right": "Excluído de folha/operacional", **S["ok"]},
                ]},
            ],
        }
    except Exception:  # noqa: BLE001
        pass
    return out
