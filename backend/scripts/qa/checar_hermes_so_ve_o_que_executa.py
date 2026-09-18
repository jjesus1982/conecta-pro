#!/usr/bin/env python3
"""O Hermes só enxerga, do conector `conecta`, as ferramentas que ele CONSEGUE executar.

Origem: 18/09/2026, medido no dump real de `/data/sessions` do Hermes. O catálogo de
ferramentas era **83% do payload de cada turno** — 154.751 de 185.700 caracteres, 257
ferramentas. Metade disso vinha de um conector só:

    mcp__conecta   150 ferramentas · 78.602 chars (50% do payload)
    mcp__ged        46 ferramentas · 14.994 chars
    mcp__pessoas    45 ferramentas · 14.980 chars
    nativas          16 ferramentas · 45.661 chars

E medido no gate do próprio conector: das 146 servidas no escopo, **4 executam e 142 recusam
SEMPRE**. Ele roda `MCP_MODO=agente` e exige `x-usuario-token` por chamada em tudo que toca
pessoa ou dinheiro; o Hermes não sabe mandar cabeçalho por chamada (headers estáticos por
conexão, `tools/mcp_tool.py`). Então 142 schemas iam e voltavam todo turno para nada — e pior
que o custo, o modelo gastava raciocínio escolhendo ferramenta que ia recusar.

Com `mcp_servers.conecta.tools.include` limitado às 4: **46.843 → 26.540 tokens de entrada
por turno, 43% a menos**, com `ged` (46) e `pessoas` (45) intactos.

## A regra afirmada, nos DOIS sentidos

O `include` é uma fotografia do que executava em 18/09. Fotografia envelhece:

  · alguém constrói o repasse de identidade por chamada → mais ferramentas passam a executar
    e a lista, que era economia, VIRA A NOVA PAREDE — o Hermes perde acesso que ganhou;
  · alguém acrescenta uma tool a `SEM_DADO_DE_TERCEIRO` no conector → mesma coisa;
  · alguém remove uma tool do conector e a lista fica apontando para o vazio.

Por isso aqui não se confere "tem 4 itens": confere-se que a lista é EXATAMENTE o conjunto
que o gate deixa passar hoje.

    python3 backend/scripts/qa/checar_hermes_so_ve_o_que_executa.py

Linha canônica: `TOTAL: <n> divergência(s) entre o que o Hermes vê e o que executa`. Exit 1 com achado.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

DOCKER = "/usr/bin/docker"  # nosec B607 — ruff S607 recusa executável parcial
CONECTOR = "conecta-pro-mcp-internal"
CONFIG = pathlib.Path("/opt/conecta-pro/hermes-runtime/config.yaml")

#: A sonda roda DENTRO do conector: a régua de sensibilidade e a lista de escopos moram lá,
#: junto do código que elas governam. Perguntar de fora exigiria repetir as duas — e duas
#: cópias da mesma régua divergem, e a que diverge cala.
_SONDA = r"""
import json, os, sys
sys.path.insert(0, "/app")
import identidade as I, tool_scopes as TS
esc = [e.strip() for e in (os.getenv("MCP_ESCOPO") or "").split(",") if e.strip()]
servidas = sorted({t for e in esc for t in TS.tools_do_escopo(e)})
print("JSON " + json.dumps({
    "escopo": esc,
    "servidas": servidas,
    "executam": sorted(t for t in servidas if not I.sensivel(t)),
    "identidade_propria": bool(I.IDENTIDADE_PROPRIA),
    "modo_agente": bool(I.MODO_AGENTE),
}))
"""


def main() -> int:
    if not CONFIG.exists():
        print(f"NÃO VERIFICADO: {CONFIG} não existe")
        print("TOTAL: 0 divergência(s) entre o que o Hermes vê e o que executa")
        return 0
    try:
        import yaml
    except ImportError:
        print("NÃO VERIFICADO: pyyaml ausente no host")
        print("TOTAL: 0 divergência(s) entre o que o Hermes vê e o que executa")
        return 0

    r = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
        [DOCKER, "exec", "-i", CONECTOR, "python3", "-"],
        input=_SONDA,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    linha = next((x for x in r.stdout.splitlines() if x.startswith("JSON ")), "")
    if not linha:
        # Conector fora do ar não é "tudo certo": é o terceiro estado, dito de frente.
        print(f"NÃO MEDIDO: o conector {CONECTOR} não respondeu — {(r.stderr or '').strip()[-160:]}")
        print("TOTAL: 0 divergência(s) entre o que o Hermes vê e o que executa")
        return 0
    d = json.loads(linha[5:])
    executam = set(d["executam"])

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf8")) or {}
    servidor = (cfg.get("mcp_servers") or {}).get("conecta") or {}
    include = set((servidor.get("tools") or {}).get("include") or [])

    achados: list[str] = []
    if not include:
        achados.append(
            f"`include` do conector `conecta` está VAZIO — o Hermes volta a receber as "
            f"{len(d['servidas'])} ferramentas do escopo em todo turno, das quais "
            f"{len(d['servidas']) - len(executam)} só sabem recusar (medido: +20 mil tokens por turno)"
        )
    else:
        faltam = executam - include
        sobram = include - executam
        if faltam:
            achados.append(
                f"{len(faltam)} ferramenta(s) EXECUTAM e o Hermes não as vê: {sorted(faltam)}. "
                f"A lista virou parede — provável que alguém tenha liberado acesso e esquecido daqui"
            )
        if sobram:
            achados.append(
                f"{len(sobram)} ferramenta(s) no `include` NÃO executam: {sorted(sobram)}. "
                f"Voltam a ocupar catálogo para recusar"
            )

    for a in achados:
        print(f"  ✗ {a}")
    print(
        f"conector `conecta`: escopo {','.join(d['escopo'])} · {len(d['servidas'])} servidas · "
        f"{len(executam)} executam · include com {len(include)} · "
        f"identidade própria={d['identidade_propria']}"
    )
    print(f"TOTAL: {len(achados)} divergência(s) entre o que o Hermes vê e o que executa")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
