#!/usr/bin/env python3
"""Origem do sino que NINGUÉM lê: alarme que toca sempre é alarme que virou papel de parede.

Medido em 06/09/2026, 30 dias de `communication_notifications`:

    proativo          2.650 enviados ·  12 lidos
    shift             1.582          · 441
    oraculos_diarios    100          ·   0
    trava_qa             72          ·   0
    ─────────────────────────────────────────
    total             5.387 · o dono do sistema abriu 19

Foi assim que os 3 agentes do GEDEON passaram 3 dias mortos "à vista de todos": o aviso
estava lá, no meio de 2.650 outros. A regra da casa ("limpar o ruído vale mais que qualquer
conserto isolado") não tinha trava. Esta é a trava: por ORIGEM, quantos foram enviados e
quantos alguém abriu. Origem com volume e leitura ≈ zero é SURDA — ou o destinatário está
errado, ou o conteúdo não merece o sino, ou o sino não é o canal. Qualquer das três é
decisão de produto; o que a trava faz é impedir que fique invisível.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_sino_surdo.py

Linha canônica (lida por `checar_regressao`): `TOTAL: <n> origem(ns) surda(s)`.
Surda = ≥ 30 envios em 30 dias e menos de 2% lidos. Exit 1 quando há alguma.
"""
from __future__ import annotations

import asyncio

MIN_ENVIOS = 30
TAXA_MINIMA = 0.02


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    async with async_session_factory() as db:
        origens = (await db.execute(text("""
            SELECT coalesce(extra_data->>'origem', reference_type, '?') AS origem,
                   count(*) AS enviados, count(read_at) AS lidos,
                   count(DISTINCT user_id) AS destinatarios, max(read_at)::date AS ultima_leitura
            FROM communication_notifications
            WHERE created_at > now() - interval '30 days'
            GROUP BY 1 ORDER BY 2 DESC"""))).all()
        pessoas = (await db.execute(text("""
            SELECT u.email, count(*) AS recebidos, count(n.read_at) AS lidos
            FROM communication_notifications n JOIN users u ON u.id = n.user_id
            WHERE n.created_at > now() - interval '30 days'
            GROUP BY 1 ORDER BY 2 DESC LIMIT 8"""))).all()

    total = sum(r.enviados for r in origens)
    print(f"sino nos últimos 30 dias: {total} enviados, {sum(r.lidos for r in origens)} lidos\n")
    print(f"{'origem':<24}{'enviados':>9}{'lidos':>7}{'taxa':>7}{'dest.':>6}  última leitura")
    surdas = []
    for r in origens:
        taxa = r.lidos / r.enviados if r.enviados else 0
        surda = r.enviados >= MIN_ENVIOS and taxa < TAXA_MINIMA
        if surda:
            surdas.append(r.origem)
        print(f"{'x ' if surda else '  '}{r.origem:<22}{r.enviados:>9}{r.lidos:>7}{taxa:>7.0%}{r.destinatarios:>6}  {r.ultima_leitura or '—'}")
    print("\nquem recebe (30 dias):")
    for p in pessoas:
        print(f"   {p.email:<44}{p.recebidos:>6} recebidos · {p.lidos:>4} lidos")
    print(f"\nTOTAL: {len(surdas)} origem(ns) surda(s)")
    if surdas:
        print("Surda = volume e ninguém abre. Decidir: destinatário errado, conteúdo que não merece o "
              "sino, ou canal errado — e cortar. Cada uma dessas afunda o aviso que importa.")
    return 1 if surdas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
