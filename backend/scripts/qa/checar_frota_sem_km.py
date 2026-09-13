#!/usr/bin/env python3
"""Veículo ativo sem leitura de KM no período (frente 10, 12/09/2026).

O painel de manutenção da frota (`Restam` = KM até a próxima troca) só vale com quilometragem
alimentada. Sem leitura, o painel mostra "sem dado" — de propósito, nunca "vencido" — e a troca
de óleo passa despercebida do mesmo jeito. Este caçador conta essa dívida.

Período = `PERIODO_KM_DIAS` de `_frente_10` (a mesma régua que o painel usa para decidir entre
`Restam` e "sem dado"). Leitura = qualquer linha em `frota_leituras` (km ou abastecimento).

Sem tabela = vermelho: o DDL da frente ainda não entrou, e o que não existe não pode estar limpo.

    docker exec -e PYTHONPATH=/app conecta-pro-backend-staging python3 /app/scripts/qa/checar_frota_sem_km.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.append("/app")  # append, não insert(0): deixa um PYTHONPATH de bancada vencer


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.operacional.controllers.redesign_builders._frente_10 import PERIODO_KM_DIAS

    async with async_session_factory() as db:
        if not (await db.execute(text("SELECT to_regclass('public.frota_veiculos')"))).scalar():
            print("tabela frota_veiculos ausente — DDL da frente 10 não aplicado")
            print("TOTAL veículos sem KM no período: ? (sem tabela)")
            print("FAIL checar_frota_sem_km")
            return 1
        rows = (await db.execute(text(
            "SELECT v.placa, coalesce(v.modelo,'—'), "
            "(SELECT max(lida_em) FROM frota_leituras l WHERE l.veiculo_id = v.id) "
            "FROM frota_veiculos v WHERE v.ativo AND NOT EXISTS ("
            "  SELECT 1 FROM frota_leituras l WHERE l.veiculo_id = v.id "
            "  AND l.lida_em > now() - make_interval(days => :d)) ORDER BY v.placa"
        ), {"d": PERIODO_KM_DIAS})).fetchall()
        total = (await db.execute(text("SELECT count(*) FROM frota_veiculos WHERE ativo"))).scalar()

    for placa, modelo, ultima in rows:
        print(f"🚗 {placa} · {modelo} · última leitura: {ultima.strftime('%d/%m/%Y') if ultima else 'nunca'}")
    print(f"\nTOTAL veículos sem KM no período: {len(rows)} (de {total} ativo(s), período {PERIODO_KM_DIAS}d)")
    if rows:
        print("FAIL checar_frota_sem_km")
        return 1
    print("OK checar_frota_sem_km")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
