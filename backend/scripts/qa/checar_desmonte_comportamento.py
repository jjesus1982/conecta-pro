#!/usr/bin/env python3
"""Trava por COMPORTAMENTO: roda o oráculo e vê se ele deixou linha para trás.

Substituiu a detecção por FORMA, que acusou 26 e acertou 1 (24/08/2026). Ela não conhecia
`UPDATE … LIKE`, `DELETE … strpos`, limpeza dentro do laço, nem função de desmonte com outro
nome. Sintaxe desconhecida virava acusação — 96% de falso positivo.

A trava por forma foi APAGADA, não comentada nem posta em quarentena: pela regra da casa,
trava que grita sem motivo é trava que se aprende a ignorar, e dar linha de base a um detector
que erra 96% institucionaliza o ruído em vez de removê-lo. Trava comentada é trava que volta.

    por FORMA         o arquivo contém DELETE … LIKE 'ZZ%'     ← erra em toda sintaxe nova
    por COMPORTAMENTO roda · conta antes · conta depois        ← não tem como fugir

Nenhum regex sabe quantas formas de escrever um DELETE existem. A contagem sabe.

⚠️ Só os que ESCREVEM. Os que apenas leem não têm o problema, e rodá-los seria caro sem
motivo. A lista sai do mesmo lugar: `INSERT INTO`/`UPDATE … SET`/`DELETE FROM` no fonte.

⚠️ Ambiente REAL. Oráculo sem credencial de banco "passa" o desmonte perfeitamente — a prova
fica vazia e sai verde, que é a mesma forma de `exibido == banco` sobre 0 linhas.

⚠️ Limite honesto: contagem igual pode significar "limpou" ou "não exercitou" (pré-condição
não atendida, tabela sem dado). Por isso o veredito tem TRÊS estados, e `NÃO EXERCITADO`
nunca é reportado como limpo.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
        python3 /app/scripts/qa/checar_desmonte_comportamento.py [--um <arquivo>]
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import re
import subprocess
import sys

ORQ = pathlib.Path("/app/scripts/orq")
ESCRITA = re.compile(
    r"INSERT\s+INTO\s+(\w+)|UPDATE\s+([a-z_][a-z0-9_]*)\s+SET|DELETE\s+FROM\s+(\w+)", re.I)

#: Tabelas que já morderam esta casa — ordenam a fila.
RISCO = ["hr_payslips", "payable_accounts", "contracts", "occurrences", "gp_clock_punches"]

TIMEOUT = 420


def _tabelas(txt: str) -> list[str]:
    achadas = {g for m in ESCRITA.findall(txt) for g in m if g}
    return sorted(achadas)


async def _contar(tabelas: list[str]) -> dict[str, int]:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    out: dict[str, int] = {}
    async with async_session_factory() as db:
        for t in tabelas:
            try:
                out[t] = int((await db.execute(text(f'SELECT count(*) FROM "{t}"'))).scalar() or 0)
            except Exception:  # noqa: BLE001 — tabela que não existe não é problema deste teste
                continue
    return out


def _rodar(script: pathlib.Path) -> tuple[int, str]:
    amb = dict(os.environ)
    amb["PYTHONPATH"] = "/app"
    try:
        r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                           timeout=TIMEOUT, env=amb)
    except subprocess.TimeoutExpired:
        return 124, "(timeout)"
    return r.returncode, (r.stdout or "") + (r.stderr or "")


async def main() -> int:
    # RECUSA rodar fora do container. `ORQ` é /app/scripts/orq: no host o caminho não existe,
    # o glob volta vazio, a fila fica vazia e o script sai 0 — aprovando por AUSÊNCIA DE
    # MEDIÇÃO. É a terceira encarnação da mesma família em dois dias: ANTES==DEPOIS sobre zero
    # escrita, e o `checar_repositorio` achando 0 no container porque a raiz lá é /app.
    # Fila vazia não é resultado.
    if not ORQ.is_dir():
        print(f"RECUSO: {ORQ} não existe — este check roda DENTRO do container.\n"
              f"  docker exec -e PYTHONPATH=/app conecta-pro-backend python3 "
              f"/app/scripts/qa/{pathlib.Path(__file__).name}")
        return 2

    alvo = None
    if "--um" in sys.argv:
        alvo = sys.argv[sys.argv.index("--um") + 1]

    fila = []
    for f in sorted(ORQ.glob("*.py")):
        if f.name.startswith("_") or (alvo and f.name != alvo):
            continue
        txt = f.read_text(errors="replace")
        tabs = _tabelas(txt)
        if tabs:
            fila.append((min([RISCO.index(t) for t in tabs if t in RISCO] or [99]), f, tabs))
    fila.sort(key=lambda x: (x[0], x[1].name))
    if not fila:
        print("RECUSO: nenhum oráculo que escreve foi encontrado — fila vazia não é verde.")
        return 2

    sujos, limpos, nao_exercitados, quebrados = [], [], [], []
    for _r, f, tabs in fila:
        antes = await _contar(tabs)
        codigo, saida = _rodar(f)
        depois = await _contar(tabs)
        cresceu = {t: depois[t] - antes[t] for t in antes if depois.get(t, antes[t]) > antes[t]}
        # "escreveu?" vem ANTES de "contagem": ANTES==DEPOIS sobre zero escrita passa sempre.
        rodou = bool(saida.strip()) and codigo != 124

        if cresceu:
            sujos.append((f.name, cresceu))
            print(f"  x {f.name}  DEIXOU LINHA: {cresceu}")
        elif not rodou:
            nao_exercitados.append(f.name)
            print(f"  ? {f.name}  NÃO EXERCITADO (sem saída ou timeout) — não conta como limpo")
        elif codigo != 0:
            quebrados.append((f.name, saida.strip().splitlines()[-1][:90] if saida.strip() else ""))
            print(f"  ! {f.name}  reprovou por DEFEITO (exit={codigo}) — limpou, mas achou algo")
        else:
            limpos.append(f.name)
            print(f"  ok {f.name}  ({', '.join(tabs[:3])})")

    print(f"\n  {len(limpos)} limpo(s) · {len(sujos)} deixaram linha · "
          f"{len(nao_exercitados)} não exercitado(s) · {len(quebrados)} com defeito real")
    if quebrados:
        print("\n  ── defeitos REAIS achados ao rodar de verdade (escalar ao dono, não consertar) ──")
        for n, ln in quebrados:
            print(f"    {n}: {ln}")
    if sujos:
        print("\n  ── deixaram linha em produção ──")
        for n, c in sujos:
            print(f"    {n}: {c}")
    return 1 if (sujos or nao_exercitados) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
