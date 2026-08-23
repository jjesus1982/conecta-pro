#!/usr/bin/env python3
"""Re-embed do índice do GEDEON para o modelo LOCAL (384d) — e a prova de que não piorou.

Por que existe: até 23/08/2026 o RAG gerava embedding pela OpenAI (`text-embedding-3-large`
travado em 1536d). O container `conecta-pro-embedding` já rodava local, multilíngue e de
graça, mas ligá-lo sem reindexar misturaria espaços vetoriais — e a busca comparava
dimensões diferentes descartando o doc em silêncio.

Modo de uso:
    python3 scripts/qa/reembed_local.py --medir      # só mede a recuperação de hoje
    python3 scripts/qa/reembed_local.py --aplicar    # reindexa e mede de novo

A medição é a parte que importa. Trocar o motor de embedding sem comparar recuperação é
trocar no escuro: o índice continua "populado" e o RAG passa a devolver o documento errado
sem nenhum erro aparecer.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from core.database import async_session_factory

MODELO_LOCAL = "local_minilm_384"

# Consultas de aferição: pergunta + trecho que DEVE aparecer no documento certo. Não medem
# "achou algo", medem "achou o que era" — recuperação que devolve qualquer coisa com score
# alto é o modo de falhar mais comum aqui.
SONDAS = [
    ("qual o piso salarial do agente de portaria", ["piso", "portaria", "cct"]),
    ("como calcular adicional noturno", ["noturno", "adicional"]),
    ("prazo de entrega do eSocial S-1200", ["esocial", "s-1200", "prazo"]),
    ("o que fazer quando o funcionário falta sem justificativa", ["falta", "justific"]),
    ("qual o prazo do aviso prévio", ["aviso", "prévio"]),
    ("como emitir nota fiscal de serviço", ["nfs", "nota", "fiscal"]),
]


async def _medir(db) -> dict:
    """Roda as sondas e devolve quantas trouxeram documento pertinente."""
    from modules.gedeon.agents.sophia import Sophia  # noqa: PLC0415

    ag = Sophia()
    acertos, total, detalhe = 0, 0, []
    for pergunta, esperado in SONDAS:
        total += 1
        try:
            # `buscar` é síncrono e usa conexão própria; threshold baixo de propósito —
            # a sonda mede se o doc CERTO aparece entre os 3 primeiros, não o score
            res = await asyncio.to_thread(ag.buscar, pergunta, 3, None, 0.05)
        except Exception as e:  # noqa: BLE001
            detalhe.append((pergunta, f"ERRO {str(e)[:60]}"))
            continue
        blob = " ".join(str(r) for r in (res or [])).lower()
        ok = any(t in blob for t in esperado)
        acertos += 1 if ok else 0
        detalhe.append((pergunta, "acertou" if ok else "não achou"))
    return {"acertos": acertos, "total": total, "detalhe": detalhe}


async def _reembed(db) -> dict:
    from modules.ai.conversation.services.embedding_local import embed_local  # noqa: PLC0415

    linhas = (await db.execute(text(
        # a coluna do texto é `texto_preview` — não existe `conteudo` nesta tabela
        "SELECT id::text, coalesce(texto_preview, '') AS texto, embedding_model "
        "FROM gedeon_document_index "
        "WHERE embedding IS NOT NULL AND coalesce(embedding_model,'') <> :m "
        "ORDER BY id"), {"m": MODELO_LOCAL})).mappings().all()
    if not linhas:
        return {"convertidos": 0, "resumo": "nada a converter — índice já está local"}

    convertidos, vazios, lote = 0, 0, 64
    for i in range(0, len(linhas), lote):
        bloco = linhas[i:i + lote]
        textos = [(r["texto"] or "")[:8000] for r in bloco]
        vetores = embed_local(textos)
        if not vetores or len(vetores) != len(bloco):
            raise RuntimeError(
                f"o serviço local devolveu {len(vetores or [])} vetores para {len(bloco)} "
                "textos — abortando para não gravar índice pela metade")
        for r, v in zip(bloco, vetores, strict=True):
            if not v:
                vazios += 1
                continue
            await db.execute(text(
                # esta tabela usa `updated_at`; `embedding_updated_at` existe em ai_kb_*
                "UPDATE gedeon_document_index SET embedding = :v, embedding_model = :m, "
                "embedding_dim = :d, updated_at = now() WHERE id::text = :i"),
                {"v": v, "m": MODELO_LOCAL, "d": len(v), "i": r["id"]})
            convertidos += 1
        print(f"    {min(i + lote, len(linhas))}/{len(linhas)}…", flush=True)
    await db.commit()
    return {"convertidos": convertidos, "vazios": vazios,
            "resumo": f"{convertidos} documento(s) reindexado(s) em 384d"}


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    async with async_session_factory() as db:
        composicao = (await db.execute(text(
            "SELECT coalesce(embedding_model,'(sem modelo)'), count(*) "
            "FROM gedeon_document_index WHERE embedding IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
        ))).all()
        print("Índice hoje:")
        for m, n in composicao:
            print(f"  {m}: {n}")

        print("\nRecuperação ANTES:")
        antes = await _medir(db)
        for p, r in antes["detalhe"]:
            print(f"  [{r}] {p}")
        print(f"  => {antes['acertos']}/{antes['total']}")

        if not aplicar:
            print("\n(modo medição — rode com --aplicar para reindexar)")
            return 0

        print("\nReindexando para o modelo local…")
        r = await _reembed(db)
        print(f"  {r['resumo']}")

        print("\nRecuperação DEPOIS:")
        depois = await _medir(db)
        for p, res in depois["detalhe"]:
            print(f"  [{res}] {p}")
        print(f"  => {depois['acertos']}/{depois['total']}")

        piorou = depois["acertos"] < antes["acertos"]
        print(f"\n{'⚠️  PIOROU' if piorou else '✅ mantido ou melhor'}: "
              f"{antes['acertos']}/{antes['total']} → {depois['acertos']}/{depois['total']}")
        return 1 if piorou else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
