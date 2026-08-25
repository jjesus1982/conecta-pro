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

⭐ VIÉS DO INSTRUMENTO AMPLO (`--todos`), exposto pelo próprio controle em 24/08/2026:
`n_tup_ins` conta TUPLA, **inclusive a que o rollback desfez** — e inserir-e-reverter é o
caminho normal de vários oráculos. Quem vir `n_tup_ins` subir e concluir "escrita persistida"
vai errar: dos 14 acusados naquele dia, 12 escreviam só em log/telemetria (esperado) e os
outros 2 eram rollback puro (`gp_clock_punches` 9351 → 9351). **Zero resíduo real.**
Por isso `pg_stat` APONTA onde olhar e `count(*)` DECIDE.

E o controle que revelou isso é a razão de rodar sempre um: `termination_processes` ins
53 → 54 num oráculo que sabidamente insere. Ele não só validou o instrumento — expôs um viés
dele, que é a melhor coisa que um controle pode fazer.

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

#: Oráculos que escrevem pela CAMADA DE APLICAÇÃO (controller, dispatcher de ação, POST) e
#: não têm SQL nenhum no arquivo. A detecção por `INSERT/UPDATE/DELETE` NÃO OS VÊ — e foi por
#: aí que `test_acao_medida_redesign` acumulou 26 advertências disciplinares na ficha de uma
#: pessoa entre 03/08 e 24/08 sem nunca entrar nesta varredura.
#: Como não dá para inferir a tabela do SQL (não há SQL), ela é DECLARADA aqui, uma a uma.
TABELAS_DECLARADAS: dict[str, list[str]] = {
    "test_acao_medida_redesign.py": ["disciplinary_actions", "redesign_gate_otp"],
    "test_oraculo_ferias_autoritativa.py": ["employee_vacation_requests",
                                            "employee_vacation_periods"],
}

#: Tabelas que já morderam esta casa — ordenam a fila.
RISCO = ["hr_payslips", "payable_accounts", "contracts", "occurrences", "gp_clock_punches"]

TIMEOUT = 420


def _tabelas(txt: str) -> list[str]:
    achadas = {g for m in ESCRITA.findall(txt) for g in m if g}
    return sorted(achadas)


async def _estatisticas() -> dict[str, tuple[int, int]]:
    """(linhas inseridas, linhas apagadas) acumuladas POR TABELA, direto do Postgres.

    Instrumento para a varredura AMPLA (`--todos`): não olha o código, olha o banco. Vê
    escrita que entrou por SQL, por ORM, por controller ou por qualquer outro caminho — que é
    exatamente o ponto cego que deixou 26 advertências disciplinares acumularem por 21 dias
    sem nenhuma trava ver, porque o oráculo grava por `rd_action_*` e não tem uma linha de SQL.

    ⚠️ Grep foi quem criou aquele ponto cego. Não se conserta ponto cego de grep com mais grep.
    """
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    async with async_session_factory() as db:
        linhas = (await db.execute(text(
            "SELECT relname, n_tup_ins, n_tup_del FROM pg_stat_user_tables"))).all()
    return {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in linhas}


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

    todos = "--todos" in sys.argv
    alvo = None
    if "--um" in sys.argv:
        alvo = sys.argv[sys.argv.index("--um") + 1]

    fila = []
    for f in sorted(ORQ.glob("*.py")):
        if f.name.startswith("_") or (alvo and f.name != alvo):
            continue
        txt = f.read_text(errors="replace")
        tabs = _tabelas(txt) or TABELAS_DECLARADAS.get(f.name, [])
        if todos and not tabs:
            tabs = ["__stat__"]  # sem tabela conhecida: mede pelo estado do Postgres
        if tabs:
            fila.append((min([RISCO.index(t) for t in tabs if t in RISCO] or [99]), f, tabs))
    fila.sort(key=lambda x: (x[0], x[1].name))
    if not fila:
        print("RECUSO: nenhum oráculo que escreve foi encontrado — fila vazia não é verde.")
        return 2

    sujos, limpos, nao_exercitados, quebrados = [], [], [], []
    for _r, f, tabs in fila:
        if tabs == ["__stat__"]:
            e0 = await _estatisticas()
            main._snapshot = await _contar(sorted(e0))  # contagem REAL antes, p/ desempatar
            codigo, saida = _rodar(f)
            e1 = await _estatisticas()
            suspeitas = {t: (e1[t][0] - e0[t][0]) - (e1[t][1] - e0[t][1])
                         for t in e1 if t in e0
                         and (e1[t][0] - e0[t][0]) - (e1[t][1] - e0[t][1]) > 0}
            # `n_tup_ins` conta TUPLA, inclusive a revertida por rollback — e o caminho normal
            # de vários oráculos é justamente inserir e dar rollback. Medido em 24/08/2026:
            # dos 14 acusados por pg_stat, os 2 em tabela de negócio eram insert REVERTIDO
            # (gp_clock_punches 9351 → 9351). pg_stat aponta ONDE olhar; a contagem decide.
            sobrou = {}
            if suspeitas:
                reais = await _contar(sorted(suspeitas))
                antes_reais = getattr(main, "_snapshot", {})
                sobrou = {t: n for t, n in suspeitas.items()
                          if reais.get(t, 0) > antes_reais.get(t, reais.get(t, 0))}
                if not sobrou:
                    print(f"  ok {f.name}  (escreveu e reverteu — pg_stat via tupla, "
                          f"contagem não mudou: {sorted(suspeitas)})")
                    limpos.append(f.name)
                    continue
            if sobrou:
                sujos.append((f.name, sobrou))
                print(f"  x {f.name}  DEIXOU LINHA (via pg_stat): {sobrou}")
            elif not (saida.strip() and codigo != 124):
                nao_exercitados.append(f.name)
                print(f"  ? {f.name}  NÃO EXERCITADO")
            else:
                escreveu_algo = any((e1[t][0] - e0[t][0]) > 0 for t in e1 if t in e0)
                limpos.append(f.name)
                print(f"  ok {f.name}  ({'escreveu e limpou' if escreveu_algo else 'não escreveu'})")
            continue
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
