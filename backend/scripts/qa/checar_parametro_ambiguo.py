#!/usr/bin/env python3
"""Caçador — parâmetro SQL ambíguo para o asyncpg (24/09/2026).

Por que existe: `text("UPDATE t SET status = :st ... CASE WHEN :st = 'x' ...")` chega ao asyncpg
como um único `$1` usado em dois lugares que deduzem tipos diferentes (`character varying` na
atribuição, `text` na comparação) e o driver recusa a query inteira com AmbiguousParameterError
— em produção vira 500 silencioso no webhook. Provado no sandbox: o webhook da Cora nunca
conseguiu marcar 'efetivada'/'cancelada' em bank_transactions. O mesmo bug já tinha derrubado
`executar_lote_inter` (`:s` em SET e em CASE, 22/09). Com psycopg2 (sessão síncrona) o padrão
passa, e por isso ele sobrevive no código: funciona num controller e explode no outro.

O que conta: no `backend/modules`, uma janela de ±10 linhas onde o MESMO `:p` aparece em
`CASE WHEN :p =` e numa atribuição `col = :p` sem `CAST(:p AS ...)`. A cura é CAST em TODO
uso do parâmetro (o tipo passa a ser um só).

Linha canônica: `TOTAL parâmetros ambíguos: N`. Sai 0 quando N == 0.
"""

from __future__ import annotations

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2] / "modules"


def main() -> int:
    achados: list[str] = []
    for f in sorted(RAIZ.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        linhas = f.read_text(errors="ignore").splitlines()
        for i, linha in enumerate(linhas):
            for p in re.findall(r"CASE WHEN :([a-z_][a-z0-9_]*)\s*=", linha):
                janela = "\n".join(linhas[max(0, i - 10) : i + 10])
                atribui = re.search(rf"(SET|,)\s*[a-z_]+\s*=\s*:{p}\b", janela)
                if atribui and not re.search(rf"CAST\(:{p} AS", janela):
                    achados.append(f"  {f.relative_to(RAIZ.parent)}:{i + 1}  :{p}")
    for a in achados:
        print(a)
    print(f"TOTAL parâmetros ambíguos: {len(achados)}")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
