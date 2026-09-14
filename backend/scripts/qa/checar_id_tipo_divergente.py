#!/usr/bin/env python3
"""Coluna `*_id` de um tipo comparando com um `id` de outro: o JOIN devolve 500 ou zero linha.

Caso real (bateria E2E de 14/09/2026), duas vezes no mesmo dia:

  1. `time_sheets.employee_id` é VARCHAR e `employees.id` é UUID. Um filtro novo entrou com
     `employee_id NOT IN (SELECT id FROM employees ...)` e o Postgres recusou a comparação:
     «operator does not exist: character varying = uuid». O endpoint que calcula e fecha o
     espelho da Portaria 671 devolvia HTTP 500 em QUALQUER competência — a função mais exigida
     legalmente do módulo, morta, e ninguém viu.

  2. `employee_alocacoes.condominio_id` aponta para `condominios`, e o builder fazia
     `LEFT JOIN clients`. Os dois lados eram UUID, então o Postgres não reclamou: o join
     simplesmente não casou nenhuma das 73 linhas e a tela mostrou «—» para todo mundo.

São os dois jeitos de errar: tipo divergente **grita** (500), tabela errada **cala** (zero
linha). Este caçador pega o primeiro, que é o que derruba a tela.

O que ele faz, sem lista branca: para cada coluna `<algo>_id` de uma tabela com dado, procura a
tabela candidata pelo nome (`<algo>` e `<algo>s`) e compara o tipo da coluna com o tipo do `id`
dela. Tipos diferentes = achado. Coluna sem tabela candidata é ignorada — não é achado, é só um
nome que não segue a convenção.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_id_tipo_divergente.py

Linha canônica (lida por `checar_regressao`): `TOTAL: <n> coluna(s) com tipo divergente`.
Exit 1 quando há achado (dívida: entra na base e acusa quando CRESCE).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

#: Sufixos de coluna que NÃO apontam para tabela alguma — id de sistema externo, protocolo,
#: identificador de dispositivo. Pegar estes seria ruído puro.
IGNORAR = (
    "inter_payment_id",
    "external_id",
    "device_id",
    "rep_serial",
    "tenant_id",  # multi-tenant: aponta para conceito, não para uma tabela só
    "session_id",
)


def _candidatas(coluna: str) -> list[str]:
    """Nomes de tabela plausíveis para uma coluna `<algo>_id`."""
    base = coluna[:-3]  # tira o "_id"
    nomes = {base, base + "s"}
    if base.endswith("y"):
        nomes.add(base[:-1] + "ies")
    if base.endswith("o"):  # condominio → condominios
        nomes.add(base + "s")
    return sorted(nomes)


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    if not Path("/app/scripts").is_dir():
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    async with async_session_factory() as db:
        # tipo do `id` de cada tabela do schema público
        ids = {
            t: d
            for t, d in (
                await db.execute(
                    text(
                        "SELECT table_name, data_type FROM information_schema.columns "
                        "WHERE table_schema='public' AND column_name='id'"
                    )
                )
            ).all()
        }
        # colunas *_id de tabelas COM dado (tabela vazia não quebra ninguém hoje)
        cols = (
            await db.execute(
                text(
                    "SELECT c.table_name, c.column_name, c.data_type "
                    "FROM information_schema.columns c "
                    "JOIN pg_stat_user_tables s ON s.relname = c.table_name "
                    "WHERE c.table_schema='public' AND c.column_name LIKE '%\\_id' "
                    "AND c.column_name <> 'id' AND s.n_live_tup > 0 "
                    "ORDER BY c.table_name, c.column_name"
                )
            )
        ).all()

    achados: list[tuple[str, str, str, str, str]] = []
    examinadas = 0
    for tabela, coluna, tipo in cols:
        if coluna in IGNORAR:
            continue
        alvo = next((n for n in _candidatas(coluna) if n in ids), None)
        if not alvo:
            continue  # sem tabela candidata: não dá para afirmar nada
        examinadas += 1
        if ids[alvo] != tipo:
            achados.append((tabela, coluna, tipo, alvo, ids[alvo]))

    print(f"{examinadas} coluna(s) *_id com tabela candidata — medido hoje\n")
    for t, c, tc, alvo, ta in achados:
        print(f"   {t}.{c} é {tc.upper()}  ×  {alvo}.id é {ta.upper()}")
        print(f"      → um JOIN ou NOT IN entre os dois devolve 'operator does not exist: {tc} = {ta}'")
    print(f"\nTOTAL: {len(achados)} coluna(s) com tipo divergente")
    return 1 if achados else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
