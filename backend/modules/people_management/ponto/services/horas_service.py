"""Horas reais do ponto — computa horas trabalhadas/noturnas das batidas.

Fonte: gp_clock_punches (batidas reais entrada/saída). Alimenta a folha com os
valores-hora REAIS do mês (noturno, trabalhadas) em vez de estimativa por escala.
Janela noturna CLT/CCT: 22:00–05:00.
"""

from datetime import date, datetime, time, timedelta

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

# ───────────────────── a que DIA um par de batidas pertence (DGX V1, 24/09/2026) ─────────────────
# Um plantão é UM dia trabalhado, ainda que as batidas cruzem a meia-noite e haja intervalo.
# O 12x36 noturno bate 19:00 → 02:00 · 03:00 → 07:00: dois pares, dois dias civis, UM plantão.
# Atribuir cada par ao dia da própria entrada contava o segmento pós-intervalo como um segundo
# dia trabalhado — ADAILSON SERRA ALVES apareceu com 31 dias em 08/2026 para 15 plantões.
# A régua: o dia do turno é a data de INÍCIO (`shifts.shift_date`); tudo entre início−tolerância
# e fim+tolerância é dele.

#: Folga nas duas pontas da janela do turno: quem entra 19:01 num turno de 19:00 e quem sai
#: 07:12 de um que termina 07:00 continua no mesmo plantão.
TOLERANCIA_TURNO_H = 1.0

#: Quando NENHUM turno cobre a batida (escala não lançada, ou lançada no dia errado — medido:
#: RILEM FERREIRA tem a escala nos ímpares e bate nos pares), o par que começa até este tanto
#: depois do anterior terminar, já do outro lado da meia-noite, é o mesmo plantão. O intervalo
#: real do 12x36 é 1h; a interjornada mínima da CLT é 11h, então 3h não alcança a jornada
#: seguinte. ponytail: heurística de continuidade; some sozinha quando a escala estiver certa.
INTERVALO_MAX_H = 3.0

SQL_TURNOS_JANELA = text(
    "SELECT shift_date, planned_start_time, planned_end_time FROM shifts "
    "WHERE CAST(employee_id AS TEXT) = :e AND shift_date BETWEEN :ini AND :fim "
    "AND lower(coalesce(status,'')) <> 'cancelled' AND NOT coalesce(is_off_day,false) "
    "ORDER BY shift_date, planned_start_time"
)


def janelas_de_turno(rows) -> list[tuple[datetime, datetime, date]]:
    """(início−tolerância, fim+tolerância, shift_date) de cada turno de `SQL_TURNOS_JANELA`.

    Turno noturno é o que termina antes de começar (`planned_start_time > planned_end_time`,
    o mesmo que `shifts.is_night_shift` marca): a janela vai até o dia seguinte.
    """
    tol = timedelta(hours=TOLERANCIA_TURNO_H)
    out = []
    for dia, ini, fim in rows:
        d0 = datetime.combine(dia, ini)
        d1 = datetime.combine(dia + timedelta(days=1) if fim < ini else dia, fim)
        out.append((d0 - tol, d1 + tol, dia))
    return out


def dia_do_plantao(entrada: datetime, janelas: list, ultimo: tuple | None = None) -> date:
    """A data do plantão a que uma batida pertence — a régua única do "um plantão, um dia".

    `janelas` de `janelas_de_turno`; `ultimo` = (saída do par anterior, dia atribuído a ele).
    Sem turno que a cubra e sem continuidade, vale o dia civil da própria batida — que é o que
    o pareamento fazia sempre, e por isso o diurno não muda.
    """
    # `janelas` vem ordenada por início: se duas se sobrepõem (noturno de D terminando 07:00 e
    # diurno de D+1 começando 07:00), vale a que começou POR ÚLTIMO — é o turno em curso.
    achado = None
    for j0, j1, dia in janelas:
        if j0 <= entrada <= j1:
            achado = dia
    if achado is not None:
        return achado
    if ultimo is not None:
        saida_ant, dia_ant = ultimo
        gap = (entrada - saida_ant).total_seconds()
        if dia_ant != entrada.date() and 0 <= gap <= INTERVALO_MAX_H * 3600:
            return dia_ant
    return entrada.date()


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


