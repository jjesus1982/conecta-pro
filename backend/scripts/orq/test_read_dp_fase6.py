"""Self-check da fatia READ-DP (Fase 6 VER) — agora sobre o READ DISPATCHER.

Até 11/08/2026 este oráculo pedia 8 tools flat (`dp_listar_funcionarios`, …) ao registry.
A refatoração de 05/08 colapsou os reads de cada módulo em UMA tool `consultar_<modulo>`
(24 flat → 3 dispatchers, para caber no teto de tools do LLM). As 8 sumiram do registry, o
oráculo estourou em `get_tool -> None` e a falha parecia buraco de produto. Não era: era
teste apontando para uma API aposentada.

A lista deixou de ser fixa: varre TODAS as ops registradas em `_READ_OPS["dp"]` (21 hoje).
Op nova entra coberta sozinha; op que sumir aparece como falha, não como silêncio.

Prova:
  (a) cada op de dp responde dict pelo dispatcher (dado real ou "aguardando dado");
  (b) belt+gate: consultar_dp ∈ tools_for_modules({"dp"}) e ∉ {"crm"}; user sem dp leva
      PermissionError; consulta inexistente é RECUSADA com as opções (fail-closed);
  (c) read-only: COUNT(*) de employees/hr_vacation_requests/admission_processes inalterado.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_read_dp_fase6.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


class FakeUser:
    def __init__(self, role, permissions):
        self.role = role
        self.permissions = permissions
        self.id = "00000000-0000-0000-0000-000000000000"


#: Ops que precisam de um filtro para significar alguma coisa. Sem isto elas devolveriam
#: "aguardando dado" honestamente e o teste não provaria nada — o filtro é o que faz a
#: consulta exercitar a query de verdade.
FILTROS = {
    "buscar_funcionario": {"q": "a"},   # o parâmetro é `q`, não `search`
    "folha_analitico": {"mes": 6, "ano": 2026},
    "folha_resumo": {"mes": 6, "ano": 2026},
}

#: Ops que exigem UM colaborador. O id é resolvido em runtime (nunca hardcodar UUID de
#: gente); sem o filtro elas respondem "informe employee_id" — honesto, mas não prova query.
PRECISA_COLABORADOR = ("banco_horas", "saldo_ferias")

_COUNT_TABLES = ("employees", "hr_vacation_requests", "admission_processes")


async def _counts(db):
    return {t: (await db.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar() for t in _COUNT_TABLES}


async def main() -> int:
    results = []

    def record(n, ok, detail=""):
        results.append((n, ok, detail))
        print(f"{n} ... {'PASS' if ok else 'FAIL'}{(' — ' + detail) if detail else ''}")

    eng = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    from modules.ai.conversation.controllers import (  # noqa: F401 — importar registra as tools
        consultor_escopado_controller,
    )
    from core.auth.module_scope import CANONICAL_MODULES
    from modules.ai.conversation.services.orquestrador import tool_registry as tr
    from modules.ai.conversation.services.orquestrador.read_dispatcher import _READ_OPS

    dp_user = FakeUser("operator", ["module:dp"])
    crm_user = FakeUser("operator", ["module:crm"])

    ops = sorted(_READ_OPS.get("dp", {}))
    assert ops, "nenhuma op de leitura registrada em dp — o dispatcher não foi montado"
    disp = tr.get_tool("consultar_dp")
    assert disp is not None, "consultar_dp ausente do registry"

    # ── (b) belt + gate + fail-closed ────────────────────────────────
    try:
        dp_belt = {t.name for t in tr.tools_for_modules({"dp"})}
        crm_belt = {t.name for t in tr.tools_for_modules({"crm"})}
        assert "consultar_dp" in dp_belt, "consultar_dp ausente do belt de dp"
        assert "consultar_dp" not in crm_belt, "consultar_dp VAZOU para o belt de crm"

        barrou = False
        try:
            await disp.handler(None, crm_user, None, consulta=ops[0])
        except PermissionError:
            barrou = True
        assert barrou, "dispatcher NÃO barrou user sem o módulo dp"

        # Gate ANTES do roteamento: quem tem dp e pede bobagem é recusado com as opções,
        # não recebe erro cru nem um chute.
        async with Session() as db:
            recusa = await disp.handler(db, dp_user, None, consulta="consulta_que_nao_existe")
        assert recusa.get("status") == "recusado", f"consulta inválida não foi recusada: {recusa}"
        assert ops[0] in recusa.get("motivo", ""), "a recusa não lista as opções válidas"
        record("(b) belt+gate+fail-closed", True,
               f"consultar_dp só em dp; PermissionError sem dp; inválida recusada ({len(ops)} ops)")
    except Exception as exc:
        record("(b) belt+gate+fail-closed", False, f"{type(exc).__name__}: {exc}")

    # ── (a) cada op responde + (c) read-only ─────────────────────────
    async with Session() as db:
        try:
            antes = await _counts(db)
            emp = (await db.execute(text(
                "SELECT id::text FROM employees WHERE status = 'ativo' ORDER BY created_at LIMIT 1"
            ))).scalar()
            assert emp, "pré-condição: nenhum colaborador ativo no banco"
            for nome in PRECISA_COLABORADOR:
                FILTROS[nome] = {"employee_id": emp}
            for nome in ops:
                try:
                    res = await disp.handler(db, dp_user, None,
                                             consulta=nome, filtros=FILTROS.get(nome))
                    ok = isinstance(res, dict) and res.get("status") != "recusado"
                    resumo = ", ".join(list(res)[:4]) if isinstance(res, dict) else type(res).__name__
                    record(f"(a) dp/{nome}", ok, f"chaves: {resumo}")
                except Exception as exc:
                    record(f"(a) dp/{nome}", False, f"{type(exc).__name__}: {exc}")
            depois = await _counts(db)
            ro_ok = antes == depois
            record("(c) read-only", ro_ok,
                   f"counts {'inalterados' if ro_ok else f'MUDARAM: {antes} -> {depois}'}")
        finally:
            await db.rollback()

    await eng.dispose()

    admin_org = {t.name for t in tr.tools_for_modules(set(CANONICAL_MODULES))}
    print("\n" + "=" * 60)
    print(f"ADMIN tool count (org, todos módulos canônicos): {len(admin_org)}")
    print(f"Registry total (inclui self/cliente fora do belt): {len(tr.all_tools())}")

    falhas = [r for r in results if not r[1]]
    print("=" * 60)
    if falhas:
        print("FALHAS:")
        for n, _ok, det in falhas:
            print(f"  x {n} — {det}")
        print("GATE: BLOQUEADO.")
        return 1
    print(f"OK read-dp ({len(results)} checks, {len(ops)} ops) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
