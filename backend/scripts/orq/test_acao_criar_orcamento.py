#!/usr/bin/env python3
"""Oráculo de `criar_orcamento` — o orçamento vira PROPOSTA no CRM.

`gerar_orcamento_itens_doc` produz o PDF e não grava. Esta ação GRAVA: `proposals` +
`proposal_items`, com número, validade e histórico. Fecha o par do que o Jordan pediu em
27/08/2026 ("preciso fazer orçamentos... quero os 854 no orçamento").

⭐ DUAS COISAS QUE ESTE ORÁCULO PROTEGE

1. INÉRCIA. Propor não grava. É a parede da casa inteira, e aqui ela é mais fácil de
   furar que em qualquer outra ação, porque o executor está no mesmo arquivo.
2. PREÇO CONGELADO NA PROPOSTA. Entre propor e aprovar o catálogo pode mudar (Bling
   reimportado, preço corrigido na tela). Uma proposta que muda de valor sozinha entre o
   "quero isso" e o "aprovado" é armadilha — o payload leva a linha já resolvida, e este
   teste MEXE no catálogo entre as duas fases para provar que o valor não seguiu.

Sete invariantes:
  1. cliente inexistente é RECUSADO (nunca cria cliente de passagem)
  2. sem título é RECUSADO (proposta sem objeto não é documento)
  3. item do Bling sem `valor_unit` é RECUSADO (não sai a zero)
  4. quantidade zero é RECUSADA (`x or 1` faria virar 1 em silêncio)
  5. o caso válido vira RASCUNHO e o banco NÃO MUDA
  6. aprovar GRAVA: proposta com número, tipo derivado das linhas, total fechando, e
     `code` do item preenchido com o SKU — o campo que estava 0 de 162
  7. o preço gravado é o CONGELADO, mesmo que o catálogo tenha mudado no meio

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_acao_criar_orcamento.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

_MARCA = "ZZteste-oraculo-criar-orcamento"


async def _limpar(db) -> None:
    """Desmonte por MARCA, nunca por id — e nas TRÊS tabelas que a ação toca.

    ⚠️ Apagar `agent_drafts` sem apagar `communication_notifications` deixa a chave de
    idempotência viva apontando para um rascunho que não existe, e a tool passa a devolver
    `duplicado=True` para sempre. Foi exatamente o que uma limpeza pela metade causou em
    25/08/2026.
    """
    from sqlalchemy import text as _t

    ids = (await db.execute(_t(
        "SELECT id FROM proposals WHERE title LIKE :m"), {"m": f"%{_MARCA}%"})).scalars().all()
    if ids:
        await db.execute(_t("DELETE FROM proposal_items WHERE proposal_id = ANY(:i)"),
                         {"i": ids})
        await db.execute(_t("DELETE FROM proposals WHERE id = ANY(:i)"), {"i": ids})
    d = (await db.execute(_t(
        "SELECT id FROM agent_drafts WHERE payload::text LIKE :m"),
        {"m": f"%{_MARCA}%"})).scalars().all()
    if d:
        await db.execute(_t(
            "DELETE FROM communication_notifications WHERE reference_id::text = ANY(:i)"),
            {"i": [str(x) for x in d]})
        await db.execute(_t("DELETE FROM agent_drafts WHERE id = ANY(:i)"), {"i": d})
    await db.commit()


async def main() -> int:
    from sqlalchemy import select, text

    from core.database import async_session_factory
    from core.models.user import User
    import modules.ai.conversation.controllers.consultor_escopado_controller as C
    from modules.ai.conversation.controllers.agente_aprovacao_controller import grau_de
    from modules.ai.conversation.models.agent_draft import AgentDraft
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import (
        executar_rascunho,
    )
    from modules.ai.conversation.services.orquestrador.agir_dispatcher import _ACOES
    from modules.ai.conversation.services.orquestrador.tools_acao_crm import (
        _propor_criar_orcamento as P,
    )

    falhas: list[str] = []
    async with async_session_factory() as db:
        await _limpar(db)

        if "criar_orcamento" not in _ACOES.get("crm", {}):
            print("FALHOU: `criar_orcamento` não está registrada em agir_crm")
            return 1
        grau, otp = grau_de("criar_orcamento")
        if grau not in ("🟡", "🔴"):
            falhas.append(f"grau {grau} — ação que GRAVA valor não pode ser 🔵")

        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalar_one()
        scope, _ = await C._resolver_tier_e_tools(db, u)

        cli = (await db.execute(text("SELECT name FROM clients LIMIT 1"))).scalar()
        cat = (await db.execute(text(
            "SELECT sku, unit_price FROM crm_products "
            "WHERE is_active = true AND unit_price > 0 ORDER BY sku LIMIT 1"))).first()
        bling = (await db.execute(text(
            "SELECT code FROM products WHERE coalesce(ativo, true) "
            "AND code IS NOT NULL ORDER BY code LIMIT 1"))).scalar()
        if not cli or not cat:
            print("FALHOU (pré-condição): sem cliente ou catálogo vazio")
            return 1
        sku, preco = cat[0], float(cat[1])
        titulo = f"{_MARCA} CFTV"

        # 1 · cliente inexistente
        r = await P(db, u, scope, cliente="ZZ_NAO_EXISTE", titulo=titulo,
                    itens=[{"sku": sku, "qtd": 1}])
        if not r.get("erro"):
            falhas.append("cliente inexistente foi aceito")

        # 2 · sem título
        r = await P(db, u, scope, cliente=cli, itens=[{"sku": sku, "qtd": 1}])
        if not r.get("erro"):
            falhas.append("orçamento SEM TÍTULO foi aceito")

        # 3 · item do Bling sem valor
        if bling:
            r = await P(db, u, scope, cliente=cli, titulo=titulo,
                        itens=[{"sku": bling, "qtd": 1}])
            if not r.get("erro"):
                falhas.append(f"item do Bling {bling} sem valor foi aceito — sairia a zero")
        else:
            print("  (tabela `products` vazia — bloco do Bling não exercitado)")

        # 4 · quantidade zero
        r = await P(db, u, scope, cliente=cli, titulo=titulo,
                    itens=[{"sku": sku, "qtd": 0}])
        if not r.get("erro"):
            falhas.append("quantidade ZERO foi aceita — `x or 1` a transformaria em 1")

        # 5 · válido vira rascunho e NADA muda
        n0 = (await db.execute(text("SELECT count(*) FROM proposals"))).scalar()
        i0 = (await db.execute(text("SELECT count(*) FROM proposal_items"))).scalar()
        r = await P(db, u, scope, cliente=cli, titulo=titulo,
                    itens=[{"sku": sku, "qtd": 2},
                           {"descricao": "Instalação", "qtd": 1, "valor_unit": 500.0,
                            "tipo": "servico"}])
        draft_id = r.get("draft_id") or r.get("id")
        if not draft_id:
            falhas.append(f"caso válido não virou rascunho: {str(r)[:110]}")
        n1 = (await db.execute(text("SELECT count(*) FROM proposals"))).scalar()
        i1 = (await db.execute(text("SELECT count(*) FROM proposal_items"))).scalar()
        if (n0, i0) != (n1, i1):
            falhas.append(f"A PROPOSTA GRAVOU: proposals {n0}→{n1}, itens {i0}→{i1}")

        esperado = preco * 2 + 500.0

        # 7 · preço CONGELADO: mexemos no catálogo ENTRE propor e aprovar.
        await db.execute(text(
            "UPDATE crm_products SET unit_price = unit_price + 1000 WHERE sku = :s"),
            {"s": sku})
        await db.commit()
        try:
            # 6 · aprovar grava
            if draft_id:
                d = (await db.execute(select(AgentDraft).where(
                    AgentDraft.id == draft_id))).scalar_one()
                pid = await executar_rascunho(db, u, d)
                await db.commit()
                if not pid:
                    falhas.append("aprovar NÃO devolveu id de proposta")
                else:
                    row = (await db.execute(text(
                        "SELECT number, proposal_type, total FROM proposals "
                        "WHERE id = :i"), {"i": pid})).first()
                    if not row or not row[0]:
                        falhas.append("proposta gravada sem NÚMERO")
                    if row and str(row[1]) != "mixed":
                        falhas.append(f"tipo {row[1]!r} — material + serviço tem de ser "
                                      f"'mixed', não o default do schema")
                    if row and abs(float(row[2] or 0) - esperado) > 0.01:
                        falhas.append(f"PREÇO NÃO FICOU CONGELADO: gravou {row[2]} e o "
                                      f"proposto era {esperado} (o catálogo mudou no meio)")
                    codes = (await db.execute(text(
                        "SELECT code FROM proposal_items WHERE proposal_id = :i "
                        "ORDER BY sort_order"), {"i": pid})).scalars().all()
                    if not codes or codes[0] != sku:
                        falhas.append(f"`code` do item não veio do catálogo: {codes!r} "
                                      f"— era esse campo que estava 0 de 162")
        finally:
            await db.execute(text(
                "UPDATE crm_products SET unit_price = unit_price - 1000 WHERE sku = :s"),
                {"s": sku})
            await db.commit()

        await _limpar(db)
        # Prova de que o desmonte funcionou — contar depois de limpar, não antes.
        sobrou = (await db.execute(text(
            "SELECT count(*) FROM proposals WHERE title LIKE :m"),
            {"m": f"%{_MARCA}%"})).scalar()
        if sobrou:
            falhas.append(f"desmonte deixou {sobrou} proposta(s) com a marca")

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK criar_orcamento: 7/7 — recusa cliente inexistente, título vazio, item do "
          "Bling sem valor e quantidade zero; o válido é INERTE; aprovar grava proposta "
          "com número, tipo 'mixed' derivado das linhas, `code` do catálogo no item, e o "
          "preço CONGELADO mesmo com o catálogo alterado entre propor e aprovar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
