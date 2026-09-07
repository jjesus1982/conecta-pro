#!/usr/bin/env python3
"""`from X import Y` onde X não existe mais no disco.

Achado na noite de 06→07/09/2026, durante a limpeza dos 🔴: 403 arquivos e 8 pacotes foram
apagados, e TRÊS deles estavam vivos por dentro — `analytics` (task que escreve os KPIs
executivos), `ai/contract_analysis` (Jurídico) e `ai/signature` (toda a assinatura digital,
1.776 pedidos). Cada um foi descoberto por um crash separado, um bake por vez:

    bake 1 → celery_app importa modules.analytics.tasks  → priority e sefaz em crash-loop
    bake 2 → main_production importa ai.contract_analysis → bloco Jurídico não monta
    bake 3 → beat de assinaturas importa ai.signature     → assinatura muda

Depois dos três, ainda sobravam **21 arquivos de produção** com import que não resolve. O
boot de prova não pega esta classe: `api/v1/__init__.py` tem 12 imports de topo de
controllers apagados e ficou INVISÍVEL, porque produção roda `main_production:app` e nunca
importa `api.v1` — quem quebrou foi `backend/main.py` e as ferramentas que passam por ele.

**Boot de prova prova o que boota. Esta trava mede o que NINGUÉM importa** — e é justamente
onde o defeito espera o dia em que alguém importar.

A distinção que dá o veredito é a COLUNA do import:

    coluna 0  → executa no import do módulo  → 💥 crash na hora que alguém tocar o arquivo
    indentado → dentro de try/except ou de função → 🔇 capacidade some calada

Os dois são achado; só o primeiro reprova. Foi o indentado que escondeu o OpenClaw e a
integração do Licitações com o CRM — `logger.warning` e a vida segue sem o recurso.

LIMITE: resolve por caminho no disco, não por `importlib`. Import dinâmico
(`__import__`, `importlib.import_module`) passa batido, e namespace package sem
`__init__.py` dá falso positivo. Achado é PISTA; confira a linha.

    python3 backend/scripts/qa/checar_import_orfao.py
    python3 backend/scripts/qa/checar_import_orfao.py --self-check
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PREFIXOS = ("modules.", "api.", "core.", "scripts.")
IGNORAR = ("venv", "__pycache__", "_orphaned", "_quarentena")
IMPORT = re.compile(r"^(\s*)(?:from\s+([a-zA-Z_][\w.]*)\s+import|import\s+([a-zA-Z_][\w.]*))")


def _existe(raiz: Path, mod: str) -> bool:
    p = raiz / mod.replace(".", "/")
    return p.with_suffix(".py").exists() or (p / "__init__.py").exists()


def achados(raiz: Path = RAIZ) -> list[dict]:
    fora = []
    for arq in sorted(raiz.rglob("*.py")):
        if any(x in p for p in arq.parts for x in IGNORAR):
            continue
        try:
            linhas = arq.read_text(errors="ignore").splitlines()
        except OSError:
            continue
        # docstring conta como texto, não como código: `delete_me.py` documenta
        # "adicione ao main.py: from api.v1.lgpd import router" — a primeira versão
        # desta trava reprovou por causa dessa linha, e trava que grita errado ninguém lê.
        aspas: str | None = None
        for n, ln in enumerate(linhas, 1):
            if aspas:
                if aspas in ln:
                    aspas = None
                continue
            for marca in ('"""', "'''"):
                if ln.count(marca) == 1:
                    aspas = marca
                    break
            if aspas:
                continue
            m = IMPORT.match(ln)
            if not m:
                continue
            mod = m.group(2) or m.group(3)
            # em `from A.B import C` e em `import A.B`, A.B TEM de ser módulo — sem folga aqui:
            # foi essa folga que, na primeira versão desta trava, engoliu o próprio caso que
            # ela existe para pegar (`from modules.morto import x`, com `modules` de pé).
            if not mod.startswith(PREFIXOS) or _existe(raiz, mod):
                continue
            fora.append({
                "arquivo": str(arq.relative_to(raiz)),
                "linha": n,
                "modulo": mod,
                "topo": m.group(1) == "",
                "teste": arq.parts[len(raiz.parts)] == "tests",
            })
    return fora


