#!/usr/bin/env python3
"""Coluna varchar(N) com valor ENCOSTADO no teto: o próximo maior vai estourar calado.

Caso real (missão de 06/09/2026): um `varchar(20)` passou meses sem acusar porque o nome
gerado tinha exatamente 20 caracteres — o caso típico cabia, o extremo não. Teste com o caso
típico não pega isto; o banco pega, se alguém perguntar.

Mecânico e sem lista branca: uma coluna só é achado quando os valores têm comprimentos
DIFERENTES e o maior é exatamente N. Coluna de formato fixo (UF 2, CPF 11, CNPJ 14, CEP 8)
tem min == max e fica de fora sozinha — não é teto, é formato.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_varchar_teto.py

Linha canônica (lida por `checar_regressao`): `TOTAL: <n> coluna(s) no teto`.
Exit 1 quando há achado (dívida: entra na base e acusa quando CRESCE).
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    if not Path("/app/scripts").is_dir():
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2
    async with async_session_factory() as db:
        cols = (await db.execute(text(
            "SELECT c.table_name, c.column_name, c.character_maximum_length "
            "FROM information_schema.columns c JOIN pg_stat_user_tables s ON s.relname = c.table_name "
            "WHERE c.table_schema='public' AND c.data_type='character varying' "
            "AND c.character_maximum_length IS NOT NULL AND s.n_live_tup > 0"))).all()
        por_tabela: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for t, c, n in cols:
            por_tabela[t].append((c, int(n)))
        achados = []
        for t, lista in sorted(por_tabela.items()):
            expr = ", ".join(f'min(length("{c}")), max(length("{c}")), count(*) FILTER (WHERE length("{c}") = {n})'
                             for c, n in lista)
            try:
                vals = (await db.execute(text(f'SELECT {expr} FROM "{t}"'))).one()
            except Exception as exc:  # noqa: BLE001 — tabela estranha não derruba a varredura
                print(f"  ? {t}: não consegui medir ({type(exc).__name__})")
                continue
            for i, (c, n) in enumerate(lista):
                mn, mx, no_teto = vals[3 * i], vals[3 * i + 1], vals[3 * i + 2]
                if mn is not None and mx == n and mn < mx:
                    achados.append((t, c, n, mn, mx, int(no_teto)))
    print(f"{len(cols)} coluna(s) varchar(N) em tabelas com dado — medido hoje\n")
    for t, c, n, mn, mx, k in sorted(achados, key=lambda a: (-a[5], a[0])):
        print(f"   {t}.{c}  varchar({n})  comprimentos {mn}..{mx}  {k} linha(s) exatamente no teto")
    print(f"\nTOTAL: {len(achados)} coluna(s) no teto")
    return 1 if achados else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
