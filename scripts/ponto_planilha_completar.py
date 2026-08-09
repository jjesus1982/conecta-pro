"""Completa a planilha do Jordan: replica o padrão nos que ficaram em branco.

O que ele preencheu fica INTOCADO. O que eu inferi entra numa cor diferente e com a origem
escrita na própria linha — ele confere só as inferências, não a planilha toda.

A regra que saiu dos 33 que ele preencheu:
  • portaria (agente E líder) em condomínio de intrajornada  -> SIM, 2 batidas
  • portaria em condomínio sem intrajornada                  -> NÃO, 4 batidas
  • serviços gerais / artífice / jardineiro (44h)            -> NÃO, 4 batidas, em qualquer lugar

O HORÁRIO não é inferível por regra — varia por posto, a pedido do cliente (palavras dele).
Depois da migração de fuso (09/08) o banco está em horário de Manaus, então o horário sai
MEDIDO das batidas reais, e não de um padrão que eu inventaria.
"""
from __future__ import annotations

import os

import openpyxl
from openpyxl.styles import Font, PatternFill
from sqlalchemy import create_engine, text

ENTRADA = "/tmp/ponto_intrajornada_preenchida.xlsx"
SAIDA = "/tmp/ponto_intrajornada_completa.xlsx"

#: condomínios cuja PORTARIA recebe intrajornada — declarado pelo Jordan e confirmado no dado
#: (Mirante veio preenchido por ele; os outros 3 estavam na declaração original de 07/08 e as
#: batidas medidas mostram ~1 a 2 por dia, contra ~3,5 dos que almoçam).
CONDS_INTRA = {"MIRANTE", "PRIME ARENA", "VILLA DEI FIORI", "VILLA PÁSSAROS"}

SQL_HORARIO = """
WITH jor AS (
  -- jornada e não dia de calendário: o noturno entra 18h e sai 06h do dia seguinte
  SELECT k.employee_id, min(k.punch_timestamp) ent, max(k.punch_timestamp) sai, count(*) n
  FROM gp_clock_punches k JOIN employees e ON e.id = k.employee_id
  WHERE e.nome LIKE :n AND k.punch_timestamp >= '2026-07-01'
  GROUP BY k.employee_id, (k.punch_timestamp - interval '6 hours')::date
)
SELECT mode() WITHIN GROUP (ORDER BY to_char(ent, 'HH24:MI')),
       mode() WITHIN GROUP (ORDER BY to_char(sai, 'HH24:MI')),
       round(avg(n), 1)
FROM jor
"""


def _arredonda(hhmm: str | None) -> str:
    """05:51 e 17:50 são 06:00 e 18:00 com a pessoa batendo alguns minutos antes."""
    if not hhmm:
        return ""
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    if m >= 45:
        h, m = (h + 1) % 24, 0
    elif m <= 15:
        m = 0
    return f"{h:02d}:{m:02d}"


def main() -> None:
    db = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "")).connect()
    wb = openpyxl.load_workbook(ENTRADA)
    ws = wb.active

    verde = PatternFill("solid", fgColor="D1FAE5")      # inferido por mim
    n_inf = 0

    # col 16=intrajornada, 17=batidas, 18=entrada, 19=saída, 20=observação (1-based)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        nome = row[0].value
        if not nome or row[15].value:                    # vazio ou já preenchido pelo Jordan
            continue
        cargo = str(row[1].value or "").upper()
        cond = str(row[2].value or "").upper()
        eh_portaria = "PORTARIA" in cargo
        intra = eh_portaria and any(c in cond for c in CONDS_INTRA)

        r = db.execute(text(SQL_HORARIO), {"n": str(nome)[:20] + "%"}).first()
        ent, sai = (_arredonda(r[0]), _arredonda(r[1])) if r else ("", "")

        row[15].value = "sim" if intra else "Não"
        row[16].value = 2 if intra else 4
        row[17].value = ent
        row[18].value = sai
        row[19].value = (f"INFERIDO — regra dos {'com' if intra else 'sem'} intrajornada; "
                         f"horário medido das batidas ({r[2] if r else '?'} batidas/dia)")
        for c in row:
            c.fill = verde
        n_inf += 1

    ws.cell(row=ws.max_row + 2, column=1,
            value=f"VERDE = {n_inf} linhas inferidas por mim (regra + horário medido). "
                  f"O restante é o que você preencheu, intocado.").font = Font(italic=True, bold=True)

    wb.save(SAIDA)
    print(f"  planilha: {SAIDA}")
    print(f"  {n_inf} linhas completadas (verde) · o que você preencheu ficou intocado")


if __name__ == "__main__":
    main()
