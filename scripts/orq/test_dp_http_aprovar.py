"""Prova do elo que faltava: APROVAR **pelo HTTP**, como o botão da Pyetra faz.

O `test_dp_e2e_aprovar.py` chama `EXECUTORES[...]` direto — prova a lógica, mas pula tudo
que fica entre o dedo dela e o executor: rota montada, autenticação, e o binding do FastAPI
(`draft_id` vem na QUERY, o motivo vem no BODY). Um mismatch aí dá 422 e o botão morre em
produção sem que nenhum teste de função perceba.

Aqui o teste bate na URL **exata** que o builder emite para o botão:
    POST /api/v1/redesign/action/aprovar-rascunho?draft_id=<id>

Cobaia: `registrar_afastamento` (🟡, reversível). Ação 🔴 de dinheiro NUNCA é executada —
só se prova que o gate de OTP barra.

Identidade: `mcp-service` (conta de serviço), NÃO a da Pyetra — aprovar em nome dela deixaria
no log de auditoria um "Pyetra aprovou" que ela nunca fez.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import timedelta

sys.path.insert(0, "/app")

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

MARCA = f"BANCADA_HTTP_{uuid.uuid4().hex[:8]}"
BASE = "http://127.0.0.1:8080"
SERVICO = "01f4c6a0-743d-4702-8a1c-562ea57cfbe1"  # mcp-service@conectamais.pro

SQL_DRAFT = text(
    "INSERT INTO agent_drafts (id, tipo, modulo, titulo, resumo, payload, status, gate, "
    " requires_otp, roles_aprovador, criado_por_agente, created_at) "
    "VALUES (gen_random_uuid(), :tp, 'dp', :ti, 'bancada http', CAST(:pl AS jsonb), "
    "        'rascunho', :g, :otp, ARRAY['admin'], true, now()) RETURNING id::text"
)


async def main() -> None:
    from core.auth.jwt import create_access_token

    tok = create_access_token(SERVICO, expires_delta=timedelta(minutes=10))
    H = {"Authorization": f"Bearer {tok}"}

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
            did = (await db.execute(SQL_DRAFT, {
                "tp": "registrar_afastamento", "ti": f"{MARCA} afast", "g": "🟡", "otp": False,
                "pl": f'{{"employee_id":"{eid}","tipo":"licenca","inicio":"2099-04-01",'
                      f'"fim":"2099-04-05","motivo":"{MARCA}"}}'})).scalar()
            did_otp = (await db.execute(SQL_DRAFT, {
                "tp": "pagar_folha_lote", "ti": f"{MARCA} dinheiro", "g": "🔴", "otp": True,
                "pl": '{"valor": 1}'})).scalar()
            await db.commit()

        async with httpx.AsyncClient(timeout=60) as cli:
            # ── 1. sem token: a mesa não é pública ──────────────────────────
            r = await cli.post(f"{BASE}/api/v1/redesign/action/aprovar-rascunho",
                               params={"draft_id": did}, json={})
            assert r.status_code in (401, 403), f"sem token deveria barrar, veio {r.status_code}"
            print(f"HTTP-1 (sem token → {r.status_code}: mesa não é pública) PASS")

            # ── 2. nada existe antes do OK ─────────────────────────────────
            async with S() as db:
                n0 = (await db.execute(text(
                    "SELECT count(*) FROM sst_afastamentos WHERE CAST(employee_id AS TEXT)=:e"),
                    {"e": eid})).scalar()
            assert n0 == 0
            print("HTTP-2 (antes do clique: 0 afastamentos) PASS")

            # ── 3. o CLIQUE de verdade: URL exata do botão ──────────────────
            r = await cli.post(f"{BASE}/api/v1/redesign/action/aprovar-rascunho",
                               params={"draft_id": did}, json={}, headers=H)
            assert r.status_code == 200, \
                f"o botão Aprovar devolveu {r.status_code}: {r.text[:400]}"
            print(f"HTTP-3 (POST na URL do botão → 200: {str(r.json())[:120]}) PASS")

            # ── 4. o afastamento NASCEU pelo caminho oficial ────────────────
            async with S() as db:
                row = (await db.execute(text(
                    "SELECT status, data_inicio FROM sst_afastamentos "
                    "WHERE CAST(employee_id AS TEXT)=:e"), {"e": eid})).mappings().first()
                st = (await db.execute(text(
                    "SELECT status FROM agent_drafts WHERE id::text=:d"), {"d": did})).scalar()
            assert row is not None, "clicou Aprovar, HTTP 200, e NADA nasceu — botão decorativo"
            assert str(row["data_inicio"]) == "2099-04-01", row
            assert str(st).lower() not in ("rascunho", "pendente"), f"draft ficou {st!r}"
            print(f"HTTP-4 (nasceu de verdade: início={row['data_inicio']}, "
                  f"rascunho → {st!r}) PASS")

            # ── 5. 🔴 com OTP: AUTORIZA, mas não executa ───────────────────
            # Aqui 'aprovado' NÃO é "pago": para requires_otp o endpoint só autoriza e
            # devolve needsOtp, empurrando a execução para a tela de OTP existente. O que
            # não pode acontecer é o dinheiro sair deste clique — é isso que se prova.
            r = await cli.post(f"{BASE}/api/v1/redesign/action/aprovar-rascunho",
                               params={"draft_id": did_otp}, json={}, headers=H)
            body = r.json() if r.status_code == 200 else {}
            assert body.get("needsOtp") is True, \
                f"🔴 de dinheiro não pediu OTP: {r.status_code} {str(body)[:300]}"
            assert not body.get("id"), f"🔴 executou e devolveu entidade: {body}"

            from modules.ai.conversation.services.orquestrador.acoes.rascunho import EXECUTORES
            assert "pagar_folha_lote" not in EXECUTORES, \
                "pagar_folha_lote tem executor — haveria caminho de execução automática"

            # e o clique não é repetível: segunda tentativa bate no 409
            r2 = await cli.post(f"{BASE}/api/v1/redesign/action/aprovar-rascunho",
                                params={"draft_id": did_otp}, json={}, headers=H)
            assert r2.status_code == 409, f"reaprovar deveria dar 409, veio {r2.status_code}"
            print(f"HTTP-5 (🔴 dinheiro: autoriza + needsOtp, NÃO executa, "
                  f"reclique → {r2.status_code}) PASS")

            print("\nO BOTÃO DA MESA FUNCIONA PELO HTTP — auth, binding, executor e gate")
    finally:
        async with S() as db:
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
            rem = (await db.execute(text(
                "SELECT (SELECT count(*) FROM employees WHERE nome LIKE :m) + "
                "       (SELECT count(*) FROM agent_drafts WHERE titulo LIKE :m)"),
                {"m": f"{MARCA}%"})).scalar()
            assert rem == 0, f"resíduo: {rem}"
            print("LIMPEZA OK — 0 resíduo")
        await eng.dispose()


asyncio.run(main())
