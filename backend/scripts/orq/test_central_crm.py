"""Bench (throwaway) das 3 ações-piloto do CRM na Central de Rascunhos. NUNCA :8080.

Prova, com sentinela + cleanup finally + 0 resíduo:
 (a) o HANDLER (via dispatcher agir_crm) de criar_contrato / ativar_contrato /
     enviar_proposta cria 1 AgentDraft status='rascunho' do tipo certo e NÃO executa
     — os serviços de domínio reais estão com BOOM (se chamados na criação, estoura);
 (b) o EXECUTOR está registrado (EXECUTORES tem a chave) e, com o serviço real
     MONKEYPATCHADO (sem efeito externo), executar_rascunho chama o serviço e devolve
     o entity_ref, marcando o draft 'executado';
 (c) limpa todos os agent_drafts/notifs/audit criados (por draft_id) → 0 remanescentes.

NUNCA aprova/executa contra cliente real; NUNCA envia proposta de verdade (monkeypatch).
"""
import asyncio
import os
import types

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import modules.crm.controllers.contract_controller as _cc
import modules.crm.controllers.proposal_controller as _pc
import modules.crm.repositories.contract_repository as _crepo
from modules.ai.conversation.services.orquestrador import tools_acao_crm  # noqa: F401 (registra ações+executores)
from modules.ai.conversation.services.orquestrador.acoes.rascunho import EXECUTORES, executar_rascunho
from modules.ai.conversation.services.orquestrador.agir_dispatcher import montar_acao_dispatchers
from modules.ai.conversation.services.orquestrador.tool_registry import get_tool
from modules.ai.conversation.models.agent_draft import AgentDraft


class _U:
    id = "00000000-0000-0000-0000-0000000000ff"
    role = "funcionario"
    email = "teste-central@conectapro.local"
    nome = "Bench Central"
    permissions = ["module:crm"]


