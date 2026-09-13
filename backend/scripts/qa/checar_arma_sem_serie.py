#!/usr/bin/env python3
"""Arma que existe como NÚMERO, não como controle (frente 05, 12/09/2026).

`4/4 armas` só significa algo com série por arma, responsável, entrega e devolução datadas. Hoje
o cadastro tem `employees.porte_arma` (flag) e `posts.requires_armed` (flag): nenhum dos dois
responde "onde está a arma 3". Este caçador conta:

  · funcionário ativo com `porte_arma`/`porte_arma_numero` no cadastro e NENHUMA arma com série
    entregue a ele (`equipamentos_controlados_alocacoes` aberta, tipo armamento);
  · gente escalada HOJE em posto `requires_armed` sem arma em posse.

Medido no nascimento (staging = produção): 0 flags de porte, 0 postos armados → TOTAL 0. Verde
de propósito, como `checar_contrato_sem_cobranca`: a trava existe para acusar no dia em que o
primeiro flag aparecer sem a série atrás. A régua é a do serviço, importada, não copiada.

Roda no container (CACADORES): PYTHONPATH=/app python3 scripts/qa/checar_arma_sem_serie.py
"""

from __future__ import annotations

import asyncio
import sys

sys.path.append("/app")  # depois do cwd/PYTHONPATH: no container é /app mesmo; fora dele não atropela


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.people_management.hr.services import conformidade_vigilante as cv

    async with async_session_factory() as db:
        if not (
            await db.execute(text("SELECT to_regclass('equipamentos_controlados_alocacoes') IS NOT NULL"))
        ).scalar():
            print("DDL da frente 05 não aplicado — nenhuma arma pode ter série (ver FRENTE_05_vigilante.md)")
            print("TOTAL armas sem série/responsável: 1")
            return 1
        linhas = await cv.armas_sem_controle(db)

    for r in linhas:
        print(f"🔫 {r['nome']} — {r['motivo']}")
    print(f"TOTAL armas sem série/responsável: {len(linhas)}")
    return 1 if linhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
