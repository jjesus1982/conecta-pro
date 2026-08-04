"""Gate do noturno por escala — o invariante que a Portte cumpre sem exceção.

Cada plantão noturno vale 7h de relógio na janela 22:00–05:00, que a redução da hora
noturna (52'30") transforma em 8h LEGAIS. O adicional é 20% sobre essas 8h. Foi essa
integralidade (múltiplos exatos de 8 em 17 pessoas × 6 meses da folha da Portte) que
provou o método — se ela quebrar, o pareamento com a Portte quebra junto.

Rodar após qualquer mexida em calculo_service/plantoes_noturnos:
  docker exec -w /app -e PYTHONPATH=/app conecta-pro-backend python3 /tmp/test_not.py
"""

import os
import sys
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "/app")
from modules.people_management.folha.services.calculo_service import (  # noqa: E402
    DIVISOR_ESCALA,
    calcular_folha_colaborador,
    plantoes_noturnos,
)

MES = int(sys.argv[sys.argv.index("--mes") + 1]) if "--mes" in sys.argv else 7
ANO = int(sys.argv[sys.argv.index("--ano") + 1]) if "--ano" in sys.argv else 2026

db = sessionmaker(bind=create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "")))()
emps = db.execute(
    text(
        "SELECT DISTINCT cast(employee_id as text) FROM hr_payslips "
        "WHERE reference_year=:a AND reference_month=:m AND source_system='conecta'"
    ),
    {"a": ANO, "m": MES},
).scalars().all()

falhas, checados, sem_escala = [], 0, 0
for eid in emps:
    pl = plantoes_noturnos(db, eid, MES, ANO)
    if not pl:
        sem_escala += 1
        continue
    r = calcular_folha_colaborador(db, eid, MES, ANO)
    nome, sal_cheio = db.execute(
        text("SELECT nome, salario_base FROM employees WHERE cast(id as text)=:e"), {"e": eid}
    ).first()
    got = next((p for p in r["proventos"] if p["codigo"] == "0020"), None)
    if not got:
        falhas.append(f"{nome}: {pl} plantões mas SEM rubrica 0020")
        continue
    # salário CHEIO, não o rateado do retorno: a hora-normal sai do piso mesmo em mês parcial
    div = DIVISOR_ESCALA.get(r.get("escala"), 220)
    esperado = Decimal(pl) * 8 * (Decimal(str(sal_cheio)) / div) * Decimal("0.20")
    if abs(Decimal(str(got["valor"])) - esperado) > Decimal("0.10"):  # tolerância = arredondamento
        falhas.append(f"{nome}: 0020={got['valor']:.2f} != 8h×{pl}×20% = {esperado:.2f}")
    checados += 1

print(f"noturno por escala: {checados} pessoas checadas, {sem_escala} sem plantão noturno")
if falhas:
    print(f"FALHOU ({len(falhas)}):")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("OK — todo adicional noturno = 8h legais × plantões × 20%")
