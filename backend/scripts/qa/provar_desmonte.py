#!/usr/bin/env python3
"""Prova de desmonte de UM oráculo, nas três perguntas — na ordem que importa.

    escreveu?   o oráculo chegou a exercitar a escrita?  ← vem PRIMEIRO
    [1]         contagem da tabela antes == depois
    [2]         uma linha REAL vizinha (sem a marca) continua lá

A ordem não é estética. `ANTES == DEPOIS` sobre zero escrita passa sempre — é a mesma forma de
`exibido == banco` sobre 0 linhas, e eu quase publiquei uma prova assim em 24/08/2026 rodando
o oráculo com env sem credencial de banco.

E a [2] é a que separa "limpou" de "limpou SÓ O SEU". Sem ela, um `DELETE` largo demais passa
nas outras duas com louvor.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/qa/provar_desmonte.py <oraculo.py> <tabela> [coluna_da_marca] [marca]
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import subprocess
import sys

ORQ = pathlib.Path("/app/scripts/orq")


async def _estado(tabela: str, coluna: str | None, marca: str | None):
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    async with async_session_factory() as db:
        n = int((await db.execute(text(f'SELECT count(*) FROM "{tabela}"'))).scalar() or 0)
        vizinha = None
        if coluna and marca:
            # vizinha REAL: uma linha que NÃO tem a marca. É ela que prova que o desmonte não
            # levou dado de produção junto.
            vizinha = (await db.execute(text(
                f'SELECT "{coluna}"::text FROM "{tabela}" '
                f"WHERE strpos(coalesce(\"{coluna}\"::text, ''), :m) = 0 LIMIT 1"),
                {"m": marca})).scalar()
        return n, vizinha


async def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    if not ORQ.is_dir():
        print(f"RECUSO: {ORQ} não existe — rode DENTRO do container.")
        return 2

    nome, tabela = sys.argv[1], sys.argv[2]
    coluna = sys.argv[3] if len(sys.argv) > 3 else None
    marca = sys.argv[4] if len(sys.argv) > 4 else None
    script = ORQ / nome
    if not script.is_file():
        print(f"RECUSO: {script} não existe")
        return 2

    antes, vizinha = await _estado(tabela, coluna, marca)

    amb = dict(os.environ)
    amb["PYTHONPATH"] = "/app"
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                       timeout=600, env=amb)
    saida = (r.stdout or "") + (r.stderr or "")
    # "escreveu?" — sem saída nenhuma o oráculo não rodou, e as outras duas viram teatro.
    escreveu = bool(saida.strip())

    depois, _ = await _estado(tabela, coluna, marca)
    ainda = None
    if vizinha is not None and coluna:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415

        async with async_session_factory() as db:
            # >= 1, não == 1: a coluna não é chave. Numa tabela de DEDUP a descrição repete
            # de propósito, e exigir unicidade fez a prova reprovar por defeito MEU.
            ainda = int((await db.execute(text(
                f'SELECT count(*) FROM "{tabela}" WHERE "{coluna}"::text = :v'),
                {"v": vizinha})).scalar() or 0)

    ok1 = antes == depois
    ok2 = (ainda >= 1) if vizinha is not None else None
    print(f"  {nome}  [{tabela}]")
    print(f"    escreveu? ......... {'SIM' if escreveu else 'NÃO — prova seria vazia'} "
          f"(exit={r.returncode})")
    print(f"    [1] contagem ...... {antes} == {depois}  {'OK' if ok1 else 'FALHOU'}")
    if ok2 is None:
        print("    [2] vizinha real .. (não medida — informe coluna e marca)")
    else:
        print(f"    [2] vizinha real .. {str(vizinha)[:28]!r}  {'OK' if ok2 else 'FALHOU'}")
    if r.returncode not in (0,) and escreveu:
        ultima = saida.strip().splitlines()[-1][:110]
        print(f"    ⚠ o oráculo reprovou (exit={r.returncode}): {ultima}")
    return 0 if (escreveu and ok1 and ok2 is not False) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
