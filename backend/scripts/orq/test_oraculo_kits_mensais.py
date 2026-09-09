"""Oráculo — o fluxo automático dos kits PRODUZIU este mês? (08/09/2026)

Afirma a REGRA, não a fotografia:
  1. Dia 1 (cron gerar_kits_mensais.sh): a partir do dia 2, o mês corrente tem kits em ged_document_kits para os
     clientes ativos com funcionários alocados — e o log do cron NÃO terminou em [ERROR] na última execução.
  2. Dia 21 (beat ged.auto_collect_documents): a partir do dia 22, ged_coleta_logs tem uma execução do tipo
     'cron' (ou 'manual') do mês corrente com status de sucesso.
Por que existe: o cron do dia 1 falhou no login de junho a setembro de 2026 e a coleta de 21/08 estourou numa
transação abortada — os dois em silêncio (só o sino do task_falha viu o segundo). Este oráculo fica vermelho no dia
seguinte a qualquer um dos dois não produzir.
Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho; imprime o motivo.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    gen = get_db()
    db = await gen.__anext__()
    hoje = date.today()
    comp = hoje.replace(day=1)
    falhas: list[str] = []

    # 1) kits do mês (dia 1)
    if hoje.day >= 2:
        n_kits = (await db.execute(text("SELECT count(*) FROM ged_document_kits WHERE reference_month = :m"), {"m": comp})).scalar() or 0
        n_cli = (await db.execute(text(
            "SELECT count(DISTINCT g.id) FROM ged_clients g WHERE coalesce(g.is_active, true)"))).scalar() or 0
        if n_kits == 0:
            falhas.append(f"dia 1: nenhum kit de {comp:%m/%Y} em ged_document_kits ({n_cli} cliente(s) GED ativos) — o cron gerar_kits_mensais.sh não produziu")
        else:
            print(f"OK dia 1: {n_kits} kit(s) de {comp:%m/%Y} ({n_cli} clientes GED ativos)")
        log = "/var/log/conecta-pro/kits_mensais.log"
        if os.path.exists(log):
            ult = [l for l in open(log, errors="ignore").read().splitlines() if "[START]" not in l][-1:]
            if ult and "[ERROR]" in ult[0]:
                falhas.append(f"dia 1: última execução do cron terminou em erro — {ult[0][:160]}")
    else:
        print("dia 1: ainda é dia 1 — sem cobrança")

    # 2) coleta do dia 21
    if hoje.day >= 22:
        row = (await db.execute(text(
            "SELECT run_at, status FROM ged_coleta_logs WHERE run_type IN ('cron','manual','auto') "
            "AND date_trunc('month', run_at AT TIME ZONE 'America/Manaus') = :m ORDER BY run_at DESC LIMIT 1"), {"m": comp})).first()
        if not row:
            falhas.append(f"dia 21: nenhuma coleta (cron/manual) registrada em ged_coleta_logs para {comp:%m/%Y} — o beat ged.auto_collect_documents não produziu")
        elif str(row[1]).lower() not in ("success", "ok", "sucesso"):
            falhas.append(f"dia 21: última coleta de {comp:%m/%Y} terminou em '{row[1]}' ({row[0]})")
        else:
            print(f"OK dia 21: coleta de {comp:%m/%Y} em {row[0]} status={row[1]}")
    else:
        print("dia 21: ainda não chegou — sem cobrança")

    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} etapa(s) do fluxo automático dos kits não produziu(ram)")
    print("OK oráculo kits mensais")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
