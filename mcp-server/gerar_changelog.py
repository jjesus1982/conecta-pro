#!/usr/bin/env python3
"""Regenera `mcp-server/changelog.json` a partir do git log — o que `changelog_mcp()` conta
ao agente quando ele pergunta "o que mudou no conector?".

Existia a INSTRUÇÃO («regenere a partir do git log») e não existia o gerador: a trava
mandava fazer à mão, e à mão ficou para trás. 17/09/2026.

Commits que só mexem neste arquivo ficam de fora: registrar a própria regeneração é ruído
para quem lê, e era o que fazia a trava nunca convergir — regenerar criava um commit novo
em `mcp-server/`, que aparecia como pendente na execução seguinte.

    python3 mcp-server/gerar_changelog.py            # escreve
    python3 mcp-server/gerar_changelog.py --ensaio   # só mostra o topo
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "mcp-server" / "changelog.json"

#: Quantas entradas o agente recebe. 40 é o que o arquivo já trazia — history longa não ajuda
#: quem pergunta "o que mudou", e o git guarda o resto.
QUANTAS = 40

GIT = "/usr/bin/git"  # nosec B607 — caminho absoluto, ruff S607


def _git(*args: str) -> str:
    return subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
        [GIT, *args], cwd=RAIZ, capture_output=True, text=True, check=False
    ).stdout


def entradas() -> list[dict]:
    bruto = _git("log", "--pretty=format:%h|%ad|%s", "--date=short", "--", "mcp-server/")
    fora = []
    for linha in bruto.splitlines():
        if not linha.strip():
            continue
        commit, data, assunto = (linha.split("|", 2) + ["", "", ""])[:3]
        tocados = [t for t in _git("show", "--name-only", "--pretty=format:", commit).splitlines() if t.strip()]
        if tocados and all(t.strip() == "mcp-server/changelog.json" for t in tocados):
            continue  # a própria regeneração não é mudança do conector
        fora.append({"commit": commit, "data": data, "mudanca": assunto})
        if len(fora) >= QUANTAS:
            break
    return fora


def main() -> int:
    lista = entradas()
    if not lista:
        print("ERRO: git log de mcp-server/ veio vazio — nada escrito")
        return 1
    if "--ensaio" in sys.argv:
        print(f"topo seria {lista[0]['commit']} ({lista[0]['data']}) — {lista[0]['mudanca'][:70]}")
        print(f"{len(lista)} entradas, nada escrito (--ensaio)")
        return 0
    DESTINO.write_text(
        json.dumps({"gerado_de": "git log -- mcp-server/", "entradas": lista}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"changelog.json: {len(lista)} entradas, topo {lista[0]['commit']} ({lista[0]['data']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
