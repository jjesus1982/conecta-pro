"""Horas reais do ponto — computa horas trabalhadas/noturnas das batidas.

Fonte: gp_clock_punches (batidas reais entrada/saída). Alimenta a folha com os
valores-hora REAIS do mês (noturno, trabalhadas) em vez de estimativa por escala.
Janela noturna CLT/CCT: 22:00–05:00.
"""

from datetime import datetime, time, timedelta

from sqlalchemy import text


def _minutos_noturnos(inicio: datetime, fim: datetime) -> float:
    """Minutos do intervalo [inicio, fim] dentro da janela noturna 22:00–05:00."""
    total = 0.0
    d = inicio.date() - timedelta(days=1)
    end_date = fim.date()
    while d <= end_date:
        win_start = datetime.combine(d, time(22, 0))
        win_end = datetime.combine(d + timedelta(days=1), time(5, 0))
        ov_start = max(inicio, win_start)
        ov_end = min(fim, win_end)
        if ov_start < ov_end:
            total += (ov_end - ov_start).total_seconds() / 60.0
        d += timedelta(days=1)
    return total


def horas_reais_ponto(db, employee_id: str, mes: int, ano: int) -> dict:
    """Computa horas reais do funcionário no mês a partir das batidas do ponto.

    Retorna dict com horas_trabalhadas, horas_noturnas, dias_com_par, tem_ponto.
    Pareia entrada→saída em ordem cronológica; ignora pares inconsistentes (>24h ou <=0).
    """
    rows = db.execute(
        text(
            "SELECT punch_type, punch_timestamp FROM gp_clock_punches "
            "WHERE CAST(employee_id AS TEXT) = :e "
            "AND EXTRACT(MONTH FROM punch_timestamp) = :m "
            "AND EXTRACT(YEAR FROM punch_timestamp) = :y "
            # desempate determinístico p/ batidas no MESMO timestamp (saída antes de
            # entrada + punch_id) — igual ao espelho, senão o total oscila entre execuções
            "ORDER BY punch_timestamp, CASE WHEN lower(coalesce(punch_type,'')) LIKE 'sa%' THEN 0 ELSE 1 END, punch_id"
        ),
        {"e": str(employee_id), "m": mes, "y": ano},
    ).fetchall()

    total_min = 0.0
    noturno_min = 0.0
    pares = 0
    dias_distintos: set = set()
    entrada: datetime | None = None
    for tipo, ts in rows:
        t = (tipo or "").lower()
        if t == "entrada":
            entrada = ts
        elif t == "saida" and entrada is not None:
            dur = (ts - entrada).total_seconds() / 60.0
            if 0 < dur < 24 * 60:
                total_min += dur
                noturno_min += _minutos_noturnos(entrada, ts)
                pares += 1
                dias_distintos.add(entrada.date())
            entrada = None

    return {
        "horas_trabalhadas": round(total_min / 60.0, 2),
        "horas_noturnas": round(noturno_min / 60.0, 2),
        "dias_com_par": pares,
        "dias_trabalhados": len(dias_distintos),  # dias DISTINTOS (para intrajornada 1h/dia)
        "tem_ponto": len(rows) > 0,
        "total_batidas": len(rows),
    }
