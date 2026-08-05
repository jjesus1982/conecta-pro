"""Bench (throwaway) da primitiva criar_rascunho + registry. NUNCA :8080.
Prova: (a) grava 1 AgentDraft rascunho, NÃO executa (boom-executor nunca dispara),
toca o sino ao aprovador; (b) propositor=agente → solicitante NÃO é excluído dos
aprovadores; (c) idempotente. Sentinela + cleanup finally + 0 resíduo.
"""
import asyncio
import os
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.ai.conversation.services.orquestrador.acoes import rascunho
from modules.notifications.proativo import entrega

TIPO = "__TESTE_CENTRAL__"
KEY = f"__TESTE_CENTRAL__:{uuid.uuid4()}"


class _U:
    def __init__(self, uid, nome="Fulano Teste"):
        self.id = uid
        self.nome = nome


async def main() -> None:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(eng, expire_on_commit=False)

    async def _boom(db, aprovador, payload):  # não pode rodar em criar_rascunho
        raise AssertionError("executor NÃO pode ser chamado por criar_rascunho")

    rascunho.registrar_executor(TIPO, _boom)

    async with Session() as db:
        try:
            admins = await entrega.resolver_usuarios_por_roles(db, ("admin",))
            assert admins, "esperado >=1 admin ativo"
            solicitante = admins[0]

            # (a)+(b) caminho feliz: cria rascunho, solicitante NÃO excluído
            r = await rascunho.criar_rascunho(
                db, _U(solicitante), tipo=TIPO, modulo="teste",
                titulo="[TESTE CENTRAL] rascunho", resumo="corpo",
                payload={"k": 1}, gate="🟡", requires_otp=False,
                roles_aprovador=("admin",), idempotency_key=KEY)
            assert r["status"] == "rascunho" and not r.get("duplicado"), r
            print("TESTE 1 (cria rascunho, executor NÃO rodou) PASS")

            n_draft = (await db.execute(text(
                "SELECT count(*) FROM agent_drafts WHERE tipo=:t"), {"t": TIPO})).scalar()
            assert n_draft == 1, f"esperado 1 rascunho, veio {n_draft}"
            st = (await db.execute(text(
                "SELECT status FROM agent_drafts WHERE tipo=:t"), {"t": TIPO})).scalar()
            assert st == "rascunho", st
            print("TESTE 2 (1 AgentDraft status=rascunho) PASS")

            n_sino = (await db.execute(text(
                "SELECT count(*) FROM communication_notifications "
                "WHERE extra_data->>'idempotency_key' = :k"), {"k": KEY})).scalar()
            assert n_sino == len(admins), f"sino: esperado {len(admins)}, veio {n_sino}"
            print(f"TESTE 3 (sino entregue a {n_sino} aprovador(es), solicitante incluído) PASS")

            # (c) idempotência: mesma key → duplicado, não cria 2º rascunho
            r2 = await rascunho.criar_rascunho(
                db, _U(solicitante), tipo=TIPO, modulo="teste",
                titulo="[TESTE CENTRAL] rascunho", resumo="corpo",
                payload={"k": 1}, gate="🟡", requires_otp=False,
                roles_aprovador=("admin",), idempotency_key=KEY)
            assert r2.get("duplicado") is True, r2
            n_draft2 = (await db.execute(text(
                "SELECT count(*) FROM agent_drafts WHERE tipo=:t"), {"t": TIPO})).scalar()
            assert n_draft2 == 1, f"idempotência quebrou: {n_draft2} rascunhos"
            print("TESTE 4 (idempotência: sem 2º rascunho) PASS")

            print("\nTODAS AS PROVAS DE rascunho.py PASSARAM")
        finally:
            await db.execute(text("DELETE FROM agent_drafts WHERE tipo=:t"), {"t": TIPO})
            await db.execute(text(
                "DELETE FROM communication_notifications "
                "WHERE extra_data->>'idempotency_key' LIKE :k"), {"k": "__TESTE_CENTRAL__:%"})
            await db.execute(text(
                "DELETE FROM audit_logs WHERE details->>'trace_id' = 'central.teste'"))
            await db.commit()
            rem = (await db.execute(text(
                "SELECT count(*) FROM agent_drafts WHERE tipo=:t"), {"t": TIPO})).scalar()
            assert rem == 0, f"remanescentes: {rem}"
            print("LIMPEZA OK — 0 remanescentes")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
