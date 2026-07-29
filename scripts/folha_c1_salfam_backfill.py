"""C1 verba 5 — backfill de filhos <14 (salário-família) do espelho Portte.
Fonte: valor-cheio da verba 'SAL...FAM' / cota 67.54 = nº de filhos. Popula
employees.dependentes (JSONB, hoje vazio) com N objetos menor_14. Idempotente:
sobrescreve só os recebedores identificados, com marcador de fonte."""
import os
import re
import json
from collections import defaultdict
from sqlalchemy import create_engine, text

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
QUOTA = 67.54
FONTE = "backfill_portte_salfam_2026-07-28"


def norm(d):
    return re.sub(r"\s+", " ", (d or "").strip().upper())


maxval = defaultdict(float)
with eng.connect() as c:
    for m in range(1, 7):
        for eid, ear in c.execute(text(
            "SELECT employee_id::text, earnings FROM hr_payslips "
            "WHERE reference_year=2026 AND reference_month=:m AND source_system='portte'"), {"m": m}).fetchall():
            for it in (ear or []):
                du = norm(it.get("descricao") or it.get("description"))
                v = float((it.get("valor") if it.get("valor") is not None else it.get("value")) or 0)
                if "SAL" in du and "FAM" in du and v > 0:
                    maxval[eid] = max(maxval[eid], v)

counts = {eid: max(1, round(v / QUOTA)) for eid, v in maxval.items()}
print(f"recebedores: {len(counts)} | distribuição filhos: "
      f"{dict(sorted(__import__('collections').Counter(counts.values()).items()))}")

with eng.begin() as c:
    # backup do estado atual (deve estar vazio p/ todos)
    bkp = c.execute(text("SELECT id::text, dependentes FROM employees WHERE CAST(id AS TEXT)=ANY(:ids)"),
                    {"ids": list(counts)}).fetchall()
    open("/tmp/employees_dependentes_backup.json", "w").write(
        json.dumps([{"id": r[0], "dependentes": r[1]} for r in bkp], ensure_ascii=False))
    naovazio = [r[0] for r in bkp if r[1] not in (None, [], {})]
    if naovazio:
        print(f"⚠️ {len(naovazio)} já tinham dependentes preenchido — abortando p/ não sobrescrever real")
        raise SystemExit(1)
    for eid, n in counts.items():
        deps = [{"tipo": "filho", "menor_14": True, "fonte": FONTE} for _ in range(n)]
        c.execute(text("UPDATE employees SET dependentes=CAST(:d AS jsonb) WHERE CAST(id AS TEXT)=:e"),
                  {"d": json.dumps(deps, ensure_ascii=False), "e": eid})
    print(f"backfill OK: {len(counts)} funcionários, backup /tmp/employees_dependentes_backup.json")
