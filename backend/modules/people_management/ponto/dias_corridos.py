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


def meses_tocados(ini: date, fim: date) -> list[tuple[int, int]]:
    """(mes, ano) de TODA competência que o período atravessa, de `ini` a `fim`."""
    out, y, m = [], ini.year, ini.month
    while (y, m) <= (fim.year, fim.month):
        out.append((m, y))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def espelho_do_periodo(db, employee_id: str, ini: date, fim: date) -> dict | None:
    """Espelho com a tabela de dias do PERÍODO LIVRE `ini..fim`. None = sem espelho calculado.

    28/09/2026 — existe porque o merge «junta o espelho de TODO mês que a janela toca antes de
    cair no fallback cru» estava inline em `espelho_ponto_controller.baixar_espelho_pdf` e ia
    virar 2ª cópia no `cartao_lote` (a 3ª no repo, contando o kit do GEDEON). Choke point único:
    quem quiser período livre chama aqui e ganha o merge certo de graça.

    ⚠️ O QUE ESTA FUNÇÃO NÃO FAZ — e é o defeito que ela evita: **não recalcula total nenhum.**
    Os totais de `ler_espelho` são SEMPRE do mês civil (`time_sheets` filtrado por
    reference_month/year, espelho_ponto_service.py:41). Período 26/07→25/08 = 31 dias, 6 deles de
    julho, e as somas seguem sendo as de 08/2026. Somar minuto por conta própria aqui seria a
    QUARTA régua de apuração desta casa (as três que existem já discordam em 59 pessoa-dia), e
    mudar matemática de folha. A saída escolhida é **rotular**: `periodo_kit` faz
    `espelho_ponto_pdf.py:315` imprimir "TOTAIS DE MM/AAAA (MÊS CIVIL)" em vez de "TOTAIS DO
    PERÍODO" — o número é fato apurado pelo motor, só faltava dizer de qual janela ele é.

    A competência dos totais é o mês de `fim` (25/08 → 08/2026), a mesma convenção de
    `janela_26a25`. Sem espelho calculado nesse mês → None, e quem chama recusa a página
    (anti-fabricação): 31 dias de tabela sob totais inexistentes seria pior que página faltando.
    """
    from modules.people_management.hr.services.espelho_ponto_service import ler_espelho

    base = ler_espelho(db, str(employee_id), fim.month, fim.year)
    if not base:
        return None
    apurados: list[dict] = []
    for m, y in meses_tocados(ini, fim):
        e = base if (m, y) == (fim.month, fim.year) else ler_espelho(db, str(employee_id), m, y)
        apurados += (e or {}).get("dias") or []
    esp = dict(base)
    esp["dias"] = dias_corridos(db, employee_id, ini, fim, apurados)
    esp["periodo_kit"] = f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}"
    # 28/09/2026 — os DOIS campos do cabeçalho que dependem da janela e NÃO são total apurado:
    # QUADRO DE HORÁRIOS (escala publicada no intervalo) e ABONO por dia. `ler_espelho` os apurou
    # sobre period_start..period_end do time_sheet, que aqui já não é o período impresso: numa
    # folha 26/07→25/08 o quadro sairia o de 08/2026 e um abono lançado em 28/07 não apareceria em
    # linha nenhuma. Refeitos aqui (o choke point) e não no controller porque `cartao_lote` tem o
    # mesmo defeito pelo mesmo motivo. Não é recálculo de hora: é LEITURA de outra janela.
    from modules.people_management.hr.services.espelho_ponto_service import (
        abono_por_dia,
        quadro_horarios,
    )

    esp["quadro_horarios"] = quadro_horarios(db, str(employee_id), ini, fim)
    abonos = abono_por_dia(db, str(employee_id), ini, fim)
    esp["abono_por_dia"] = abonos
    if abonos:
        esp["dias"] = [
            ({**d, "abono": abonos[str(d.get("date") or d.get("data"))[:10]]}
             if str(d.get("date") or d.get("data"))[:10] in abonos else d)
            for d in esp["dias"]
        ]
    return esp
