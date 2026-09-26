#!/usr/bin/env python3
"""Custo que se repete todo mês e não está cadastrado em lugar nenhum.

## A regra que isto afirma

Não se planeja o que não se vê. Um custo que sai da conta em 4 ou mais meses distintos é
compromisso recorrente — e precisa existir em `financial_custos_recorrentes` para entrar em
orçamento, previsão de caixa e decisão de corte.

Medido em 25/09/2026: a tabela tinha **3 linhas, todas `[TESTE]`, todas inativas**. Zero
custos recorrentes ativos. Enquanto isso, o extrato mostrava **R$ 702.682,49 em 26
contrapartes que se repetem**, entre elas:

    SOLIDES TECNOLOGIA     R$ 167.989,89 no ano · ~R$ 21.536/mês · parou em 16/07
    Caixa (FGTS)           R$ 102.179,35 · ~R$ 12.772/mês
    Cruz Queiroz Advogados R$  15.000,00 · R$ 3.000/mês exatos
    One Port Tecnologia    R$  14.607,13
    Atlas Monitoramento    R$  13.408,71

A Sólides sozinha custava R$ 21 mil por mês e existia apenas como 8 a 12 PIX espalhados no
extrato. Nenhuma tela mostrava «pagamos isto todo mês».

## O que ele separa, e por quê

**Folha** (CPF que está no cadastro de funcionários) é recorrente por natureza e já tem
lugar próprio — aparece contada, não listada. O que interessa listar é o **compromisso com
terceiro**: plataforma, assessoria, monitoramento, aluguel, assinatura.

E marca o que **PAROU**: contraparte recorrente sem pagamento há mais de 45 dias ou foi
encerrada — e então deve sair do orçamento — ou está atrasada. As duas coisas são decisão,
e nenhuma aparece sozinha.

## O que ele NÃO faz

Não cadastra nada. Cadastrar custo recorrente é decisão de quem assina o contrato: valor,
vigência, se renova. A trava mede a lacuna.

Linha canônica: `TOTAL: <n> custo(s) recorrente(s) fora do cadastro`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

#: Quantos meses distintos com pagamento fazem de algo "recorrente".
MESES_MINIMO = 4
#: Abaixo disto não vale um compromisso de orçamento.
PISO_ANO = 3000.0
#: Sem pagamento há mais tempo que isto: parou ou está atrasado. As duas coisas são decisão.
DIAS_PARA_SUSPEITA = 45


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    async with async_session_factory() as db:
        cadastrados = {
            (r[0] or "").strip().upper()
            for r in (await db.execute(text(
                "SELECT coalesce(favorecido, descricao) FROM financial_custos_recorrentes "
                " WHERE coalesce(ativo, FALSE) IS TRUE"
            ))).all()
        }
        n_cad = len(cadastrados)

        # Agrupa pela CHAVE do fornecedor, não pelo par (documento, nome). Quando o
        # extrato preencheu o documento numa linha e não na outra, o par separa o MESMO
        # fornecedor em dois — e «decidir por contraparte resolve em lote» deixa de valer.
        # Medido em 26/09/2026, logo depois de o extrator passar a nomear 545 transações:
        # «Solides» e «Sólides» viraram duas linhas (R$ 86.144,00 + R$ 81.845,89), e
        # «One Port Tecnologia» apareceu duas vezes, uma com CNPJ e outra sem.
        # A normalização é a do radar de fornecedores — mesma casa, mesmo problema.
        brutas = (await db.execute(text("""
            SELECT regexp_replace(coalesce(counterparty_document,''), '[^0-9]', '', 'g') doc,
                   coalesce(nullif(counterparty_name,''), '(sem nome)') nome,
                   to_char(transaction_date, 'YYYY-MM') comp, transaction_date::date dia,
                   abs(amount) v
              FROM bank_transactions
             WHERE amount < 0
               AND transaction_date >= (CURRENT_DATE - INTERVAL '12 months')
        """))).all()

        from modules.financial.services.plano_contas_caixa import (  # noqa: PLC0415
            CNPJS_DO_GRUPO,
        )
        from modules.financial.services.radar_fornecedores_service import (  # noqa: PLC0415
            _chave as chave_fornecedor,
        )

        hoje = date.today()
        grupos: dict[str, dict] = {}
        for doc, nome, comp, dia, v in brutas:
            # Dinheiro que a Patrimonial manda para a Eletrônica não é custo com
            # terceiro — é transferência entre os nossos CNPJs, e o razão já a leva para
            # `1.1.9.01`. Sem este filtro ela entrava na lista como o segundo maior
            # «compromisso recorrente» da empresa (R$ 169.800 em 4 meses, sob o nome de
            # registro da própria Eletrônica), e ninguém a cortaria do orçamento porque
            # não há o que cortar.
            if doc in CNPJS_DO_GRUPO:
                continue
            k = doc or chave_fornecedor(nome) or "(sem nome)"
            g = grupos.setdefault(
                k, {"doc": "", "nomes": {}, "meses": set(), "n": 0, "total": 0.0, "ultimo": dia}
            )
            if doc and not g["doc"]:
                g["doc"] = doc
            g["nomes"][nome] = g["nomes"].get(nome, 0.0) + float(v)
            g["meses"].add(comp)
            g["n"] += 1
            g["total"] += float(v)
            g["ultimo"] = max(g["ultimo"], dia)

        linhas = [
            (
                g["doc"],
                # o rótulo é a variante de nome que mais dinheiro moveu neste grupo
                max(g["nomes"].items(), key=lambda kv: kv[1])[0],
                len(g["meses"]),
                g["n"],
                round(g["total"], 2),
                round(g["total"] / len(g["meses"]), 2),
                g["ultimo"],
                (hoje - g["ultimo"]).days,
            )
            for g in grupos.values()
            if len(g["meses"]) >= MESES_MINIMO and g["total"] >= PISO_ANO
        ]
        linhas.sort(key=lambda r: -float(r[4]))

        cpfs_func = {
            r[0] for r in (await db.execute(text(
                "SELECT regexp_replace(coalesce(cpf,''), '[^0-9]', '', 'g') FROM employees"
            ))).all() if r[0] and len(r[0]) == 11
        }

    folha = [r for r in linhas if r[0] in cpfs_func]
    terceiros = [r for r in linhas if r[0] not in cpfs_func]
    fora = [r for r in terceiros if (r[1] or "").strip().upper() not in cadastrados]

    print(f"custos recorrentes ATIVOS no cadastro: {n_cad}")
    print(f"contrapartes que repetem ({MESES_MINIMO}+ meses, ≥ R$ {PISO_ANO:,.0f}/ano): {len(linhas)}")
    print(f"  delas, folha (CPF de funcionário): {len(folha)} · "
          f"R$ {sum(float(r[4]) for r in folha):,.2f}")
    print(f"  delas, compromisso com terceiro ..: {len(terceiros)} · "
          f"R$ {sum(float(r[4]) for r in terceiros):,.2f}")
    print()

    if fora:
        print(f"FORA DO CADASTRO — {len(fora)} compromisso(s), "
              f"R$ {sum(float(r[4]) for r in fora):,.2f} nos últimos 12 meses:")
        print(f"   {'contraparte':<34} {'meses':>5} {'total':>13} {'média/mês':>12}  último")
        for doc, nome, meses, _n, total, media, ultimo, dias in fora:
            t = "CNPJ" if len(doc) == 14 else "CPF " if len(doc) == 11 else "----"
            marca = f"  ⚠ parado há {dias}d" if dias and int(dias) > DIAS_PARA_SUSPEITA else ""
            print(f"   {t} {nome[:29]:<29} {meses:>5} R$ {float(total):>10,.2f} "
                  f"R$ {float(media):>9,.2f}  {ultimo}{marca}")
        print()
        print("   → Sem cadastro, nenhum destes entra em orçamento nem em previsão de caixa.")
        print("     Os marcados como parados são decisão: encerrar de vez (e tirar do")
        print("     orçamento) ou é pagamento atrasado.")

    print(f"\nTOTAL: {len(fora)} custo(s) recorrente(s) fora do cadastro")
    return 1 if fora else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
