"""Tools POSTO-SCOPED do líder. Filtram SEMPRE por scope.post_ids (nunca por argumento).

Reusa o mesmo escopo que os endpoints operacionais aplicam (operacional/scope.py resolve
post_ids por posts.leader_id). Aqui as queries são posto-scoped por construção — o LLM
jamais recebe dado de outro posto."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text

from .tool_registry import ToolDef, register

_NO_ARGS = {"type": "object", "properties": {}}


def _postos_do_escopo(scope) -> list[str] | None:
    """Retorna a lista de post_ids do escopo, ou None se não há posto (líder sem posto)."""
    if scope is None:
        return None
    if getattr(scope, "all_posts", False):
        return None  # tratado como 'sem filtro' só para gestor; líder nunca chega aqui
    pids = getattr(scope, "post_ids", None) or []
    return pids or None


async def _escala_hoje(db, user, scope, **_) -> dict[str, Any]:
    pids = _postos_do_escopo(scope)
    if not pids:
        return {"status": "aguardando dado", "motivo": "sem posto vinculado ao seu usuário"}
    rows = (await db.execute(
        text(
            "SELECT p.id::text AS post_id, p.name AS posto, "
            "COUNT(a.id) FILTER (WHERE a.status::text ILIKE 'ACTIVE%') AS alocados "
            "FROM posts p LEFT JOIN allocations a ON a.post_id = p.id "
            "WHERE p.id = ANY(:pids) GROUP BY p.id, p.name ORDER BY p.name"
        ),
        {"pids": pids},
    )).fetchall()
    return {"postos": [{"posto": r.posto, "alocados": int(r.alocados or 0)} for r in rows]}


async def _presenca_hoje(db, user, scope, **_) -> dict[str, Any]:
    pids = _postos_do_escopo(scope)
    if not pids:
        return {"status": "aguardando dado", "motivo": "sem posto vinculado ao seu usuário"}
    hoje = datetime.utcnow().date()
    rows = (await db.execute(
        text(
            "SELECT posto_id, COUNT(*) AS batidas "
            "FROM gp_clock_punches "
            "WHERE posto_id = ANY(:pids) AND date(punch_timestamp) = :hoje "
            "GROUP BY posto_id"
        ),
        {"pids": [str(p) for p in pids], "hoje": hoje},
    )).fetchall()
    return {"data": str(hoje), "presenca": [{"posto_id": r.posto_id, "batidas": int(r.batidas)} for r in rows]}


POSTO_TOOLS: list[ToolDef] = [
    register(ToolDef("posto_escala_hoje", "operacional",
                     "Escala/alocação de HOJE apenas dos SEUS postos (líder).", _NO_ARGS, _escala_hoje)),
    register(ToolDef("posto_presenca_hoje", "operacional",
                     "Presença/batidas de HOJE apenas dos SEUS postos (líder).", _NO_ARGS, _presenca_hoje)),
]
