"""Dias CORRIDOS de uma janela de ponto 26/x → 25/y — a janela que o DP usa no papel.

CÓPIA deliberada de `modules/gedeon/services/ponto_kit_service.py:35-71` (`_janela_kit` e
`_dias_corridos`). Não é refator: o kit do GEDEON é mantido por outra frente e não pode ser
mexido daqui. Mesma regra, dois donos — se a regra da janela mudar, muda nos dois.

O que este módulo NÃO faz: não apura hora nenhuma, não cria uma quarta régua de pareamento.
  • dia apurado pelo motor  → vem do motor (`time_sheets.daily_summary`, via `ler_espelho`);
  • dia fora da apuração    → batida CRUA do dia (min/max de `gp_clock_punches`);
  • dia sem batida          → "Folga / sem registro".

⚠️ Ceiling do fallback cru: min/max do dia NÃO junta turno noturno (uma escala 19:00→07:00
aparece como duas linhas de batida única, uma em cada data) — é o registro literal, não jornada
apurada. Quem chama deve alimentar `dias_apurados` com o espelho dos DOIS meses que a janela
toca, para o fallback só sobrar onde o motor não rodou.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text


def janela_26a25(mes: int, ano: int) -> tuple[date, date]:
    """Janela da folha de ponto do DP: 26 do mês anterior a 25 da competência."""
    fim = date(ano, mes, 25)
    ini = date(ano - 1, 12, 26) if mes == 1 else date(ano, mes - 1, 26)
    return ini, fim


def dias_corridos(db, employee_id: str, ini: date, fim: date, dias_apurados: list[dict]) -> list[dict]:
    """TODOS os dias do período, não só os trabalhados (a folha de papel tem 26/x a 25/y corridos)."""
    por_data = {str(d.get("date") or d.get("data"))[:10]: d for d in (dias_apurados or []) if isinstance(d, dict)}
    linhas_bd = db.execute(
        text(
            "SELECT punch_timestamp::date AS d, min(punch_timestamp::time) AS ent, max(punch_timestamp::time) AS sai, count(*) AS n "
            "FROM gp_clock_punches WHERE employee_id = CAST(:e AS uuid) AND punch_timestamp::date BETWEEN :i AND :f "
            "GROUP BY 1"
        ),
        {"e": str(employee_id), "i": ini, "f": fim},
    ).fetchall()
    batidas = {str(r[0]): r for r in linhas_bd}
    out: list[dict] = []
    d = ini
    while d <= fim:
        chave = d.isoformat()
        if chave in por_data:
            out.append(por_data[chave])
        elif chave in batidas:
            r = batidas[chave]
            out.append(
                {
                    "date": chave,
                    "entrada": str(r[1])[:5],
                    "saida": str(r[2])[:5],
                    "ocorrencia": "Registro de ponto" if r[3] > 1 else "Batida única",
                }
            )
        else:
            out.append({"date": chave, "entrada": "—", "saida": "—", "ocorrencia": "Folga / sem registro"})
        d += timedelta(days=1)
    return out
