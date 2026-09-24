#!/usr/bin/env python3
"""Oráculo — TODA tela que o backend serve tem porta; TODA ação /redesign/action tem tela (dgx u3, 24/09/2026).

Por que existe: o caçador `scripts/qa/checar_tela_sem_porta.py` mede a PRODUÇÃO — é fotografia:
acusou 13 telas órfãs e 2 ações por semanas, e a leitura só acontecia à meia-noite, depois do
bake. Este oráculo aplica a MESMA régua (importa as funções puras do caçador) ao app IMPORTADO,
com o banco do sandbox, ANTES do bake: uma frente que monta tela depois de `montar_grupos`, ou
esquece o `ctaTo`, fica vermelha aqui, no container efêmero, não na produção do dia seguinte.

O que afirma, por módulo que tem JSON de menu no front:
  1. Para cada tela em `screens` do builder: está no menu do pacote, no `EXTRA_MENU` que o
     controller soma no import, é aba de um grupo, é alvo de `ctaTo` de uma tela de topo com
     `cta`, ou é stub `type: redirect`. Fora disso é TELA SEM PORTA.
  2. Para cada rota `/action/...` do `redesign_data_controller.router` (onde o discovery inclui
     o router de todo builder): algum `submit.endpoint` a referencia, ou o nome aparece no fonte
     dos builders (ação de linha só nasce quando há linha). Fora disso é AÇÃO SEM TELA.
  3. Nenhum módulo é pulado em silêncio: builder que cai é listado como achado (população
     contada — «0 falhas» não pode ser «0 medidos»).

Precisa dos JSONs de menu do front: `QA_MENUS=<dir>` ou `/menus` (montado) ou
`<repo>/frontend/src/app/redesign/_modules` (host). Sem eles: NÃO MEDIDO, exit 2 — nunca verde.

Estado medido no nascimento (sandbox, 24/09/2026, HEAD 7e297d134 sem as portas desta frente):
VERMELHO — 13 telas + 2 ações, os mesmos 15 do caçador em produção. Depois das portas: 0.

Como roda (container efêmero, receita do CONTRATO_AGENTE, + o volume dos menus):
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \\
      -v "$WT/frontend/src/app/redesign/_modules:/menus:ro" -e PYTHONPATH=/app ... \\
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_toda_tela_tem_porta.py
Em produção (após o bake, com o front publicado):
    docker exec -e PYTHONPATH=/app -e QA_MENUS=/menus conecta-pro-backend python3 /app/scripts/orq/...
    (o container de produção não tem o front; o caçador do host cobre esse caso)

Linha canônica: `TOTAL: <n> sem porta`. Exit 0 = verde; 1 = vermelho; 2 = não medido.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
from pathlib import Path
from types import SimpleNamespace

_AQUI = Path(__file__).resolve()
sys.path.insert(0, str(_AQUI.parents[1] / "qa"))  # scripts/qa — as funções puras do caçador
from checar_tela_sem_porta import (  # noqa: E402
    acoes_orfas,
    colhe_endpoints,
    fonte_builders,
    portas_do_menu,
    telas_sem_porta,
)


def _menus() -> Path | None:
    cands = [os.environ.get("QA_MENUS"), "/menus", _AQUI.parents[3] / "frontend/src/app/redesign/_modules"]
    for c in cands:
        if c and Path(c).is_dir() and any(Path(c).glob("*.json")):
            return Path(c)
    return None


async def main() -> int:  # noqa: C901, PLR0912
    menus = _menus()
    if menus is None:
        print("NÃO MEDIDO — JSONs de menu do front não encontrados (QA_MENUS=<dir> ou monte em /menus)")
        return 2

    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415
    from modules.operacional.controllers import redesign_data_controller as RD  # noqa: PLC0415, N812

    achados: list[str] = []
    endpoints: set[str] = set()
    medidos = 0

    async with async_session_factory() as db:
        # usuário REAL (só `current_user.id` é lido pelos builders self-scoped: meu-espaço, portal)
        email = os.environ.get("QA_USER", "jjesus@conectamais.pro")
        uid = (await db.execute(text("SELECT id::text FROM users WHERE email=:e LIMIT 1"), {"e": email})).scalar()
        user = SimpleNamespace(id=uid, email=email, role="admin")

        for arq in sorted(menus.glob("*.json")):
            slug = arq.stem
            builder = RD.BUILDERS.get(slug)
            if not builder:
                continue  # menu sem builder: o payload é {} e nada é servido — não há tela para ter porta
            medidos += 1
            try:
                if "current_user" in inspect.signature(builder).parameters:
                    telas = await builder(db, current_user=user)
                else:
                    telas = await builder(db)
            except Exception as e:  # noqa: BLE001
                await db.rollback()
                achados.append(f"{slug}: builder caiu — {type(e).__name__}: {str(e)[:90]}")
                continue
            raiz = portas_do_menu(menus, slug) | {
                m.get("id") for m in RD.EXTRA_MENU.get(slug, []) if isinstance(m, dict) and m.get("id")
            }
            colhe_endpoints(telas, endpoints)
            achados += [f"tela sem porta: {slug}/{tid}" for tid in telas_sem_porta(telas or {}, raiz)]

    acoes = {
        getattr(r, "path", "").split("/action/", 1)[1]
        for r in RD.router.routes
        if "/action/" in getattr(r, "path", "")
    }
    achados += [f"ação sem tela: /redesign/action/{a}" for a in acoes_orfas(acoes, endpoints, fonte_builders(_AQUI.parents[2] / "modules"))]

    for a in achados:
        print(f"   ✗ {a}")
    print(f"   · {medidos} módulo(s) medido(s), {len(acoes)} ação(ões) no router, menus em {menus}")
    print(f"\nTOTAL: {len(achados)} sem porta")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
