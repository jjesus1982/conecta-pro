#!/usr/bin/env python3
"""Observação INTERNA saindo no documento que vai ao CLIENTE.

Achado pelo Cowork em 11/09/2026, e ele só pôde achar porque a correção CP-MCP-005 passou a
devolver o TEXTO do documento — antes só vinha um link que o agente não conseguia abrir.

A PROP-2026-00114 (Ração Confiança), marcada "— CONFIDENCIAL —", carregava no
`payment_terms` — campo que o PDF renderiza como condições de pagamento PARA O CLIENTE:

    "OBS INTERNA: custos de equipamento são ESTIMATIVA de mercado — substituir pela cotação
     real VTV antes de assinar. Margem atual 34,3%."

Se a proposta tivesse sido enviada, o cliente leria a margem antes de negociar o preço.

⭐ MEDE O TEXTO DO DOCUMENTO — e a primeira versão desta trava NÃO fazia isso.

Eu escrevi exatamente esta frase no cabeçalho e, logo abaixo, varri COLUNAS: title,
description, payment_terms, payment_conditions, terms_conditions. Deixei `notes` de fora
porque ACHEI que `notes` era interno. Horas depois movi a observação de margem de
`payment_terms` para `notes` — e `notes` é impresso como "Observações" no PDF do cliente.
A trava disse "0 propostas com texto interno" enquanto o texto estava no papel. O Cowork
pegou; eu não, porque a trava media o que eu acreditava e não o que sai.

Agora ela RENDERIZA a proposta e lê o texto que o cliente receberia. Mais lenta e sem
opinião: se está no papel, ela vê, venha de que coluna vier.

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
    # ⭐ MARGEM SEGUIDA DE NÚMERO. A versão anterior exigia contexto — "margem atual",
    # "margem de lucro" — justamente para não acusar "margem de segurança". Essa escolha
    # criou o FALSO NEGATIVO no caso real: o Cowork achou "Margem 12,5% na portaria e 15%
    # nos demais" na PROP-2026-00097, status `sent`, JÁ ENTREGUE ao cliente. Meu padrão não
    # casou com nada ali.
    #
    # O que separa é o NÚMERO: "margem de segurança" não tem percentual atrás; "Margem
    # 12,5%" tem. Distingue sem inflar — e evitar falso positivo ao preço de perder o caso
    # real é o pior negócio possível numa trava.
    (r"margem\s*(?:de\s+lucro\s*)?(?:é|de|:)?\s*\d{1,3}[.,]?\d*\s*%",
     "MARGEM COM PERCENTUAL — o cliente negocia sabendo o quanto cabe"),
    (r"margem\s+(atual|de\s+lucro|bruta|l[íi]quida)", "margem declarada"),
    (r"\bmark[- ]?up\b", "markup"),
    (r"custo\s+real\b", "custo real"),
    (r"\bcotaç[ãa]o\s+real\b", "referência a cotação interna"),
    # e-mail de TERCEIRO no documento do cliente: o da nossa contabilidade não é da conta
    # dele, e sai junto quando alguém escreve "e-mail de cópia" num campo que vai ao papel.
    (r"porttecontabil|e-?mail\s+de\s+c[óo]pia", "e-mail de terceiro/contabilidade"),
)


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    achados: list[str] = []
    verificadas = 0
    async with async_session_factory() as db:
        # ⚠️ A BASE INTEIRA, não as 60 mais recentes — e TODOS os status. O caso real
        # (PROP-2026-00097) já estava `sent`, e limitar a 60 recentes é como decidir que o
        # que já saiu não importa mais. Importa mais: aquele o cliente já leu.
        props = (await db.execute(text(
            "SELECT number FROM proposals WHERE coalesce(is_active, true) "
            "ORDER BY created_at DESC"))).scalars().all()
        if not props:
            print("NÃO VERIFICADO: nenhuma proposta ativa.")
            return 0
        from modules.crm.repositories.proposal_repository import ProposalRepository
        from modules.crm.services.proposal_pdf import build_proposal_pdf

        for numero in props:
            # ⭐ O PAPEL, não as colunas. Renderiza e extrai o texto que o cliente leria.
            pid = (await db.execute(text(
                "SELECT id FROM proposals WHERE number = :n"), {"n": numero})).scalar()
            try:
                prop = await ProposalRepository(db).get_by_id(str(pid))
                from modules.crm.services.docs_registry import extrair_de_bytes

                texto, _, _ = extrair_de_bytes(build_proposal_pdf(prop), "pdf")
            except Exception as e:  # noqa: BLE001
                # não conseguir renderizar é achado, não silêncio: uma proposta que o
                # cliente não recebe é outro problema, mas alguém precisa saber.
                achados.append(f"{numero} · NÃO CONSEGUI RENDERIZAR para conferir: "
                               f"{type(e).__name__}: {str(e)[:80]}")
                continue
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
        # ⚠️ Esta linha já mandou "mova para `notes`" — e `notes` é impresso como
        # "Observações" no PDF do cliente, como o próprio cabeçalho deste arquivo conta.
        # O rodapé contradizia o docstring e mandava o próximo repetir o erro exato: em
        # 25/09/2026 uma anotação minha («Preços já definidos pelo dono; sem markup
        # adicional») foi parar no `notes` da PROP-2026-00125 e saiu no papel do condomínio.
        print("  NÃO mova para `notes`: ele é impresso como «Observações» no PDF do cliente.")
        print("  A tabela `proposals` não tem campo interno. Ou o texto sai da proposta")
        print("  (vai para o deal/oportunidade, ou para o commit), ou é reescrito para dizer")
        print("  só o que o cliente pode ler. Nada de margem, custo, markup ou fornecedor.")
        print("FAIL checar_vazamento_interno")
        return 1
    print("OK checar_vazamento_interno")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
