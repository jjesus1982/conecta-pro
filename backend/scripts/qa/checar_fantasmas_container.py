#!/usr/bin/env python3
"""Arquivo .py que existe no CONTAINER e não existe no repositório = fantasma (09/09/2026).

Por que existe: `docker cp` de diretório copia, nunca apaga. Em 08/09 a poda apagou push/subscribe do repositório,
o container guardou o arquivo antigo, as travas de cobertura (que enumeram rotas DO CONTAINER) disseram 0 · 0, e o
bake de 09/09 00:54 — que reconstrói a imagem do repositório — fez o 404 aparecer no provider do layout raiz.
Roda no host. Compara `find /app/modules /app/core /app/scripts -name '*.py'` do backend com backend/ no disco.
Linha canônica: `TOTAL fantasmas no container: N` (binária: N = 0). Ignora __pycache__ e o que está no .gitignore.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CONTAINER = "conecta-pro-backend"
RAIZES = ("modules", "core", "scripts")


def main() -> int:
    out = subprocess.run(
        ["docker", "exec", CONTAINER, "sh", "-c",
         "find " + " ".join(f"/app/{r}" for r in RAIZES) + " -name '*.py' -not -path '*/__pycache__/*' 2>/dev/null"],
        capture_output=True, text=True, timeout=120,
    ).stdout
    no_container = {l.strip()[len("/app/"):] for l in out.splitlines() if l.strip().startswith("/app/")}
    if not no_container:
        print("ERRO: não consegui listar o container"); return 2
    ignorados = subprocess.run(["git", "-C", ROOT, "check-ignore", "--stdin"], input="\n".join(f"backend/{p}" for p in no_container),
                               capture_output=True, text=True).stdout.splitlines()
    ign = {l[len("backend/"):] for l in ignorados}
    fantasmas = sorted(p for p in no_container if p not in ign and not os.path.exists(os.path.join(ROOT, "backend", p)))
    for p in fantasmas[:60]:
        print(f"  fantasma: {p}")
    print(f"TOTAL fantasmas no container: {len(fantasmas)}")
    return 1 if fantasmas else 0


if __name__ == "__main__":
    sys.exit(main())
