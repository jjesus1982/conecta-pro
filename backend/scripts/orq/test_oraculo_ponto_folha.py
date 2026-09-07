#!/usr/bin/env python3
"""Quem bateu ponto no mês tem holerite do mês — batida × espelho × folha.

7.827 batidas em `gp_clock_punches` alimentam a folha e NENHUM oráculo conferia as pontas.
Os 9 oráculos do DP olhavam cada lado separado; a passagem de um para o outro era cega.

O QUE ISSO ESCONDIA, medido em julho/2026 na primeira vez que cruzei:
    55 pessoas bateram ponto · 51 no espelho de dias · 51 na folha
Quatro trabalharam e não têm holerite daquela competência. Três delas foram desligadas em
22/07 — bateram ponto até dias antes e a folha de julho não as inclui. Trabalho registrado
sem contrapartida na folha é passivo trabalhista, e o silêncio era total.

TRÊS BALDES, e só um reprova:

  COM FOLHA   bateu e tem holerite. Nada a fazer.
  RESCISÃO    bateu, não tem holerite, e foi desligado naquele mês. NÃO reprova: as verbas
              podem estar na rescisão em vez do holerite mensal, e afirmar "não foi pago"
              sem olhar o TRCT seria conclusão fabricada. Conta e aparece.
  SEM PAGAMENTO  bateu, não tem holerite, não foi desligado. **Reprova.**

Exclusões declaradas, e cada uma tem motivo — não são conveniência:
  · matrículas de homologação/teste (`COLABORADOR TESTE`, `HOMOLOGACAO`): a própria tela de
    ponto do DP já as exclui; são batidas de bancada, não de gente;
  · o mês corrente: a folha dele ainda não fechou, então "sem holerite" é o estado normal e
    reprovar por isso faria o oráculo tocar todo dia útil do mês — alarme que toca sempre é
    alarme que ninguém lê.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/orq/test_oraculo_ponto_folha.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: Quantas competências fechadas olhar para trás. Fixo e pequeno de propósito: o valor de
#: pegar isto está nos meses recentes, e varrer o ano inteiro traria dívida histórica que
#: ninguém vai reabrir para dentro de um alarme diário.
MESES = 3

SQL = text("""
WITH mes AS (
  SELECT (date_trunc('month', current_date) - (n || ' month')::interval)::date AS ini
  FROM generate_series(1, :meses) AS n
),
bateu AS (
  -- ENTRADA, e só entrada. A escala 12x36 entra 18:00 e sai 06:00 do dia seguinte: contar
  -- saídas faz o turno que COMEÇOU em 30/06 marcar presença em julho. Foi assim que a
  -- CINTIA (afastada, uma única linha `saida` em 01/07 às 10:00 fechando o turno de junho)
  -- apareceu como "trabalhou em julho e não recebeu" na primeira versão deste oráculo.
  SELECT DISTINCT m.ini, p.employee_id
  FROM mes m JOIN gp_clock_punches p
    ON date_trunc('month', p.punch_timestamp)::date = m.ini
  WHERE lower(coalesce(p.punch_type,'')) LIKE 'entrada%'
)
SELECT b.ini AS competencia, e.nome AS nome, e.status AS status,
       count(*) OVER (PARTITION BY b.ini) AS na_competencia,
       EXISTS (SELECT 1 FROM hr_payslips h
               WHERE h.employee_id = b.employee_id
                 AND h.reference_year = EXTRACT(YEAR FROM b.ini)::int
                 AND h.reference_month = EXTRACT(MONTH FROM b.ini)::int) AS tem_folha,
       EXISTS (SELECT 1 FROM termination_processes t
               WHERE t.employee_id = b.employee_id
                 AND date_trunc('month', coalesce(t.last_working_day,
                       (t.notice_start_date
                        + (coalesce(t.notice_period_days,0) || ' days')::interval)::date
                     ))::date = b.ini) AS desligado_no_mes,
       -- afastado (INSS, acidente) não entra na folha mensal comum, e a batida dele já
       -- tem vigia próprio: a regra `dp_ponto_de_afastado`. Cobrar holerite aqui seria
       -- acusar duas vezes o mesmo fato, uma delas errada.
       EXISTS (SELECT 1 FROM sst_afastamentos a
               WHERE CAST(a.employee_id AS TEXT) = CAST(b.employee_id AS TEXT)
                 AND a.data_inicio <= (b.ini + interval '1 month' - interval '1 day')::date
                 AND (a.data_retorno IS NULL OR a.data_retorno >= b.ini)) AS afastado,
       coalesce(e.data_demissao, e.data_desligamento) AS dt_demissao
