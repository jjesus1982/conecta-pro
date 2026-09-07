#!/usr/bin/env python3
"""Licitação → CRM/Financeiro: contrato público vira cliente+contrato; oportunidade vira lead.

Nasceu em 07/09/2026: `contrato_para_crm` importava um serviço que nunca existiu e respondia
"pendente_integracao" para sempre — a tela tinha o botão, o clique não fazia nada. Este oráculo
cria um contrato público e uma oportunidade DE TESTE (marcados ORACULO), chama os dois serviços,
afirma o efeito nas tabelas reais (clients, contracts, leads), prova a idempotência (2ª chamada
= vinculado, sem linha nova) e APAGA tudo o que criou — inclusive o que a integração criou.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_licitacao_crm.py
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")
import main_production  # noqa: E402,F401

MARCA = f"ORACULO-LICIT-{uuid.uuid4().hex[:8]}"
CNPJ_TESTE = "00000000000191"  # CNPJ de teste (Banco do Brasil formal), nunca cliente real


async def main() -> None:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.bidding.services.erp_integration_service import ERPIntegrationService

    criados = {"contract": None, "opp": None}
    async with async_session_factory() as db:
        svc = ERPIntegrationService(db)
        try:
            cid = str((await db.execute(text(
                "INSERT INTO bidding_public_contracts (id, numero_contrato, ano_contrato, orgao_nome, orgao_cnpj, orgao_uf, "
                " objeto, objeto_resumido, valor_contrato, prazo_meses, data_vigencia_inicio, data_vigencia_fim, status, ativo, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :n, 2026, :org, :cnpj, 'AM', CAST(:obj AS text), CAST(:obj AS varchar), 120000, 12, current_date, current_date + 365, 'active', true, now(), now()) RETURNING id"),
                {"n": MARCA, "org": f"ORGAO {MARCA}", "cnpj": CNPJ_TESTE, "obj": f"Portaria {MARCA}"})).scalar())
            criados["contract"] = cid
            oid = str((await db.execute(text(
                "INSERT INTO bidding_opportunities (id, objeto, orgao_nome, orgao_cnpj, uf, valor_estimado, status, portal, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :obj, :org, :cnpj, 'AM', 50000, 'nova', 'pncp', now(), now()) RETURNING id"),
                {"obj": f"Limpeza {MARCA}", "org": f"ORGAO {MARCA}", "cnpj": CNPJ_TESTE})).scalar())
            criados["opp"] = oid
            await db.commit()

            r1 = await svc.contrato_para_crm(uuid.UUID(cid))
            assert r1["status"] == "criado" and r1["cliente"] == "criado" and r1["contrato_crm"] == "criado", r1
            cli = (await db.execute(text("SELECT client_type::text, status::text, crm_origin FROM clients WHERE id = CAST(:i AS uuid)"), {"i": r1["cliente_id"]})).first()
            assert cli and cli[0] == "government" and cli[1] == "active" and cli[2] == "licitacao", cli
            ctr = (await db.execute(text("SELECT status::text, monthly_value, client_id::text, contract_number FROM contracts WHERE id = CAST(:i AS uuid)"), {"i": r1["contrato_crm_id"]})).first()
            assert ctr and ctr[0] == "active" and abs(float(ctr[1]) - 10000) < 0.01 and ctr[2] == r1["cliente_id"] and ctr[3] == MARCA, ctr
            print(f"OK contrato público → cliente 'government' ativo + contrato ativo R$ {float(ctr[1]):,.2f}/mês")

            r2 = await svc.contrato_para_crm(uuid.UUID(cid))
            assert r2["status"] == "vinculado" and r2["cliente_id"] == r1["cliente_id"] and r2["contrato_crm_id"] == r1["contrato_crm_id"], r2
            n_cli = (await db.execute(text("SELECT count(*) FROM clients WHERE regexp_replace(document_number,'\\D','','g') = :c"), {"c": CNPJ_TESTE})).scalar()
            assert n_cli == 1, f"2ª chamada duplicou o cliente: {n_cli}"
            print("OK idempotente: 2ª chamada vincula, não duplica")

            l1 = await svc.oportunidade_para_lead(uuid.UUID(oid))
            assert l1["status"] == "criado", l1
            lead = (await db.execute(text("SELECT source, status, expected_value, custom_fields->>'bidding_opportunity_id' FROM leads WHERE id = CAST(:i AS uuid)"), {"i": l1["lead_id"]})).first()
            assert lead and lead[0] == "licitacao" and lead[1] == "new" and float(lead[2]) == 50000 and lead[3] == oid, lead
            l2 = await svc.oportunidade_para_lead(uuid.UUID(oid))
            assert l2["status"] == "vinculado" and l2["lead_id"] == l1["lead_id"], l2
            print("OK oportunidade → lead 'licitacao' no funil; 2ª chamada não duplica")
        finally:
            # LIMPEZA — nada de teste fica em produção (checar_desmonte_comportamento)
            await db.rollback()
            await db.execute(text("DELETE FROM leads WHERE custom_fields->>'bidding_opportunity_id' = :o OR name LIKE :m"), {"o": criados["opp"] or "", "m": f"%{MARCA}%"})
            await db.execute(text("DELETE FROM contracts WHERE contract_number = :n"), {"n": MARCA})
            await db.execute(text("DELETE FROM clients WHERE regexp_replace(coalesce(document_number,''),'\\D','','g') = :c AND name LIKE :m"), {"c": CNPJ_TESTE, "m": f"%{MARCA}%"})
            await db.execute(text("DELETE FROM bidding_opportunities WHERE orgao_nome LIKE :m"), {"m": f"%{MARCA}%"})
            await db.execute(text("DELETE FROM bidding_public_contracts WHERE numero_contrato = :n"), {"n": MARCA})
            await db.commit()
            sobras = (await db.execute(text(
                "SELECT (SELECT count(*) FROM clients WHERE name LIKE :m) + (SELECT count(*) FROM contracts WHERE contract_number = :n) "
                "+ (SELECT count(*) FROM leads WHERE name LIKE :m) + (SELECT count(*) FROM bidding_opportunities WHERE orgao_nome LIKE :m) "
                "+ (SELECT count(*) FROM bidding_public_contracts WHERE numero_contrato = :n)"), {"m": f"%{MARCA}%", "n": MARCA})).scalar()
            print(f"LIMPEZA OK — {sobras} remanescente(s)")
            assert sobras == 0
    print("TEST oraculo_licitacao_crm PASS")


if __name__ == "__main__":
    asyncio.run(main())
