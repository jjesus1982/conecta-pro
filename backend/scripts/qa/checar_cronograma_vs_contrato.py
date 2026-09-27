#!/usr/bin/env python3
"""Linha do cronograma que não bate com o contrato — e contrato sem linha.

## A regra que isto afirma

Desde 27/09/2026 o cronograma de emissão **nasce do contrato** (`semear_de_contratos`).
Mas ele continua aceitando linha escrita à mão, e deve mesmo: valor combinado por fora,
serviço extra do mês, cobrança de uma empresa por outra. O que não pode é a divergência
existir **em silêncio** — porque é ela que vira nota no valor errado.

Três coisas que este caçador separa:

  • **linha sem contrato** — alguém transcreveu algo que não tem contrato por trás;
  • **contrato sem linha** — o contrato existe, está vigente, fora da carência, e não vai
    virar nota;
  • **valor ou empresa divergente** — os dois existem e discordam.

## Por que ele existe

Até 27/09 a única fonte era `_SEED_2026_09`: 14 linhas de Python transcritas à mão da
planilha `.ods` do dono. Medido naquele dia, ao abrir a planilha:

  • as duas abas (`Conectamais` e `Cópia_de_Conectamais`) diferem em UMA linha — Mirante
    limpeza R$ 12.061,50 numa e R$ 13.561,50 na outra — **e a planilha não diz qual vale**;
  • a coluna de data diz `XX/XX` em todas as 14 linhas: ela não sabe de que mês é;
  • o cabeçalho diz «Conectamais Eletrônica» e a lista mistura clientes das duas empresas —
    a empresa era adivinhada lendo os dados bancários no texto da descrição;
  • a linha do Green Hills descrevia o contrato VELHO (R$ 500,00, da Eletrônica, hoje
    `terminated`) enquanto o novo, de R$ 22.100,00, não tinha linha nenhuma;
  • duas linhas estavam com `empresa_cnpj` VAZIO, e a rota de emissão as recusa com
    `EMPRESA_SEM_FONTE`.

## O que ele NÃO faz

Não corrige a linha nem apaga nada. Valor divergente pode ser erro de transcrição OU
acordo do mês, e só quem fez sabe.

Linha canônica: `TOTAL: <n> divergência(s) entre cronograma e contrato`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta

#: Centavo de arredondamento não é divergência.
TOLERANCIA = 0.01


def _fim(comp: str) -> date:
    a, m = int(comp[:4]), int(comp[5:7])
    return date(a + m // 12, m % 12 + 1, 1) - timedelta(days=1)


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    total = 0
    async with async_session_factory() as db:
        comps = [
            r[0]
            for r in (
                await db.execute(text("SELECT DISTINCT competencia FROM nfse_cronograma ORDER BY 1 DESC LIMIT 2"))
            ).all()
        ]
        if not comps:
            print("  cronograma vazio — nada a comparar")
            print("\nTOTAL: 0 divergência(s) entre cronograma e contrato")
            return 0

        for comp in sorted(comps):
            print(f"\n  competência {comp}")
            ini, fim = date(int(comp[:4]), int(comp[5:7]), 1), _fim(comp)

            contratos = (
                (
                    await db.execute(
                        text(r"""
                SELECT c.contract_number num, c.monthly_value valor,
                       coalesce(c.grace_period_days,0) carencia, c.start_date,
                       regexp_replace(coalesce(cl.document_number,''),'\D','','g') tomador,
                       coalesce(cl.name,'(sem nome)') nome,
                       regexp_replace(coalesce(e.cnpj,''),'\D','','g') empresa
                  FROM contracts c
                  JOIN clients cl ON cl.id = c.client_id
                  JOIN empresas e ON e.id = c.empresa_id
                 WHERE c.status='active' AND coalesce(c.monthly_value,0) > 0
                   AND c.start_date <= :fim
                   AND (c.end_date IS NULL OR c.end_date >= :ini)
            """),
                        {"ini": ini, "fim": fim},
                    )
                )
                .mappings()
                .all()
            )
            linhas = (
                (
                    await db.execute(
                        text(
                            "SELECT ordem, tomador_cnpj, tomador_nome, valor_bruto,"
                            "       coalesce(empresa_cnpj,'') empresa, estado, fonte"
                            "  FROM nfse_cronograma WHERE competencia = :c ORDER BY ordem"
                        ),
                        {"c": comp},
                    )
                )
                .mappings()
                .all()
            )

            usadas: set[int] = set()
            for ct in contratos:
                fim_car = ct["start_date"] + timedelta(days=int(ct["carencia"]))
                if ct["carencia"] and fim < fim_car:
                    print(
                        f"     (carência) {ct['num']:<16} {ct['nome'][:30]:<30}"
                        f" R$ {float(ct['valor']):>11,.2f}  1ª nota a partir de {fim_car:%d/%m/%Y}"
                    )
                    continue
                par = [
                    i
                    for i, ln in enumerate(linhas)
                    if i not in usadas
                    and ln["tomador_cnpj"] == ct["tomador"]
                    and abs(float(ln["valor_bruto"]) - float(ct["valor"])) <= TOLERANCIA
                ]
                if par:
                    usadas.add(par[0])
                    ln = linhas[par[0]]
                    if ln["empresa"] and ln["empresa"] != ct["empresa"]:
                        total += 1
                        print(
                            f"     x EMPRESA {ct['num']:<14} {ct['nome'][:28]:<28}"
                            f" cronograma {ln['empresa']} × contrato {ct['empresa']}"
                        )
                    elif not ln["empresa"]:
                        total += 1
                        print(
                            f"     x SEM EMPRESA {ct['num']:<11} {ct['nome'][:28]:<28}"
                            " — a rota de emissão recusa com EMPRESA_SEM_FONTE"
                        )
                    continue
                # mesmo tomador, valor diferente
                quase = [i for i, ln in enumerate(linhas) if i not in usadas and ln["tomador_cnpj"] == ct["tomador"]]
                total += 1
                if quase:
                    usadas.add(quase[0])
                    ln = linhas[quase[0]]
                    d = float(ln["valor_bruto"]) - float(ct["valor"])
                    print(
                        f"     x VALOR   {ct['num']:<16} {ct['nome'][:28]:<28}"
                        f" cronograma R$ {float(ln['valor_bruto']):>11,.2f}"
                        f" × contrato R$ {float(ct['valor']):>11,.2f}  ({d:+,.2f})"
                    )
                else:
                    print(
                        f"     x SEM LINHA {ct['num']:<14} {ct['nome'][:28]:<28}"
                        f" R$ {float(ct['valor']):>11,.2f} — contrato vigente que não vira nota"
                    )

            for i, ln in enumerate(linhas):
                if i in usadas:
                    continue
                total += 1
                print(
                    f"     x SEM CONTRATO ordem {ln['ordem']:<3} {ln['tomador_nome'][:28]:<28}"
                    f" R$ {float(ln['valor_bruto']):>11,.2f}  (fonte: {ln['fonte']})"
                )

    print(f"\nTOTAL: {total} divergência(s) entre cronograma e contrato")
    return 1 if total else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
