#!/usr/bin/env python3
"""Remove artefatos de teste E2E (prefixo `ZZE2E`/`ZZ `) do banco de produção.

Os terminais rodam QA end-to-end contra a base real e deixam registros para trás
— em 2026-08-10 havia 15 espalhados por 10 tabelas, o mais antigo de 27/06. Eles
poluem o CRM (aparecem no funil junto de oportunidade de verdade) e distorcem
contagem.

Conservador por construção:
  • dry-run por padrão;
  • só apaga o que casa com o PREFIXO de teste, nunca "contém";
  • **recusa apagar registro REFERENCIADO** por outra tabela (FK) — some a origem
    e sobra o filho órfão. Esses são listados para decisão humana;
  • `--modulo crm` limita ao CRM (default), `--tudo` varre o banco inteiro.

  docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
    python3 scripts/limpar_lixo_e2e.py                 # preview do CRM
  ... python3 scripts/limpar_lixo_e2e.py --aplicar
  ... python3 scripts/limpar_lixo_e2e.py --tudo        # preview do banco inteiro
"""

import argparse
import asyncio
import os
import sys

import asyncpg

PREFIXOS = ("ZZE2E", "ZZ_E2E")
TABELAS_CRM = ("leads", "opportunities", "proposals", "customers", "contacts", "clients")


async def _referencias(con, tabela: str, ident) -> int:
    """Quantas linhas de OUTRAS tabelas apontam para este id (via FK declarada)."""
    fks = await con.fetch(
        """SELECT tc.table_name, kcu.column_name
             FROM information_schema.table_constraints tc
             JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
             JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = $1""",
        tabela,
    )
    total = 0
    for fk in fks:
        try:
            total += await con.fetchval(
                f'SELECT count(*) FROM "{fk["table_name"]}" WHERE "{fk["column_name"]}" = $1', ident
            )
        except Exception:  # noqa: BLE001 — tipo incompatível = não é referência de verdade
            pass
    return total


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="sem isto, só mostra o que faria")
    ap.add_argument("--tudo", action="store_true", help="varre o banco inteiro, não só o CRM")
    a = ap.parse_args()

    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url)
    try:
        tabelas = [
            r["table_name"]
            for r in await con.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1"
            )
        ]
        if not a.tudo:
            tabelas = [t for t in tabelas if t in TABELAS_CRM]

        apagar, presos = [], []
        for t in tabelas:
            cols = [
                r["column_name"]
                for r in await con.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name=$1 AND data_type IN ('text','character varying')",
                    t,
                )
            ]
            if not cols:
                continue
            # PREFIXO, não 'contém': um cliente real chamado "...zze2e..." não seria alvo.
            cond = " OR ".join(f'"{c}" ILIKE ANY($1)' for c in cols)
            padroes = [f"{p}%" for p in PREFIXOS]
            # Mostra o valor que CASOU, não um rótulo adivinhado: em `allocations` o
            # match veio de `notes`, e um preview exibindo a coluna `status` ("active")
            # esconderia por que a linha vai ser apagada. Preview de deleção tem de
            # justificar a deleção.
            casou = ", ".join(
                f"""coalesce("{c}",'')""" for c in cols
            )
            try:
                linhas = await con.fetch(
                    f'SELECT id, concat_ws(\' | \', {casou}) AS todos FROM "{t}" WHERE {cond}', padroes
                )
            except Exception as e:  # noqa: BLE001 — tabela sem `id` própria
                print(f"  (pulei {t}: {str(e)[:50]})")
                continue
            for ln in linhas:
                n = await _referencias(con, t, ln["id"])
                # o trecho ZZE2E dentro do concat — é a evidência
                pedaco = next(
                    (p for p in str(ln["todos"]).split(" | ") if p.upper().startswith(PREFIXOS)), str(ln["todos"])
                )
                (presos if n else apagar).append((t, ln["id"], pedaco[:34], n))

        print(f"{'tabela':26} {'registro':36} situação")
        for t, _i, r, _n in apagar:
            print(f"  {t:24} {r:36} apaga")
        for t, _i, r, n in presos:
            print(f"  {t:24} {r:36} PRESO ({n} referência(s)) — não apago")

        if not apagar and not presos:
            print("  (nada encontrado)")
        elif a.aplicar and apagar:
            # Ordem importa: um alvo pode estar PRESO por outro alvo (a proposta de
            # teste segura a oportunidade de teste). Apagar o filho libera o pai, então
            # repassa até não haver mais progresso — sem hardcodar ordem de tabela.
            fila, feitos = apagar + presos, 0
            while fila:
                rodada = []
                for t, ident, r, _n in fila:
                    if await _referencias(con, t, ident):
                        rodada.append((t, ident, r, 1))
                        continue
                    await con.execute(f'DELETE FROM "{t}" WHERE id = $1', ident)
                    feitos += 1
                if len(rodada) == len(fila):  # nenhum saiu nesta passada: para
                    break
                fila = rodada
            print(f"\nAPAGADOS: {feitos}")
            for t, _i, r, _n in fila:
                print(f"  MANTIDO (preso por registro que não é de teste): {t} · {r}")
        elif not a.aplicar:
            print("\n(preview — nada foi apagado. Repita com --aplicar.)")
    finally:
        await con.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
