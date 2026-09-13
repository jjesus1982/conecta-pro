#!/usr/bin/env python3
"""Módulo com código e ninguém que o use: 0 rotas montadas, 0 imports de produção, 0 task Celery.

Por que existe (frente 9, 12/09/2026). A contagem por grep de `@router.<verbo>` disse que oito
módulos tinham zero rotas — e estava errada duas vezes: `pessoas`/`comercial`/`tecnico`/… são
AGREGADORES (só re-exportam routers de outros módulos), e um router pode ter outro nome de
variável. A única medida que vale é `app.routes` do app montado, atribuindo cada rota ao módulo
pelo `endpoint.__module__`. Medido assim em 12/09: bidding 101 .py/0 rotas, hr 172/0,
retention 47/0, health_occupational 33/0, fase5 23/0, document_kits 16/0, services 16/0,
scheduler 16/0, lgpd 3/0 — e só QUATRO deles são mortos de verdade; os outros vivem por import
(hr é biblioteca da folha: hr_payslips tem 888 linhas) ou por task no beat.

Três perguntas, três estados:
    rotas montadas == 0        → DESLIGADO ou MORTO (quem decide é a próxima pergunta)
    alguém de produção importa → DESLIGADO (biblioteca: modelo, serviço, cliente externo)
    task no include do Celery  → DESLIGADO (roda sem rota)
    nada disso                 → MORTO — apagar exige decisão do dono, não deste script

"Alguém de produção" = modules/**, core/**, celery_app.py, scripts/*.py operacionais.
NÃO conta: main_production.py e os agregadores (montar um router vazio não é usar), api/ (só
main.py, que não é produção), tests/. Oráculos e caçadores (scripts/orq, scripts/qa) aparecem
na coluna `vigia` — um oráculo de módulo morto é dívida que vai junto quando o módulo for.
Import tardio dentro de função CONTA (regex por linha, sem exigir coluna 0) — foi o que
derrubou o meu-espaço em 09/09.

Excluídos por construção: os agregadores (lista fixa) e `hr/rep_integration` (frente 1 em curso).

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_modulo_morto.py
    ... --todos        # uma linha por módulo, não só os sem rota
    ... --self-check   # o veredito puro, sem app nem disco

Linha canônica (lida por `checar_regressao`): `TOTAL módulos mortos: N`. Exit 1 se N > 0.
Dívida contada: entra na base e só acusa quando CRESCE (módulo novo nascendo morto).
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

APP = Path("/app")
MODS = APP / "modules"
AGREGADORES = {"comercial", "pessoas", "tecnico", "operacoes", "financeiro", "gestao", "inteligencia"}
IGNORAR_SUBARVORES = {"hr/rep_integration"}  # frente 1 (AFD) em curso — medir depois que ela fechar
MIN_PY = 3
RE_IMPORT = re.compile(r"^\s*(?:from\s+modules\.(\w+)[.\s]|import\s+modules\.(\w+)\b)", re.M)
RE_CELERY = re.compile(r"""['"]modules\.(\w+)[.'"]""")


def veredito(py: int, rotas: int, uso: int, celery: bool) -> str:
    if py < MIN_PY:
        return "VAZIO"
    if rotas:
        return "VIVO"
    return "DESLIGADO" if (uso or celery) else "MORTO"


def _ignorado(rel: str) -> bool:
    return any(rel.startswith(f"modules/{s}/") for s in IGNORAR_SUBARVORES)


def _py(raiz: Path):
    for p in raiz.rglob("*.py"):
        if "__pycache__" not in p.parts:
            yield p


def medir() -> dict[str, dict]:
    modulos = sorted(
        p.name for p in MODS.iterdir() if p.is_dir() and (p / "__init__.py").exists() and not p.name.startswith("_")
    )
    info = {m: {"py": 0, "rotas": 0, "uso": set(), "vigia": set(), "celery": False} for m in modulos}
    for m in modulos:
        info[m]["py"] = sum(1 for p in _py(MODS / m) if not _ignorado(str(p.relative_to(APP))))

    from fastapi.routing import APIRoute  # noqa: PLC0415

    from main_production import app  # noqa: PLC0415 — ~30 s: monta o app inteiro

    for r in app.routes:
        if not isinstance(r, APIRoute) or not r.endpoint.__module__.startswith("modules."):
            continue
        mod = r.endpoint.__module__
        top = mod.split(".")[1]
        if top in info and not _ignorado(mod.replace(".", "/") + "/"):
            info[top]["rotas"] += 1

    vigias = (APP / "scripts/orq", APP / "scripts/qa")
    arquivos = [APP / "celery_app.py"]
    for raiz in (MODS, APP / "core", APP / "scripts"):
        arquivos += list(_py(raiz))
    for p in arquivos:
        if not p.exists():
            continue
        rel = str(p.relative_to(APP))
        if _ignorado(rel) or p.name.startswith("extract_"):
            continue
        dono = rel.split("/")[1] if rel.startswith("modules/") else None
        if dono in AGREGADORES:
            continue
        coluna = "vigia" if any(p.is_relative_to(v) for v in vigias) else "uso"
        for a, b in RE_IMPORT.findall(p.read_text(errors="ignore")):
            alvo = a or b
            if alvo in info and alvo != dono:
                info[alvo][coluna].add(rel)
    for alvo in set(RE_CELERY.findall((APP / "celery_app.py").read_text(errors="ignore"))):
        if alvo in info:
            info[alvo]["celery"] = True
    for m in AGREGADORES:
        info.pop(m, None)
    return info


def main() -> int:
    if "--self-check" in sys.argv:
        assert veredito(101, 0, 0, False) == "MORTO"
        assert veredito(101, 0, 2, False) == "DESLIGADO"
        assert veredito(33, 0, 0, True) == "DESLIGADO"
        assert veredito(16, 5, 0, False) == "VIVO"
        assert veredito(1, 0, 0, False) == "VAZIO"
        print("OK checar_modulo_morto --self-check")
        return 0
    if not MODS.is_dir():
        print("RECUSO: roda DENTRO do container (precisa de /app e do app montado)")
        return 2
    info = medir()
    todos = "--todos" in sys.argv
    print(
        f"módulos de /app/modules medidos em {date.today()} por app.routes · endpoint.__module__ "
        f"(agregadores fora: {', '.join(sorted(AGREGADORES))}; fora também: {', '.join(sorted(IGNORAR_SUBARVORES))})"
    )
    print(f"   {'módulo':<24}{'py':>5}{'rotas':>7}{'uso':>5}{'vigia':>7}{'celery':>8}  veredito")
    mortos = []
    for m, v in sorted(info.items(), key=lambda kv: (kv[1]["rotas"] > 0, kv[0])):
        vd = veredito(v["py"], v["rotas"], len(v["uso"]), v["celery"])
        if vd == "MORTO":
            mortos.append(m)
        if not todos and vd == "VIVO":
            continue
        quem = ", ".join(sorted(v["uso"])[:3]) if v["uso"] else ""
        print(
            f"   {m:<24}{v['py']:>5}{v['rotas']:>7}{len(v['uso']):>5}{len(v['vigia']):>7}"
            f"{'sim' if v['celery'] else '—':>8}  {vd}{'  ← ' + quem if quem else ''}"
        )
    print(f"\nTOTAL módulos mortos: {len(mortos)}" + (" — " + ", ".join(mortos) if mortos else ""))
    return 1 if mortos else 0


if __name__ == "__main__":
    raise SystemExit(main())