async def main() -> None:
    montar_acao_dispatchers()
    agir = get_tool("agir_crm")
    assert agir is not None and agir.module == "crm", "agir_crm não registrado no módulo crm"
    disp = agir.handler

    # ── BOOM: nenhum serviço de domínio real pode ser chamado na CRIAÇÃO do rascunho ──
    executou = {"n": 0}

    def _boom(nome):
        async def _b(*a, **k):
            executou["n"] += 1
            raise AssertionError(f"serviço real {nome} NÃO pode ser chamado na criação do rascunho")
        return _b

    _orig = (_crepo.ContractRepository.create, _cc.activate_contract, _pc.send_proposal)
    _crepo.ContractRepository.create = _boom("ContractRepository.create")
    _cc.activate_contract = _boom("contract_controller.activate_contract")
    _pc.send_proposal = _boom("proposal_controller.send_proposal")

    eng = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(eng, expire_on_commit=False)
    draft_ids: list[str] = []
    try:
        async with Session() as db:
            # refs REAIS (o rascunho é inerte — resolver != executar)
            cli_real = (await db.execute(text(
                "SELECT name FROM clients WHERE coalesce(ativo,true)=true ORDER BY name LIMIT 1"))).scalar()
            ct_real = (await db.execute(text(
                "SELECT contract_number FROM contracts WHERE contract_number IS NOT NULL LIMIT 1"))).scalar()
            prop_real = (await db.execute(text("SELECT id::text FROM proposals LIMIT 1"))).scalar()
            assert cli_real and ct_real and prop_real, \
                f"faltam refs reais: cliente={cli_real} contrato={ct_real} proposta={prop_real}"

            casos = [
                ("criar_contrato", {"cliente": cli_real, "produto": "Portaria", "valor": "5000"}, "🟡"),
                ("ativar_contrato", {"contrato_numero": ct_real}, "🔴"),
                ("enviar_proposta", {"proposta_id": prop_real}, "🔴"),
            ]

            # ── (a) HANDLER cria rascunho inerte, tipo/gate certos, NÃO executa, idempotente ──
            for acao, dados, gate_exp in casos:
                r = await disp(db, _U(), None, acao=acao, dados=dados)
                assert r.get("status") == "rascunho" and not r.get("duplicado"), (acao, r)
                did = r["draft_id"]; draft_ids.append(did)
                row = (await db.execute(text(
                    "SELECT tipo, modulo, status, gate, requires_otp, resumo FROM agent_drafts "
                    "WHERE id = CAST(:i AS uuid)"), {"i": did})).mappings().first()
                assert row and row["tipo"] == acao and row["modulo"] == "crm" \
                    and row["status"] == "rascunho" and row["gate"] == gate_exp \
                    and row["requires_otp"] is False, (acao, dict(row) if row else None)
                # idempotência: 2ª chamada não cria 2º rascunho
                r2 = await disp(db, _U(), None, acao=acao, dados=dados)
                assert r2.get("duplicado") is True, (acao, r2)
            # enviar_proposta: resumo deixa CLARO que vai AO CLIENTE (externo/LGPD)
            resumo_env = (await db.execute(text(
                "SELECT resumo FROM agent_drafts WHERE tipo='enviar_proposta' "
                "AND id = ANY(CAST(:i AS uuid[]))"), {"i": draft_ids})).scalar()
            assert resumo_env and "CLIENTE" in resumo_env.upper() and "LGPD" in resumo_env.upper(), resumo_env
            assert executou["n"] == 0, "serviço real chamado na CRIAÇÃO (handler executou) — proibido"
            print("TESTE (a) 3 handlers → AgentDraft 'rascunho' (tipos criar/ativar/enviar, "
                  "gate 🟡/🔴/🔴, sem OTP), resumo AO CLIENTE/LGPD, NÃO executa, idempotente PASS")

            # ── (b) EXECUTOR registrado + roda o serviço real (monkeypatchado) na aprovação ──
            assert {"criar_contrato", "ativar_contrato", "enviar_proposta"} <= set(EXECUTORES), set(EXECUTORES)

            chamou = {"criar_contrato": 0, "ativar_contrato": 0, "enviar_proposta": 0}

            def _fake_obj(entity_id):
                return types.SimpleNamespace(id=entity_id)

            async def _fake_create(self, data, created_by_id):  # ContractRepository.create
                chamou["criar_contrato"] += 1
                return _fake_obj("fake-contract-id")

            async def _fake_activate(*, contract_id, current_user, db):  # activate_contract
                chamou["ativar_contrato"] += 1
                return _fake_obj(contract_id)

            async def _fake_send(*, proposal_id, current_user, db):  # send_proposal
                chamou["enviar_proposta"] += 1
                return _fake_obj(proposal_id)

            _crepo.ContractRepository.create = _fake_create
            _cc.activate_contract = _fake_activate
            _pc.send_proposal = _fake_send

            for did in draft_ids:
                draft = await db.get(AgentDraft, did)
                assert draft is not None and draft.status == "rascunho", (did, draft)
                ref = await executar_rascunho(db, _U(), draft)
                assert ref, (draft.tipo, ref)
                assert draft.status == "executado" and draft.entity_ref == ref, (draft.tipo, draft.status)
            assert all(v == 1 for v in chamou.values()), chamou
            print(f"TESTE (b) executores registrados + rodam o serviço real (monkeypatch) na "
                  f"aprovação e devolvem entity_ref; drafts→'executado' ({chamou}) PASS")

            print("\nTODAS AS PROVAS DE test_central_crm.py PASSARAM "
                  "(reuso: ContractRepository.create, contract_controller.activate_contract, "
                  "proposal_controller.send_proposal — os MESMOS do REDESIGN-1)")
    finally:
        _crepo.ContractRepository.create = _orig[0]
        _cc.activate_contract = _orig[1]
        _pc.send_proposal = _orig[2]
        # ── (c) cleanup por draft_id (sino via reference_id, audit via entity_id) ──
        async with Session() as db:
            ids = draft_ids or ["00000000-0000-0000-0000-000000000000"]
            await db.execute(text("DELETE FROM communication_notifications WHERE reference_id = ANY(:i)"), {"i": ids})
            await db.execute(text("DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": ids})
            await db.execute(text("DELETE FROM agent_drafts WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
            await db.commit()
            rem_d = (await db.execute(text(
                "SELECT count(*) FROM agent_drafts WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": ids})).scalar()
            rem_n = (await db.execute(text(
                "SELECT count(*) FROM communication_notifications WHERE reference_id = ANY(:i)"), {"i": ids})).scalar()
            assert rem_d == 0 and rem_n == 0, f"remanescentes rascunho={rem_d} sino={rem_n}"
            print("LIMPEZA OK — 0 remanescentes (agent_drafts/communication_notifications/audit)")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
