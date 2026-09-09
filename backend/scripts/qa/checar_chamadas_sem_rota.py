#!/usr/bin/env python3
"""Inversa do checar_cobertura_rotas (08/09/2026, sugestão da auditoria t6): "toda CHAMADA tem rota?".

Extrai todo literal `/api/v1/...` de frontend/src (fora de types/generated, api/*/generated, testes e stories)
e confere contra as rotas montadas no container. `${x}`/`{x}` viram parâmetro. Literal que é PREFIXO de rota
montada (`/api/v1/ged`, `${BASE}/...`) não é falta. Duas contas:
  - ALCANÇÁVEL PELO REDESIGN: arquivo alcançado, pelo grafo de imports, a partir das raízes do redesign
    (app/redesign, components/redesign, contexts, features/notifications, app/area-cliente, app/modulos/meu-espaco,
    apps públicos) → trava binária: reprova se > 0
  - só clássico: só app/modulos/** (fora o meu-espaço) chega lá → dívida contada (clássico fora do escopo, decisão
    do dono em 08/09); listado para ninguém se surpreender quando o clássico quebrar
Linha canônica: `TOTAL chamadas sem rota: N (alcançável pelo redesign) · M (só clássico)`.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FRONT = os.path.join(ROOT, "frontend", "src")
IGNORAR = ("/types/generated/", "/generated/", "/__tests__/", ".test.", ".stories.", "/test/", "/tests/")
LIT = re.compile(r"""['"`](/api/v1/[^'"`\s?#]+)""")
IMP = re.compile(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""")
VAR = r"[^/]+"
RAIZES = ("app/redesign/", "components/redesign/", "contexts/", "features/notifications/", "app/area-cliente/",
          "app/modulos/meu-espaco/", "app/homologacao/", "app/painel-ponto/", "app/login/", "app/candidato/",
          "app/autocadastro-pj/", "app/primeiro-acesso/", "app/layout.tsx", "app/page.tsx")


def rotas_montadas() -> list[str]:
    code = ("import main_production as m\nfrom fastapi.routing import APIRoute\n"
            "for r in m.app.routes:\n    if isinstance(r, APIRoute): print(r.path)\n")
    out = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "-w", "/app", "conecta-pro-backend", "python3", "-c", code],
                         capture_output=True, text=True, timeout=600).stdout
    return sorted({l.strip() for l in out.splitlines() if l.startswith("/api/")})


def normalizar(lit: str) -> str:
    return re.sub(r"\$\{[^}]*\}|\{[^}]*\}", "{x}", lit).rstrip("/")


def resolver(origem: str, alvo: str) -> str | None:
    """Caminho relativo ou '@/' → arquivo em frontend/src (ts/tsx/index)."""
    if alvo.startswith("@/"):
        base = os.path.join(FRONT, alvo[2:])
    elif alvo.startswith("."):
        base = os.path.normpath(os.path.join(os.path.dirname(origem), alvo))
    else:
        return None
    for cand in (base, base + ".ts", base + ".tsx", os.path.join(base, "index.ts"), os.path.join(base, "index.tsx")):
        if os.path.isfile(cand):
            return cand
    return None


def main() -> int:
    rotas = rotas_montadas()
    if not rotas:
        print("ERRO: não consegui enumerar as rotas do container"); return 2
    rx = [(p, re.compile("^" + re.sub(r"\\\{[^}]*\\\}", VAR, re.escape(p)) + "/?$")) for p in rotas]
    arquivos = [f for f in glob.glob(os.path.join(FRONT, "**", "*.ts*"), recursive=True) if not any(x in f for x in IGNORAR)]
    textos = {}
    for f in arquivos:
        try:
            textos[f] = open(f, errors="ignore").read()
        except OSError:
            pass
    # grafo de imports: quem importa quem
    imports = {f: {r for r in (resolver(f, a) for a in IMP.findall(t)) if r} for f, t in textos.items()}
    # alcance a partir das raízes do redesign
    rel = lambda f: os.path.relpath(f, FRONT)  # noqa: E731
    fila = [f for f in textos if rel(f).startswith(RAIZES)]
    alcancado = set(fila)
    while fila:
        f = fila.pop()
        for g in imports.get(f, ()):
            if g not in alcancado:
                alcancado.add(g); fila.append(g)
    achados: dict[str, tuple[set[str], bool]] = {}
    for f, t in textos.items():
        for lit in set(LIT.findall(t)):
            core = normalizar(lit)
            if any(p.startswith(core + "/") or p == core for p in rotas):  # prefixo de rota montada = não é falta
                continue
            if any(r.match(core) for _, r in rx):
                continue
            arqs, red = achados.get(core, (set(), False))
            arqs.add(rel(f)); achados[core] = (arqs, red or f in alcancado)
    red = {k: v[0] for k, v in achados.items() if v[1]}
    cla = {k: v[0] for k, v in achados.items() if not v[1]}
    for titulo, grupo in (("ALCANÇÁVEL PELO REDESIGN (reprova)", red), ("só clássico (dívida, fora do escopo)", cla)):
        print(f"\n── {titulo}: {len(grupo)}")
        for k in sorted(grupo)[:80]:
            print(f"  {k}\n     ← {', '.join(sorted(grupo[k])[:3])}")
    print(f"\nTOTAL chamadas sem rota: {len(red)} (alcançável pelo redesign) · {len(cla)} (só clássico)")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
