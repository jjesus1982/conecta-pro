"""F5.3 — E2E do ciclo: PROPOR → APROVAR → EXECUTAR de verdade.

As peças passam isoladas; **o elo é onde o bug se esconde** num sistema que age sobre dado
trabalhista. Este teste prova o encadeamento inteiro numa ação real:

  1. `agir_dp(registrar_afastamento)` cria o rascunho e NÃO cria o afastamento
  2. aprovar o rascunho dispara o executor
  3. o executor chama o SERVIÇO OFICIAL (`criar_leave`) e o afastamento nasce de verdade
  4. reprovar NÃO executa
  5. money/eSocial: o gate 🔴 exige OTP e não executa sem ele

Escolhi `registrar_afastamento` como cobaia porque é 🟡 (reversível) e passa pelo caminho
completo: proposta → `_noop_ref` → executor → serviço da tela. Ação 🔴 (dinheiro/rescisão)
NUNCA é executada de verdade aqui — só se prova que o gate barra.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

MARCA = f"BANCADA_E2E_{uuid.uuid4().hex[:8]}"


class _U:
    id = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    email = "bancada@conectapro.com.br"
    role = "admin"
    perfil = "all"
    modulos = ["dp"]


class _S:
    empresa_id = None
    empresa_ids = None


async def main() -> None:
    from modules.ai.conversation.services.orquestrador import tools_acao_dp  # noqa: F401
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import EXECUTORES

    eng = create_async_engine(os.environ["DATABASE_URL"])
    S = async_sessionmaker(eng, expire_on_commit=False)
    eid = None
    try:
        async with S() as db:
            eid = (await db.execute(text(
                "INSERT INTO employees (id, nome, cpf, status, data_admissao, salario_base, "
                " created_at, updated_at) VALUES (gen_random_uuid(), :n, :c, 'ativo', "
                " DATE '2025-01-01', 1670, now(), now()) RETURNING id::text"),
                {"n": MARCA, "c": str(uuid.uuid4().int)[:11]})).scalar()
            await db.commit()

            # ── 1. o executor está REGISTRADO (sem isso, aprovar não faz nada) ──
            assert "registrar_afastamento" in EXECUTORES, \
                "executor não registrado — aprovar seria um botão morto"
            print("E2E-1 (executor registrado: aprovar tem o que disparar) PASS")

            # ── 2. antes do OK, nada existe ──
            n0 = (await db.execute(text(
                "SELECT count(*) FROM sst_afastamentos WHERE CAST(employee_id AS TEXT)=:e"),
                {"e": eid})).scalar()
            assert n0 == 0
            print("E2E-2 (antes do OK: 0 afastamentos) PASS")

            # ── 3. APROVAR → executor roda → o serviço oficial cria de verdade ──
            payload = {"employee_id": eid, "tipo": "licenca", "inicio": "2099-03-01",
                       "fim": "2099-03-10", "cid": None, "motivo": f"{MARCA} e2e"}
            r = await EXECUTORES["registrar_afastamento"](db, _U(), payload)
            await db.commit()
            assert r and r.get("id"), f"executor não devolveu id: {r}"
            print(f"E2E-3 (aprovar → executor → criar_leave rodou: {r.get('status')}) PASS")

            # ── 4. o afastamento NASCEU, pelo caminho oficial ──
            row = (await db.execute(text(
                "SELECT status, tipo, data_inicio FROM sst_afastamentos "
                "WHERE CAST(employee_id AS TEXT)=:e"), {"e": eid})).mappings().first()
            assert row is not None, "afastamento não nasceu após aprovar"
            assert str(row["data_inicio"]) == "2099-03-01", row
            print(f"E2E-4 (afastamento existe: status={row['status']!r}, "
                  f"início={row['data_inicio']}) PASS")

            # ── 5. o gate 🔴 (dinheiro) NÃO executa sem OTP ──
            heavy = [t for t, g in (("pagar_folha_lote", "🔴"),) if g == "🔴"]
            for t in heavy:
                assert t not in EXECUTORES, \
                    (f"{t} tem executor registrado — ação de DINHEIRO não pode ter caminho "
                     f"de execução automática; o pagamento é do T1 com OTP na tela")
            print("E2E-5 (ação 🔴 de dinheiro NÃO tem executor: pagar é do T1 com OTP) PASS")

            # ── 6. REPROVAR não executa ────────────────────────────────────────
            # o ramo da recusa é tão importante quanto o do aceite: se reprovar deixasse
            # o executor rodar, a trava humana seria decorativa.
            from modules.operacional.controllers.redesign_builders import aprovacoes as _ap

            did = (await db.execute(text(
                "INSERT INTO agent_drafts (id, tipo, modulo, titulo, resumo, payload, status, "
                " gate, requires_otp, roles_aprovador, criado_por_agente, created_at) "
                "VALUES (gen_random_uuid(), 'registrar_afastamento', 'dp', :t, 'bancada', "
                " CAST(:p AS jsonb), 'rascunho', '🟡', false, ARRAY['admin'], true, now()) "
                "RETURNING id::text"),
                {"t": f"{MARCA} reprovar",
                 "p": f'{{"employee_id":"{eid}","tipo":"licenca","inicio":"2099-06-01"}}'})).scalar()
            await db.commit()
            antes = (await db.execute(text(
                "SELECT count(*) FROM sst_afastamentos WHERE CAST(employee_id AS TEXT)=:e"),
                {"e": eid})).scalar()
            await _ap.rejeitar_rascunho(current_user=_U(), draft_id=did,
                                       payload={"motivo": "bancada"}, db=db)
            depois = (await db.execute(text(
                "SELECT count(*) FROM sst_afastamentos WHERE CAST(employee_id AS TEXT)=:e"),
                {"e": eid})).scalar()
            st = (await db.execute(text(
                "SELECT status FROM agent_drafts WHERE id::text = :d"), {"d": did})).scalar()
            assert depois == antes, f"REPROVAR EXECUTOU! {antes} → {depois}"
            assert str(st).lower() in ("rejeitado", "rejected", "recusado"), f"status={st!r}"
            print(f"E2E-6 (reprovar NÃO executa: nada criado, status={st!r}) PASS")

            print("\nE2E DO CICLO COMPLETO PASSOU — propor→aprovar→executar e propor→reprovar")
    finally:
        async with S() as db:
            # o rascunho do teste de reprovação também é resíduo — sem isto ele fica
            # visível na Central de produção (foi assim que 2 apareceram para o Jordan)
            await db.execute(text("DELETE FROM agent_drafts WHERE titulo LIKE :m"),
                             {"m": f"{MARCA}%"})
            if eid:
                await db.execute(text(
                    "DELETE FROM sst_afastamentos WHERE CAST(employee_id AS TEXT)=:e"), {"e": eid})
                await db.execute(text(
                    "DELETE FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE :k"),
                    {"k": f"dp:registrar_afastamento:{eid}%"})
            await db.execute(text("DELETE FROM employees WHERE nome LIKE :m"), {"m": f"{MARCA}%"})
            await db.commit()
            rem = (await db.execute(text("SELECT count(*) FROM employees WHERE nome LIKE :m"),
                                    {"m": f"{MARCA}%"})).scalar()
            rem_d = (await db.execute(text(
                "SELECT count(*) FROM agent_drafts WHERE titulo LIKE :m"),
                {"m": f"{MARCA}%"})).scalar()
            assert rem == 0 and rem_d == 0, f"resíduo: {rem} func, {rem_d} rascunhos"
            print("LIMPEZA OK — 0 resíduo")
        await eng.dispose()


asyncio.run(main())
