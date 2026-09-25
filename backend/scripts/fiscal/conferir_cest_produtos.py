#!/usr/bin/env python3
"""Confere o CEST dos produtos contra o Convênio ICMS 142/2018 — e recusa o que não tem respaldo.

Roda depois de `importar_cest_convenio142.py`. Faz três coisas, nesta ordem:

  1. **PREENCHE** `fin_produtos.cest` quando o Convênio dá um CEST único para o NCM e o produto
     não tem nenhum;
  2. **CORRIGE** quando o produto tem um CEST diferente do que o Convênio dá para aquele NCM;
  3. **MARCA para revisão** o CEST declarado por fornecedor que não encontra respaldo — sem
     apagar às cegas, porque há um caso em que o errado é a tabela, não o CEST (ver abaixo).

## Por que não se copia o CEST do fornecedor

Medido em 25/09/2026 nos 14 CESTs declarados nas notas de compra desta casa: **11 conferem,
3 estão errados.** Um controle remoto de portão como «peça de veículo automotor», naftalina e
um sensor magnético como «venda porta a porta». O CEST vai DENTRO da nossa nota de saída —
copiar o do fornecedor propaga o erro dele com o nosso CNPJ embaixo.

## ⚠️ O caso em que o Convênio é que está velho

O Convênio 142/18 cita NCMs da redação vigente em 2018. Algumas dessas posições **foram
extintas** em revisões posteriores da NCM e não existem mais na tabela atual.

Medido: o NVR do catálogo tem NCM **8521.90.00** e o fornecedor declarou CEST 21.061.00. O
Convênio associa esse CEST a **8521.90.90** — que **não existe** na tabela oficial de hoje,
enquanto 8521.90.00 existe. O CEST do fornecedor está certo; o texto do Convênio é que
envelheceu.

Por isso a etapa 3 **marca para revisão** em vez de apagar: «sem respaldo» pode significar
«CEST errado» **ou** «NCM do Convênio extinto». Distinguir exige olhar caso a caso, e apagar
o certo é pior que manter o suspeito sinalizado.

Uso:
    python3 backend/scripts/fiscal/conferir_cest_produtos.py <html-do-convenio> [--aplicar]

Linha canônica: `TOTAL: <n> produto(s) com CEST ajustado`.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts/fiscal")


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    caminho = next((a for a in sys.argv[1:] if not a.startswith("--")), "")
    if not caminho:
        print("uso: conferir_cest_produtos.py <html-do-convenio> [--aplicar]")
        return 2
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415

        from importar_cest_convenio142 import casar, ler_convenio  # noqa: PLC0415
    except ModuleNotFoundError as e:
        print(f"RECUSO: roda DENTRO do container e ao lado do importador ({e})")
        return 2

    tabela = ler_convenio(caminho)
    por_cest = {r["cest"]: r for r in tabela}
    preencher: list[tuple] = []
    corrigir: list[tuple] = []
    revisar: list[tuple] = []

    async with async_session_factory() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT codigo, descricao, coalesce(ncm,'') ncm, coalesce(cest,'') cest"
                    " FROM fin_produtos WHERE coalesce(ativo,true) ORDER BY codigo"
                )
            )
        ).mappings().all()

        for r in rows:
            ncm, atual = r["ncm"], r["cest"]
            oficiais = {a["cest"] for a in casar(tabela, ncm)} if len(ncm) == 8 else set()
            unico = next(iter(oficiais)) if len(oficiais) == 1 else ""
            if atual and unico and atual != unico:
                corrigir.append((r, unico))
            elif not atual and unico:
                preencher.append((r, unico))
            elif atual and not unico:
                reg = por_cest.get(atual)
                cobre = bool(reg) and any(len(p) >= 4 and ncm.startswith(p) for p in reg["ncms"])
                if not cobre:
                    motivo = (
                        f"CEST {atual} não existe no Convênio"
                        if not reg
                        else f"o Convênio associa o CEST {atual} a «{reg['descricao'][:50]}»"
                        f" (NCM {', '.join(reg['ncms'][:2]) or 'por capítulo'}), e o produto é NCM {ncm}"
                    )
                    revisar.append((r, motivo))

        for titulo, lista in (("PREENCHER", preencher), ("CORRIGIR", corrigir)):
            print(f"{titulo}: {len(lista)}")
            for r, novo in lista[:10]:
                de = f"{r['cest']} -> " if r["cest"] else ""
                print(f"   {r['codigo']:<16} NCM {r['ncm']}  {de}{novo}   [{r['descricao'][:28]}]")
        print(f"REVISAR (sem respaldo — pode ser CEST errado OU NCM do Convênio extinto): {len(revisar)}")
        for r, motivo in revisar:
            print(f"   {r['codigo']:<16} NCM {r['ncm']} CEST {r['cest']}  [{r['descricao'][:26]}]")
            print(f"        {motivo}")

        if aplicar:
            for r, novo in preencher + corrigir:
                await db.execute(
                    text(
                        "UPDATE fin_produtos SET cest = CAST(:c AS VARCHAR),"
                        " observacao = coalesce(observacao,'') || ' | CEST ' || CAST(:c AS TEXT)"
                        " || ' do Convenio ICMS 142/2018 (conferido 25/09/2026)' || CAST(:x AS TEXT),"
                        " atualizado_em = now() WHERE codigo = CAST(:cod AS VARCHAR)"
                    ),
                    {
                        "c": novo,
                        "cod": r["codigo"],
                        "x": f" — substituiu {r['cest']}, declarado pelo fornecedor" if r["cest"] else "",
                    },
                )
            for r, motivo in revisar:
                await db.execute(
                    text(
                        "UPDATE fin_produtos SET observacao = coalesce(observacao,'')"
                        " || ' | ⚠️ CEST A REVISAR (25/09/2026): ' || CAST(:m AS TEXT)"
                        " || '. Nao apagado: pode ser CEST errado OU NCM que o Convenio cita e foi extinto.',"
                        " atualizado_em = now() WHERE codigo = CAST(:cod AS VARCHAR)"
                    ),
                    {"m": motivo, "cod": r["codigo"]},
                )
            await db.commit()

    print(f"\nTOTAL: {len(preencher) + len(corrigir)} produto(s) com CEST ajustado"
          f" · {len(revisar)} marcado(s) para revisão"
          f" {'GRAVADO' if aplicar else '(conferência, nada gravado)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
