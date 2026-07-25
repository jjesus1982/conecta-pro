"""Fase 5.4 — Primitiva "Proposta de Ação".

Uma única função `propor(...)` que TODAS as seis ações usam. Por construção:
  1. só grava PENDENTE na tabela nativa (via callback `inserir`; zero execução);
  2. audita append-only (agent_audit.registrar_proposta_acao);
  3. entrega no sino (5.3) ao aprovador por role (matriz RBAC server-side).
Fail-closed: sem roles_aprovador declarado, ou se a resolução de roles não
achar nenhum usuário ativo, NÃO grava nada (proposta órfã de aprovador é
recusada). Idempotência: 2 propostas com a mesma idempotency_key não duplicam
o pendente (dedup via communication_notifications.extra_data->>'idempotency_key').
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ai.conversation.services.garantia import agent_audit
from modules.notifications.proativo import entrega

#: Classes de risco declaradas por ação (espelha o tool_risk_manifest do conector).
GATES = frozenset({"🔴", "🟡", "🔵"})

#: Matriz RBAC de APROVADORES por natureza (server-side; NUNCA vem do LLM/achado).
#: 'admin' está sempre presente ⇒ nenhuma proposta fica órfã de aprovador.
ROLES_MONEY = ("admin",)                         # 🔴 dinheiro/eSocial → diretoria
ROLES_KIT_OP = ("admin", "gerente_operacional")  # kit / substituição
#: NOTA DE DIVERGÊNCIA brief×real: o brief propunha ROLES_COMERCIAL =
#: ("admin", "comercial"), porém o role 'comercial' NÃO existe na base
#: (roles reais ativos: admin, gerente_operacional, supervisor, lider,
#: funcionario, agente, operator, developer, staff, suporte). Um role
#: inexistente resolveria 0 usuários e seria ruído. Por decisão do plano,
#: proposta/cobrança aprovam via diretoria → ('admin',).
ROLES_COMERCIAL = ("admin",)                     # proposta / cobrança → diretoria


async def propor(
    db: AsyncSession,
    *,
    user,
    scope,
    dominio: str,
    gate: str,
    roles_aprovador: tuple[str, ...],
    idempotency_key: str,
    titulo: str,
    corpo: str,
    action_url: str,
    tool: str,
    args: dict[str, Any],
    entity_type: str,
    inserir: Callable[[AsyncSession], Awaitable[str]],
) -> dict[str, Any]:
    """Grava a proposta PENDENTE e a entrega ao aprovador. NUNCA executa.

    `inserir(db)` faz o ÚNICO INSERT na tabela nativa e devolve o entity_id do
    PENDENTE criado. Nenhum caminho deste código chama execução (pagar/transmitir/
    enviar) — a execução real permanece na tela humana existente.
    """
    if gate not in GATES:
        return {"erro": f"gate inválido {gate!r} — recusado (fail-closed)"}
    # fail-closed 1: sem roles_aprovador declarado, nada é registrado.
    if not roles_aprovador:
        return {"erro": "sem aprovador declarado — proposta recusada (fail-closed)"}

    # Idempotência: um pendente vivo com a MESMA idempotency_key não é duplicado.
    ja = (await db.execute(text(
        "SELECT reference_id FROM communication_notifications "
        "WHERE extra_data->>'idempotency_key' = :k "
        "  AND coalesce(is_active, true) = true LIMIT 1"),
        {"k": idempotency_key})).scalar()
    if ja:
        return {"status": "pendente", "duplicado": True, "dominio": dominio,
                "entity_id": ja, "gate": gate,
                "aviso": "Proposta idêntica já está aguardando aprovação."}

    # fail-closed 2: aprovador precisa existir de fato (proposta órfã é recusada).
    aprovadores = await entrega.resolver_usuarios_por_roles(db, roles_aprovador)
    if not aprovadores:
        return {"erro": "nenhum aprovador ativo para este domínio — proposta recusada (fail-closed)"}

    # ÚNICO ponto de escrita na tabela nativa: só INSERT de PENDENTE.
    entity_id = await inserir(db)

    # Auditoria append-only (quem propôs ≠ quem aprova — os 3 papéis).
    await agent_audit.registrar_proposta_acao(
        db, origem=getattr(scope, "tier", "consultor_escopado"),
        tool=tool, args=args, dominio=dominio, gate=gate,
        entity_type=entity_type, entity_id=str(entity_id),
        aprovadores=aprovadores, proposto_por=str(getattr(user, "id", "")),
        trace_id=f"5.4.{dominio}",
    )

    # Entrega no sino ao aprovador por ROLE (RBAC server-side).
    await entrega.enviar_individual(
        db, user_ids=aprovadores, title=titulo, body=corpo,
        familia=dominio, severidade=("critico" if gate == "🔴" else "aviso"),
        correlation_id=idempotency_key, action_url=action_url,
        reference_type="proposta_acao", reference_id=str(entity_id),
        idempotency_key=idempotency_key,
    )
    await db.commit()
    return {"status": "pendente", "dominio": dominio, "entity_id": str(entity_id),
            "gate": gate, "aprovadores": aprovadores,
            "aviso": f"Proposta ENVIADA para aprovação ({dominio}). "
                     f"NADA foi executado — {'exige OTP humano' if gate == '🔴' else 'aguarda aprovação humana'}."}


if __name__ == "__main__":
    import asyncio
    import os
    import uuid

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    class _U:  # usuário-stub (só precisa de .id)
        id = "00000000-0000-0000-0000-0000000000ff"

    class _S:  # scope-stub
        tier = "gestor"

    KEY = f"__TESTE_5.4__:base:{uuid.uuid4()}"

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        notif_ids: list[str] = []
        audit_ids: list[str] = []
        inseriu = {"n": 0}
        # reference_id em communication_notifications é UUID no banco real; as
        # tabelas nativas das ações usam PK UUID, então o stub devolve um UUID.
        ENTITY = str(uuid.uuid4())

        async def _fake_insert(db) -> str:
            inseriu["n"] += 1
            return ENTITY

        async def _boom_insert(db) -> str:  # não deve ser chamado nos fail-closed
            raise AssertionError("inserir NÃO pode ser chamado quando fail-closed")

        async with Session() as db:
            try:
                # 1) fail-closed: sem roles_aprovador → nada grava, inserir não roda
                r = await propor(
                    db, user=_U(), scope=_S(), dominio="teste", gate="🟡",
                    roles_aprovador=(), idempotency_key=KEY + ":a",
                    titulo="t", corpo="c", action_url="/x", tool="t", args={},
                    entity_type="teste", inserir=_boom_insert)
                assert "erro" in r, r
                print("TESTE 1 (fail-closed sem aprovador) PASS")

                # 2) gate inválido → recusa
                r = await propor(
                    db, user=_U(), scope=_S(), dominio="teste", gate="X",
                    roles_aprovador=ROLES_MONEY, idempotency_key=KEY + ":b",
                    titulo="t", corpo="c", action_url="/x", tool="t", args={},
                    entity_type="teste", inserir=_boom_insert)
                assert "erro" in r, r
                print("TESTE 2 (gate inválido) PASS")

                # 3) caminho feliz → cria pendente, audita, entrega no sino
                r = await propor(
                    db, user=_U(), scope=_S(), dominio="teste", gate="🟡",
                    roles_aprovador=ROLES_MONEY, idempotency_key=KEY,
                    titulo="[TESTE 5.4] proposta", corpo="corpo teste",
                    action_url="/x", tool="propor_teste", args={"k": 1},
                    entity_type="teste", inserir=_fake_insert)
                assert r["status"] == "pendente" and not r.get("duplicado"), r
                assert inseriu["n"] == 1, inseriu
                assert r["aprovadores"], r
                print("TESTE 3 (caminho feliz cria pendente) PASS")

                # 4) idempotência: mesma key → duplicado, inserir NÃO roda de novo
                r2 = await propor(
                    db, user=_U(), scope=_S(), dominio="teste", gate="🟡",
                    roles_aprovador=ROLES_MONEY, idempotency_key=KEY,
                    titulo="[TESTE 5.4] proposta", corpo="corpo teste",
                    action_url="/x", tool="propor_teste", args={"k": 1},
                    entity_type="teste", inserir=_fake_insert)
                assert r2.get("duplicado") is True, r2
                assert inseriu["n"] == 1, "inserir rodou de novo (quebrou idempotência)"
                print("TESTE 4 (idempotência) PASS")

                # 5) 3 papéis: o propositor NUNCA é registrado como aprovador
                assert str(_U.id) not in (r.get("aprovadores") or []), \
                    "propositor não pode constar como aprovador (3 papéis)"
                print("TESTE 5 (propositor != aprovador) PASS")

                # coleta ids p/ limpeza
                notif_ids = [x for x in (await db.execute(text(
                    "SELECT id::text FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' = :k"), {"k": KEY})).scalars().all()]
                audit_ids = [x for x in (await db.execute(text(
                    "SELECT id::text FROM audit_logs "
                    "WHERE details->>'trace_id' = '5.4.teste'"))).scalars().all()]
                print("TODOS OS TESTES DE base.py PASSARAM")
            finally:
                if notif_ids:
                    await db.execute(text("DELETE FROM communication_notifications WHERE id = ANY(:i)"),
                                     {"i": notif_ids})
                if audit_ids:
                    await db.execute(text("DELETE FROM audit_logs WHERE id = ANY(:i)"),
                                     {"i": audit_ids})
                await db.commit()
                rem = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE :k"),
                    {"k": "__TESTE_5.4__:base:%"})).scalar()
                assert rem == 0, f"remanescentes={rem}"
        await eng.dispose()

    asyncio.run(main())
