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
import re
import os
import subprocess
import sys
from collections import Counter

ROOT = "/opt/conecta-pro"
SKIP = ("/api/v1/redesign", "/api/v1/health", "/api/v1/auth", "/health", "/metrics", "/docs", "/openapi", "/redoc")
REDESIGN = ["backend/modules/operacional/controllers/redesign_builders/*.py", "backend/modules/operacional/controllers/redesign_data_controller.py",
            "backend/modules/operacional/controllers/redesign_write_gate.py", "frontend/src/app/redesign/**/*.tsx", "frontend/src/components/redesign/*.tsx",
            "frontend/src/app/portal-funcionario/**/*.tsx", "frontend/src/app/area-cliente/**/*.tsx", "frontend/src/app/assinar/**/*.tsx",
            # apps-satélite VIVOS do redesign (08/09): portal-funcionario só redireciona para /modulos/meu-espaco — é ele o portal
            # real (1.635 batidas faciais em 30 dias); os públicos (homologação, painel de ponto, login facial, candidato, PJ,
            # primeiro acesso) são a porta de entrada. Helpers que esses apps importam também contam.
            "frontend/src/app/modulos/meu-espaco/**/*.tsx", "frontend/src/app/homologacao/**/*.tsx", "frontend/src/app/painel-ponto/**/*.tsx",
            "frontend/src/app/login/**/*.tsx", "frontend/src/app/candidato/**/*.tsx", "frontend/src/app/autocadastro-pj/**/*.tsx",
            "frontend/src/app/primeiro-acesso/**/*.tsx", "frontend/src/services/portal/*.ts", "frontend/src/hooks/useNotifications.ts",
            "frontend/src/components/gdrive/*.tsx"]
INTERNA = ["mcp-server/server.py", "agents/**/*.py", "backend/modules/**/tasks*.py", "backend/modules/**/tasks/*.py",
           "backend/modules/ai/conversation/services/orquestrador/*.py", "backend/modules/**/services/*.py", "backend/core/**/*.py",
           "backend/scripts/**/*.py", "det-robot/*.py", "mcp-server/**/*.py", "scripts/*.sh", "scripts/**/*.py",
           "/etc/nginx/sites-enabled/*", "/etc/cron.d/*", "/var/spool/cron/crontabs/*"]
EXTERNO = re.compile(r"webhook|callback|/oauth|/solides/|/inter/(?:pix|cobranca)")  # quem chama é o banco/Sólides/Meta
CLASSICO = ["frontend/src/**/*.ts", "frontend/src/**/*.tsx"]


def _read(patterns: list[str]) -> str:
    buf = []
    for pat in patterns:
        for f in glob.glob(pat if pat.startswith("/") else os.path.join(ROOT, pat), recursive=True):
            if any(x in f for x in ("node_modules", "/.next/", "graphify", "__pycache__", "/transcritos/")):
                continue
            try:
                buf.append(_normalizar(open(f, errors="ignore").read()))
            except OSError:
                pass
    return "\n".join(buf)


_CONST = re.compile(r"^\s*(?:const |let |export const )?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*[\"'`]([^\"'`\n]*?(/api/v1[\w/.-]*))[\"'`]", re.M)


def _normalizar(txt: str) -> str:
    """Faz aparecer no texto a URL que o código monta em pedaços (padrões medidos em 08/09):
    - constante de prefixo: `_HR = "/api/v1/people-management/human-resources"` + f"{_HR}/training" ou `${API_BASE}/kits`
    - concatenação implícita de literais em Python ('…/discipline/' '…/estatisticas')
    - portalFetch('/avisos') da área do cliente → /api/v1/portal/avisos"""
    consts = {name: pref for name, _full, pref in _CONST.findall(txt)}
    for name, pref in consts.items():
        txt = txt.replace("{" + name + "}", pref).replace("${" + name + "}", pref)
    txt = re.sub(r"(['\"])\s*\n\s*\1", "", txt)  # 'a'\n'b' → 'ab'
    txt = re.sub(r"portalFetch(?:<[^>]*>)?\(\s*[`'\"](/)", r"portalFetch(`/api/v1/portal\1", txt)
    return txt


