#!/usr/bin/env python3
"""Cobertura rotas × telas do redesign (08/09/2026).

Enumera as rotas montadas no app (dentro do container) e classifica cada uma pelo chamador:
  redesign  — builders/actions do redesign ou apps novos (redesign, portal-funcionario, area-cliente, assinar)
  interna   — MCP, agents/, tasks do celery, tools do orquestrador (Hermes), serviços, core, oráculos, scripts
  classico  — só o frontend antigo (/modulos) a chama
  nenhum    — ninguém a chama por texto (suspeita: ou é morta, ou URL montada por variável)
Alvo do loop de 08/09: nenhum = 0 e classico = 0. Match por texto: path literal ou prefixo literal antes
do primeiro `{` (≥ 12 chars). Uso: python3 backend/scripts/qa/checar_cobertura_rotas.py [--tsv out.tsv]
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
from collections import Counter

ROOT = "/opt/conecta-pro"
SKIP = ("/api/v1/redesign", "/api/v1/health", "/api/v1/auth", "/health", "/metrics", "/docs", "/openapi", "/redoc")
REDESIGN = ["backend/modules/operacional/controllers/redesign_builders/*.py", "backend/modules/operacional/controllers/redesign_data_controller.py",
            "backend/modules/operacional/controllers/redesign_write_gate.py", "frontend/src/app/redesign/**/*.tsx", "frontend/src/components/redesign/*.tsx",
            "frontend/src/app/portal-funcionario/**/*.tsx", "frontend/src/app/area-cliente/**/*.tsx", "frontend/src/app/assinar/**/*.tsx"]
INTERNA = ["mcp-server/server.py", "agents/**/*.py", "backend/modules/**/tasks*.py", "backend/modules/**/tasks/*.py",
           "backend/modules/ai/conversation/services/orquestrador/*.py", "backend/modules/**/services/*.py", "backend/core/**/*.py",
           "backend/scripts/orq/*.py", "scripts/*.sh", "/etc/nginx/sites-enabled/*"]
CLASSICO = ["frontend/src/**/*.ts", "frontend/src/**/*.tsx"]


def _read(patterns: list[str]) -> str:
    buf = []
    for pat in patterns:
        for f in glob.glob(pat if pat.startswith("/") else os.path.join(ROOT, pat), recursive=True):
            if any(x in f for x in ("node_modules", "/.next/", "graphify", "__pycache__", "/transcritos/")):
                continue
            try:
                buf.append(open(f, errors="ignore").read())
            except OSError:
                pass
    return "\n".join(buf)


def rotas() -> list[tuple[str, str]]:
    code = ("import main_production as m\nfrom fastapi.routing import APIRoute\n"
            "for r in m.app.routes:\n    if isinstance(r, APIRoute):\n        [print(x, r.path) for x in r.methods]\n")
    out = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "-w", "/app", "conecta-pro-backend", "python3", "-c", code],
                         capture_output=True, text=True, timeout=600).stdout
    return sorted({tuple(l.split(" ", 1)) for l in out.splitlines() if l.split(" ")[0] in ("GET", "POST", "PUT", "PATCH", "DELETE") and " " in l})


def usada(path: str, txt: str) -> bool:
    core = path.replace("/api/v1", "")
    if core in txt or path in txt:
        return True
    pre = core.split("{")[0].rstrip("/")
    return len(pre) > 12 and pre in txt


def main() -> int:
    tsv = sys.argv[sys.argv.index("--tsv") + 1] if "--tsv" in sys.argv else None
    red, inte, cla = _read(REDESIGN), _read(INTERNA), _read(CLASSICO)
    classes: dict[str, list[tuple[str, str]]] = {"redesign": [], "interna": [], "classico": [], "nenhum": []}
    for m, p in rotas():
        if p.startswith(SKIP) or p in ("/", "/api", "/api/v1"):
            continue
        k = "redesign" if usada(p, red) else "interna" if usada(p, inte) else "classico" if usada(p, cla) else "nenhum"
        classes[k].append((m, p))
    tot = sum(len(v) for v in classes.values())
    for k, v in classes.items():
        print(f"  {k:9s} {len(v):5d}  ({100 * len(v) // max(tot, 1)}%)")
    if tsv:
        with open(tsv, "w") as f:
            f.write("\n".join(f"{k}\t{m}\t{p}" for k, v in classes.items() for m, p in v) + "\n")
    for k in ("nenhum", "classico"):
        c = Counter("/".join(p.split("/")[3:5]) for m, p in classes[k])
        print(f"  {k} por prefixo: {c.most_common(12)}")
    print(f"TOTAL nenhum: {len(classes['nenhum'])} · classico: {len(classes['classico'])} · rotas: {tot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
