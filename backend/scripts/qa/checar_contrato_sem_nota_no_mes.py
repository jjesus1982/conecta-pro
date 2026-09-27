#!/usr/bin/env python3
"""Contrato ativo, já fora da carência, que não virou nota na competência.

## A regra que isto afirma

Contrato ativo, com valor, vigente na competência e **com a carência já vencida** tem de
virar nota até o dia de faturar. O que não virou é serviço prestado e não cobrado.

## Por que ele existe, se já havia dois parentes

`checar_contrato_vs_faturado.py` e `checar_contrato_vs_nota.py` existem e **não pegaram** o
buraco de setembro/2026. As razões, medidas em 26/09, valem a leitura porque explicam o
desenho deste aqui:

  • O primeiro **exclui o mês corrente por desenho** (`MESES=3`, e `_competencias()` começa
    em `mes-1`). A justificativa dele está certa: *"acusar dia 10 que não faturou é alarme
    que ensina a ignorar o painel."* Mas assim o buraco só aparece no mês seguinte.
  • E a cláusula `start_date <= :fim` dele foi **adicionada por causa do Green Hills**, para
    matar um falso positivo em 25/09 — a mesma linha que matou o falso positivo cegou para
    o contrato novo.
  • O segundo tem `_DIA_DE_COBRAR = 11` e aponta para a competência anterior; além disso
    invoca `/usr/bin/docker`, que não existe dentro do container.

Este olha a competência **CORRENTE**, e resolve a tensão "cedo demais × tarde demais" com o
`DIA_DE_FATURAR`: antes dele, cala; a partir dele, cobra.

## A carência — e a lição que ela deu

O `CTR-2026-00019` (Green Hills, R$ 22.100/mês, ativo desde 01/09/2026) **não deve nota em
setembro**: o contrato tem 90 dias de carência e a primeira nota é de dezembro. O dado
sempre esteve certo — `contracts.grace_period_days = 90`, gravado na assinatura.

**O que faltava era alguém lê-lo.** Em 26/09/2026, os únicos usos de `grace_period_days` em
todo o código eram o formulário que o captura (`juridico.py:654`) e dois SELECT que copiam
colunas. Nenhuma lógica de faturamento, cobrança ou vigia o consultava.

Sem esta regra, este caçador nasceria acusando R$ 22.100 de falso positivo por três meses
seguidos — e alarme falso recorrente é exatamente como se ensina alguém a ignorar o painel.

Linha canônica: `TOTAL: <n> contrato(s) ativo(s) sem nota na competência`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

#: A partir deste dia do mês, contrato sem nota é cobrança — antes, é cedo.
#: 11 é o mesmo número que `checar_contrato_vs_nota.py` já usava; manter dois valores
#: diferentes para o mesmo fato é como se cria a próxima divergência.
DIA_DE_FATURAR = 11

#: Abaixo disto não vale a atenção de ninguém.
PISO = 100.0


def _fim_da_competencia(comp: str) -> date:
    ano, mes = int(comp[:4]), int(comp[5:7])
    return date(ano + mes // 12, mes % 12 + 1, 1) - __import__("datetime").timedelta(days=1)


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    hoje = date.today()
    comp = f"{hoje:%Y-%m}"
    if hoje.day < DIA_DE_FATURAR:
        print(
            f"  dia {hoje.day} — antes do dia {DIA_DE_FATURAR} de faturar. A competência {comp} ainda não é cobrança."
        )
        print("\nTOTAL: 0 contrato(s) ativo(s) sem nota na competência")
        return 0

    total, valor_total = 0, 0.0
    async with async_session_factory() as db:
        linhas = (
            (
                await db.execute(
                    text("""
            SELECT e.razao_social empresa, c.contract_number num, left(cl.name, 34) cliente,
                   c.monthly_value valor, c.start_date, c.end_date,
                   coalesce(c.grace_period_days, 0) carencia,
                   (SELECT coalesce(sum(n.valor_servicos), 0)
                      FROM nfse_emitidas_nacional n
                     WHERE n.empresa_id = c.empresa_id
                       AND n.competencia = :comp
                       AND coalesce(n.cancelada, false) = false
                       AND coalesce(n.ambiente, '') <> 'homologacao'
                       AND regexp_replace(coalesce(n.tomador_cnpj, ''), '\\D', '', 'g')
                         = regexp_replace(coalesce(cl.document_number, ''), '\\D', '', 'g')
                   ) faturado
              FROM contracts c
              JOIN empresas e ON e.id = c.empresa_id
         LEFT JOIN clients cl ON cl.id = c.client_id
             WHERE c.status = 'active'
             ORDER BY e.razao_social, c.monthly_value DESC
        """),
                    {
                        "comp": comp,
                        "piso": PISO,
                        "fim": _fim_da_competencia(comp),
                        "ini": date(hoje.year, hoje.month, 1),
                    },
                )
            )
            .mappings()
            .all()
        )

        em_carencia, descartados = [], []
        fim_comp = _fim_da_competencia(comp)
        ini_comp = date(hoje.year, hoje.month, 1)

        for r in linhas:
            # O FILTRO DECLARA O QUE DESCARTA. A consulta traz todos os ativos e a exclusão
            # acontece aqui, contada e com motivo — porque filtro que descarta calado faz
            # «0 contratos sem nota» parecer «tudo faturado». Medido em 26/09/2026: o
            # CTR-2026-00018 venceu em 31/08 e continua `active`, e o CTR-2026-00022 fatura
            # R$ 23.160 com `monthly_value = 0`. Os dois sairiam sem deixar rastro.
            if float(r["valor"] or 0) <= PISO:
                descartados.append((r, f"valor mensal R$ {float(r['valor'] or 0):,.2f} (abaixo do piso)"))
                continue
            if r["start_date"] and r["start_date"] > fim_comp:
                descartados.append((r, f"começa em {r['start_date']:%d/%m/%Y}, depois da competência"))
                continue
            if r["end_date"] and r["end_date"] < ini_comp:
                descartados.append((r, f"venceu em {r['end_date']:%d/%m/%Y} — mas o status ainda é 'active'"))
                continue
            # A carência corre a partir do início do contrato. Enquanto o fim da competência
            # não passar dela, não há nota a cobrar — e dizer que há é ensinar a ignorar.
            fim_carencia = r["start_date"] + __import__("datetime").timedelta(days=int(r["carencia"]))
            if r["carencia"] and _fim_da_competencia(comp) < fim_carencia:
                em_carencia.append((r, fim_carencia))
                continue
            if float(r["faturado"]) > 0:
                continue
            total += 1
            valor_total += float(r["valor"])
            print(
                f"  {r['empresa'][:28]:<28} {r['num']:<16} {r['cliente'][:30]:<30}"
                f" R$ {float(r['valor']):>11,.2f}  SEM NOTA em {comp}"
            )

        if em_carencia:
            print()
            for r, ate in em_carencia:
                print(
                    f"  (carência) {r['num']:<16} {r['cliente'][:30]:<30}"
                    f" R$ {float(r['valor']):>11,.2f}  1ª nota a partir de {ate:%d/%m/%Y}"
                )

        if descartados:
            print(f"\n  não avaliados ({len(descartados)}) — e o motivo de cada um:")
            for r, motivo in descartados:
                print(f"     {r['num']:<16} {r['cliente'][:30]:<30} {motivo}")

    if total:
        print(f"\n  valor não faturado na competência {comp}: R$ {valor_total:,.2f}")
    print(f"\nTOTAL: {total} contrato(s) ativo(s) sem nota na competência")
    return 1 if total else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
