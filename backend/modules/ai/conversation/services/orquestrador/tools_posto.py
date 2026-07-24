"""Tools POSTO-SCOPED do líder. Filtram SEMPRE por scope.post_ids (nunca por argumento).

Reusa o mesmo escopo que os endpoints operacionais aplicam (operacional/scope.py resolve
post_ids por posts.leader_id). Aqui as queries são posto-scoped por construção — o LLM
jamais recebe dado de outro posto."""
from __future__ import annotations

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
    """Presença de HOJE (dia civil de Manaus) dos postos do escopo.

    `gp_clock_punches.posto_id` está NULL em ~99,97% das batidas reais — filtrar
    diretamente por ele não funciona. A atribuição batida->posto é derivada via
    ALOCAÇÃO: presença do posto = batidas de hoje dos employees com alocação ATIVA
    (vigente na data) nos postos do escopo. A trava de escopo continua a mesma:
    o conjunto de postos vem EXCLUSIVAMENTE de scope.post_ids (via _postos_do_escopo),
    nunca de argumento do LLM (schema _NO_ARGS).
    """
    pids = _postos_do_escopo(scope)
    if not pids:
        return {"status": "aguardando dado", "motivo": "sem posto vinculado ao seu usuário"}
    hoje = (await db.execute(text("SELECT (now() AT TIME ZONE 'America/Manaus')::date"))).scalar()
    rows = (await db.execute(
        text(
            "SELECT p.id::text AS post_id, p.name AS posto, "
            "a.employee_id::text AS employee_id, e.nome AS funcionario, "
            "COUNT(cp.id) FILTER ("
            "  WHERE (cp.punch_timestamp)::date = (now() AT TIME ZONE 'America/Manaus')::date"
            ") AS batidas_hoje "
            "FROM posts p "
            "LEFT JOIN allocations a ON a.post_id = p.id AND a.status ILIKE 'ACTIVE%' "
            "  AND a.start_date <= (now() AT TIME ZONE 'America/Manaus')::date "
            "  AND (a.end_date IS NULL OR a.end_date >= (now() AT TIME ZONE 'America/Manaus')::date) "
            "LEFT JOIN employees e ON e.id::text = a.employee_id::text "
            "LEFT JOIN gp_clock_punches cp ON cp.employee_id::text = a.employee_id::text "
            "WHERE p.id = ANY(:pids) "
            "GROUP BY p.id, p.name, a.employee_id, e.nome "
            "ORDER BY p.name, e.nome"
        ),
        {"pids": pids},
    )).fetchall()

    postos: dict[str, dict[str, Any]] = {}
    for r in rows:
        posto = postos.setdefault(r.post_id, {"posto": r.posto, "alocados": 0, "presentes": []})
        if r.employee_id is None:
            continue
        posto["alocados"] += 1
        if int(r.batidas_hoje or 0) > 0:
            posto["presentes"].append(r.funcionario)

    return {
        "data": str(hoje),
        "postos": [
            {"posto": v["posto"], "alocados": v["alocados"], "presentes": v["presentes"]}
            for v in postos.values()
        ],
    }


POSTO_TOOLS: list[ToolDef] = [
    register(ToolDef("posto_escala_hoje", "operacional",
                     "Escala/alocação de HOJE apenas dos SEUS postos (líder).", _NO_ARGS, _escala_hoje,
                     scope_kind="posto")),
    register(ToolDef("posto_presenca_hoje", "operacional",
                     "Presença/batidas de HOJE apenas dos SEUS postos (líder).", _NO_ARGS, _presenca_hoje,
                     scope_kind="posto")),
]
