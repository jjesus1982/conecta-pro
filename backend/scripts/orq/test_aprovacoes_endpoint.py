"""Bench (throwaway) dos endpoints aprovar/rejeitar rascunho. NUNCA :8080.
Prova: (a) aprovar 🔵 → executa executor REVERSÍVEL (sem efeito externo), status=executado;
(b) aprovar requires_otp → NÃO executa (boom nunca dispara), status=aprovado+needsOtp;
(c) aprovar sem role → 403; (d) rejeitar → status=rejeitado. Sentinela + cleanup + 0 resíduo.
"""
import asyncio
import os
import uuid

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.notifications.proativo import entrega
from modules.ai.conversation.services.orquestrador.acoes import rascunho
from modules.operacional.controllers.redesign_builders import aprovacoes

TIPO = "__TESTE_APROVA__"
TIPO_OTP = "__TESTE_APROVA_OTP__"
KEY = f"__TESTE_APROVA__:{uuid.uuid4()}"
KEY_OTP = f"__TESTE_APROVA__:{uuid.uuid4()}:otp"
executou = {"n": 0}


class _U:
    def __init__(self, uid, role="admin"):
        self.id = uid
        self.role = role
        self.perfil = "all" if role == "admin" else ""
        self.nome = "Teste"


async def _exec_ok(db, aprovador, payload):
    executou["n"] += 1
    return "FAKE-REF-123"  # sem efeito externo


async def _exec_boom(db, aprovador, payload):
    raise AssertionError("executor OTP NÃO pode rodar na Central (deve rotear p/ tela de OTP)")


async def main() -> None:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(eng, expire_on_commit=False)
    rascunho.registrar_executor(TIPO, _exec_ok)
    rascunho.registrar_executor(TIPO_OTP, _exec_boom)

    async with Session() as db:
        try:
            admins = await entrega.resolver_usuarios_por_roles(db, ("admin",))
            assert admins, "esperado >=1 admin"
            adm = admins[0]

            # cria os 2 rascunhos
            r1 = await rascunho.criar_rascunho(
                db, _U(adm), tipo=TIPO, modulo="teste", titulo="[TESTE] aprova",
                resumo="x", payload={"a": 1}, gate="🔵", requires_otp=False,
                roles_aprovador=("admin",), idempotency_key=KEY)
            did = r1["draft_id"]
            r2 = await rascunho.criar_rascunho(
                db, _U(adm), tipo=TIPO_OTP, modulo="teste", titulo="[TESTE] aprova otp",
                resumo="x", payload={"action_url_execucao": "/redesign/financeiro"},
                gate="🔴", requires_otp=True, roles_aprovador=("admin",), idempotency_key=KEY_OTP)
            did_otp = r2["draft_id"]

            # (a) aprovar 🔵 → executa
            res = await aprovacoes.aprovar_rascunho(current_user=_U(adm), draft_id=did, payload={}, db=db)
            assert res["ok"] and res.get("id") == "FAKE-REF-123", res
            assert executou["n"] == 1, executou
            st = (await db.execute(text("SELECT status, entity_ref FROM agent_drafts WHERE id=:i"), {"i": did})).first()
            assert st[0] == "executado" and st[1] == "FAKE-REF-123", st
            print("TESTE 1 (aprovar 🔵 executa, status=executado) PASS")

            # (b) aprovar requires_otp → NÃO executa, status=aprovado+needsOtp
            res2 = await aprovacoes.aprovar_rascunho(current_user=_U(adm), draft_id=did_otp, payload={}, db=db)
            assert res2.get("needsOtp") is True, res2
            assert executou["n"] == 1, "boom-executor rodou? não deveria"
            sto = (await db.execute(text("SELECT status FROM agent_drafts WHERE id=:i"), {"i": did_otp})).scalar()
            assert sto == "aprovado", sto
            print("TESTE 2 (requires_otp NÃO executa, status=aprovado, needsOtp) PASS")

            # (c) aprovar sem role → 403
            r3 = await rascunho.criar_rascunho(
                db, _U(adm), tipo=TIPO, modulo="teste", titulo="[TESTE] 403",
                resumo="x", payload={}, gate="🔵", requires_otp=False,
                roles_aprovador=("admin",), idempotency_key=KEY + ":403")
            got403 = False
            try:
                await aprovacoes.aprovar_rascunho(
                    current_user=_U("00000000-0000-0000-0000-0000000000cc", role="funcionario"),
                    draft_id=r3["draft_id"], payload={}, db=db)
            except HTTPException as e:
                got403 = e.status_code == 403
            assert got403, "esperado 403 para quem não tem role de aprovador"
            print("TESTE 3 (aprovar sem role → 403) PASS")

            # (d) rejeitar → status=rejeitado
            res4 = await aprovacoes.rejeitar_rascunho(
                current_user=_U(adm), draft_id=r3["draft_id"], payload={"motivo": "teste"}, db=db)
            assert res4["ok"], res4
            st4 = (await db.execute(text("SELECT status FROM agent_drafts WHERE id=:i"), {"i": r3["draft_id"]})).scalar()
            assert st4 == "rejeitado", st4
            print("TESTE 4 (rejeitar → status=rejeitado) PASS")

            print("\nTODAS AS PROVAS DE aprovacoes (endpoints) PASSARAM")
        finally:
            await db.execute(text("DELETE FROM agent_drafts WHERE tipo LIKE '__TESTE_APROVA%'"))
            await db.execute(text(
                "DELETE FROM communication_notifications WHERE extra_data->>'idempotency_key' LIKE '__TESTE_APROVA__:%'"))
            await db.execute(text("DELETE FROM audit_logs WHERE details->>'trace_id' = 'central.teste'"))
            await db.commit()
            rem = (await db.execute(text("SELECT count(*) FROM agent_drafts WHERE tipo LIKE '__TESTE_APROVA%'"))).scalar()
            assert rem == 0, f"remanescentes {rem}"
            print("LIMPEZA OK — 0 remanescentes")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
