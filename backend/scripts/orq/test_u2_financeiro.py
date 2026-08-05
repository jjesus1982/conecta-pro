"""Bancada throwaway U2 — LEITURAS novas do dispatcher consultar_financeiro.

Prova (sem :8080, só SELECT/leitura in-process contra o Postgres real):
  (a) montar_read_dispatchers() cria o ToolDef `consultar_financeiro` e as novas
      consultas U2 constam do enum do schema;
  (b) 3 das novas leituras rodam via o HANDLER do dispatcher com um usuário admin REAL
      (id vindo de entrega.resolver_usuarios_por_roles) → retornam dict/list sem erro.

Receita:
docker run --rm --network conecta-pro_conecta-pro-network -v /opt/conecta-pro/backend:/app:ro \
  -w /app -e PYTHONPATH=/app \
  -e DATABASE_URL="$(docker exec conecta-pro-backend sh -c 'echo $DATABASE_URL')" \
  --entrypoint python conecta-pro-backend:latest scripts/orq/test_u2_financeiro.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback

sys.path.insert(0, "/app")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

MODULO = "financeiro"
# consultas U2 adicionadas (esperadas no enum do dispatcher)
NOVAS = [
    "inter_saldo", "inter_extrato_resumo", "pix_recebidos", "cobrancas_inter",
    "teto_diario_pagamentos", "previsao_custos_mensais", "runway_ao_vivo",
    "margem_por_condominio", "resumo_financeiro", "reembolsos", "beneficiarios_pix",
]
# subconjunto seguro (só DB, sem API externa nem estado exótico do user) p/ chamar de fato
CHAMAR = ["resumo_financeiro", "previsao_custos_mensais", "margem_por_condominio"]


class StubUser:
    """Admin real (id do banco) — role=admin ⇒ user_has_module libera todos os módulos.
    __getattr__ devolve None p/ qualquer atributo que um controller acesse e não exista."""

    def __init__(self, uid: str) -> None:
        self.id = uid
        self.role = "admin"
        self.perfil = "all"
        self.permissions = ["all"]
        self.is_active = True
        self.email = "admin@conectapro.com.br"

    def __getattr__(self, _name):  # só chamado p/ atributos ausentes
        return None


async def main() -> int:
    eng = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    # importa o read-adapter (dispara registrar_read) + monta o dispatcher
    import modules.ai.conversation.services.orquestrador.tools_read_financeiro  # noqa: F401
    from modules.ai.conversation.services.orquestrador.read_dispatcher import montar_read_dispatchers
    from modules.ai.conversation.services.orquestrador.tool_registry import get_tool
    from modules.notifications.proativo import entrega

    montar_read_dispatchers()

    falhas: list[str] = []

    # (a) ToolDef existe e o enum de consultas cobre as novas
    tool = get_tool(f"consultar_{MODULO}")
    if tool is None:
        print(f"FALHA: ToolDef consultar_{MODULO} não registrado")
        return 1
    enum = set(tool.params_schema["properties"]["consulta"]["enum"])
    faltando = [n for n in NOVAS if n not in enum]
    if faltando:
        falhas.append(f"consultas ausentes do enum: {faltando}")
    print(f"[a] consultar_{MODULO}: {len(enum)} consultas no enum; novas presentes = {not faltando}")

    # (b) roda 3 leituras via o handler do dispatcher com identidade real
    async with Session() as db:
        ids = await entrega.resolver_usuarios_por_roles(db, ("admin",))
        if not ids:
            print("FALHA: nenhum admin real no banco p/ identidade")
            return 1
        user = StubUser(ids[0])
        for consulta in CHAMAR:
            try:
                res = await tool.handler(db, user, None, consulta=consulta, filtros={})
                ok = isinstance(res, (dict, list))
                if not ok:
                    falhas.append(f"{consulta}: retorno não é dict/list ({type(res).__name__})")
                elif isinstance(res, dict) and res.get("status") == "recusado":
                    falhas.append(f"{consulta}: dispatcher recusou ({res.get('motivo')})")
                print(f"[b] {consulta}: ok={ok} tipo={type(res).__name__}")
            except Exception as e:  # noqa: BLE001
                falhas.append(f"{consulta}: EXCEÇÃO {e!r}")
                traceback.print_exc()

    if falhas:
        print("\nFALHAS:")
        for f in falhas:
            print("  -", f)
        return 1
    print("\nOK — dispatcher consultar_financeiro expõe e roda as novas leituras U2.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
