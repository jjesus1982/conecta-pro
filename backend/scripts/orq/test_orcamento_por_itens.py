#!/usr/bin/env python3
"""Oráculo do ORÇAMENTO POR ITENS — material, produto e projeto.

O buraco que isto fecha (medido em 27/08/2026):

    proposal_items          162 itens em 33 propostas
      code preenchido         0    ← nenhum item veio de catálogo
      nomes distintos       116    ← 46 itens eram REDIGITAÇÃO
    crm_products              0    ← tabela + 4 rotas CRUD prontas, VAZIA

O Jordan já fazia orçamento de NVR, câmera bullet, HD Purple, fibra e torre — digitando
cada linha, toda vez. E `build_orcamento_pdf` já sabia montar N itens com
tipo material|servico desde sempre. A capacidade não faltava: faltava porta.

⭐ O QUE ESTE ORÁCULO PROTEGE é a origem do PREÇO. Um orçamento é um número que vai para o
cliente; se o modelo puder arbitrar valor, ele arbitra. As duas únicas fontes legítimas
são o CATÁLOGO (preço praticado, com a proposta de origem carimbada) e um valor que a
PESSOA informou. Qualquer terceiro caminho é fabricação.

Sete invariantes:
  1. SKU inexistente é RECUSADO (não vira descrição livre a preço zero)
  2. item sem SKU e sem valor é RECUSADO (o modelo não estima preço)
  3. cliente inexistente é RECUSADO (nunca cria cliente de passagem)
  4. lista vazia é RECUSADA
  5. o caso válido gera PDF de verdade (header %PDF) e o total FECHA na conta
  6. `valor_unit` informado SOBREPÕE o catálogo (a pessoa manda no preço)
  7. INÉRCIA: gerar orçamento NÃO grava proposta nenhuma

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_orcamento_por_itens.py
"""
from __future__ import annotations

import asyncio
import base64
import sys

sys.path.insert(0, "/app")


async def main() -> int:
    from sqlalchemy import select, text

    from core.database import async_session_factory
    from core.models.user import User
    import modules.ai.conversation.controllers.consultor_escopado_controller as C
    from modules.ai.conversation.services.orquestrador.tool_registry import _REGISTRY
    import modules.ai.conversation.services.orquestrador.tools_comercial_doc  # noqa: F401

    falhas: list[str] = []
    async with async_session_factory() as db:
        if "gerar_orcamento_itens_doc" not in _REGISTRY:
            print("FALHOU: `gerar_orcamento_itens_doc` não está registrada")
            return 1
        h = _REGISTRY["gerar_orcamento_itens_doc"].handler

        u = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalar_one()
        scope, _ = await C._resolver_tier_e_tools(db, u)

        cli = (await db.execute(text("SELECT name FROM clients LIMIT 1"))).scalar()
        prod = (await db.execute(text(
            "SELECT sku, unit_price FROM crm_products "
            "WHERE is_active = true AND unit_price > 0 ORDER BY sku LIMIT 1"))).first()
        if not cli or not prod:
            # Fila vazia não é resultado: sem cliente ou sem catálogo o teste não exercita
            # nada e um "0 falhas" seria verde que não prova coisa alguma.
            print("FALHOU (pré-condição): base sem cliente ou catálogo vazio — rode "
                  "scripts/orq/semear_catalogo_de_propostas.py --gravar")
            return 1
        sku, preco_cat = prod[0], float(prod[1])

        # 1 · SKU inexistente
        r = await h(db, u, scope, cliente_nome=cli, itens=[{"sku": "CAT-ZZNAOEXISTE"}])
        if r.get("status") != "recusado":
            falhas.append("SKU inexistente foi ACEITO — viraria linha a preço zero no PDF")

        # 2 · sem SKU e sem valor → o modelo teria de estimar
        r = await h(db, u, scope, cliente_nome=cli,
                    itens=[{"descricao": "Uma coisa qualquer", "qtd": 2}])
        if r.get("status") != "recusado":
            falhas.append("item sem SKU e sem valor foi ACEITO — o modelo arbitrou preço")

        # 3 · cliente inexistente
        r = await h(db, u, scope, cliente_nome="ZZ_NAO_EXISTE_NO_CADASTRO",
                    itens=[{"sku": sku, "qtd": 1}])
        if r.get("status") != "recusado":
            falhas.append("cliente inexistente foi aceito")

        # 4 · lista vazia
        r = await h(db, u, scope, cliente_nome=cli, itens=[])
        if r.get("status") != "recusado":
            falhas.append("lista de itens vazia foi aceita")

        # 5 · válido: PDF real e total que fecha
        n0 = (await db.execute(text("SELECT count(*) FROM proposals"))).scalar()
        i0 = (await db.execute(text("SELECT count(*) FROM proposal_items"))).scalar()
        r = await h(db, u, scope, cliente_nome=cli, titulo="Oráculo — orçamento por itens",
                    itens=[{"sku": sku, "qtd": 3},
                           {"descricao": "Frete", "qtd": 1, "valor_unit": 250.0,
                            "tipo": "servico"}])
        if r.get("status") == "recusado":
            falhas.append(f"caso VÁLIDO recusado: {r.get('motivo', '')[:100]}")
        else:
            pdf = base64.b64decode(r.get("arquivo_base64") or "")
            if not pdf.startswith(b"%PDF"):
                falhas.append(f"não saiu PDF de verdade (começa com {pdf[:8]!r})")
            if len(pdf) < 5000:
                falhas.append(f"PDF suspeito de vazio: {len(pdf)} bytes")
            esperado = preco_cat * 3 + 250.0
            if abs(float(r.get("total") or 0) - esperado) > 0.01:
                falhas.append(f"total NÃO fecha: {r.get('total')} != {esperado}")
            if not r.get("lastro"):
                falhas.append("resposta sem `lastro` — preço sem procedência declarada")

        # 6 · valor informado sobrepõe o catálogo
        outro = preco_cat + 1234.56
        r = await h(db, u, scope, cliente_nome=cli,
                    itens=[{"sku": sku, "qtd": 1, "valor_unit": outro}])
        if r.get("status") == "recusado":
            falhas.append(f"valor informado sobre SKU foi recusado: {r.get('motivo', '')[:80]}")
        elif abs(float(r.get("total") or 0) - outro) > 0.01:
            falhas.append(f"`valor_unit` informado NÃO sobrepôs o catálogo: "
                          f"{r.get('total')} != {outro}")

        # 7 · INÉRCIA — a maior de todas: gerar não grava
        n1 = (await db.execute(text("SELECT count(*) FROM proposals"))).scalar()
        i1 = (await db.execute(text("SELECT count(*) FROM proposal_items"))).scalar()
        if (n0, i0) != (n1, i1):
            falhas.append(f"GRAVOU ao gerar: proposals {n0}→{n1}, itens {i0}→{i1}")

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK orcamento_por_itens: 7/7 — recusa SKU fantasma, recusa item sem preço "
          "(não estima), recusa cliente inexistente e lista vazia; o válido sai em PDF "
          "com o total fechando e o lastro do preço; valor informado manda no catálogo; "
          "e gerar NÃO grava proposta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