def rotas() -> list[tuple[str, str, str]]:
    """(método, path, handler) — handler = módulo.função, para reconhecer montagem dupla e reuso por import."""
    code = ("import main_production as m\nfrom fastapi.routing import APIRoute\n"
            "for r in m.app.routes:\n    if isinstance(r, APIRoute):\n"
            "        [print(x, r.endpoint.__module__ + '.' + r.endpoint.__name__, r.path) for x in r.methods]\n")
    out = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "-w", "/app", "conecta-pro-backend", "python3", "-c", code],
                         capture_output=True, text=True, timeout=600).stdout
    seen = set()
    for l in out.splitlines():
        parts = l.split(" ", 2)
        if len(parts) == 3 and parts[0] in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            seen.add((parts[0], parts[2], parts[1]))
    return sorted(seen)


_IMPORTADOS: set[str] | None = None


def _indexar_imports(txt: str) -> set[str]:
    """Uma passada só sobre o corpus: todo nome trazido por `from modules.x import (a, b as c)` e todo
    `alias.nome(` de módulo importado por `from modules.x import mod as alias`. Devolve 'modules.x.nome'."""
    idx: set[str] = set()
    aliases: dict[str, set[str]] = {}  # alias -> {'modules.x.mod'}
    blocos = re.findall(r"from (modules\.[\w.]+) import[ \t]*\(([^)]*)\)", txt) + re.findall(r"from (modules\.[\w.]+) import[ \t]*([^\n(]+)\n", txt)
    for mod, body in blocos:
        for part in body.split(","):
            bits = [x.strip() for x in part.strip().split(" as ")]
            if bits and re.match(r"^[A-Za-z_]\w*$", bits[0]):
                idx.add(f"{mod}.{bits[0]}")
                aliases.setdefault(bits[-1], set()).add(f"{mod}.{bits[0]}")
    for alias, fn in set(re.findall(r"\b([A-Za-z_]\w*)\.([a-z_][a-z0-9_]*)\s*[(,)]", txt)):  # chamada OU referência (chamar(Mod.fn, …))
        for full in aliases.get(alias, ()):
            idx.add(f"{full}.{fn}")
    return idx


def importado(handler: str, txt: str) -> bool:
    """O handler é reusado por import (builder do redesign, MCP, orquestrador…) — chamador interno sem URL."""
    global _IMPORTADOS
    if _IMPORTADOS is None:
        _IMPORTADOS = _indexar_imports(txt)
    return handler in _IMPORTADOS


def usada(path: str, txt: str) -> bool:
    core = path.replace("/api/v1", "")
    if core in txt or path in txt:
        return True
    pre = core.split("{")[0].rstrip("/")
    if len(pre) > 12:
        return pre in txt
    return len(pre) >= 8 and pre.count("/") >= 2 and (pre + "/") in txt  # /crm/leads/{id}, /clients/{id}/activate


def main() -> int:
    tsv = sys.argv[sys.argv.index("--tsv") + 1] if "--tsv" in sys.argv else None
    red, inte, cla = _read(REDESIGN), _read(INTERNA), _read(CLASSICO)
    classes: dict[str, list[tuple[str, str]]] = {"redesign": [], "interna": [], "alias": [], "externo": [], "classico": [], "nenhum": []}
    todas = [(m, p, h) for m, p, h in rotas() if not p.startswith(SKIP) and p not in ("/", "/api", "/api/v1")]
    cobertos: set[str] = set()  # handlers alcançados por path do redesign/interna
    pend = []
    for m, p, h in todas:
        k = "redesign" if usada(p, red) else "interna" if usada(p, inte) or importado(h, red + inte) else None
        if k:
            classes[k].append((m, p)); cobertos.add(h)
        else:
            pend.append((m, p, h))
    for m, p, h in pend:  # montagem dupla (main_production.py, fora do escopo editável): mesmo handler já coberto
        k = "alias" if h in cobertos else "externo" if EXTERNO.search(p) else "classico" if usada(p, cla) else "nenhum"
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
