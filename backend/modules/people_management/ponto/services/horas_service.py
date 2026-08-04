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


# Teto de duração de um turno. Calibrado pela distribuição REAL das batidas (julho/2026):
# duas modas — 4-5h (diurno partido pelo almoço) e 11-13h (12x36) — e nada legítimo acima
# de 13h. Acima disso são emendas causadas por batida faltando, que inflam o noturno.
# ponytail: constante; se entrar escala > 13h (dobra autorizada), virar parâmetro por escala.
MAX_TURNO_H = 13.0

# Uma query só, usada pelo caminho sync (folha/dashboard) e pelo async (fechamento de mês) —
# antes cada um tinha a sua cópia, e a correção de pareamento teria que ser feita duas vezes.
SQL_BATIDAS = text(
    "SELECT punch_type, (punch_timestamp) AS punch_timestamp FROM gp_clock_punches "
    "WHERE CAST(employee_id AS TEXT) = :e "
    "AND punch_timestamp >= :ini AND punch_timestamp < :fim "
    # desempate determinístico p/ batidas no MESMO timestamp (saída antes de
    # entrada + punch_id) — igual ao espelho, senão o total oscila entre execuções
    "ORDER BY punch_timestamp, CASE WHEN lower(coalesce(punch_type,'')) LIKE 'sa%' THEN 0 ELSE 1 END, punch_id"
)


def params_batidas(employee_id: str, mes: int, ano: int) -> dict:
    """Params do SQL_BATIDAS: o mês com margem de 1 dia nas duas pontas.

    A margem existe pelo turno da virada — quem entra 31/07 22:00 e sai 01/08 07:00 tem a
    saída FORA do mês. Sem ela a entrada ficava órfã e o mês perdia o turno inteiro.
    """
    ini_mes = datetime(ano, mes, 1)
    fim_mes = datetime(ano + (mes == 12), (mes % 12) + 1, 1)
    return {
        "e": str(employee_id),
        "ini": ini_mes - timedelta(days=1),
        "fim": fim_mes + timedelta(days=1),
        "_ini_mes": ini_mes,
        "_fim_mes": fim_mes,
    }


def parear_batidas(rows, ini_mes: datetime, fim_mes: datetime) -> dict:
    """Pareia batidas em ordem CRONOLÓGICA e devolve as horas do mês.

    Ignora o `punch_type`: as batidas do noturno vêm tipadas erradas com frequência (turno
    que entra 21:01 e sai 09:01 grava as duas como 'entrada'), e confiar no tipo fazia a
    entrada ser sobrescrita — o turno inteiro sumia e levava junto o adicional noturno.
    O tipo segue só como desempate de timestamp igual, na ordenação.

    Batida sem par não desincroniza o resto do mês: quando a duração não é um turno
    plausível, a batida é tratada como órfã e avança UMA posição (a alternância pura
    avança duas e desalinha tudo que vem depois).

    O par conta no mês da ENTRADA — senão o turno da virada seria contado duas vezes.
    """
    total_min = 0.0
    noturno_min = 0.0
    pares = 0
    orfas = 0
    dias_distintos: set = set()
    no_mes = 0
    i = 0
    while i < len(rows) - 1:
        entrada, saida = rows[i][1], rows[i + 1][1]
        dur = (saida - entrada).total_seconds() / 60.0
        if not (0 < dur <= MAX_TURNO_H * 60):
            orfas += 1
            i += 1
            continue
        i += 2
        if not (ini_mes <= entrada < fim_mes):
            continue  # turno da virada pertence ao mês da entrada, não a este
        total_min += dur
        noturno_min += _minutos_noturnos(entrada, saida)
        pares += 1
        dias_distintos.add(entrada.date())

    no_mes = sum(1 for _, ts in rows if ini_mes <= ts < fim_mes)
    return {
        "horas_trabalhadas": round(total_min / 60.0, 2),
        "horas_noturnas": round(noturno_min / 60.0, 2),
        "dias_com_par": pares,
        "dias_trabalhados": len(dias_distintos),  # dias DISTINTOS (para intrajornada 1h/dia)
        "batidas_orfas": orfas,  # batida sem par: buraco de ponto, não de cálculo
        "tem_ponto": no_mes > 0,
        "total_batidas": no_mes,
    }


def horas_reais_ponto(db, employee_id: str, mes: int, ano: int) -> dict:
    """Horas reais do funcionário no mês a partir das batidas (caminho sync)."""
    p = params_batidas(employee_id, mes, ano)
    rows = db.execute(SQL_BATIDAS, {k: v for k, v in p.items() if not k.startswith("_")}).fetchall()
    return parear_batidas(rows, p["_ini_mes"], p["_fim_mes"])


def _self_check():
    """Os 3 casos que motivaram o pareamento cronológico. Roda: python3 horas_service.py"""

    class _FakeDB:
        def __init__(self, punches):
            self._p = punches

        def execute(self, _sql, params):
            ini, fim = params["ini"], params["fim"]
            rows = sorted((t, ts) for t, ts in self._p if ini <= ts < fim)
            return type("R", (), {"fetchall": lambda _s: rows})()

    d = datetime

    # 1) turno noturno com AMBAS as batidas tipadas 'entrada' (caso RENE, 05→06/07)
    r = horas_reais_ponto(
        _FakeDB([("entrada", d(2026, 7, 5, 21, 1)), ("entrada", d(2026, 7, 6, 9, 1))]), "x", 7, 2026
    )
    assert r["dias_com_par"] == 1, f"tipo errado ainda perde o turno: {r}"
    assert r["horas_trabalhadas"] == 12.0, r
    assert r["horas_noturnas"] == 7.0, r  # 22:00–05:00

    # 2) turno da virada do mês: entra 31/07, sai 01/08 -> conta em JULHO, não em agosto
    p = [("entrada", d(2026, 7, 31, 22, 0)), ("saida", d(2026, 8, 1, 7, 0))]
    assert horas_reais_ponto(_FakeDB(p), "x", 7, 2026)["dias_com_par"] == 1, "virada perdida em julho"
    assert horas_reais_ponto(_FakeDB(p), "x", 8, 2026)["dias_com_par"] == 0, "virada contada 2x em agosto"

    # 3) batida órfã não desincroniza o resto do mês
    r = horas_reais_ponto(
        _FakeDB(
            [
                ("entrada", d(2026, 7, 10, 8, 0)),  # órfã (saída não registrada)
                ("entrada", d(2026, 7, 12, 8, 0)),
                ("saida", d(2026, 7, 12, 17, 0)),
            ]
        ),
        "x",
        7,
        2026,
    )
    assert r["dias_com_par"] == 1 and r["horas_trabalhadas"] == 9.0, f"órfã desalinhou: {r}"
    assert r["batidas_orfas"] == 1, r

    print("horas_service: 3/3 OK")


if __name__ == "__main__":
    _self_check()
