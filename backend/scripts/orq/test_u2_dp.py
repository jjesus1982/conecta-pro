"""Self-check U2 — leituras novas do DP em tools_read_dp.py (bancada THROWAWAY, NUNCA :8080).

Prova:
  (a) montar_read_dispatchers() gera consultar_dp e o schema.enum lista as consultas novas;
  (b) chamar 3 das novas leituras via o handler do dispatcher, com um admin REAL do banco
      (entrega.resolver_usuarios_por_roles + stub), retorna dict sem quebrar (ou "aguardando
      dado" honesto se vazio).

Receita:
  docker run --rm --network conecta-pro_conecta-pro-network \\
    -v /opt/conecta-pro/backend:/app:ro -w /app -e PYTHONPATH=/app \\
    -e DATABASE_URL="$(docker exec conecta-pro-backend sh -c 'echo $DATABASE_URL')" \\
    --entrypoint python conecta-pro-backend:latest scripts/orq/test_u2_dp.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback

sys.path.insert(0, "/app")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


class FakeUser:
    def __init__(self, uid):
        self.id = uid
        self.role = "admin"
        self.perfil = "all"
        self.permissions = ["all"]


NOVAS = ("ponto_dashboard", "folha_dashboard", "banco_horas", "saldo_ferias", "rescisoes",
         "justificativas_ponto_pendentes", "rubricas_folha", "candidatos",
         "recrutamento_overview", "esocial_eventos")


async def main() -> int:
    results = []

    def record(n, ok, detail=""):
        results.append((n, ok, detail))
        print(f"{n} ... {'PASS' if ok else 'FAIL'}{(' — ' + detail) if detail else ''}")

    eng = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    from modules.ai.conversation.controllers import (  # noqa: F401 — importa registra as tools
        consultor_escopado_controller,
    )
    from modules.ai.conversation.services.orquestrador import tool_registry as tr
    from modules.ai.conversation.services.orquestrador.read_dispatcher import (
        montar_read_dispatchers,
    )
    from modules.notifications.proativo import entrega

    # ── (a) dispatcher consultar_dp existe e lista as novas consultas ─────────
    montar_read_dispatchers()
    disp = tr.get_tool("consultar_dp")
    try:
        assert disp is not None, "consultar_dp não registrado"
        enum = set(disp.params_schema["properties"]["consulta"]["enum"])
        faltam = [n for n in NOVAS if n not in enum]
        assert not faltam, f"consultas ausentes no schema: {faltam}"
        record("(a) consultar_dp schema", True,
               f"{len(NOVAS)} novas no enum ({len(enum)} total)")
    except Exception as exc:
        record("(a) consultar_dp schema", False, f"{type(exc).__name__}: {exc}")

    # ── (b) leituras novas via handler do dispatcher, com admin REAL ──────────
    # Mistura: async (rescisoes, rubricas_folha, recrutamento_overview) + sync-session
    # (ponto_dashboard, folha_dashboard, candidatos) para provar os dois caminhos.
    async with Session() as db:
        try:
            ids = await entrega.resolver_usuarios_por_roles(db, ("admin",))
            assert ids, "nenhum usuário admin ativo no banco"
            user = FakeUser(ids[0])
            record("(b0) admin real", True, f"user id={ids[0]}")

            for consulta in ("rescisoes", "rubricas_folha", "recrutamento_overview",
                             "ponto_dashboard", "folha_dashboard", "candidatos",
                             "justificativas_ponto_pendentes"):
                try:
                    res = await disp.handler(db, user, None, consulta=consulta, filtros={})
                    ok = isinstance(res, (dict, list))
                    if isinstance(res, dict):
                        resumo = ", ".join(list(res)[:4])
                    else:
                        resumo = f"list[{len(res)}]"
                    record(f"(b) {consulta}", ok, f"{type(res).__name__}: {resumo}")
                except Exception as exc:
                    record(f"(b) {consulta}", False, f"{type(exc).__name__}: {exc}")
                finally:
                    await db.rollback()  # sync-session controllers não sujam o async db
        except Exception as exc:
            record("(b0) admin real", False, f"{type(exc).__name__}: {exc}")
        finally:
            await db.rollback()

    await eng.dispose()

    falhas = [r for r in results if not r[1]]
    print("=" * 60)
    if falhas:
        print("FALHAS:")
        for n, _ok, det in falhas:
            print(f"  x {n} — {det}")
        return 1
    print(f"OK u2-dp ({len(results)} checks).")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
