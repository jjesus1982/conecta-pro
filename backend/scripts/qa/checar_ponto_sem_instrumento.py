#!/usr/bin/env python3
"""Quem bateu ponto este mês SEM linha AFD (a partir do corte do REP-P)?

Nasceu em 12/09/2026 (frente 01). O AFD começa em 13/09/2026 00:00 Manaus e vai para frente;
antes disso não há instrumento nenhum — 52 pessoas batiam num programa que não era REP-P.
A partir do corte, pessoa com batida e sem linha AFD é dívida: ou o gerador não rodou, ou o
cadastro não tem CPF (sem CPF não há linha, e CPF não se inventa).

Roda no container (PYTHONPATH=/app). Linha canônica: `TOTAL pessoas sem instrumento: N`. Sai 1 se N>0.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    try:
        from modules.hr.rep_integration.services.rep_p import CORTE
    except Exception:  # noqa: BLE001 — sem o módulo, ninguém gera AFD: conta tudo desde o corte
        CORTE = datetime.fromisoformat(os.environ.get("REP_P_CORTE", "2026-09-13T00:00:00"))
    hoje = datetime.now(ZoneInfo("America/Manaus"))
    desde = max(CORTE, datetime(hoje.year, hoje.month, 1))

    gen = get_db()
    db = await gen.__anext__()
    rows = (await db.execute(text("""
        SELECT e.nome, count(*) batidas,
               length(regexp_replace(coalesce(e.cpf,''),'\\D','','g')) = 11 tem_cpf
        FROM gp_clock_punches p JOIN employees e ON e.id = p.employee_id
        LEFT JOIN afd_records a ON a.punch_id = p.punch_id
        WHERE p.punch_timestamp >= :d AND a.id IS NULL
        GROUP BY 1, 3 ORDER BY 2 DESC"""), {"d": desde})).all()
    for nome, n, cpf in rows[:20]:
        print(f"  {nome}: {n} batida(s) sem AFD{'' if cpf else ' — SEM CPF no cadastro'}")
    if len(rows) > 20:
        print(f"  (+{len(rows) - 20} não listadas)")
    print(f"TOTAL pessoas sem instrumento: {len(rows)}  (desde {desde:%d/%m/%Y})")
    return 1 if rows else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