INCLUDE = re.compile(r"include\s*=\s*\[(.*?)\]", re.S)
DOTTED = re.compile(r"[\"']((?:modules|api|core|scripts)\.[\w.]+)[\"']")


def celery_orfaos(raiz: Path = RAIZ) -> list[dict]:
    """A lista `include=[...]` do celery referencia módulo por STRING, não por import.

    Foi assim que `modules.analytics.tasks` derrubou os workers `priority` e `sefaz` em
    crash-loop no bake de 07/09: nenhum `import` apontava para lá, então a camada 1 desta
    trava passa por cima. Varredura de string dotted no repositório inteiro dá 603 achados
    (relationship do SQLAlchemy, caminho que termina em classe) — ruído. Aqui só a lista
    do celery, onde a string É o carregamento.
    """
    arq = raiz / "celery_app.py"
    if not arq.exists():
        return []
    bloco = INCLUDE.search(arq.read_text(errors="ignore"))
    if not bloco:
        return []
    base = arq.read_text(errors="ignore").index(bloco.group(1))
    fora = []
    for m in DOTTED.finditer(bloco.group(1)):
        if _existe(raiz, m.group(1)):
            continue
        linha = arq.read_text(errors="ignore")[: base + m.start()].count("\n") + 1
        fora.append({"arquivo": "celery_app.py", "linha": linha, "modulo": m.group(1)})
    return fora


def _self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        raiz = Path(d)
        (raiz / "modules" / "vivo").mkdir(parents=True)
        (raiz / "modules" / "__init__.py").write_text("")
        (raiz / "modules" / "vivo" / "__init__.py").write_text("")
        (raiz / "app.py").write_text(
            "from modules.vivo import ok\n"           # existe        → não acusa
            "from modules.morto import x\n"           # topo          → acusa, reprova
            "try:\n    from modules.sumiu import y\nexcept Exception:\n    pass\n"  # indentado
        )
        r = achados(raiz)
        mods = {a["modulo"] for a in r}
        assert mods == {"modules.morto", "modules.sumiu"}, mods
        assert [a["topo"] for a in r if a["modulo"] == "modules.morto"] == [True]
        assert [a["topo"] for a in r if a["modulo"] == "modules.sumiu"] == [False]

        # camada 2: a string do celery, que nenhum import alcança
        (raiz / "celery_app.py").write_text(
            'app = Celery(\n    include=[\n'
            '        "modules.vivo",\n'
            '        "modules.analytics.tasks",\n    ],\n)\n'
        )
        c = celery_orfaos(raiz)
        assert [a["modulo"] for a in c] == ["modules.analytics.tasks"], c
    print("self-check OK: topo, indentado, e a string do celery que derrubou os workers")


def main() -> int:
    if "--self-check" in sys.argv:
        _self_check()
        return 0

    todos = achados()
    prod = [a for a in todos if not a["teste"]]
    quebra = [a for a in prod if a["topo"]]
    calado = [a for a in prod if not a["topo"]]

    if quebra:
        print(f"💥 IMPORT DE TOPO PARA MÓDULO INEXISTENTE ({len(quebra)}) — quebra ao importar")
        for a in quebra:
            print(f"   {a['arquivo']}:{a['linha']}  {a['modulo']}")
    if calado:
        print(f"🔇 guardado por try/except ou dentro de função ({len(calado)}) — capacidade some calada")
        for a in calado[:15]:
            print(f"   {a['arquivo']}:{a['linha']}  {a['modulo']}")
        if len(calado) > 15:
            print(f"   ... mais {len(calado) - 15}")

    cel = celery_orfaos()
    if cel:
        print(f"💥 celery include=[] aponta para módulo inexistente ({len(cel)}) — worker em crash-loop")
        for a in cel:
            print(f"   {a['arquivo']}:{a['linha']}  {a['modulo']}")

    n_teste = len(todos) - len(prod)
    print(f"\nprodução: {len(quebra)} de topo · {len(calado)} guardados · "
          f"celery: {len(cel)} · testes: {n_teste}")
    quebra = quebra + cel
    if quebra:
        print("FAIL checar_import_orfao")
        return 1
    print("OK checar_import_orfao: nenhum import de topo órfão")
    return 0


if __name__ == "__main__":
    sys.exit(main())
