#!/usr/bin/env python3
"""Religa documentos órfãos ao cliente cadastrado — pelo NOME que está no próprio título.

POR QUE EXISTE (BUG-04, 30/09/2026)
`crm_documents.ref_tipo`/`ref_id` existem desde sempre e ninguém preenchia no caminho do
orçamento: `gerar_orcamento` recebia o cliente como TEXTO LIVRE e morria aí. O cliente
CLI-2026-00020 (Villa Toscana) recebeu dois orçamentos e `ver_ficha_cliente` devolvia
`negociacao: null` e nenhum documento — o dono olhava a ficha e concluía que não havia
nada, com mais de R$ 100 mil em papel emitido, invisível.

A rota já foi corrigida: documento novo nasce vinculado. Este script é só o passado.

O QUE ELE FAZ E O QUE NÃO FAZ
Preenche uma FK que está NULA. Não apaga, não altera valor, não muda flag, não mexe em
documento que já tem vínculo. É aditivo e reversível (`ref_tipo`/`ref_id` de volta a NULL).

COMO CASA
O título é «<Tipo> <NÚMERO> - <NOME DO CLIENTE>». O nome depois do « - » é comparado com
`clients.name` por igualdade exata sem caixa. Casamento PARCIAL é recusado de propósito:
«CONDOMINIO VILLA» casaria com Villa Toscana e Villa-Lobos, e vincular o documento ao
cliente errado é pior que deixá-lo sem vínculo.

    --aplicar   grava. Sem ele, só mostra (dry-run é o padrão).
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

SQL = """
SELECT d.id::text AS doc_id, d.tipo, d.titulo,
       btrim(split_part(d.titulo, ' - ', 2)) AS nome_no_titulo,
       c.id::text AS cliente_id, c.name AS cliente_nome
  FROM crm_documents d
  LEFT JOIN clients c
         ON upper(c.name) = upper(btrim(split_part(d.titulo, ' - ', 2)))
 WHERE d.ref_id IS NULL
   AND d.arquivado = false
   AND position(' - ' in coalesce(d.titulo,'')) > 0
 ORDER BY d.created_at DESC
"""


async def main(aplicar: bool) -> int:
    async with async_session_factory() as db:
        linhas = (await db.execute(text(SQL))).mappings().all()
        casados = [r for r in linhas if r["cliente_id"]]
        sem = [r for r in linhas if not r["cliente_id"]]

        print(f"{len(linhas)} documento(s) sem vinculo com ' - ' no titulo")
        print(f"  {len(casados)} casam com um cliente cadastrado (nome exato)")
        print(f"  {len(sem)} NAO casam - ficam como estao\n")

        for r in casados:
            print(f"  LIGAR  {r['titulo'][:64]:<64} -> {r['cliente_nome']}")
        if sem:
            print("\n  sem cliente cadastrado com este nome exato:")
            vistos = set()
            for r in sem:
                if r["nome_no_titulo"] not in vistos:
                    vistos.add(r["nome_no_titulo"])
                    print(f"    {r['nome_no_titulo'][:70]}")

        if not aplicar:
            print(f"\nDRY-RUN. Nada foi gravado. Rode com --aplicar para ligar os {len(casados)}.")
            return 0

        for r in casados:
            await db.execute(
                text(
                    "UPDATE crm_documents SET ref_tipo='client', ref_id=:c "
                    " WHERE id = CAST(:d AS uuid) AND ref_id IS NULL"
                ),
                {"c": r["cliente_id"], "d": r["doc_id"]},
            )
        await db.commit()
        conferido = (
            await db.execute(text("SELECT count(*) FROM crm_documents WHERE ref_tipo='client' AND arquivado=false"))
        ).scalar()
        print(f"\nAPLICADO. {len(casados)} ligado(s). Total com vinculo agora: {conferido}.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--aplicar" in sys.argv)))