def parear_batidas(rows, ini_mes: datetime, fim_mes: datetime, janelas: list | None = None) -> dict:
    """Pareia batidas em ordem CRONOLÓGICA e devolve as horas do mês.

    Ignora o `punch_type`: as batidas do noturno vêm tipadas erradas com frequência (turno
    que entra 21:01 e sai 09:01 grava as duas como 'entrada'), e confiar no tipo fazia a
    entrada ser sobrescrita — o turno inteiro sumia e levava junto o adicional noturno.
    O tipo segue só como desempate de timestamp igual, na ordenação.

    Batida sem par não desincroniza o resto do mês: quando a duração não é um turno
    plausível, a batida é tratada como órfã e avança UMA posição (a alternância pura
    avança duas e desalinha tudo que vem depois).

    O par conta no mês da ENTRADA — senão o turno da virada seria contado duas vezes.

    `janelas` (de `janelas_de_turno`) é a régua do "um plantão é UM dia" (DGX V1/W1): o 12x36
    noturno bate 19:00 → 02:00 · 03:00 → 07:00 e o segmento pós-intervalo contava como um
    SEGUNDO dia trabalhado — ADAILSON aparecia com 31 dias em 08/2026 para 15 plantões. Só
    `dias_trabalhados` muda: horas, noturno e `dias_com_par` seguem pelo par, como sempre.
    """
    total_min = 0.0
    noturno_min = 0.0
    pares = 0
    orfas = 0
    dias_distintos: set = set()
    no_mes = 0
    i = 0
    ultimo: tuple | None = None  # (saída, dia do plantão) do par anterior — continuidade
    while i < len(rows) - 1:
        entrada, saida = rows[i][1], rows[i + 1][1]
        dur = (saida - entrada).total_seconds() / 60.0
        if not (0 < dur <= MAX_TURNO_H * 60):
            orfas += 1
            i += 1
            continue
        i += 2
        # o dia do plantão é calculado ANTES do filtro de mês: o par da virada (31/07 19:00)
        # é a continuidade do segmento de 01/08 03:00, e sem ele o mês novo ganhava um dia.
        dia = dia_do_plantao(entrada, janelas or [], ultimo)
        ultimo = (saida, dia)
        if not (ini_mes <= entrada < fim_mes):
            continue  # turno da virada pertence ao mês da entrada, não a este
        total_min += dur
        noturno_min += _minutos_noturnos(entrada, saida)
        pares += 1
        if ini_mes.date() <= dia < fim_mes.date():
            dias_distintos.add(dia)

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


def params_turnos(p: dict) -> dict:
    """Params do SQL_TURNOS_JANELA na mesma janela (mês ± 1 dia) de `params_batidas`."""
    return {"e": p["e"], "ini": p["ini"].date(), "fim": p["fim"].date()}


def horas_reais_ponto(db, employee_id: str, mes: int, ano: int) -> dict:
    """Horas reais do funcionário no mês a partir das batidas (caminho sync)."""
    p = params_batidas(employee_id, mes, ano)
    rows = db.execute(SQL_BATIDAS, {k: v for k, v in p.items() if not k.startswith("_")}).fetchall()
    turnos = db.execute(SQL_TURNOS_JANELA, params_turnos(p)).fetchall()
    return parear_batidas(rows, p["_ini_mes"], p["_fim_mes"], janelas_de_turno(turnos))


