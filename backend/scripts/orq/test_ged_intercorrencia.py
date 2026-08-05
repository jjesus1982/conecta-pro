"""Bench (throwaway) das 3 ações de INTERCORRÊNCIA do GED na Central de Rascunhos.
NUNCA :8080; NUNCA aprova/executa de verdade (serviços reais monkeypatchados).

Prova, com sentinela + cleanup finally + 0 resíduo:
 (a) o HANDLER (via dispatcher agir_ged) de registrar/tratar/excluir_intercorrencia
     cria 1 AgentDraft status='rascunho' do tipo/gate certo e NÃO executa — os serviços
     de domínio reais (consultor_service.registrar/tratar/excluir) estão com BOOM (se
     chamados na criação, estoura); idempotente (2ª chamada não duplica);
 (b) o EXECUTOR está registrado (EXECUTORES tem a chave) e, com o serviço real
     MONKEYPATCHADO (sem efeito no banco), executar_rascunho chama o serviço e devolve
     o entity_ref, marcando o draft 'executado';
 (c) ação inválida → recusa listando opções.
"""
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import modules.gedeon.services.consultor_service as cs
from modules.ai.conversation.services.orquestrador import tools_acao_ged  # noqa: F401 (registra ações+executores)
from modules.ai.conversation.services.orquestrador.acoes.rascunho import EXECUTORES, executar_rascunho
from modules.ai.conversation.services.orquestrador.agir_dispatcher import montar_acao_dispatchers
from modules.ai.conversation.services.orquestrador.tool_registry import get_tool
from modules.ai.conversation.models.agent_draft import AgentDraft

SENT = "__TESTE_F6_GED_INTERC__"


class _U:
    id = "00000000-0000-0000-0000-0000000000ff"
    role = "funcionario"
    email = "teste-ged-interc@conectapro.local"
    nome = "Bench GED Interc"
    permissions = ["module:ged"]


