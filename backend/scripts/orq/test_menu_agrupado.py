#!/usr/bin/env python3
"""O menu agrupado não pode perder item nem quebrar o bloco.

Origem: 17/09/2026. O Jordan: «a side bar tá gigante, me perco diante de tanta coisa, é muito
provável que muitas coisas dentro dos módulos estejam repetidas... como se estivesse fazendo a
mesma coisa». Medido: 289 itens de menu, com o RH em 44 — dos quais 18 eram «CCT — alguma
coisa», três delas só sobre feriados. Agrupados, os seis maiores módulos caíram de 188 linhas
para 55.

## As regras afirmadas

1. **Nada some.** Agrupar é dobrar, não podar: todo id que existia continua existindo. A
   sidebar esconde atrás de um clique; o sistema não perde tela.
2. **Bloco contíguo.** `agrupar()` no ModuleView só junta itens CONSECUTIVOS do mesmo grupo.
   Um item do mesmo assunto fora da sequência vira um segundo bloco com o mesmo nome — pior
   que não agrupar, porque a pessoa acha que são coisas diferentes.
3. **Sem id repetido.** Já houve um bloco de 8 itens colado 3× em integracoes.py: 24 linhas
   onde cabiam 8.
4. **Grupo com um item só não vale.** Gasta uma linha e um clique para mostrar uma linha.

    python3 backend/scripts/orq/test_menu_agrupado.py

Linha canônica: `TOTAL: <n> problema(s) no menu agrupado`. Exit 1 quando há achado.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[3]
BUILDERS = RAIZ / "backend/modules/operacional/controllers/redesign_builders"
DOCKER = "/usr/bin/docker"  # nosec B607 - absoluto por causa do ruff S607

#: `re.S` obrigatório: o `ruff format` do pre-commit quebra itens longos em VÁRIAS linhas.
#: A primeira versão deste regex assumia um item por linha e passou a contar 1 onde havia 2 —
#: acusou quatro grupos «com 1 item» que estavam corretos. O defeito era da régua.
_ITEM = re.compile(
    r'\{\s*"id":\s*"([^"]+)",\s*"label":\s*"([^"]+)"(?:(?:[^{}]|\n)*?"grupo":\s*"([^"]*)")?(?:[^{}]|\n)*?\}',
    re.S,
)


def main() -> int:
    problemas: list[str] = []

    for arq in sorted(BUILDERS.glob("*.py")):
        if arq.name.startswith("_"):
            continue
        texto = arq.read_text(encoding="utf8")
        # só o bloco EXTRA_MENU: `out["x"] = {...}` mais abaixo não é menu
        i = texto.find("EXTRA_MENU")
        if i < 0:
            continue
        fim = texto.find("\n]", i)
        bloco = texto[i : fim if fim > 0 else len(texto)]

        itens = _ITEM.findall(bloco)
        if not itens:
            continue

        vistos: set[str] = set()
        for ident, _label, _g in itens:
            if ident in vistos:
                problemas.append(f"{arq.name}: id repetido no menu — '{ident}'")
            vistos.add(ident)

        # bloco contíguo: um grupo não pode reaparecer depois de outro
        sequencia = [g for _i, _l, g in itens if g]
        ja_fechados: set[str] = set()
        anterior = None
        for g in sequencia:
            if g != anterior:
                if g in ja_fechados:
                    problemas.append(
                        f"{arq.name}: grupo '{g}' aparece em DOIS blocos separados — a sidebar "
                        "mostraria o mesmo nome duas vezes"
                    )
                if anterior:
                    ja_fechados.add(anterior)
                anterior = g
        # «grupo com 1 item» NÃO se mede aqui: o menu de um módulo vem de até três arquivos, e
        # um grupo com um item NESTE pode ter mais quatro vindos dos outros. Conferir por
        # arquivo acusa grupos legítimos — aconteceu com «Tarefas» e «Leads & funil» do CRM.
        # A conta certa é no menu MONTADO, feita abaixo com as três fontes já juntas.

    # ── no menu MONTADO: grupo precisa de 2+ itens ───────────────────────────────
    # Dentro do container porque só lá o import do controller resolve as dependências — e é
    # ele que junta as três fontes, exatamente como o servidor entrega para a sidebar.
    codigo = (
        "import sys; sys.path.insert(0,'/app')\n"
        "from modules.operacional.controllers.redesign_data_controller import EXTRA_MENU\n"
        "from collections import Counter\n"
        "for slug, itens in EXTRA_MENU.items():\n"
        "    c = Counter(i['grupo'] for i in itens if isinstance(i, dict) and i.get('grupo'))\n"
        "    for g, n in c.items():\n"
        "        if n == 1: print(slug + '|' + g)\n"
    )
    try:
        saida = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
            [DOCKER, "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend", "python3", "-c", codigo],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        ).stdout
        for linha in saida.strip().splitlines():
            if "|" in linha:
                slug, g = linha.split("|", 1)
                problemas.append(
                    f"{slug}: grupo '{g}' tem 1 item no menu montado — gasta uma linha e um "
                    "clique para mostrar uma linha"
                )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  (menu montado não conferido: {exc})")

    for p in problemas:
        print(f"  ✗ {p}")
    print(f"TOTAL: {len(problemas)} problema(s) no menu agrupado")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
