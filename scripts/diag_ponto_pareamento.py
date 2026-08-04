"""Diagnóstico: pareamento de batidas por PUNCH_TYPE (atual) × por ALTERNÂNCIA (proposto).

Oráculo do fix da Task 3+4 (paridade folha × Portte). READ-ONLY.
Roda no container:  docker exec conecta-pro-backend python3 /app/../scripts/diag_ponto_pareamento.py

Por que existe: `horas_reais_ponto` pareia confiando no `punch_type`, mas as batidas do
noturno vêm quase todas tipadas 'entrada' → nunca forma par → 0 horas → 0 noturno.
Este script mede o tamanho do buraco antes e depois.
"""

import os
import sys
from datetime import datetime, time, timedelta

from sqlalchemy import create_engine, text

MES = int(sys.argv[sys.argv.index("--mes") + 1]) if "--mes" in sys.argv else 7
ANO = int(sys.argv[sys.argv.index("--ano") + 1]) if "--ano" in sys.argv else 2026

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))


def _minutos_noturnos(inicio, fim):
    total = 0.0
    d = inicio.date() - timedelta(days=1)
    while d <= fim.date():
        ov_s = max(inicio, datetime.combine(d, time(22, 0)))
        ov_e = min(fim, datetime.combine(d + timedelta(days=1), time(5, 0)))
        if ov_s < ov_e:
            total += (ov_e - ov_s).total_seconds() / 60.0
        d += timedelta(days=1)
    return total


def por_punch_type(rows):
    """Algoritmo ATUAL de horas_reais_ponto."""
    tot = not_ = 0.0
    pares = 0
    entrada = None
    for tipo, ts in rows:
        t = (tipo or "").lower()
        if t == "entrada":
            entrada = ts
        elif t == "saida" and entrada is not None:
            dur = (ts - entrada).total_seconds() / 60.0
            if 0 < dur < 24 * 60:
                tot += dur
                not_ += _minutos_noturnos(entrada, ts)
                pares += 1
            entrada = None
    return tot / 60.0, not_ / 60.0, pares


def por_alternancia(rows):
    """Proposto: 1ª→2ª, 3ª→4ª batida, ignorando o punch_type."""
    tot = not_ = 0.0
    pares = 0
    for i in range(0, len(rows) - 1, 2):
        ini, fim = rows[i][1], rows[i + 1][1]
        dur = (fim - ini).total_seconds() / 60.0
        if 0 < dur < 24 * 60:
            tot += dur
            not_ += _minutos_noturnos(ini, fim)
            pares += 1
    return tot / 60.0, not_ / 60.0, pares


def por_guloso(rows, max_h=16.0):
    """Proposto v2: cronológico + janela de plausibilidade, re-sincroniza em batida ímpar.

    Pareia batida[i] com batida[i+1] se a duração for um turno plausível; senão trata
    batida[i] como órfã e avança 1 (a alternância pura avança 2 e desincroniza o mês).
    """
    tot = not_ = 0.0
    pares = orfas = 0
    i = 0
    while i < len(rows) - 1:
        ini, fim = rows[i][1], rows[i + 1][1]
        dur = (fim - ini).total_seconds() / 60.0
        if 0 < dur <= max_h * 60:
            tot += dur
            not_ += _minutos_noturnos(ini, fim)
            pares += 1
            i += 2
        else:
            orfas += 1
            i += 1
    return tot / 60.0, not_ / 60.0, pares, orfas


with eng.connect() as db:
    emps = db.execute(
        text(
            "SELECT DISTINCT CAST(employee_id AS TEXT) FROM gp_clock_punches "
            "WHERE EXTRACT(MONTH FROM punch_timestamp)=:m AND EXTRACT(YEAR FROM punch_timestamp)=:y"
        ),
        {"m": MES, "y": ANO},
    ).scalars().all()

    print(f"=== Ponto {MES:02d}/{ANO} — {len(emps)} funcionários com batidas ===\n")

    tipos = db.execute(
        text(
            "SELECT lower(coalesce(punch_type,'(null)')), count(*) FROM gp_clock_punches "
            "WHERE EXTRACT(MONTH FROM punch_timestamp)=:m AND EXTRACT(YEAR FROM punch_timestamp)=:y "
            "GROUP BY 1 ORDER BY 2 DESC"
        ),
        {"m": MES, "y": ANO},
    ).all()
    print("Distribuição de punch_type:")
    for t, c in tipos:
        print(f"  {t:<12} {c:>6}")
    print()

    tot_a = tot_b = tot_c = not_a = not_b = not_c = 0.0
    par_a = par_b = par_c = orf_c = 0
    zerados = []
    for e in emps:
        rows = db.execute(
            text(
                "SELECT punch_type, punch_timestamp FROM gp_clock_punches "
                "WHERE CAST(employee_id AS TEXT)=:e "
                "AND EXTRACT(MONTH FROM punch_timestamp)=:m AND EXTRACT(YEAR FROM punch_timestamp)=:y "
                "ORDER BY punch_timestamp, CASE WHEN lower(coalesce(punch_type,'')) LIKE 'sa%' THEN 0 ELSE 1 END, punch_id"
            ),
            {"e": e, "m": MES, "y": ANO},
        ).all()
        ha, na, pa = por_punch_type(rows)
        hb, nb, pb = por_alternancia(rows)
        hc, nc, pc, oc = por_guloso(rows)
        tot_a += ha; not_a += na; par_a += pa
        tot_b += hb; not_b += nb; par_b += pb
        tot_c += hc; not_c += nc; par_c += pc; orf_c += oc
        if na == 0 and nc > 0:
            zerados.append((e, len(rows), pc, round(nc, 1)))

    print(f"{'':<22}{'ATUAL(punch_type)':>19}{'ALTERNÂNCIA':>14}{'GULOSO+janela':>16}")
    print(f"{'pares formados':<22}{par_a:>19}{par_b:>14}{par_c:>16}")
    print(f"{'horas trabalhadas':<22}{tot_a:>19.1f}{tot_b:>14.1f}{tot_c:>16.1f}")
    print(f"{'horas noturnas':<22}{not_a:>19.1f}{not_b:>14.1f}{not_c:>16.1f}")
    print(f"{'batidas órfãs':<22}{'-':>19}{'-':>14}{orf_c:>16}")
    print()
    print(f"Funcionários com ZERO noturno hoje que passam a ter: {len(zerados)}")
    for e, n, pc, nc in zerados[:15]:
        print(f"  {e[:8]}  batidas={n:<4} pares={pc:<4} noturno={nc}h")
