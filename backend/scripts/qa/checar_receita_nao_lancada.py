#!/usr/bin/env python3
"""NFS-e emitida que não virou receita no razão — e o contrário: teste que virou.

## A regra que isto afirma

Toda NFS-e de PRODUÇÃO, viva (não cancelada), tem exatamente um lançamento de receita no
razão, na competência da própria nota. E nenhuma nota de HOMOLOGAÇÃO tem lançamento nenhum.

Três silêncios diferentes quebram isso, e os três foram medidos em produção em 25/09/2026:

**1. Nota de competência anterior ao corte que chega depois dele.**
`_post()` recusa lançamento antes de `CORTE_CONTABIL` (01/08/2026) — corretamente: jan–jul
foram vividos fora do sistema, e deixar lançamento novo cair lá contamina todo acumulado.
Mas a recusa só deixava uma linha de log. As NFS-e 3 e 4 da Patrimonial (competência
06/2026, R$ 108.386,92) chegaram pelo ADN às 08:30 de 25/09/2026 e **nunca vão entrar no
razão**. Nada avisava.

**2. Competência corrigida na nota que não chega ao razão.**
As NFS-e 109 e 111 nasceram com `competencia_origem_adn = 2026-07` e depois foram
reclassificadas para 2026-06. Os lançamentos ficaram em 07. A purga do repost é escopada a
`data_lancamento >= CORTE`, e esses lançamentos são de 09/07 e 14/07 — nunca são revisitados.
Junho aparecia R$ 108.386,92 a menos e julho exatamente isso a mais.

**3. Nota de homologação virando faturamento.**
O escriturador não filtrava `ambiente`. Em 24/09/2026 duas notas de teste (nº 8 e 9,
R$ 1.500) entraram no DRE de setembro como receita real.

## O que ele NÃO faz

Não lança, não corrige competência, não apaga. Reabrir período fechado e reclassificar
competência são atos de contador. Isto aqui só recusa o silêncio.

Linha canônica: `TOTAL: <n> divergência(s) entre NFS-e e razão`.
"""

from __future__ import annotations

import asyncio
import re
import sys

#: O histórico que o escriturador grava: "Receita NFS-e <numero> (<competencia>)".
RX_HIST = re.compile(r"Receita NFS-e\s+(\S+)\s+\((\d{4}-\d{2})\)")

