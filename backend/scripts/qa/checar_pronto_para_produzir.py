#!/usr/bin/env python3
"""O que falta para emitir a PRIMEIRA nota fiscal de verdade — NF-e e NFS-e, por CNPJ.

Não é trava de regressão: é uma LISTA DE CONFERÊNCIA, para responder numa tela só a pergunta
que o Jordan fez em 25/09/2026 — *«quero depois emitir a primeira nota pelo conecta pro»*.

Nasceu porque a resposta estava espalhada: ambiente em `empresas`, frase-senha no `.env`,
numeração em duas tabelas, tributação no cadastro do produto, e três decisões dele registradas
em `auditoria/frentes/DECISOES_FISCAIS_PENDENTES.md`. Perguntar isso a mão, no dia, é como se
perde meia hora e se erra um item.

Cada linha diz o ESTADO e QUEM resolve. Ela não muda nada — só olha.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
        python3 /app/scripts/qa/checar_pronto_para_produzir.py

Linha canônica: `TOTAL: <n> item(ns) faltando para emitir em produção`. Exit 1 se faltar algo.
Exit 0 significa que o caminho está livre — NÃO significa que o dono mandou emitir.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

#: (rótulo, quem resolve). «dono» = decisão de negócio; «sistema» = a casa resolve sozinha.
DONO, SISTEMA = "dono", "sistema"


async def main() -> int:  # noqa: PLR0912, PLR0915 — é uma lista de conferência, é linear
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    faltam: list[tuple[str, str, str]] = []  # (quem, item, detalhe)
    ok: list[str] = []

    async with async_session_factory() as db:
        empresas = (
            (
                await db.execute(
                    text(
                        "SELECT slug, razao_social, regexp_replace(cnpj,'\\D','','g') AS cnpj,"
                        "       coalesce(inscricao_estadual,'') AS ie,"
                        "       coalesce(nfse_ambiente,'homologacao') AS amb_nfse,"
                        "       coalesce(nfse_serie_rps,'') AS serie_nfse"
                        "  FROM empresas WHERE status = 'ativa' ORDER BY razao_social"
                    )
                )
            )
            .mappings()
            .all()
        )

        # ── 1. A frase-senha de cada documento (mora no .env; zona proibida p/ o agente) ──
        for var, doc in (("NFE_PRODUCAO_LIBERADA", "NF-e"), ("NFSE_PRODUCAO_LIBERADA", "NFS-e")):
            if os.environ.get(var):
                ok.append(f"{doc}: gate `{var}` definido")
            else:
                faltam.append((DONO, f"{doc}: gate `{var}` não definido", "só o dono põe no `.env` de produção"))

        # ── 2. O ambiente declarado por empresa (NFS-e) e global (NF-e) ──
        amb_nfe = os.environ.get("NFE_AMBIENTE", "2")
        if amb_nfe == "1":
            ok.append("NF-e: `NFE_AMBIENTE=1` (produção)")
        else:
            faltam.append((DONO, f"NF-e: `NFE_AMBIENTE` = {amb_nfe} (homologação)", "trocar para 1 no `.env`"))

        for e in empresas:
            nome = e["razao_social"].replace("CONECTAMAIS ", "")
            if e["amb_nfse"] == "producao":
                ok.append(f"NFS-e {nome}: ambiente produção")
            else:
                faltam.append(
                    (
                        DONO,
                        f"NFS-e {nome}: `empresas.nfse_ambiente` = {e['amb_nfse']}",
                        "UPDATE empresas SET nfse_ambiente='producao'",
                    ),
                )

        # ── 3. Numeração: o último número REAL tem de estar declarado ANTES da 1ª emissão ──
        for e in empresas:
            nome = e["razao_social"].replace("CONECTAMAIS ", "")
            if e["ie"].strip():  # só quem tem IE emite NF-e 55
                n = (
                    await db.execute(
                        text("SELECT count(*) FROM nfe_numeracao WHERE emitente_cnpj = :c AND tp_amb = '1'"),
                        {"c": e["cnpj"]},
                    )
                ).scalar_one()
                if n:
                    ok.append(f"NF-e {nome}: numeração de produção declarada")
                else:
                    faltam.append(
                        (
                            DONO,
                            f"NF-e {nome}: último número real não declarado",
                            "o emissor RECUSA emitir sem isto (NUMERACAO_NAO_DECLARADA)",
                        ),
                    )
            n2 = (
                await db.execute(
                    text("SELECT count(*) FROM nfse_numeracao WHERE prestador_cnpj = :c AND ambiente = 'producao'"),
                    {"c": e["cnpj"]},
                )
            ).scalar_one()
            if n2:
                ok.append(f"NFS-e {nome}: numeração de produção declarada")
            else:
                faltam.append(
                    (
                        DONO,
                        f"NFS-e {nome}: último nº de DPS de produção não declarado",
                        "série + último número, para não colidir com o portal da contabilidade",
                    ),
                )

            if not e["serie_nfse"].strip():
                faltam.append(
                    (
                        DONO,
                        f"NFS-e {nome}: série não declarada em `empresas.nfse_serie_rps`",
                        "sandbox usa 900 e o portal usa 70000 — produção precisa da sua",
                    ),
                )
            else:
                ok.append(f"NFS-e {nome}: série {e['serie_nfse']}")

        # ── 4. Produto sem saber como entrou não pode sair numa NF-e ──
        existe = (await db.execute(text("SELECT to_regclass('public.fin_produtos') IS NOT NULL"))).scalar()
        if existe:
            sem = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM fin_produtos"
                        " WHERE coalesce(ativo,true) AND coalesce(icms_entrada_cst,'') = ''"
                    )
                )
            ).scalar_one()
            tot = (await db.execute(text("SELECT count(*) FROM fin_produtos WHERE coalesce(ativo,true)"))).scalar_one()
            if sem:
                faltam.append(
                    (
                        SISTEMA,
                        f"{sem} de {tot} produtos sem saber como a mercadoria ENTROU",
                        "vem do XML da NF-e de compra; sem isso o emissor recusa o item",
                    ),
                )
            else:
                ok.append(f"todos os {tot} produtos com entrada conhecida")

        # ── 5. Nota de compra sem XML: é de onde sai o item 4 ──
        sem_xml = (
            await db.execute(text("SELECT count(*) FROM nfe_entradas WHERE coalesce(xml_raw,'') = ''"))
        ).scalar_one()
        if sem_xml:
            faltam.append(
                (
                    SISTEMA,
                    f"{sem_xml} NF-e de compra sem o XML completo",
                    "manifestadas em 25/09; a SEFAZ distribui o procNFe em NSU novos",
                ),
            )
        else:
            ok.append("todas as NF-e de compra com XML")

    print("PRONTO:")
    for o in ok:
        print(f"   ok  {o}")
    if faltam:
        print("\nFALTA:")
        for quem, item, detalhe in faltam:
            print(f"   {'DONO   ' if quem == DONO else 'sistema'}  {item}")
            print(f"            → {detalhe}")
    print(f"\nTOTAL: {len(faltam)} item(ns) faltando para emitir em produção")
    if not faltam:
        print("  O CAMINHO ESTÁ LIVRE. Isto não é ordem de emitir — quem manda é o dono.")
    return 1 if faltam else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
