#!/usr/bin/env python3
"""Observação INTERNA saindo no documento que vai ao CLIENTE.

Achado pelo Cowork em 11/09/2026, e ele só pôde achar porque a correção CP-MCP-005 passou a
devolver o TEXTO do documento — antes só vinha um link que o agente não conseguia abrir.

A PROP-2026-00114 (Ração Confiança), marcada "— CONFIDENCIAL —", carregava no
`payment_terms` — campo que o PDF renderiza como condições de pagamento PARA O CLIENTE:

    "OBS INTERNA: custos de equipamento são ESTIMATIVA de mercado — substituir pela cotação
     real VTV antes de assinar. Margem atual 34,3%."

Se a proposta tivesse sido enviada, o cliente leria a margem antes de negociar o preço.

⭐ MEDE O TEXTO DO DOCUMENTO, não a coluna. Uma varredura por coluna acerta o caso que já
conheço e perde o próximo, que vai estar em `terms_conditions`, num item, ou numa variável
do modelo. A pergunta certa é "isto aparece no papel?", e o papel é o que o render produz.

⚠️ SEM FALSO POSITIVO BARATO: "margem" aparece legitimamente em texto técnico ("margem de
segurança", "margem da via"). Por isso os padrões exigem CONTEXTO — "margem atual", "margem
de lucro", "OBS INTERNA", "não enviar" — e não a palavra solta.

    python3 backend/scripts/qa/checar_vazamento_interno.py
"""
from __future__ import annotations

import asyncio
import re
import sys

sys.path.insert(0, "/app")

# Cada padrão é uma decisão registrada: o que NUNCA pode chegar ao cliente.
PROIBIDO = (
    (r"OBS\.?\s*INTERNA", "observação marcada como interna"),
    (r"\buso interno\b", "texto declarado de uso interno"),
    (r"n[ãa]o\s+enviar", "anotação de 'não enviar'"),
    (r"margem\s+(atual|de\s+lucro|bruta|l[íi]quida)", "MARGEM — o cliente negocia sabendo o quanto cabe"),
    (r"\bmark[- ]?up\b", "markup"),
    (r"custo\s+real\b", "custo real"),
    (r"\bcotaç[ãa]o\s+real\b", "referência a cotação interna"),
)


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    achados: list[str] = []
    verificadas = 0
    async with async_session_factory() as db:
        props = (await db.execute(text(
            "SELECT number FROM proposals WHERE coalesce(is_active, true) "
            "ORDER BY created_at DESC LIMIT 60"))).scalars().all()
        if not props:
            print("NÃO VERIFICADO: nenhuma proposta ativa.")
            return 0
        for numero in props:
            # o texto do CLIENTE: junta o que o render manda para o papel
            linha = (await db.execute(text(
                "SELECT concat_ws(' | ', title, description, payment_terms, "
                "payment_conditions, terms_conditions) FROM proposals WHERE number = :n"),
                {"n": numero})).scalar() or ""
            itens = (await db.execute(text(
                "SELECT coalesce(string_agg(concat_ws(' ', name, description), ' | '), '') "
                "FROM proposal_items WHERE proposal_id = "
                "(SELECT id FROM proposals WHERE number = :n)"), {"n": numero})).scalar() or ""
            texto = f"{linha} | {itens}"
            verificadas += 1
            for padrao, rotulo in PROIBIDO:
                if (m := re.search(padrao, texto, re.I)):
                    trecho = texto[max(m.start() - 40, 0):m.start() + 90].replace("\n", " ")
                    achados.append(f"{numero} · {rotulo}\n        …{trecho}…")

    for a in achados:
        print(f"  🔴 {a}")
    print(f"\nTOTAL propostas com texto interno no material do cliente: {len(achados)} "
          f"(de {verificadas} verificadas)")
    if achados:
        print("  Mova para `notes` (interno) ou `margin_percent`. Nada se perde — muda de lugar.")
        print("FAIL checar_vazamento_interno")
        return 1
    print("OK checar_vazamento_interno")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
