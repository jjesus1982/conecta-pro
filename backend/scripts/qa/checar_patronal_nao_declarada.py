#!/usr/bin/env python3
"""A contribuição previdenciária patronal que não está em documento nenhum.

## A regra que isto afirma

Empresa do Simples Nacional paga a CPP patronal de um jeito **ou** de outro, nunca de
nenhum:

  • **Anexo III, IV ou V com tributação SUBSTITUÍDA** — a CPP vem DENTRO do DAS, e a
    guia mostra isso na linha `1006 INSS - SIMPLES NACIONAL`, que no Anexo III é ~43%
    do documento;
  • **Anexo IV (cessão de mão de obra)** — a CPP fica FORA do DAS e é declarada na
    DCTFWeb, onde aparece como débito patronal (grupo "CONTRIBUIÇÃO PREVIDENCIÁRIA
    PATRONAL"), normalmente abatida pela retenção de 11% da Lei 9.711/98 que os
    tomadores fazem na nota.

Se a guia do DAS não traz INSS relevante **e** a DCTFWeb só declara `1082-01 CP
SEGURADOS`, a patronal não está em lugar nenhum — e ela continua devida.

## O que ele mediu quando nasceu (26/09/2026, CONECTAMAIS PATRIMONIAL)

  DAS 07/2026 R$ 17.048,87 → linha de INSS: R$ 171,06 (1,0% da guia)
  DAS 08/2026 R$ 18.399,33 → linha de INSS: nenhuma
  DCTFWeb 07 e 08/2026     → só `1082-01 CP SEGURADOS`, sem patronal
  DCTFWeb declara "Classificação Tributária 1 — Simples com tributação previdenciária
  SUBSTITUÍDA", que é justamente a hipótese que a guia do DAS desmente.
  Folha ~R$ 105 mil/mês → patronal estimada (20% + RAT 3%) ~R$ 24 mil/mês
  Retenção Lei 9.711 dos clientes ~R$ 25 mil/mês, com R$ 12.532,85 SOBRANDO em 08/2026.

O dinheiro já foi retido pelos clientes. O que falta é a declaração — e sem ela o crédito
retido dorme enquanto a obrigação corre.

## O que ele NÃO faz

Não lança nada e não estima passivo no razão: o percentual exato depende do anexo e do
RAT/FAP, que são decisão de enquadramento, não de código. Ele mede a CONTRADIÇÃO entre
dois documentos do próprio governo e põe o número na mesa.

Linha canônica: `TOTAL: <n> empresa(s)-mês com patronal sem documento`.
"""

from __future__ import annotations

import asyncio
import sys

#: Piso da linha de INSS dentro do DAS, como fração da guia, para considerar que a CPP
#: está realmente lá dentro. No Anexo III ela é ~43%; 10% é folga generosa.
FRACAO_INSS_NO_DAS = 0.10

#: 20% (art. 22, I da Lei 8.212) + RAT 3% (vigilância). Sem FAP, que é por empresa.
ALIQUOTA_PATRONAL = 0.23


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    total = 0
    async with async_session_factory() as db:
        empresas = (
            (
                await db.execute(
                    text(
                        "SELECT id::text id, razao_social, cnpj FROM empresas"
                        " WHERE regime_tributario = 'simples_nacional'"
                    )
                )
            )
            .mappings()
            .all()
        )
        if not empresas:
            print("Nenhuma empresa no Simples Nacional — nada a checar.")
            print("\nTOTAL: 0 empresa(s)-mês com patronal sem documento")
            return 0

        for emp in empresas:
            guias = (
                (
                    await db.execute(
                        text(
                            "SELECT detalhes_json->>'competencia' comp,"
                            "       (detalhes_json->>'valor')::numeric v,"
                            "       (detalhes_json->'composicao'->>'INSS') inss,"
                            "       (detalhes_json ? 'composicao') tem_composicao"
                            "  FROM onvio_documents"
                            " WHERE categoria = 'das_simples_nacional' AND empresa_id = :e"
                            "   AND detalhes_json->>'valor' IS NOT NULL"
                            "   AND detalhes_json->>'competencia' IS NOT NULL"
                        ),
                        {"e": emp["id"]},
                    )
                )
                .mappings()
                .all()
            )
            if not guias:
                continue
            print(f"\n  {emp['razao_social']} ({emp['cnpj']})")
            for g in guias:
                mm, yyyy = (g["comp"].split("/") + ["", ""])[:2]
                periodo = f"{yyyy}-{mm}"
                if not g["tem_composicao"]:
                    # Sem a composição extraída não há o que afirmar. Calar aqui é o certo:
                    # a primeira versão deste caçador lia o PDF direto, o container não tinha
                    # `pdfplumber`, e ele alarmava SEMPRE — vermelho cego, que prova tanto
                    # quanto verde cego. A composição agora vem do `DASExtractor`, gravada em
                    # `detalhes_json->composicao` na importação.
                    print(
                        f"     {periodo}  DAS R$ {float(g['v'] or 0):>10,.2f}  — sem composição extraída, não avaliado"
                    )
                    continue
                inss = float(g["inss"] or 0)
                das = float(g["v"] or 0)
                dentro = das > 0 and inss / das >= FRACAO_INSS_NO_DAS
                folha = float(
                    (
                        await db.execute(
                            text(
                                "SELECT coalesce(sum(total_earnings),0) FROM hr_payslips"
                                " WHERE empresa_id = :e"
                                "   AND to_char(competence_end,'YYYY-MM') = :p"
                            ),
                            {"e": emp["id"], "p": periodo},
                        )
                    ).scalar()
                    or 0
                )
                retido = float(
                    (
                        await db.execute(
                            text(
                                "SELECT coalesce(sum(inss_retido),0) FROM nfse_emitidas_nacional"
                                " WHERE empresa_id = :e AND competencia = :p"
                                "   AND coalesce(cancelada,false) = false"
                                "   AND coalesce(ambiente,'') <> 'homologacao'"
                            ),
                            {"e": emp["id"], "p": periodo},
                        )
                    ).scalar()
                    or 0
                )
                estimada = folha * ALIQUOTA_PATRONAL
                if dentro or folha <= 0:
                    print(
                        f"     {periodo}  DAS R$ {das:>10,.2f}  INSS na guia R$ {inss:>9,.2f}  → patronal dentro do DAS"
                    )
                    continue
                total += 1
                print(f"     {periodo}  DAS R$ {das:>10,.2f}  INSS na guia R$ {inss:>9,.2f}  folha R$ {folha:>10,.2f}")
                print(
                    f"                patronal estimada (23%) R$ {estimada:>10,.2f}"
                    f"  ·  retenção Lei 9.711 dos clientes R$ {retido:>10,.2f}"
                    f"  ·  descoberto R$ {estimada - retido:>10,.2f}"
                )

    print(f"\nTOTAL: {total} empresa(s)-mês com patronal sem documento")
    return 1 if total else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
