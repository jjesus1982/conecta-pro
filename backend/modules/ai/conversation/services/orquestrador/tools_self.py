"""Tools SELF do CLT: SÓ sobre o próprio colaborador (scope.employee_id).

NUNCA aceitam employee_id por argumento — o escopo é a identidade. Reusa as MESMAS
fontes dos leitores self do employee_portal (gp_clock_punches p/ ponto; hr_payslips
p/ holerite; allocations/posts p/ escala). Módulo declarado = 'self' (fora do belt
de módulo; adicionado por tier).

Dia-de-negócio (regra canônica, TZ): "hoje"/mês-ano padrão é o de MANAUS, computado
em SQL via `(now() AT TIME ZONE 'America/Manaus')::date` — nunca datetime.utcnow().
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .tool_registry import ToolDef, register

_PONTO_ARGS = {
    "type": "object",
    "properties": {
        "mes": {"type": "integer", "minimum": 1, "maximum": 12},
        "ano": {"type": "integer", "minimum": 2020, "maximum": 2030},
    },
}
_HOLERITE_ARGS = {
    "type": "object",
    "properties": {"competencia": {"type": "string", "description": "AAAA-MM"}},
}
_NO_ARGS = {"type": "object", "properties": {}}


def _emp(scope) -> str | None:
    return getattr(scope, "employee_id", None) if scope else None


async def _hoje_manaus(db) -> Any:
    """Dia civil de MANAUS (regra canônica de TZ — nunca utcnow().date())."""
    return (await db.execute(text("SELECT (now() AT TIME ZONE 'America/Manaus')::date"))).scalar()


async def _meu_ponto(db, user, scope, mes: int | None = None, ano: int | None = None, **_) -> dict[str, Any]:
    emp = _emp(scope)
    if not emp:
        return {"status": "aguardando dado", "motivo": "usuário sem colaborador vinculado"}
    hoje = await _hoje_manaus(db)
    m = mes or hoje.month
    a = ano or hoje.year
    rows = (await db.execute(
        text(
            "SELECT punch_type, punch_timestamp, posto_nome "
            "FROM gp_clock_punches "
            "WHERE employee_id::text = :e AND extract(month FROM punch_timestamp) = :m "
            "AND extract(year FROM punch_timestamp) = :a "
            "ORDER BY punch_timestamp DESC LIMIT 200"
        ),
        {"e": emp, "m": m, "a": a},
    )).fetchall()
    return {
        "mes": m, "ano": a, "total_batidas": len(rows),
        "batidas": [{"tipo": r.punch_type, "quando": str(r.punch_timestamp), "posto": r.posto_nome} for r in rows[:50]],
    }


async def _meu_holerite(db, user, scope, competencia: str | None = None, **_) -> dict[str, Any]:
    emp = _emp(scope)
    if not emp:
        return {"status": "aguardando dado", "motivo": "usuário sem colaborador vinculado"}
    # NOTA (ajuste de schema — hr_payslips não tem colunas 'competencia'/'gross_salary'):
    # competência = reference_period ('AAAA-MM', ex.: '2026-06'); bruto = total_earnings
    # (fallback base_salary), o MESMO cálculo do PayslipPortalService.get_payslip_detail
    # (payslip_portal_service.py:222) usado pelo portal clássico — não inventa fórmula nova.
    where = "WHERE employee_id::text = :e"
    params: dict[str, Any] = {"e": emp}
    if competencia:
        where += " AND reference_period = :c"
        params["c"] = competencia
    rows = (await db.execute(
        text(
            f"SELECT reference_period, net_salary, total_earnings, base_salary FROM hr_payslips {where} "
            "ORDER BY reference_year DESC, reference_month DESC LIMIT 12"
        ),
        params,
    )).fetchall()
    return {"holerites": [
        {
            "competencia": r.reference_period,
            "liquido": float(r.net_salary or 0),
            "bruto": float(r.total_earnings or r.base_salary or 0),
        }
        for r in rows
    ]}


async def _minha_escala(db, user, scope, **_) -> dict[str, Any]:
    emp = _emp(scope)
    if not emp:
        return {"status": "aguardando dado", "motivo": "usuário sem colaborador vinculado"}
    rows = (await db.execute(
        text(
            "SELECT p.name AS posto, a.status::text AS status "
            "FROM allocations a JOIN posts p ON p.id = a.post_id "
            "WHERE a.employee_id::text = :e AND a.status::text ILIKE 'ACTIVE%'"
        ),
        {"e": emp},
    )).fetchall()
    return {"alocacoes_ativas": [{"posto": r.posto, "status": r.status} for r in rows]}


SELF_TOOLS: list[ToolDef] = [
    register(ToolDef("meu_ponto", "self",
                     "As MINHAS batidas de ponto do mês (só do usuário logado).", _PONTO_ARGS, _meu_ponto,
                     scope_kind="self")),
    register(ToolDef("meu_holerite", "self",
                     "Os MEUS holerites (líquido/bruto por competência).", _HOLERITE_ARGS, _meu_holerite,
                     scope_kind="self")),
    register(ToolDef("minha_escala", "self",
                     "A MINHA escala/alocação ativa (só do usuário logado).", _NO_ARGS, _minha_escala,
                     scope_kind="self")),
]