async def main() -> None:
    montar_acao_dispatchers()
    agir = get_tool("agir_ged")
    assert agir is not None and agir.module == "ged", "agir_ged não registrado no módulo ged"
    disp = agir.handler

    # ── BOOM: nenhum serviço de domínio real pode ser chamado na CRIAÇÃO do rascunho ──
    executou = {"n": 0}

    def _boom(nome):
        async def _b(*a, **k):
            executou["n"] += 1
            raise AssertionError(f"serviço real {nome} NÃO pode ser chamado na criação do rascunho")
        return _b

    _orig = (cs.registrar_intercorrencia, cs.tratar_intercorrencia, cs.excluir_intercorrencia)
    cs.registrar_intercorrencia = _boom("consultor_service.registrar_intercorrencia")
    cs.tratar_intercorrencia = _boom("consultor_service.tratar_intercorrencia")
    cs.excluir_intercorrencia = _boom("consultor_service.excluir_intercorrencia")

    eng = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(eng, expire_on_commit=False)
    draft_ids: list[str] = []
    sent_id: int | None = None
    try:
        async with Session() as db:
            # fixture: 1 intercorrência sentinela REAL (p/ tratar/excluir resolverem por id).
            # É fixture do teste, NÃO a ação — limpa no finally.
            await cs._ensure_schema(db)
            sent_id = (await db.execute(text(
                "INSERT INTO gedeon_intercorrencias "
                "(condominio, competencia, tipo, descricao, impacto_folha) "
                "VALUES (:c, '2099-12', 'falta', :d, true) RETURNING id"),
                {"c": f"{SENT} Cond", "d": f"{SENT} fixture"})).scalar()
            await db.commit()

            casos = [
                ("registrar_intercorrencia",
                 {"condominio": f"{SENT} Cond", "tipo": "falta",
                  "descricao": f"{SENT} agente faltou no plantão", "impacto_folha": True}, "🟡"),
                ("tratar_intercorrencia",
                 {"intercorrencia_id": sent_id, "resolucao": "regularizado no ponto"}, "🔵"),
                ("excluir_intercorrencia", {"intercorrencia_id": sent_id}, "🟡"),
            ]

            # ── (a) HANDLER cria rascunho inerte, tipo/gate certos, NÃO executa, idempotente ──
            for acao, dados, gate_exp in casos:
                r = await disp(db, _U(), None, acao=acao, dados=dados)
                assert r.get("status") == "rascunho" and not r.get("duplicado"), (acao, r)
                did = r["draft_id"]; draft_ids.append(did)
                row = (await db.execute(text(
                    "SELECT tipo, modulo, status, gate, requires_otp FROM agent_drafts "
                    "WHERE id = CAST(:i AS uuid)"), {"i": did})).mappings().first()
                assert row and row["tipo"] == acao and row["modulo"] == "ged" \
                    and row["status"] == "rascunho" and row["gate"] == gate_exp \
                    and row["requires_otp"] is False, (acao, dict(row) if row else None)
                r2 = await disp(db, _U(), None, acao=acao, dados=dados)
                assert r2.get("duplicado") is True, (acao, r2)
            # excluir: resumo deixa CLARO que é DESTRUTIVO
            resumo_del = (await db.execute(text(
                "SELECT resumo FROM agent_drafts WHERE tipo='excluir_intercorrencia' "
                "AND id = ANY(CAST(:i AS uuid[]))"), {"i": draft_ids})).scalar()
            assert resumo_del and "DESTRUTIVO" in resumo_del.upper(), resumo_del
            assert executou["n"] == 0, "serviço real chamado na CRIAÇÃO (handler executou) — proibido"
            print("TESTE (a) 3 handlers → AgentDraft 'rascunho' (registrar 🟡 / tratar 🔵 / "
                  "excluir 🟡, sem OTP), resumo DESTRUTIVO no excluir, NÃO executa, idempotente PASS")

            # ── (b) EXECUTOR registrado + roda o serviço real (monkeypatchado) na aprovação ──
            assert {"registrar_intercorrencia", "tratar_intercorrencia", "excluir_intercorrencia"} \
                <= set(EXECUTORES), set(EXECUTORES)

            chamou = {"registrar_intercorrencia": 0, "tratar_intercorrencia": 0, "excluir_intercorrencia": 0}

            async def _fake_registrar(db, **k):
                chamou["registrar_intercorrencia"] += 1
                return {"id": 999999}

            async def _fake_tratar(db, iid):
                chamou["tratar_intercorrencia"] += 1
                return {"id": iid, "status": "tratada", "tratada_em": "x"}

            async def _fake_excluir(db, iid):
                chamou["excluir_intercorrencia"] += 1
                return None

            cs.registrar_intercorrencia = _fake_registrar
            cs.tratar_intercorrencia = _fake_tratar
            cs.excluir_intercorrencia = _fake_excluir

            for did in draft_ids:
                draft = await db.get(AgentDraft, did)
                assert draft is not None and draft.status == "rascunho", (did, draft)
                ref = await executar_rascunho(db, _U(), draft)
                assert ref, (draft.tipo, ref)
                assert draft.status == "executado" and draft.entity_ref == ref, (draft.tipo, draft.status)
            assert all(v == 1 for v in chamou.values()), chamou
            print(f"TESTE (b) executores registrados + rodam o serviço real (monkeypatch) na "
                  f"aprovação e devolvem entity_ref; drafts→'executado' ({chamou}) PASS")

            # ── (c) ação inválida → recusa listando opções ──
            rb = await disp(db, _U(), None, acao="apagar_tudo", dados={})
            assert rb.get("status") == "recusado" and "opções" in rb.get("motivo", ""), rb
            assert "registrar_intercorrencia" in rb["motivo"], rb
            print("TESTE (c) ação inválida → recusa listando opções PASS")

            print("\nTODAS AS PROVAS DE test_ged_intercorrencia.py PASSARAM "
                  "(reuso: consultor_service.registrar/tratar/excluir_intercorrencia)")
    finally:
        cs.registrar_intercorrencia = _orig[0]
        cs.tratar_intercorrencia = _orig[1]
        cs.excluir_intercorrencia = _orig[2]
        async with Session() as db:
            ids = draft_ids or ["00000000-0000-0000-0000-000000000000"]
            await db.execute(text("DELETE FROM communication_notifications WHERE reference_id = ANY(:i)"), {"i": ids})
            await db.execute(text("DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": ids})
            await db.execute(text("DELETE FROM agent_drafts WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
            if sent_id is not None:
                await db.execute(text("DELETE FROM gedeon_intercorrencias WHERE id = :i"), {"i": sent_id})
            await db.commit()
            rem_d = (await db.execute(text(
                "SELECT count(*) FROM agent_drafts WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": ids})).scalar()
            rem_n = (await db.execute(text(
                "SELECT count(*) FROM communication_notifications WHERE reference_id = ANY(:i)"), {"i": ids})).scalar()
            rem_i = (await db.execute(text(
                "SELECT count(*) FROM gedeon_intercorrencias WHERE descricao LIKE :s OR condominio LIKE :s"),
                {"s": "%" + SENT + "%"})).scalar()
            assert rem_d == 0 and rem_n == 0 and rem_i == 0, \
                f"remanescentes rascunho={rem_d} sino={rem_n} intercorrencia={rem_i}"
            print("LIMPEZA OK — 0 remanescentes (agent_drafts/communication_notifications/audit/"
                  "gedeon_intercorrencias fixture)")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
