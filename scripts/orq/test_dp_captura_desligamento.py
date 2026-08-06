"""Prova de `agir_dp(registrar_desligamento)` — a CAPTURA que fecha o buraco do Keyson.

O que precisa ser verdade (o teste falha se deixar de ser):
  a) PROPÕE sem CONCLUIR — o processo nasce INERTE (status 'initiated', o mesmo padrão de
     `solicitar_ferias` nascer 'SUBMITTED'). O que NUNCA pode disparar sem o OK humano é a
     CONCLUSÃO: verbas calculadas, rescisão completada, eSocial S-2299. Provado por
     monkeypatch-boom em complete_termination/calculate_termination.
  b) NÃO INVENTA — sem data de desligamento no cadastro, recusa (não fabrica desligamento).
  c) Idempotente — 2 chamadas, 1 proposta.
  d) Honestidade do não-derivável — sem `tipo`, o corpo PEDE confirmação em vez de chutar
     (o tipo da rescisão é decisão do DP, não do agente).
  e) 0 resíduo — cleanup no finally + sentinela.
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
    # o dispatcher é montado a partir do registry (mesmo caminho do self-check do módulo)
    from modules.ai.conversation.services.orquestrador import tools_acao_dp  # noqa: F401  (registra)
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import montar_acao_dispatchers
    from modules.ai.conversation.services.orquestrador.tool_registry import get_tool

    montar_acao_dispatchers()
    _agir_tool = get_tool("agir_dp")

    async def _agir(db, user, scope, *, dominio=None, acao=None, dados=None):  # noqa: ARG001
        return await _agir_tool.handler(db, user, scope, acao=acao, dados=dados or {})

    eng = create_async_engine(os.environ["DATABASE_URL"])
    S = async_sessionmaker(eng, expire_on_commit=False)
    marca = f"BANCADA_CAPT_{uuid.uuid4().hex[:8]}"
    eid_com = eid_sem = None
    try:
        async with S() as db:
            for nome, dt in ((f"{marca}_COM", date(2026, 7, 1)), (f"{marca}_SEM", None)):
                r = (await db.execute(text(
                    "INSERT INTO employees (id, nome, cpf, status, data_admissao, "
                    " data_desligamento, salario_base, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :n, :c, 'inativo', DATE '2025-01-01', "
                    "        :d, 1670, now(), now()) RETURNING id::text"),
                    {"n": nome, "c": str(uuid.uuid4().int)[:11], "d": dt})).scalar()
                if dt:
                    eid_com = r
                else:
                    eid_sem = r
            await db.commit()

            from modules.people_management.hr.services import termination_service as _ts

            # boom nas EXECUÇÕES irreversíveis — nascer inerte é ok, concluir não é
            _origs = {}
            for _m in ("complete_termination", "calculate_termination", "calculate_verbas"):
                if hasattr(_ts.TerminationService, _m):
                    _origs[_m] = getattr(_ts.TerminationService, _m)

            def _mk(nome):
                async def _boom(*_a, **_k):
                    raise AssertionError(f"EXECUTOU! {nome} disparou sem aprovação humana")
                return _boom

            for _m in _origs:
                setattr(_ts.TerminationService, _m, _mk(_m))
            try:
                r1 = await _agir(db, _U(), _S(), dominio="dp", acao="registrar_desligamento",
                                 dados={"employee_id": eid_com})
                assert "erro" not in r1, f"proposta falhou: {r1}"
                print("TESTE a (PROPÕE sem executar: serviço oficial nunca chamado) PASS")

                # o corpo vive na notificação entregue ao aprovador, não no retorno
                corpo = (await db.execute(text(
                    "SELECT coalesce(body,'') FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' = :k LIMIT 1"),
                    {"k": f"dp:registrar_desligamento:{eid_com}"})).scalar() or ""
                assert "CONFIRME" in corpo and "tipo da rescis" in corpo, \
                    f"deveria PEDIR confirmação do tipo, não chutar: {corpo[:300]}"
                print("TESTE d (não-derivável: pede confirmação do tipo, não chuta) PASS")

                await _agir(db, _U(), _S(), dominio="dp", acao="registrar_desligamento",
                            dados={"employee_id": eid_com})
                # a idempotência se prova na ENTIDADE, não na notificação: `propor` cria
                # uma notificação POR APROVADOR (5 diretores = 5 linhas, correto).
                n = (await db.execute(text(
                    "SELECT count(*) FROM termination_processes "
                    "WHERE CAST(employee_id AS TEXT) = :e"), {"e": eid_com})).scalar()
                assert n == 1, f"idempotência quebrou: {n} processos de rescisão"
                print("TESTE c (idempotente: 2 chamadas = 1 proposta) PASS")

                r3 = await _agir(db, _U(), _S(), dominio="dp", acao="registrar_desligamento",
                                 dados={"employee_id": eid_sem})
                assert "erro" in r3 and "desligamento" in str(r3).lower(), \
                    f"deveria recusar quem não tem desligamento: {r3}"
                print("TESTE b (não fabrica: sem data de desligamento → recusa) PASS")
            finally:
                for _m, _f in _origs.items():
                    setattr(_ts.TerminationService, _m, _f)

            st = (await db.execute(text(
                "SELECT lower(coalesce(status::text,'')) FROM termination_processes "
                "WHERE CAST(employee_id AS TEXT) = :e"), {"e": eid_com})).scalar()
            assert st in ("initiated", "iniciado", "pendente"), \
                f"processo NÃO nasceu inerte — status={st!r} (deveria ser 'initiated')"
            print(f"TESTE a2 (processo nasce INERTE: status={st!r}, nunca concluído) PASS")
            print("\nTODAS AS PROVAS DA CAPTURA PASSARAM")
    finally:
        async with S() as db:
            for e in (eid_com, eid_sem):
                if e:
                    await db.execute(text(
                        "DELETE FROM communication_notifications "
                        "WHERE extra_data->>'idempotency_key' = :k"),
                        {"k": f"dp:registrar_desligamento:{e}"})
                    await db.execute(text(
                        "DELETE FROM termination_processes WHERE CAST(employee_id AS TEXT) = :e"),
                        {"e": e})
            await db.execute(text("DELETE FROM employees WHERE nome LIKE :m"), {"m": f"{marca}%"})
            await db.commit()
            rem = (await db.execute(text("SELECT count(*) FROM employees WHERE nome LIKE :m"),
                                    {"m": f"{marca}%"})).scalar()
            assert rem == 0, f"resíduo: {rem}"
            print("LIMPEZA OK — 0 resíduo")
        await eng.dispose()


asyncio.run(main())
