"""Fase 5.4 — Primitiva "Proposta de Ação".

Uma única função `propor(...)` que TODAS as seis ações usam. Por construção:
  1. só grava PENDENTE na tabela nativa (via callback `inserir`; zero execução);
  2. audita append-only (agent_audit.registrar_proposta_acao);
  3. entrega no sino (5.3) ao aprovador por role (matriz RBAC server-side).
Fail-closed: sem roles_aprovador declarado, ou se a resolução de roles não
achar nenhum aprovador ativo DISTINTO do propositor, NÃO grava nada (proposta
órfã de aprovador é recusada). Os 3 papéis nunca coincidem: o PROPOSITOR é
EXCLUÍDO do conjunto de aprovadores — quem propõe não aprova a si mesmo (num
tenant com 1 só admin propondo, isso zera os aprovadores → fail-closed, que é o
comportamento correto de segregação). Idempotência ATÔMICA: o par (destinatário,
idempotency_key) é único no banco (índice parcial `uq_notif_idempotency_user`) +
`ON CONFLICT DO NOTHING` no sino → 2 execuções concorrentes = N notificações (não
2N). Atomicidade: um ÚNICO commit no fim (inserir+audit+sino); qualquer falha →
rollback de tudo (nada durável sem entrega).
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

    # fail-closed 2: aprovador precisa existir de fato E ser DISTINTO do propositor
    # (3 papéis nunca no mesmo ator — quem propõe NÃO aprova a si mesmo). Num tenant
    # com 1 só admin propondo, sobra 0 → proposta órfã é recusada (segregação).
    proponente_id = str(getattr(user, "id", None))
    aprovadores = [
        a for a in await entrega.resolver_usuarios_por_roles(db, roles_aprovador)
        if str(a) != proponente_id
    ]
    if not aprovadores:
        return {"erro": "nenhum aprovador ativo distinto do propositor — "
                        "proposta recusada (fail-closed, 3 papéis)"}

    try:
        # ÚNICO ponto de escrita na tabela nativa: só INSERT de PENDENTE.
        entity_id = await inserir(db)

        # Auditoria append-only (quem propôs ≠ quem aprova — os 3 papéis).
        # NÃO commita internamente (atomicidade — o commit único é no fim).
        await agent_audit.registrar_proposta_acao(
            db, origem=getattr(scope, "tier", "consultor_escopado"),
            tool=tool, args=args, dominio=dominio, gate=gate,
            entity_type=entity_type, entity_id=str(entity_id),
            aprovadores=aprovadores, proposto_por=proponente_id,
            trace_id=f"5.4.{dominio}",
        )

        # Entrega no sino ao aprovador por ROLE (RBAC server-side). ON CONFLICT
        # DO NOTHING no INSERT torna o par (destinatário, key) idempotente atômico.
        await entrega.enviar_individual(
            db, user_ids=aprovadores, title=titulo, body=corpo,
            familia=dominio, severidade=("critico" if gate == "🔴" else "aviso"),
            correlation_id=idempotency_key, action_url=action_url,
            reference_type="proposta_acao", reference_id=str(entity_id),
            idempotency_key=idempotency_key,
        )
        # COMMIT ÚNICO: inserir + audit + sino viram duráveis juntos ou nada.
        await db.commit()
    except Exception:
        # Qualquer falha (inclusive no sino) reverte pendente+audit → nada durável.
        await db.rollback()
        raise
    return {"status": "pendente", "dominio": dominio, "entity_id": str(entity_id),
            "gate": gate, "aprovadores": aprovadores,
            "aviso": f"Proposta ENVIADA para aprovação ({dominio}). "
                     f"NADA foi executado — {'exige OTP humano' if gate == '🔴' else 'aguarda aprovação humana'}."}


if __name__ == "__main__":
    import asyncio
    import os
    import uuid

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    class _U:  # usuário-stub (só precisa de .id); id configurável p/ testes 5/6/8
        def __init__(self, uid="00000000-0000-0000-0000-0000000000ff"):
            self.id = uid

    class _S:  # scope-stub
        tier = "gestor"

    PREFIX = "__TESTE_5.4__:base:"
    KEY = f"{PREFIX}{uuid.uuid4()}"          # base (testes 3/4, mesma key)
    KEY5 = f"{PREFIX}{uuid.uuid4()}:t5"      # teste 5 (propositor admin real)
    KEY7 = f"{PREFIX}{uuid.uuid4()}:t7"      # teste 7 (concorrência)
    KEY8 = f"{PREFIX}{uuid.uuid4()}:t8"      # teste 8 (falha no sino)
    IDX = "uq_notif_idempotency_user"

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        inseriu = {"n": 0}
        ENTITY = str(uuid.uuid4())

        async def _fake_insert(db) -> str:
            inseriu["n"] += 1
            return ENTITY

        async def _boom_insert(db) -> str:  # não deve ser chamado nos fail-closed
            raise AssertionError("inserir NÃO pode ser chamado quando fail-closed")

        # Garante o índice único parcial (mesma DDL da migration fase54_notif_idem).
        # Se o teste o criou, ele é removido no finally (respeita deploy GATED).
        idx_criado_pelo_teste = False
        async with Session() as db0:
            existe = (await db0.execute(text(
                "SELECT 1 FROM pg_indexes WHERE indexname = :n"), {"n": IDX})).scalar()
            if not existe:
                await db0.execute(text(
                    f"CREATE UNIQUE INDEX {IDX} ON communication_notifications "
                    f"(user_id, (extra_data->>'idempotency_key')) "
                    f"WHERE (extra_data->>'idempotency_key') IS NOT NULL"))
                await db0.commit()
                idx_criado_pelo_teste = True

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
                #    (propositor = uuid fake, NÃO admin → aprovadores = todos admins)
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

                # 4) idempotência sequencial: mesma key → duplicado, inserir NÃO re-roda
                r2 = await propor(
                    db, user=_U(), scope=_S(), dominio="teste", gate="🟡",
                    roles_aprovador=ROLES_MONEY, idempotency_key=KEY,
                    titulo="[TESTE 5.4] proposta", corpo="corpo teste",
                    action_url="/x", tool="propor_teste", args={"k": 1},
                    entity_type="teste", inserir=_fake_insert)
                assert r2.get("duplicado") is True, r2
                assert inseriu["n"] == 1, "inserir rodou de novo (quebrou idempotência)"
                print("TESTE 4 (idempotência sequencial) PASS")

                # 5-corrigida) 3 papéis: um admin REAL propondo é EXCLUÍDO do conjunto
                #    de aprovadores (não aprova a si mesmo).
                admins = await entrega.resolver_usuarios_por_roles(db, ROLES_MONEY)
                assert admins, "esperado >=1 admin ativo no banco"
                proponente_admin = admins[0]
                r5 = await propor(
                    db, user=_U(proponente_admin), scope=_S(), dominio="teste",
                    gate="🟡", roles_aprovador=ROLES_MONEY, idempotency_key=KEY5,
                    titulo="[TESTE 5.4] t5", corpo="c", action_url="/x",
                    tool="propor_t5", args={}, entity_type="teste",
                    inserir=_fake_insert)
                if len(admins) >= 2:
                    assert r5.get("status") == "pendente", r5
                    aps = r5.get("aprovadores") or []
                    assert str(proponente_admin) not in aps, \
                        f"propositor admin REAL não pode aprovar a si mesmo: {aps}"
                    assert set(aps) == set(admins) - {proponente_admin}, (aps, admins)
                    print(f"TESTE 5 (propositor admin real EXCLUÍDO; "
                          f"{len(admins)} admins → {len(aps)} aprovadores) PASS")
                else:
                    # tenant com 1 só admin: propositor==único admin → fail-closed
                    assert "erro" in r5, r5
                    print("TESTE 5 (1 admin: propositor==único → fail-closed) PASS")

                # 6) fail-closed quando SÓ o propositor seria aprovador (sobra 0).
                #    Monkeypatch resolver → devolve apenas o propositor.
                orig_resolver = entrega.resolver_usuarios_por_roles
                so_ele = "11111111-1111-1111-1111-1111111111aa"

                async def _resolver_so_propositor(db, roles):
                    return [so_ele]

                entrega.resolver_usuarios_por_roles = _resolver_so_propositor
                try:
                    r6 = await propor(
                        db, user=_U(so_ele), scope=_S(), dominio="teste", gate="🔴",
                        roles_aprovador=ROLES_MONEY, idempotency_key=KEY + ":t6",
                        titulo="t", corpo="c", action_url="/x", tool="propor_t6",
                        args={}, entity_type="teste", inserir=_boom_insert)
                finally:
                    entrega.resolver_usuarios_por_roles = orig_resolver
                assert "erro" in r6 and "fail-closed" in r6["erro"], r6
                print("TESTE 6 (fail-closed: só o propositor seria aprovador) PASS")

                # commit dos testes 1-6 (propor já commitou os que gravaram)
                await db.commit()

                # 7) idempotência sob CONCORRÊNCIA (2 conexões) = N (não 2N).
                async def _uma_conc():
                    async with Session() as s:
                        return await propor(
                            s, user=_U(), scope=_S(), dominio="teste", gate="🟡",
                            roles_aprovador=ROLES_MONEY, idempotency_key=KEY7,
                            titulo="[TESTE 5.4] conc", corpo="c", action_url="/x",
                            tool="propor_conc", args={}, entity_type="teste",
                            inserir=lambda _s: _async_uuid())

                async def _async_uuid():
                    return str(uuid.uuid4())

                await asyncio.gather(_uma_conc(), _uma_conc())
                n_admins = len(admins)
                got = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' = :k"), {"k": KEY7})).scalar()
                assert got == n_admins, \
                    f"concorrência: esperado N={n_admins} notifs, veio {got} (esperado NÃO 2N)"
                print(f"TESTE 7 (concorrência: 2 execuções = N={got}, não 2N) PASS")

                # 8) se enviar_individual FALHA → nada durável (pendente+audit revertidos).
                orig_enviar = entrega.enviar_individual

                async def _enviar_boom(*a, **k):
                    raise RuntimeError("falha simulada no sino (teste 8)")

                entrega.enviar_individual = _enviar_boom
                levantou = False
                try:
                    await propor(
                        db, user=_U(), scope=_S(), dominio="teste", gate="🟡",
                        roles_aprovador=ROLES_MONEY, idempotency_key=KEY8,
                        titulo="t", corpo="c", action_url="/x",
                        tool="propor_t8_boom", args={}, entity_type="teste",
                        inserir=_fake_insert)
                except RuntimeError:
                    levantou = True
                finally:
                    entrega.enviar_individual = orig_enviar
                assert levantou, "propor deveria propagar a falha do sino"
                # prova em conexão NOVA: o INSERT append-only do audit foi revertido
                async with Session() as chk:
                    a8 = (await chk.execute(text(
                        "SELECT count(*) FROM audit_logs "
                        "WHERE details->>'tool' = 'propor_t8_boom'"))).scalar()
                    n8 = (await chk.execute(text(
                        "SELECT count(*) FROM communication_notifications "
                        "WHERE extra_data->>'idempotency_key' = :k"), {"k": KEY8})).scalar()
                assert a8 == 0, f"audit NÃO foi revertido (durável sem entrega): {a8}"
                assert n8 == 0, f"notificação durável apesar da falha: {n8}"
                print("TESTE 8 (falha no sino → rollback total, nada durável) PASS")

                print("\nTODAS AS 8 PROVAS DE base.py PASSARAM")
            finally:
                notif_ids = [x for x in (await db.execute(text(
                    "SELECT id::text FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE :k"),
                    {"k": PREFIX + "%"})).scalars().all()]
                audit_ids = [x for x in (await db.execute(text(
                    "SELECT id::text FROM audit_logs "
                    "WHERE details->>'trace_id' = '5.4.teste'"))).scalars().all()]
                if notif_ids:
                    await db.execute(text("DELETE FROM communication_notifications WHERE id = ANY(:i)"),
                                     {"i": notif_ids})
                if audit_ids:
                    await db.execute(text("DELETE FROM audit_logs WHERE id = ANY(:i)"),
                                     {"i": audit_ids})
                if idx_criado_pelo_teste:
                    await db.execute(text(f"DROP INDEX IF EXISTS {IDX}"))
                await db.commit()
                rem_n = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE :k"),
                    {"k": PREFIX + "%"})).scalar()
                rem_a = (await db.execute(text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE details->>'trace_id' = '5.4.teste'"))).scalar()
                assert rem_n == 0 and rem_a == 0, f"remanescentes notif={rem_n} audit={rem_a}"
                print(f"LIMPEZA OK — 0 remanescentes (notif/audit); "
                      f"índice {'removido (criado pelo teste)' if idx_criado_pelo_teste else 'preexistente, mantido'}")
        await eng.dispose()

    asyncio.run(main())
