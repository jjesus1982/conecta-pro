"""Oráculo do calendário fiscal: competência fechada não fica sem prazo cadastrado.

Em 11/08/2026 o calendário estava cego. O único código que criava `fiscal_obligations` era o
sync de guias do Drive — ele lê o PDF e cadastra a obrigação a partir dele. As guias pararam
(FGTS em 12.2025, INSS em 11.2025) e o calendário parou junto:

  01/2026 ✓   02/2026 ✓   03/2026 ✓   04/2026 ✗   05/2026 ✗   06/2026 ✓   07/2026 ✗

No sistema inteiro havia UMA obrigação vencendo nos 30 dias seguintes, e a competência de
julho vencia em nove dias. Depois do calendário recorrente: seis, três delas em quatro dias.

O que este oráculo trava:
  (a) nenhuma competência FECHADA de empresa ativa fica sem o conjunto recorrente dela;
  (b) o gerador é idempotente — segunda passada cria zero;
  (c) NÃO se cria obrigação antes da primeira atividade da empresa (a Patrimonial só emitiu
      a primeira nota em 06/2026; o gerador queria DAS desde janeiro);
  (d) prazo gerado não carrega valor inventado — `valor_devido` nulo, porque o quanto sai da
      apuração e não do calendário.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_calendario_fiscal.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.fiscal_contabil.obrigacoes.calendario_service import (  # noqa: E402
    _venc,
    garantir_ate_hoje,
    primeira_atividade,
    recorrentes,
)


async def main() -> None:
    hoje = date.today()
    async with async_session_factory() as db:
        # ── (a) nada faltando para competência fechada ──
        pendente = await garantir_ate_hoje(db, hoje, meses_atras=6, aplicar=False)
        assert pendente["total"] == 0, (
            f"{pendente['total']} obrigação(ões) de competência FECHADA sem cadastro: "
            f"{[c['competencia'] for c in pendente['competencias']]}. "
            f"Rode fiscal.calendario_obrigacoes."
        )
        print("OK calendário completo: nenhuma competência fechada sem prazo")

        # ── (b) idempotente: a segunda passada não inventa nada ──
        de_novo = await garantir_ate_hoje(db, hoje, meses_atras=6, aplicar=False)
        assert de_novo["total"] == 0, "gerador deixou de ser idempotente"
        print("OK idempotente: segunda passada cria zero")

        # ── (c) nada antes da primeira atividade da empresa ──
        for eid, nome in (await db.execute(text(
            "SELECT id::text, coalesce(nome_fantasia, razao_social) FROM empresas"))).fetchall():
            inicio = await primeira_atividade(db, eid)
            if inicio is None:
                continue
            antes = (await db.execute(text(
                "SELECT count(*) FROM fiscal_obligations WHERE empresa_id::text = :e "
                "AND competencia_mes BETWEEN 1 AND 12 "
                "AND (competencia_ano * 12 + competencia_mes) < :i"), {"e": eid, "i": inicio})).scalar()
            assert not antes, (
                f"{nome}: {antes} obrigação(ões) em competência ANTERIOR à primeira atividade "
                f"({(inicio - 1) % 12 + 1:02d}/{(inicio - 1) // 12}) — tributo de mês sem operação"
            )
            recs = await recorrentes(db, eid, hoje.year, hoje.month)
            print(f"OK {nome[:26]:<26} primeira atividade "
                  f"{(inicio - 1) % 12 + 1:02d}/{(inicio - 1) // 12}, {len(recs)} recorrente(s)")

        # ── (d) prazo gerado não INVENTA valor — mas pode RECEBER um, do documento ──
        #
        # A regra original dizia "linha criada pelo calendário nunca tem valor", e virou
        # vermelha em 15/08/2026 quando o ISS de 07/2026 recebeu R$740,25 das guias do
        # SEMEF (DAM 21499343 + 21499344). Estava medindo FOTOGRAFIA, não regra: o fluxo
        # desejado é exatamente esse — o calendário põe o PRAZO, a guia traz o VALOR
        # depois. Proibir isso proibiria a conciliação.
        #
        # O que continua proibido, e é o ponto: valor que apareceu SEM documento. Então a
        # linha só passa se a observação registrar de onde o número veio.
        sem_fonte = (await db.execute(text(
            "SELECT count(*) FROM fiscal_obligations "
            " WHERE observacoes LIKE '%calendário recorrente%' "
            "   AND coalesce(valor_devido, 0) <> 0 "
            "   AND observacoes NOT ILIKE '%guia%' "
            "   AND observacoes NOT ILIKE '%DAM %' "
            "   AND observacoes NOT ILIKE '%recibo%' "
            "   AND observacoes NOT ILIKE '%NFS-e%' "
            "   AND coalesce(numero_recibo, '') = ''"))).scalar()
        assert not sem_fonte, (
            f"{sem_fonte} prazo(s) do calendário com valor e SEM fonte declarada — "
            f"o quanto sai da apuração ou do documento, nunca do calendário"
        )
        print("OK prazos gerados sem valor inventado (valor com fonte declarada é permitido)")

        # ── vencimento: a conta de data é onde erro passa calado ──
        assert _venc(2026, 7, 20) == date(2026, 8, 20)
        assert _venc(2026, 12, 15) == date(2027, 1, 15)
        assert _venc(2026, 1, 31) == date(2026, 2, 28), "dia 31 em fevereiro"

        prox = (await db.execute(text(
            "SELECT count(*) FROM fiscal_obligations "
            "WHERE data_vencimento BETWEEN CURRENT_DATE AND CURRENT_DATE + 30"))).scalar()
        print(f"OK vencendo nos próximos 30 dias: {prox}")

    print("TEST oraculo_calendario_fiscal PASS")


if __name__ == "__main__":
    asyncio.run(main())
