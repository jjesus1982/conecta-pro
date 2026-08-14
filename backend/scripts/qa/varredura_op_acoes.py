#!/usr/bin/env python3
"""Varredura do operacional: tela/ação que EXISTE mas não tem como funcionar.

Nasceu de três achados tropeçados um a um no fechamento T4 (13/08/2026):
  · "Avaliar diarista" caía sempre em 400 (exigia dado de tabela com 0 linhas)
  · "Escala diaristas" lia diarist_schedules (0) havendo diaria_lancamentos (308)
  · toda ação disciplinar batia em rota 404 (prefixo e verbo errados)

Os três são a MESMA família: a tela está lá, bonita, e não há caminho até o efeito.
Nenhum oráculo pegava, porque oráculo confere o que EXISTE — e aqui tudo existe.

O que acusa, por tela renderizada de verdade (build(db)), não por leitura de código:

  ROTA-MORTA    submit.endpoint que não está montado no app → clique vira 404. FATAL.
  SEM-TELA      o menu oferece um slug que o builder não entrega. FATAL.
  SEM-FILA      form com select* obrigatório sem opção. NÃO é veredito, é FATO: ou não
                há item pendente (honesto) ou o filtro exclui tudo (bug). Só o dado da
                tabela de origem separa os dois — a primeira versão desta varredura
                chamou os 18 de "fatal" e 17 eram vazio honesto. Cheque a origem antes
                de acusar.
  TABELA-VAZIA  tabela com 0 linhas. Idem: vazio honesto vira suspeita só quando existe
                fonte equivalente COM linha (foi o caso de diaristas, ver F3).

Uso:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/varredura_op_acoes.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app/scripts/orq")


def _rotas_montadas() -> set[str]:
    from main_production import app  # noqa: PLC0415

    return {r.path for r in app.routes}


def _selects_vazios(scr: dict) -> list[str]:
    """Campos select obrigatórios sem opção. Obrigatório = label termina em '*'."""
    ruins = []
    for f in scr.get("fields") or []:
        if f.get("type") != "select":
            continue
        obrig = (f.get("label") or "").rstrip().endswith("*")
        if obrig and not (f.get("options") or []):
            ruins.append(f.get("key") or f.get("label") or "?")
    return ruins


async def main() -> int:
    from core.database import async_session_factory  # noqa: PLC0415
    from modules.operacional.controllers.redesign_builders import _op_grupos  # noqa: PLC0415
    from modules.operacional.controllers.redesign_builders.operacional import build  # noqa: PLC0415

    from _fixtures import tela  # noqa: PLC0415

    montadas = _rotas_montadas()
    achados: list[tuple[str, str, str]] = []

    # só o que o menu OFERECE: tela que ninguém alcança não é defeito de ninguém
    slugs = []
    for g in _op_grupos.GRUPOS:
        for item in g[3]:
            slugs.append(item[0] if isinstance(item, tuple) else item)

    async with async_session_factory() as db:
        screens = await build(db)
        for slug in slugs:
            scr = tela(screens, slug)
            if not isinstance(scr, dict):
                achados.append(("SEM-TELA", slug, "o menu oferece, o builder não entrega"))
                continue

            tipo = scr.get("type")
            if tipo == "form":
                vazios = _selects_vazios(scr)
                if vazios:
                    achados.append(("SEM-FILA", slug,
                                    f"select obrigatório sem opção: {', '.join(vazios)}"))
                ep = ((scr.get("submit") or {}).get("endpoint") or "").split("?")[0]
                if ep and ep not in montadas:
                    achados.append(("ROTA-MORTA", slug, f"submit → {ep} (não montada)"))
            elif tipo == "table" and not (scr.get("rows") or []):
                achados.append(("TABELA-VAZIA", slug, scr.get("sub", "")[:90]))

    ordem = {"ROTA-MORTA": 0, "SEM-TELA": 1, "SEM-FILA": 2, "TABELA-VAZIA": 3}
    achados.sort(key=lambda a: (ordem.get(a[0], 9), a[1]))

    print(f"VARREDURA OPERACIONAL — {len(slugs)} slugs oferecidos no menu\n")
    for tipo, slug, det in achados:
        print(f"  [{tipo:12}] {slug:32} {det}")

    fatais = [a for a in achados if a[0] in ("ROTA-MORTA", "SEM-TELA")]
    sem_fila = [a for a in achados if a[0] == "SEM-FILA"]
    print(f"\nTOTAL: {len(achados)} · {len(fatais)} FATAL(is) · {len(sem_fila)} sem fila "
          f"(ação pronta esperando alguém produzir o item)")
    return 1 if fatais else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
