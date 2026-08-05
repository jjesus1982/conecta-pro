"""Oraculo do fix de _pair_punches (telas de ponto do RH). READ-ONLY.

Conta quantos turnos o pareamento fecha (clock_in E clock_out). Antes do fix, o
plantao noturno virava dois registros quebrados porque o agrupamento por DIA
acontecia antes do pareamento.

Rodar no host (venv de dev):
    cd /opt/conecta-pro/backend && venv/bin/python scripts/diag_pair_punches_telas.py --mes 7 --ano 2026
"""

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from modules.people_management.hr.services.time_record_service import (  # noqa: E402
    TimeRecordService,
)

MES = int(sys.argv[sys.argv.index("--mes") + 1]) if "--mes" in sys.argv else 7
ANO = int(sys.argv[sys.argv.index("--ano") + 1]) if "--ano" in sys.argv else 2026

DB = os.environ.get("DATABASE_URL") or (
    "postgresql://postgres:"
    + os.environ.get("POSTGRES_PASSWORD", "")
    + "@127.0.0.1:5432/conecta_pro"
)


def main():
    eng = create_engine(DB.replace("+asyncpg", ""))
    d1 = date(ANO, MES, 1)
    d2 = date(ANO + (MES == 12), (MES % 12) + 1, 1)
    with eng.connect() as conn:
        rows = (
            conn.execute(
                text("""
                    SELECT id, punch_id, employee_id, punch_type, punch_timestamp,
                           status, latitude, longitude, device_type, created_at
                    FROM gp_clock_punches
                    WHERE punch_timestamp >= :d1 AND punch_timestamp < :d2
                    ORDER BY employee_id, punch_timestamp
                """),
                {"d1": d1, "d2": d2},
            )
            .mappings()
            .all()
        )

    recs = TimeRecordService(None)._pair_punches(rows)
    fechados = sum(1 for r in recs if r["clock_in"] and r["clock_out"])
    virada = sum(
        1
        for r in recs
        if r["clock_in"] and r["clock_out"] and r["clock_out"] < r["clock_in"]
    )
    print(f"mes {MES:02d}/{ANO}")
    print(f"  batidas no periodo .............. {len(rows)}")
    print(f"  turnos pareados ................. {len(recs)}")
    print(f"  turnos FECHADOS (entrada+saida) . {fechados}")
    print(f"  turnos que CRUZAM a meia-noite .. {virada}")
    print(f"  batidas orfas (sem par) ......... {len(rows) - 2 * len(recs)}")


if __name__ == "__main__":
    main()
