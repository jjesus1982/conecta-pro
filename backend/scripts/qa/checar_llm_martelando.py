#!/usr/bin/env python3
"""Rotina que MARTELA o provedor de LLM falhando — 30 mil chamadas por dia sem uma resposta.

Medido em 07/09/2026 (`llm_usage`, origem llm_provider): 04/09 30.800 chamadas e 0 ok;
05/09 31.616 e 0; 06/09 32.877 e 0. O redator do proativo chamava o LLM para cada achado a
cada 15 minutos com o provedor sem crédito; caía no template e seguia. Nenhuma trava via:
não é código morto, não é número mentiroso, não é beat que não produz — é beat que produz
falha em loop, e a única evidência era a fatura que não subia.

Regra: por ORIGEM, nas últimas 24h, mais de LIMIAR chamadas com menos de 5% de sucesso é
martelo. Fonte: a própria telemetria (`llm_usage`), nada de fora.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_llm_martelando.py

Linha canônica: `TOTAL: <n> origem(ns) martelando`. Exit 1 se houver.
"""
from __future__ import annotations

import asyncio

LIMIAR = 500
TAXA_MINIMA = 0.05


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    async with async_session_factory() as db:
        rows = (await db.execute(text("""
            SELECT origem, count(*) AS n, count(*) FILTER (WHERE ok) AS oks,
                   left(min(erro) FILTER (WHERE NOT ok), 60) AS erro
            FROM llm_usage WHERE criado_em > now() - interval '24 hours'
            GROUP BY 1 ORDER BY 2 DESC"""))).all()
    martelos = []
    print(f"{'origem':<24}{'24h':>8}{'ok':>7}{'taxa':>7}  erro")
    for r in rows:
        taxa = (r.oks / r.n) if r.n else 0
        m = r.n >= LIMIAR and taxa < TAXA_MINIMA
        if m:
            martelos.append(r.origem)
        print(f"{'x ' if m else '  '}{r.origem:<22}{r.n:>8}{r.oks:>7}{taxa:>7.0%}  {r.erro or ''}")
    print(f"\nTOTAL: {len(martelos)} origem(ns) martelando")
    return 1 if martelos else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