#: Abaixo disto é poeira de arredondamento.
PISO = 0.01


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    async with async_session_factory() as db:
        notas = (await db.execute(text("""
            SELECT chave_acesso, numero::text, competencia, data_emissao::date, valor_servicos,
                   coalesce(tomador_nome,''), coalesce(ambiente,''), coalesce(cancelada,false),
                   coalesce(competencia_origem_adn,'')
              FROM nfse_emitidas_nacional
             ORDER BY competencia, numero
        """))).all()

        lanc = (await db.execute(text("""
            SELECT coalesce(documento_ref,''), historico, valor, periodo_competencia,
                   data_lancamento::date
              FROM accounting_entries
             WHERE coalesce(tipo_lancamento,'') = 'nfse_emitida'
        """))).all()

    # indexa os lançamentos pela chave de acesso (documento_ref = 'RECNAC-<chave>')
    por_chave: dict[str, list] = {}
    for ref, hist, valor, comp_lanc, data in lanc:
        if not ref.startswith("RECNAC-"):
            continue
        por_chave.setdefault(ref[len("RECNAC-"):], []).append(
            {"valor": float(valor or 0), "comp": comp_lanc, "data": data, "hist": hist or ""}
        )

    sem_lancamento: list = []
    competencia_torta: list = []
    homologacao_lancada: list = []
    duplicados: list = []

    for chave, numero, comp, emissao, vserv, tomador, ambiente, cancelada, comp_adn in notas:
        entradas = por_chave.get(chave, [])
        if ambiente == "homologacao":
            for e in entradas:
                homologacao_lancada.append((numero, comp, e["valor"], e["data"], tomador))
            continue
        if cancelada:
            for e in entradas:
                duplicados.append((numero, comp, e["valor"], "nota CANCELADA ainda lançada"))
            continue
        if not entradas:
            sem_lancamento.append((numero, comp, emissao, float(vserv or 0), tomador, comp_adn))
            continue
        if len(entradas) > 1:
            duplicados.append((numero, comp, sum(e["valor"] for e in entradas),
                               f"{len(entradas)} lançamentos para a mesma nota"))
        for e in entradas:
            if e["comp"] and comp and e["comp"] != comp:
                competencia_torta.append(
                    (numero, comp, e["comp"], e["valor"], comp_adn, tomador)
                )

    vivas_prod = sum(
        1 for _c, _n, _cp, _d, _v, _t, amb, canc, _o in notas
        if amb != "homologacao" and not canc
    )
    print(f"NFS-e de produção vivas: {vivas_prod} · lançamentos de receita no razão: {len(lanc)}")
    print()

    if sem_lancamento:
        total = sum(r[3] for r in sem_lancamento)
        print(f"NUNCA VIRARAM RECEITA — {len(sem_lancamento)} nota(s), R$ {total:,.2f}:")
        for numero, comp, emissao, v, tomador, comp_adn in sorted(sem_lancamento, key=lambda x: -x[3]):
            print(f"  nº {numero:<5} comp {comp or '—':<8} emissão {emissao} "
                  f"R$ {v:>12,.2f}  {tomador[:34]}")
        print("  → Causa provável: competência anterior ao corte contábil (01/08/2026). A")
        print("    recusa é correta; a nota ficar de fora sem ninguém saber, não. Reabrir")
        print("    período é ato de contador.")
        print()

    if competencia_torta:
        total = sum(r[3] for r in competencia_torta)
        print(f"LANÇADAS EM COMPETÊNCIA DIFERENTE DA NOTA — {len(competencia_torta)}, "
              f"R$ {total:,.2f}:")
        for numero, comp, comp_l, v, comp_adn, tomador in sorted(competencia_torta, key=lambda x: -x[3]):
            extra = f" (ADN dizia {comp_adn})" if comp_adn and comp_adn != comp else ""
            print(f"  nº {numero:<5} nota diz {comp}{extra} · razão diz {comp_l} "
                  f"· R$ {v:>12,.2f}  {tomador[:30]}")
        print("  → A competência da nota foi corrigida e o razão ficou com a antiga. O repost")
        print("    só revisita lançamentos a partir do corte, então estes nunca se corrigem.")
        print()

    if homologacao_lancada:
        total = sum(r[2] for r in homologacao_lancada)
        print(f"NOTA DE HOMOLOGAÇÃO LANÇADA COMO RECEITA — {len(homologacao_lancada)}, "
              f"R$ {total:,.2f}:")
        for numero, comp, v, data, tomador in homologacao_lancada:
            print(f"  nº {numero:<5} comp {comp or '—':<8} lançada em {data} "
                  f"R$ {v:>12,.2f}  {tomador[:34]}")
        print("  → Teste virou faturamento. O escriturador passou a filtrar ambiente; o que")
        print("    já está no razão sai sozinho no próximo fechamento (a purga alcança tudo")
        print("    a partir do corte).")
        print()

    if duplicados:
        print(f"OUTRAS DIVERGÊNCIAS — {len(duplicados)}:")
        for numero, comp, v, motivo in duplicados:
            print(f"  nº {numero:<5} comp {comp or '—':<8} R$ {v:>12,.2f}  {motivo}")
        print()

    n = len(sem_lancamento) + len(competencia_torta) + len(homologacao_lancada) + len(duplicados)
    if not n:
        print("Toda NFS-e de produção viva tem receita no razão, na competência certa, e")
        print("nenhuma nota de homologação virou faturamento.")
    print(f"TOTAL: {n} divergência(s) entre NFS-e e razão")
    return 1 if n else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
