"""Self-check U2 — leituras novas do OPERACIONAL em tools_read_operacional.py (bancada THROWAWAY).

Prova: (a) montar_read_dispatchers() gera consultar_operacional e o schema.enum lista as novas;
(b) chama 3 leituras novas via handler do dispatcher, com admin REAL, retorna dict/list sem quebrar.

Receita:
  docker run --rm --network conecta-pro_conecta-pro-network \\
    -v /opt/conecta-pro/backend:/app:ro -w /app -e PYTHONPATH=/app \\
    -e DATABASE_URL="$(docker exec conecta-pro-backend sh -c 'echo $DATABASE_URL')" \\
    --entrypoint python conecta-pro-backend:latest scripts/orq/test_u2_operacional.py
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


NOVAS = ("grade_do_posto", "alocacoes_vigentes", "substituicoes_pendentes",
         "relatorio_cobertura", "colaboradores_sem_escala", "dashboard_campo", "visitas_campo")


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

    montar_read_dispatchers()
    disp = tr.get_tool("consultar_operacional")
    try:
        assert disp is not None, "consultar_operacional não registrado"
        enum = set(disp.params_schema["properties"]["consulta"]["enum"])
        faltam = [n for n in NOVAS if n not in enum]
        assert not faltam, f"consultas ausentes no schema: {faltam}"
        record("(a) consultar_operacional schema", True,
               f"{len(NOVAS)} novas no enum ({len(enum)} total)")
    except Exception as exc:
        record("(a) consultar_operacional schema", False, f"{type(exc).__name__}: {exc}")

    async with Session() as db:
        try:
            ids = await entrega.resolver_usuarios_por_roles(db, ("admin",))
            assert ids, "nenhum usuário admin ativo no banco"
            user = FakeUser(ids[0])
            record("(b0) admin real", True, f"user id={ids[0]}")

            for consulta in ("dashboard_campo", "relatorio_cobertura", "substituicoes_pendentes"):
                try:
                    res = await disp.handler(db, user, None, consulta=consulta, filtros={})
                    ok = isinstance(res, (dict, list))
                    resumo = (", ".join(list(res)[:4]) if isinstance(res, dict)
                              else f"list[{len(res)}]") if ok else type(res).__name__
                    record(f"(b) {consulta}", ok, resumo)
                except Exception as exc:
                    record(f"(b) {consulta}", False, f"{type(exc).__name__}: {exc}")
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
    print(f"OK u2-operacional ({len(results)} checks).")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
