#!/usr/bin/env python3
"""Mede a taxa de captura de DIMENSIONAMENTO nas fichas de lead do José Luís.

A régua é do plano irmão (`2026-08-09-jose-luis-sdr.md`, Task 7): capturar
primeiro, medir ~2 semanas, e só derivar `expected_value` quando `unidades`
estiver presente em **mais de 60%** das fichas novas. Derivar antes seria
fórmula sem insumo — hoje as oportunidades nascem com `value=0` justamente
por isso.

BASELINE em 2026-08-10, antes da mudança de prompt (7 fichas):
    unidades              2/7  (29%)
    postos_portaria_hoje  1/7  (14%)

  docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
    python3 scripts/medir_captura_dimensionamento.py            # tudo
  ... python3 scripts/medir_captura_dimensionamento.py --desde 2026-08-10   # só o depois
"""

import argparse
import asyncio
import json
import sys

from sqlalchemy import text

from core.database import async_session_factory

META_UNIDADES = 0.60  # régua do plano p/ liberar a derivação de expected_value
CAMPOS = ("unidades", "postos_portaria_hoje", "tipo_imovel", "blocos", "tem_guarita", "portoes_veiculares")
BASELINE = {"unidades": (2, 7), "postos_portaria_hoje": (1, 7)}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", help="AAAA-MM-DD — conta só fichas atualizadas a partir daí")
    a = ap.parse_args()

    sql = (
        "SELECT name, qualificacao, updated_at FROM leads "
        "WHERE qualificacao IS NOT NULL AND qualificacao::text <> '{}'"
    )
    params: dict = {}
    if a.desde:
        sql += " AND updated_at >= :d"
        params["d"] = a.desde

    async with async_session_factory() as db:
        rows = (await db.execute(text(sql), params)).mappings().all()

    if not rows:
        print("Nenhuma ficha no período — nada a medir (não confunda com 0%).")
        return 0

    fichas = []
    for r in rows:
        q = r["qualificacao"]
        fichas.append(json.loads(q) if isinstance(q, str) else (q or {}))

    total = len(fichas)
    print(f"{total} fichas{' desde ' + a.desde if a.desde else ''}\n")
    print(f"  {'campo':24} {'presente':>10} {'taxa':>7}   baseline (pré-prompt)")
    taxa_unidades = 0.0
    for campo in CAMPOS:
        n = sum(1 for f in fichas if f.get(campo) not in (None, "", []))
        taxa = n / total
        if campo == "unidades":
            taxa_unidades = taxa
        base = ""
        if campo in BASELINE:
            bn, bt = BASELINE[campo]
            base = f"{bn}/{bt} ({bn / bt * 100:.0f}%)"
        print(f"  {campo:24} {f'{n}/{total}':>10} {taxa * 100:6.0f}%   {base}")

    print()
    if taxa_unidades > META_UNIDADES:
        print(f"META ATINGIDA — `unidades` em {taxa_unidades * 100:.0f}% (> {META_UNIDADES * 100:.0f}%).")
        print("Liberado derivar expected_value (Task 7 do plano irmão, 2a metade).")
        print("Âncoras reais medidas na época: mediana R$ 10.954 · média R$ 19.264 · faixa R$ 500–65.842.")
    else:
        falta = int((META_UNIDADES * total - sum(1 for f in fichas if f.get("unidades"))) + 1)
        print(f"AINDA NÃO — `unidades` em {taxa_unidades * 100:.0f}%, meta > {META_UNIDADES * 100:.0f}%.")
        print(f"Faltam ~{max(falta, 0)} fichas com unidades neste recorte. NÃO derivar valor ainda.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
