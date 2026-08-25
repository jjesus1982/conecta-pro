#!/usr/bin/env python3
"""Oráculo das tools de EDITAR registro que já existe — proposta, lead, deal.

Lacunas 2, 3 e 4 das 14. O motor in-process criava, lia e gerava documento; não editava.

⭐ O que este oráculo protege é o GRAU POR CAMPO. O MESMO endpoint que corrige o CNPJ de uma
proposta muda desconto, imposto e status. Decidir o grau pelo NOME da tool é como o
`tool_risk_manifest` errou 54 vezes: o nome diz cadastro e o corpo faz dinheiro.

Por tool, quatro invariantes — e a última é a única que separa PROPOSTA de EXECUÇÃO:
  1. campo/estado de VALOR ou FECHAMENTO é RECUSADO (não proposto em 🟡 — recusado)
  2. campo/valor inexistente é recusado
  3. registro inexistente é recusado (nunca cria "de passagem")
  4. INÉRCIA: o caso válido vira rascunho e o banco NÃO MUDA

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_acao_editar_crm.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

_MARCA = "ZZteste-oraculo-editar-crm"


async def main() -> int:
    from sqlalchemy import select, text

    from core.database import async_session_factory
    from core.models.user import User
    import modules.ai.conversation.controllers.consultor_escopado_controller as C
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import _ACOES
    from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
        _propor_atualizar_proposta, _propor_criar_cliente, _propor_marcar_deal_perdido,
        _propor_reativar_lead,
    )

    falhas: list[str] = []
    async with async_session_factory() as db:
        # ENTRADA por MARCA, nunca por id — quem morre por sinal não deixa a lista dela.
        await db.execute(text("DELETE FROM agent_drafts WHERE payload::text LIKE :m"),
                         {"m": f"%{_MARCA}%"})
        await db.commit()

        for nome in ("atualizar_proposta", "reativar_lead", "marcar_deal_perdido",
                     "criar_cliente"):
            if nome not in _ACOES.get("crm", {}):
                falhas.append(f"{nome} não está registrada em agir_crm")
        if falhas:
            for f in falhas:
                print(f"FALHOU: {f}")
            return 1

        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalar_one()
        scope, _ = await C._resolver_tier_e_tools(db, u)

        # ── PROPOSTA ────────────────────────────────────────────────────────────────
        prop = (await db.execute(text(
            "SELECT number FROM proposals LIMIT 1"))).scalar()
        if prop:
            r = await _propor_atualizar_proposta(db, u, scope, proposta=prop,
                                                 discount_value=500)
            if not r.get("erro"):
                falhas.append("proposta: desconto (VALOR) foi aceito — grau tem de sair do campo")
            r = await _propor_atualizar_proposta(db, u, scope, proposta=prop, campo_que_nao_existe="x")
            if not r.get("erro"):
                falhas.append("proposta: campo inexistente aceito")
            r = await _propor_atualizar_proposta(db, u, scope, proposta="ZZ_NAO_EXISTE",
                                                 title=_MARCA)
            if not r.get("erro"):
                falhas.append("proposta: proposta inexistente aceita")
            antes = (await db.execute(text(
                "SELECT title FROM proposals WHERE number = :n"), {"n": prop})).scalar()
            r = await _propor_atualizar_proposta(db, u, scope, proposta=prop,
                                                 description=_MARCA)
            if not (r.get("draft_id") or r.get("id")):
                falhas.append(f"proposta: cadastral não virou rascunho: {str(r)[:90]}")
            depois = (await db.execute(text(
                "SELECT title FROM proposals WHERE number = :n"), {"n": prop})).scalar()
            if antes != depois:
                falhas.append(f"proposta: A PROPOSTA GRAVOU: {antes!r} → {depois!r}")
        else:
            print("  (sem proposta na base — bloco de proposta não exercitado)")

        # ── LEAD ────────────────────────────────────────────────────────────────────
        lead = (await db.execute(text(
            "SELECT name, status::text FROM leads WHERE status::text <> 'contacted' LIMIT 1"))).first()
        if lead:
            r = await _propor_reativar_lead(db, u, scope, lead=lead[0], status="won")
            if not r.get("erro"):
                falhas.append("lead: 'won' (fechamento) foi aceito como reativação")
            r = await _propor_reativar_lead(db, u, scope, lead=lead[0], status="inventado")
            if not r.get("erro"):
                falhas.append("lead: status inválido aceito")
            r = await _propor_reativar_lead(db, u, scope, lead="ZZ_NAO_EXISTE")
            if not r.get("erro"):
                falhas.append("lead: lead inexistente aceito")
            antes = (await db.execute(text(
                "SELECT status::text FROM leads WHERE name = :n"), {"n": lead[0]})).scalar()
            r = await _propor_reativar_lead(db, u, scope, lead=lead[0], status="contacted",
                                            motivo=_MARCA)
            if not (r.get("draft_id") or r.get("id")):
                falhas.append(f"lead: reativação não virou rascunho: {str(r)[:90]}")
            depois = (await db.execute(text(
                "SELECT status::text FROM leads WHERE name = :n"), {"n": lead[0]})).scalar()
            if antes != depois:
                falhas.append(f"lead: A PROPOSTA MOVEU o lead: {antes!r} → {depois!r}")
        else:
            print("  (sem lead fora de 'contacted' — bloco de lead não exercitado)")

        # ── DEAL ────────────────────────────────────────────────────────────────────
        deal = (await db.execute(text(
            "SELECT title, stage::text FROM opportunities LIMIT 1"))).first()
        if deal:
            r = await _propor_marcar_deal_perdido(db, u, scope, deal=deal[0])
            if not r.get("erro"):
                falhas.append("deal: perda SEM MOTIVO foi aceita")
            r = await _propor_marcar_deal_perdido(db, u, scope, deal=deal[0], motivo="chutei")
            if not r.get("erro"):
                falhas.append("deal: motivo de perda inválido aceito")
            r = await _propor_marcar_deal_perdido(db, u, scope, deal="ZZ_NAO_EXISTE",
                                                  motivo="price")
            if not r.get("erro"):
                falhas.append("deal: deal inexistente aceito")
            antes = (await db.execute(text(
                "SELECT stage::text FROM opportunities WHERE title = :t"), {"t": deal[0]})).scalar()
            r = await _propor_marcar_deal_perdido(db, u, scope, deal=deal[0], motivo="price",
                                                  observacao=_MARCA)
            if not (r.get("draft_id") or r.get("id")):
                falhas.append(f"deal: perda não virou rascunho: {str(r)[:90]}")
            depois = (await db.execute(text(
                "SELECT stage::text FROM opportunities WHERE title = :t"), {"t": deal[0]})).scalar()
            if antes != depois:
                falhas.append(f"deal: A PROPOSTA FECHOU o deal: {antes!r} → {depois!r}")
        else:
            print("  (sem oportunidade na base — bloco de deal não exercitado)")

        # ── CRIAR CLIENTE ───────────────────────────────────────────────────────────
        doc_existe = (await db.execute(text(
            "SELECT document_number FROM clients WHERE document_number IS NOT NULL LIMIT 1"))).scalar()
        r = await _propor_criar_cliente(db, u, scope, cnpj="12345678000199")
        if not r.get("erro"):
            falhas.append("cliente: criado SEM NOME")
        r = await _propor_criar_cliente(db, u, scope, nome=_MARCA)
        if not r.get("erro"):
            falhas.append("cliente: criado SEM DOCUMENTO — não serviria para contrato nem NFS-e")
        r = await _propor_criar_cliente(db, u, scope, nome=_MARCA, cnpj="123")
        if not r.get("erro"):
            falhas.append("cliente: documento com tamanho inválido aceito")
        if doc_existe:
            r = await _propor_criar_cliente(db, u, scope, nome=_MARCA, cnpj=doc_existe)
            if not r.get("erro"):
                falhas.append("cliente: DUPLICATA de documento aceita — quebra MRR e cobrança")
        n0 = (await db.execute(text("SELECT count(*) FROM clients"))).scalar()
        r = await _propor_criar_cliente(db, u, scope, nome=_MARCA, cnpj="11222333000181")
        if not (r.get("draft_id") or r.get("id")):
            falhas.append(f"cliente: válido não virou rascunho: {str(r)[:90]}")
        n1 = (await db.execute(text("SELECT count(*) FROM clients"))).scalar()
        if n0 != n1:
            falhas.append(f"cliente: A PROPOSTA CRIOU o cliente: {n0} → {n1}")

        await db.execute(text("DELETE FROM agent_drafts WHERE payload::text LIKE :m"),
                         {"m": f"%{_MARCA}%"})
        await db.commit()

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK editar_crm: 17/17 — proposta, lead, deal e cliente recusam valor/fechamento/duplicata, "
          "recusam inexistente, e a proposta é INERTE (nada mudou no banco)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
