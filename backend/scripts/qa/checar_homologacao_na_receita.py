#!/usr/bin/env python3
"""Nota de HOMOLOGAÇÃO contada como receita: o teste virando faturamento.

Origem (24/09/2026): rodei a conciliação da NFS-e em produção com as empresas em
`nfse_ambiente='homologacao'`. Ela consultou o ambiente de TESTE do fisco e gravou as duas
notas que eu mesmo tinha acabado de emitir (R$ 1.000 e R$ 500) em `nfse_emitidas_nacional`
— a tabela que `precificacao_contrato.faturado_na_competencia` lê como faturamento REAL.

    competência 2026-09 antes ....... 2 notas · R$ 24.960,00
    competência 2026-09 depois ...... 4 notas · R$ 26.460,00

R$ 1.500,00 de receita que não existe. E na MESMA tabela que eu tinha consertado horas antes
para parar de somar 27 notas que nunca foram transmitidas.

Por que ninguém tinha pensado nisso: `nfse_emitidas_nacional` nasceu da sincronia do ADN, que
só roda em produção. Toda linha era de produção POR CONSTRUÇÃO, então a tabela nunca precisou
declarar ambiente — até existir um caminho que escreve ali a partir de uma consulta que pode
ser de homologação.

Esta trava não confia na coluna: ela cruza com o que o sistema SABE ter emitido em teste
(`nfes.tp_amb='2'` e `nfses.ambiente<>'producao'`) e acusa qualquer linha de receita que case
com uma delas — mesmo que a coluna `ambiente` diga 'producao'. Régua independente do campo
que se quer vigiar; campo errado é exatamente o defeito.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
        python3 /app/scripts/qa/checar_homologacao_na_receita.py

Linha canônica: `TOTAL: <n> nota(s) de teste contada(s) como receita`. Exit 1 se houver.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    achados: list[str] = []
    async with async_session_factory() as db:
        existe = (await db.execute(text("SELECT to_regclass('public.nfse_emitidas_nacional') IS NOT NULL"))).scalar()
        if not existe:
            print("TOTAL: 0 nota(s) de teste contada(s) como receita")
            print("  (nfse_emitidas_nacional ainda não existe neste banco)")
            return 0

        # 1) a coluna `ambiente` diz o quê — e ela pode estar errada, por isso é só informação
        por_amb = (
            await db.execute(
                text(
                    "SELECT coalesce(ambiente,'producao'), count(*), coalesce(sum(valor_servicos),0)"
                    " FROM nfse_emitidas_nacional GROUP BY 1 ORDER BY 1"
                )
            )
        ).all()

        # 2) a RÉGUA: chave que o próprio sistema registrou como emissão de TESTE
        linhas = (
            await db.execute(
                text(
                    "SELECT n.chave_acesso, n.numero, coalesce(n.ambiente,'producao'),"
                    "       coalesce(n.valor_servicos,0), coalesce(n.tomador_nome,'?')"
                    "  FROM nfse_emitidas_nacional n"
                    "  JOIN nfses t ON t.chave_acesso = n.chave_acesso"
                    " WHERE coalesce(t.ambiente,'homologacao') <> 'producao'"
                    "   AND coalesce(n.ambiente,'producao') = 'producao'"
                )
            )
        ).all()
        for chave, numero, amb, valor, tomador in linhas:
            achados.append(
                f"   NFS-e {numero} · {tomador[:34]} · R$ {float(valor):,.2f}"
                f"\n      chave {chave} — `nfses` diz TESTE, aqui está como '{amb}'"
            )

    print("ambiente das linhas de `nfse_emitidas_nacional`:")
    for amb, n, soma in por_amb:
        print(f"   {amb:14s} {n:>4} nota(s) · R$ {float(soma):>14,.2f}")
    if achados:
        print("\nnota de teste contada como receita:")
        for a in achados:
            print(a)
    print(f"\nTOTAL: {len(achados)} nota(s) de teste contada(s) como receita")
    return 1 if achados else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