FROM bateu b JOIN employees e ON e.id = b.employee_id
-- batidas de bancada, não de gente: a própria tela de ponto do DP já as exclui
WHERE upper(coalesce(e.nome,'')) NOT LIKE '%HOMOLOGA%'
  AND upper(coalesce(e.nome,'')) NOT LIKE '%TESTE%'
ORDER BY b.ini DESC, e.nome
""")


async def main() -> int:
    com_folha: list[str] = []
    rescisao: list[str] = []
    afastados: list[str] = []
    sem_pagamento: list[str] = []

    async with async_session_factory() as db:
        linhas = (await db.execute(SQL, {"meses": MESES})).mappings().all()
        for r in linhas:
            rotulo = f"{r['competencia'].strftime('%m/%Y')}  {r['nome']} ({r['status']})"
            if r["tem_folha"]:
                com_folha.append(rotulo)
            elif r["afastado"]:
                afastados.append(rotulo)
            elif r["desligado_no_mes"] or (
                r["dt_demissao"] and r["dt_demissao"].month == r["competencia"].month
                and r["dt_demissao"].year == r["competencia"].year
            ):
                rescisao.append(rotulo)
            else:
                sem_pagamento.append(rotulo)

    print(f"últimas {MESES} competências fechadas · {len(linhas)} pessoa(s)-competência "
          f"com batida de ponto")
    print(f"  COM FOLHA      {len(com_folha)}")
    print(f"  AFASTADO       {len(afastados)}  (vigiado por `dp_ponto_de_afastado`)")
    for x in afastados:
        print(f"      {x}")
    print(f"  RESCISÃO       {len(rescisao)}  (bateu, sem holerite, desligado no mês)")
    for x in rescisao:
        print(f"      {x}")
    print(f"  SEM PAGAMENTO  {len(sem_pagamento)}  (bateu, sem holerite, sem desligamento)")
    for x in sem_pagamento:
        print(f"    ✗ {x}")

    if sem_pagamento:
        # Se TODO mundo com ponto numa competência está sem holerite, a folha daquele mês
        # não foi gerada no sistema — é uma decisão/ação pendente do DP, não 49 defeitos
        # (06/09/2026: 0 holerites de 08/2026 para 49 pessoas com ponto).
        import collections, re as _re
        por_comp = collections.Counter(_re.match(r"(\d{2}/\d{4})", x).group(1) for x in sem_pagamento if _re.match(r"(\d{2}/\d{4})", x))
        com_comp = collections.Counter(_re.match(r"(\d{2}/\d{4})", x).group(1) for x in com_folha if _re.match(r"(\d{2}/\d{4})", x))
        for comp, n in por_comp.items():
            if com_comp.get(comp, 0) == 0:
                print(f"FOLHA AUSENTE: {comp} não tem NENHUM holerite no sistema — {n} pessoa(s) com ponto. "
                      f"Gerar a folha (calcular_folha_todos) é ação do DP, não conserto de código.")
        print(f"FALHA: {len(sem_pagamento)} pessoa(s) bateram ponto numa competência "
              f"fechada e não têm holerite dela, sem desligamento que explique — trabalho "
              f"registrado sem contrapartida na folha")
        print("TEST oraculo_ponto_folha FAIL")
        return 1
    if rescisao:
        print(f"\nOS {len(rescisao)} DE RESCISÃO NÃO SÃO PROVA DE PAGAMENTO: só dizem que "
              f"há desligamento no mês que explica a ausência do holerite. Se as verbas "
              f"saíram, quem mostra é o TRCT — este oráculo não olha lá.")
    print("TEST oraculo_ponto_folha PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