def _self_check():
    """Os 3 casos que motivaram o pareamento cronológico. Roda: python3 horas_service.py"""

    class _FakeDB:
        def __init__(self, punches, turnos=()):
            self._p = punches
            self._t = list(turnos)

        def execute(self, sql, params):
            if sql is SQL_TURNOS_JANELA:
                return type("R", (), {"fetchall": lambda _s: self._t})()
            ini, fim = params["ini"], params["fim"]
            # mesma ordenação do SQL_BATIDAS: timestamp, saída antes de entrada no empate
            rows = sorted(
                ((t, ts) for t, ts in self._p if ini <= ts < fim),
                key=lambda r: (r[1], 0 if r[0].lower().startswith("sa") else 1),
            )
            return type("R", (), {"fetchall": lambda _s: rows})()

    d = datetime

    # 1) turno noturno com AMBAS as batidas tipadas 'entrada' (caso RENE, 05→06/07)
    r = horas_reais_ponto(_FakeDB([("entrada", d(2026, 7, 5, 21, 1)), ("entrada", d(2026, 7, 6, 9, 1))]), "x", 7, 2026)
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

    # 4) DGX V1 — 12x36 noturno 19:00–07:00 com intervalo: o segmento pós-meia-noite é do
    #    plantão da véspera, pela janela do turno e, sem turno lançado, pela continuidade.
    jan = janelas_de_turno([(date(2026, 8, 2), time(19, 0), time(7, 0))])
    assert dia_do_plantao(d(2026, 8, 2, 19, 0), jan) == date(2026, 8, 2), jan
    assert dia_do_plantao(d(2026, 8, 3, 3, 0), jan) == date(2026, 8, 2), "pós-intervalo virou outro dia"
    assert dia_do_plantao(d(2026, 8, 3, 3, 0), [], (d(2026, 8, 3, 2, 0), date(2026, 8, 2))) == date(2026, 8, 2)
    assert dia_do_plantao(d(2026, 8, 3, 19, 0), [], (d(2026, 8, 3, 7, 0), date(2026, 8, 2))) == date(2026, 8, 3), (
        "12h de intervalo não é o mesmo plantão"
    )
    # diurno com almoço: os dois pares já eram do mesmo dia e continuam sendo
    jan_d = janelas_de_turno([(date(2026, 8, 3), time(8, 0), time(17, 0))])
    assert dia_do_plantao(d(2026, 8, 3, 13, 0), jan_d) == date(2026, 8, 3), jan_d

    # 5) DGX W1 — o gêmeo: `dias_trabalhados` de um 12x36 noturno com intervalo. Três
    #    plantões 19:00→02:00 · 03:00→07:00 são TRÊS dias, não seis. As horas não mudam.
    _p5 = []
    for _d0 in (2, 4, 6):
        _p5 += [
            ("entrada", d(2026, 8, _d0, 19, 0)),
            ("saida", d(2026, 8, _d0 + 1, 2, 0)),
            ("entrada", d(2026, 8, _d0 + 1, 3, 0)),
            ("saida", d(2026, 8, _d0 + 1, 7, 0)),
        ]
    _t5 = [(date(2026, 8, _d0), time(19, 0), time(7, 0)) for _d0 in (2, 4, 6)]
    r = horas_reais_ponto(_FakeDB(_p5, _t5), "x", 8, 2026)
    assert r["dias_trabalhados"] == 3, f"plantão noturno virou 2 dias: {r}"
    assert r["dias_com_par"] == 6 and r["horas_trabalhadas"] == 33.0, f"as horas mudaram: {r}"
    # sem escala lançada (a classe RILEM: escala na paridade errada) a continuidade segura
    assert horas_reais_ponto(_FakeDB(_p5), "x", 8, 2026)["dias_trabalhados"] == 3, "sem escala, o gêmeo voltou"
    # diurno partido pelo almoço: já era 1 dia e continua 1
    _p5d = [
        ("entrada", d(2026, 8, 3, 8, 0)),
        ("saida", d(2026, 8, 3, 12, 0)),
        ("entrada", d(2026, 8, 3, 13, 0)),
        ("saida", d(2026, 8, 3, 17, 0)),
    ]
    assert horas_reais_ponto(_FakeDB(_p5d), "x", 8, 2026)["dias_trabalhados"] == 1

    print("horas_service: 5/5 OK")


if __name__ == "__main__":
    _self_check()
