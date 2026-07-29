"""C1 base — fatia dos DIAS NORMAIS pelo espelho Portte. Deriva dias_trabalhados por
(emp,competência) = 30 × (base_Portte / nominal), onde base_Portte = Σ DIAS/HORAS
NORMAIS + SALDO DE SALARIO (a porção trabalhada) e nominal = max(salario_base, piso).
Captura admissão E férias uniformemente (a Portte já reduz a base pelos dois). O motor
lê folha_dias_espelho e, havendo linha, usa dias_trab/30 como fator da base (substitui
o fator_prop no espelho). Idempotente."""
import os
import re
from collections import defaultdict
from sqlalchemy import create_engine, text

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
ANO = 2026
PISO = 1670.0
FONTE = "backfill_portte_base_2026-07-28"
BASE_KW = ["DIAS NORMAIS", "HORAS NORMAIS", "SALDO DE SALARIO", "SALDO SALARIO"]


def norm(d):
    return re.sub(r"\s+", " ", (d or "").strip().upper())


def f(x):
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        return 0.0


rows = {}
with eng.connect() as c:
    for m in range(1, 7):
        for eid, ear in c.execute(text(
            "SELECT employee_id::text, earnings FROM hr_payslips "
            "WHERE reference_year=:a AND reference_month=:m AND source_system='portte'"),
            {"a": ANO, "m": m}).fetchall():
            base = sum(f(it.get("valor") if it.get("valor") is not None else it.get("value"))
                       for it in (ear or [])
                       if any(k in norm(it.get("descricao") or it.get("description")) for k in BASE_KW))
            if base <= 0:
                continue
            nominal = c.execute(text("SELECT salario_base FROM employees WHERE CAST(id AS TEXT)=:e"), {"e": eid}).scalar()
            nominal = max(f(nominal), PISO)
            dias = round(30.0 * base / nominal, 2)
            dias = min(dias, 31.0)  # guarda contra ruído
            rows[(eid, m)] = dias

parciais = sum(1 for d in rows.values() if d < 29.5)
print(f"linhas dias: {len(rows)} | com fatia (<29.5 dias = admissão/férias): {parciais}")
import statistics as st
menores = sorted(rows.items(), key=lambda x: x[1])[:6]
print("menores dias_trab (mais fatiados):", [(k[1], round(v, 1)) for k, v in menores])

with eng.begin() as c:
    c.execute(text("""
        CREATE TABLE IF NOT EXISTS folha_dias_espelho (
            employee_id uuid NOT NULL, ano int NOT NULL, mes int NOT NULL,
            dias_trabalhados numeric, fonte text,
            PRIMARY KEY (employee_id, ano, mes))"""))
    c.execute(text("DELETE FROM folha_dias_espelho WHERE ano=:a AND fonte=:f"), {"a": ANO, "f": FONTE})
    for (eid, m), dias in rows.items():
        c.execute(text("""
            INSERT INTO folha_dias_espelho (employee_id, ano, mes, dias_trabalhados, fonte)
            VALUES (CAST(:e AS uuid), :a, :m, :d, :f)"""),
            {"e": eid, "a": ANO, "m": m, "d": dias, "f": FONTE})
    print(f"inseridas {len(rows)} linhas em folha_dias_espelho.")
