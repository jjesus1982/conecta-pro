"""E2E vivo Fase 6: chat NL -> engine.run_engine -> tool gera-doc -> PDF real.

Roda in-backend (bancada throwaway), com LLM+DB reais. Prova ROTEAMENTO + PDF, nao unidade.
3 mensagens (DRE / proposta / visita). Captura qual tool o engine chamou e se veio %PDF.

Bancada throwaway (NUNCA :8080; faz 3 chamadas REAIS de LLM):
  docker run --rm --network conecta-pro_conecta-pro-network --env-file /opt/conecta-pro/.env \\
    -e DATABASE_URL="postgresql+asyncpg://postgres:<pwd>@postgres:5432/conecta_pro" \\
    -v /opt/conecta-pro/backend:/app:ro -w /app -e PYTHONPATH=/app \\
    --entrypoint python conecta-pro-backend:latest scripts/orq/e2e_fase6_gera_doc.py
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import json

# 1) registra TODAS as tools (o import do controller dispara os register())
import modules.ai.conversation.controllers.consultor_escopado_controller as ctrl  # noqa: E402
from core.auth.module_scope import user_modules  # noqa: E402
from core.database import async_session_factory  # noqa: E402
from core.models.user import User  # noqa: E402
from modules.ai.conversation.services.orquestrador.engine import OrqScope, run_engine  # noqa: E402
from sqlalchemy import select  # noqa: E402

ADMIN_EMAIL = "jjesus@conectamais.pro"

_calls: list[dict] = []  # preenchido por mensagem (reset antes de cada run)


def _wrap(tool):
    async def handler(db, user, scope, **args):
        res = await tool.handler(db, user, scope, **args)
        rec = {"tool": tool.name, "args": args}
        if isinstance(res, dict) and res.get("arquivo_base64"):
            raw = base64.b64decode(res["arquivo_base64"])
            rec["pdf"] = raw[:4] == b"%PDF"
            rec["pdf_bytes"] = len(raw)
            rec["nome"] = res.get("nome")
        elif isinstance(res, dict) and res.get("status") == "recusado":
            rec["recusa"] = res.get("motivo")
        else:
            rec["raw"] = str(res)[:200]
        _calls.append(rec)
        return res
    return dataclasses.replace(tool, handler=handler)


async def main():
    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.email == ADMIN_EMAIL))).scalars().first()
        assert user is not None, f"admin {ADMIN_EMAIL} nao encontrado"
        mods = user_modules(user)
        print(f"user={user.email} role={user.role} modules={sorted(mods)}", flush=True)

        # mesmo caminho de montagem do controller p/ o tier GESTOR (diretoria via engine)
        tools = [_wrap(t) for t in ctrl._modulo_tools(mods)]
        gera = sorted(t.name for t in tools if t.name.startswith("gerar_"))
        print(f"gera-doc tools no escopo ({len(gera)}): {gera}", flush=True)
        scope = OrqScope(tier="gestor", is_manager=True, all_posts=True)
        sysp = ctrl._SYSTEM_BASE

        mensagens = [
            "gera o DRE de 2026",
            "monta uma proposta de portaria para o cliente CONDOMINIO RESIDENCIAL GREEN HILLS "
            "com salario base 1670, 2 postos, 12 meses",
            "gera o relatorio da visita VIS-2026-00001",
        ]
        for i, pergunta in enumerate(mensagens, 1):
            _calls.clear()
            print(f"\n===== MSG {i}: {pergunta!r} =====", flush=True)
            try:
                out = await run_engine(db, user, scope, tools, pergunta,
                                       system_prompt=sysp, origem="e2e_fase6")
                print("resposta:", (out.get("resposta") or "")[:400], flush=True)
                print("modelo:", out.get("modelo"), "grounded:", out.get("grounded"), flush=True)
            except Exception as e:
                print(f"ENGINE_ERRO: {type(e).__name__}: {e}", flush=True)
            print("TOOLS_CHAMADAS:", json.dumps(_calls, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
