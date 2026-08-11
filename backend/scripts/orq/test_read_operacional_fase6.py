"""Self-check da fatia READ-OPERACIONAL (Fase 6 VER, DISP-2) — tools_read_operacional.py.

Prova (bancada THROWAWAY, NUNCA :8080):
  (a) user operacional → consultar_operacional(consulta="postos") e ("escalas") retornam
      dado REAL do banco (dict, sem exceção);
  (b) consulta inválida → status "recusado" listando as opções (fail-closed);
  (c) belt+gate: consultar_operacional ∈ tools_for_modules({"operacional"}) e ∉ {"crm"};
      _gate(user sem operacional) levanta PermissionError; _gate(user operacional) não;
  (d) read-only: COUNT(*) de posts/scales/allocations/occurrences/inspection_rounds
      inalterado antes/depois de rodar as ops.
Reporta o TOTAL de tools de um admin (todos os módulos canônicos).

Receita:
  docker run --rm --network conecta-pro_conecta-pro-network --env-file /opt/conecta-pro/.env \\
    -e DATABASE_URL="postgresql+asyncpg://postgres:$POSTGRES_PASSWORD@postgres:5432/conecta_pro" \\
    -v /opt/conecta-pro/backend:/app -w /app --memory=2g \\
    --entrypoint python conecta-pro-backend:latest scripts/orq/test_read_operacional_fase6.py
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


_COUNT_TABLES = ("posts", "scales", "allocations", "occurrences", "inspection_rounds")


async def _counts(db):
    out = {}
    for t in _COUNT_TABLES:
        out[t] = (await db.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar()  # nomes fixos, sem input
    return out


async def main() -> int:
    results = []

    def record(n, ok, detail=""):
        results.append((n, ok, detail))
        print(f"{n} ... {'PASS' if ok else 'FAIL'}{(' — ' + detail) if detail else ''}")

    eng = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    from modules.ai.conversation.controllers import (  # noqa: F401 — importa registra + monta dispatchers
        consultor_escopado_controller,
    )
    from modules.ai.conversation.services.orquestrador import tool_registry as tr
    from modules.ai.conversation.services.orquestrador import tools_read_operacional as tro
    from core.auth.module_scope import CANONICAL_MODULES

    op_user = FakeUser("admin", ["module:operacional"])   # admin p/ all_posts no OperationalScope
    crm_user = FakeUser("operator", ["module:crm"])

    disp = tr.get_tool("consultar_operacional")

    # ── (c) belt + gate ──────────────────────────────────────────────
    try:
        op_belt = {t.name for t in tr.tools_for_modules({"operacional"})}
        crm_belt = {t.name for t in tr.tools_for_modules({"crm"})}
        assert disp is not None, "consultar_operacional não registrado"
        assert "consultar_operacional" in op_belt, "consultar_operacional ausente no belt operacional"
        assert "consultar_operacional" not in crm_belt, "consultar_operacional vazou p/ crm"
        tro._gate(op_user)  # não deve levantar
        levantou = False
        try:
            tro._gate(crm_user)
        except PermissionError:
            levantou = True
        assert levantou, "_gate deveria levantar p/ user sem operacional"
        record("(c) belt+gate", True, "dispatcher em operacional, 0 em crm; _gate barra não-op")
    except Exception as exc:
        record("(c) belt+gate", False, f"{type(exc).__name__}: {exc}")

    # ── (a) ops reais + (b) fail-closed + (d) read-only ──────────────
    async with Session() as db:
        try:
            antes = await _counts(db)

            # (a) duas ops reais via o dispatcher
            for consulta in ("postos", "escalas"):
                try:
                    res = await disp.handler(db, op_user, None, consulta=consulta, filtros={})
                    ok = isinstance(res, dict) and res.get("status") != "recusado"
                    resumo = ", ".join(list(res)[:4]) if isinstance(res, dict) else type(res).__name__
                    record(f"(a) {consulta}", ok, f"dict com chaves: {resumo}")
                except Exception as exc:
                    record(f"(a) {consulta}", False, f"{type(exc).__name__}: {exc}")

            # todas as ops rodam sem exceção (cobertura completa, read-only)
            for consulta in ("alocacoes", "ocorrencias", "rondas", "grade_postos",
                             "dashboard", "presenca_ao_vivo"):
                try:
                    res = await disp.handler(db, op_user, None, consulta=consulta, filtros={})
                    record(f"(a+) {consulta}", isinstance(res, dict), type(res).__name__)
                except Exception as exc:
                    record(f"(a+) {consulta}", False, f"{type(exc).__name__}: {exc}")

            # (b) consulta inválida → recusado com opções
            try:
                res = await disp.handler(db, op_user, None, consulta="apagar_posto", filtros={})
                ok = isinstance(res, dict) and res.get("status") == "recusado" and "opções" in res.get("motivo", "")
                record("(b) fail-closed", ok, res.get("motivo", str(res))[:90])
            except Exception as exc:
                record("(b) fail-closed", False, f"{type(exc).__name__}: {exc}")

            depois = await _counts(db)
            ro_ok = antes == depois
            record("(d) read-only", ro_ok,
                   f"counts {'inalterados' if ro_ok else f'MUDARAM: {antes} -> {depois}'}")
        finally:
            await db.rollback()

    await eng.dispose()

    # ── contagem admin (todos os módulos canônicos) ──────────────────
    admin_org = {t.name for t in tr.tools_for_modules(set(CANONICAL_MODULES))}
    total_registry = len(tr.all_tools())
    print("\n" + "=" * 60)
    print(f"ADMIN tool count (org, todos módulos canônicos): {len(admin_org)}")
    print(f"Registry total (inclui self/cliente fora do belt): {total_registry}")

    falhas = [r for r in results if not r[1]]
    print("=" * 60)
    if falhas:
        print("FALHAS:")
        for n, _ok, det in falhas:
            print(f"  x {n} — {det}")
        print("GATE: BLOQUEADO.")
        return 1
    print(f"OK read-operacional ({len(results)} checks) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
