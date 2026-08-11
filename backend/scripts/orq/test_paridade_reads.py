"""Self-check da fatia PARIDADE-READS — novas consultas de LEITURA nos dispatchers
consultar_<mod> (dp, operacional, financeiro, fiscal, ged, juridico).

Prova (bancada THROWAWAY, NUNCA :8080):
  (a) os dispatchers consultar_<mod> LISTAM as novas consultas (enum do schema);
  (b) com admin REAL (resolver_usuarios_por_roles(db,("admin",))[0], stub role='admin'),
      roda 4-5 das novas consultas via o dispatcher e cada uma retorna dado real (sem exceção);
  (c) read-only: COUNT(*) de tabelas sensíveis inalterado antes/depois.

Receita:
  docker run --rm --network conecta-pro_conecta-pro-network \\
    -v /opt/conecta-pro/backend:/app:ro -w /app -e PYTHONPATH=/app \\
    -e DATABASE_URL="$(docker exec conecta-pro-backend sh -c 'echo $DATABASE_URL')" \\
    --entrypoint python conecta-pro-backend:latest scripts/orq/test_paridade_reads.py
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
    def __init__(self, uid):
        self.id = uid
        self.role = "admin"
        self.perfil = "all"
        self.permissions = ["all"]


# módulo -> consultas novas que DEVEM aparecer no enum do dispatcher
NOVAS = {
    "dp": ("panorama", "epis"),
    "operacional": ("panorama",),
    "financeiro": ("panorama", "recebido_por_cliente", "adimplencia_clientes",
                   "projecao_caixa", "custos_recorrentes", "briefing_executivo"),
    "fiscal": ("panorama_grupo",),
    "ged": ("intercorrencias",),
    "juridico": ("analise_contrato",),
}

# subconjunto executado ao vivo (reads sem argumento obrigatório e baratos)
LIVE = [
    ("dp", "panorama"),
    ("operacional", "panorama"),
    ("financeiro", "panorama"),
    ("financeiro", "custos_recorrentes"),
    ("ged", "intercorrencias"),
]

_COUNT_TABLES = ("employees", "posts", "contracts", "gedeon_intercorrencias")


async def _counts(db):
    out = {}
    for t in _COUNT_TABLES:
        try:
            out[t] = (await db.execute(text(f"SELECT COUNT(*) FROM {t}"))).scalar()
        except Exception:
            await db.rollback()
            out[t] = "n/a"
    return out


async def main() -> int:
    results = []

    def record(n, ok, detail=""):
        results.append((n, ok, detail))
        print(f"{n} ... {'PASS' if ok else 'FAIL'}{(' — ' + detail) if detail else ''}")

    eng = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    from modules.ai.conversation.controllers import (  # noqa: F401 — importa registra as tools + monta dispatchers
        consultor_escopado_controller,
    )
    from modules.ai.conversation.services.orquestrador import tool_registry as tr

    # ── (a) dispatchers listam as novas consultas ────────────────────
    for modulo, consultas in NOVAS.items():
        tool = tr.get_tool(f"consultar_{modulo}")
        try:
            enum = set(tool.params_schema["properties"]["consulta"]["enum"])
            faltando = [c for c in consultas if c not in enum]
            record(f"(a) consultar_{modulo} lista {list(consultas)}", not faltando,
                   "todas presentes" if not faltando else f"FALTAM: {faltando}")
        except Exception as exc:
            record(f"(a) consultar_{modulo}", False, f"{type(exc).__name__}: {exc}")

    # ── admin real ───────────────────────────────────────────────────
    async with Session() as db:
        from modules.notifications.proativo.entrega import resolver_usuarios_por_roles
        admins = await resolver_usuarios_por_roles(db, ("admin",))
        if not admins:
            record("admin real", False, "nenhum user role=admin ativo")
            await eng.dispose()
            return 1
        user = FakeUser(admins[0])
        record("admin real", True, f"id={admins[0]}")

        # ── (b) rodar as consultas ao vivo via dispatcher + (c) read-only ─
        antes = await _counts(db)
        for modulo, consulta in LIVE:
            tool = tr.get_tool(f"consultar_{modulo}")
            try:
                res = await tool.handler(db, user, None, consulta=consulta, filtros={})
                ok = isinstance(res, dict) and res.get("status") != "recusado"
                resumo = ", ".join(list(res)[:5]) if isinstance(res, dict) else type(res).__name__
                record(f"(b) {modulo}.{consulta}", ok, f"chaves: {resumo}")
            except Exception as exc:
                record(f"(b) {modulo}.{consulta}", False, f"{type(exc).__name__}: {exc}")
        depois = await _counts(db)
        ro_ok = antes == depois
        record("(c) read-only", ro_ok,
               f"counts {'inalterados' if ro_ok else f'MUDARAM: {antes} -> {depois}'}")
        await db.rollback()

    await eng.dispose()

    falhas = [r for r in results if not r[1]]
    print("=" * 60)
    if falhas:
        print("FALHAS:")
        for n, _ok, det in falhas:
            print(f"  x {n} — {det}")
        print("GATE: BLOQUEADO.")
        return 1
    print(f"OK paridade-reads ({len(results)} checks) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
