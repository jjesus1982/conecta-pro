"""Provas de F1.2 (afastamento) e F3.1 (fechar ponto / justificar ponto).

Invariante único que atravessa todas: **PROPÕE, nunca executa**. Cada ação leva um
monkeypatch-boom no serviço oficial correspondente — se a criação do rascunho chamar o
serviço, o teste explode. E cada uma recusa o que não é derivável, em vez de chutar.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

MARCA = f"BANCADA_ROT_{uuid.uuid4().hex[:8]}"


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
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import (
        montar_acao_dispatchers,
    )
    from modules.ai.conversation.services.orquestrador.tool_registry import get_tool

    montar_acao_dispatchers()
    tool = get_tool("agir_dp")

    async def agir(db, acao, dados):
        return await tool.handler(db, _U(), _S(), acao=acao, dados=dados)

    eng = create_async_engine(os.environ["DATABASE_URL"])
    S = async_sessionmaker(eng, expire_on_commit=False)
    eid = None
    try:
        async with S() as db:
            eid = (await db.execute(text(
                "INSERT INTO employees (id, nome, cpf, status, data_admissao, salario_base, "
                " created_at, updated_at) "
                "VALUES (gen_random_uuid(), :n, :c, 'ativo', DATE '2025-01-01', 1670, now(), now()) "
                "RETURNING id::text"),
                {"n": MARCA, "c": str(uuid.uuid4().int)[:11]})).scalar()
            await db.commit()

            # ── F1.2 afastamento ──────────────────────────────────────────────
            from modules.people_management.hr.controllers import leave_controller as _lc
            _o_leave = _lc.criar_leave

            async def _boom_leave(*_a, **_k):
                raise AssertionError("EXECUTOU! criar_leave chamado na criação do rascunho")

            _lc.criar_leave = _boom_leave
            try:
                r = await agir(db, "registrar_afastamento", {"employee_id": eid})
                assert "erro" in r and "inicio" in str(r), f"deveria exigir início: {r}"
                print("TESTE afast-1 (sem data de início → recusa, não inventa) PASS")

                r = await agir(db, "registrar_afastamento",
                               {"employee_id": eid, "inicio": "2099-03-01"})
                assert "erro" not in r, f"proposta falhou: {r}"
                corpo = (await db.execute(text(
                    "SELECT coalesce(body,'') FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' = :k LIMIT 1"),
                    {"k": f"dp:registrar_afastamento:{eid}:2099-03-01"})).scalar() or ""
                assert "CONFIRME" in corpo and "ESTABILIDADE" in corpo, \
                    f"deveria avisar do risco de estabilidade: {corpo[:250]}"
                print("TESTE afast-2 (propõe sem executar + avisa da estabilidade art.118) PASS")
            finally:
                _lc.criar_leave = _o_leave

            n = (await db.execute(text(
                "SELECT count(*) FROM sst_afastamentos WHERE CAST(employee_id AS TEXT) = :e"),
                {"e": eid})).scalar()
            assert n == 0, f"afastamento criado sem aprovação! ({n})"
            print("TESTE afast-3 (nenhum sst_afastamentos criado sem o OK) PASS")

            # ── F3.1 fechar ponto ─────────────────────────────────────────────
            from modules.people_management.ponto.services import punch_service as _ps
            _o_fechar = _ps.PunchService.fechar_mes
            _o_rev = _ps.PunchService.revisar_justificativa

            async def _boom_p(*_a, **_k):
                raise AssertionError("EXECUTOU! serviço de ponto chamado na criação")

            _ps.PunchService.fechar_mes = _boom_p
            _ps.PunchService.revisar_justificativa = _boom_p
            try:
                r = await agir(db, "fechar_ponto", {"employee_id": eid, "mes": 13, "ano": 2099})
                assert "erro" in r, f"mês 13 deveria recusar: {r}"
                print("TESTE ponto-1 (competência inválida → recusa) PASS")

                r = await agir(db, "fechar_ponto", {"employee_id": eid, "mes": 3, "ano": 2099})
                assert "erro" not in r, f"proposta falhou: {r}"
                print("TESTE ponto-2 (propõe fechar sem executar) PASS")

                # ── justificativa: decisão é humana ──
                r = await agir(db, "justificar_ponto",
                               {"justification_id": str(uuid.uuid4())})
                assert "erro" in r and "decisao" in str(r), \
                    f"sem decisão deveria recusar: {r}"
                print("TESTE just-1 (sem decisão aprovar/rejeitar → recusa, não decide por você) PASS")

                r = await agir(db, "justificar_ponto",
                               {"justification_id": str(uuid.uuid4()), "decisao": "aprovar"})
                assert "erro" in r and "não encontrada" in str(r), \
                    f"justificativa inexistente deveria recusar: {r}"
                print("TESTE just-2 (justificativa inexistente → recusa) PASS")
            finally:
                _ps.PunchService.fechar_mes = _o_fechar
                _ps.PunchService.revisar_justificativa = _o_rev

            print("\nTODAS AS PROVAS DAS ROTINEIRAS PASSARAM")
    finally:
        async with S() as db:
            if eid:
                for k in (f"dp:registrar_afastamento:{eid}:2099-03-01",
                          f"dp:fechar_ponto:{eid}:2099-03"):
                    await db.execute(text(
                        "DELETE FROM communication_notifications "
                        "WHERE extra_data->>'idempotency_key' = :k"), {"k": k})
                await db.execute(text(
                    "DELETE FROM sst_afastamentos WHERE CAST(employee_id AS TEXT) = :e"), {"e": eid})
                await db.execute(text(
                    "DELETE FROM gp_monthly_closings WHERE CAST(employee_id AS TEXT) = :e"), {"e": eid})
            await db.execute(text("DELETE FROM employees WHERE nome LIKE :m"), {"m": f"{MARCA}%"})
            await db.commit()
            rem = (await db.execute(text("SELECT count(*) FROM employees WHERE nome LIKE :m"),
                                    {"m": f"{MARCA}%"})).scalar()
            assert rem == 0, f"resíduo: {rem}"
            print("LIMPEZA OK — 0 resíduo")
        await eng.dispose()


asyncio.run(main())
