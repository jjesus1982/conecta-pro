"""C1 verba 2 (intrajornada) — backfill do espelho Portte.
Portte paga INTRAJORNADA DIURNO (hn×1.5) e NOTURNA (hn×~1.8, redução+20% embutidos)
por HORA real. Taxa noturna não é reproduzível limpa → p/ o espelho gravamos o VALOR
da Portte (verdade). Going-forward o motor computa do ponto×taxa CCT.
Cria folha_intrajornada_espelho + backfilla valor/horas + liga recebe_intrajornada
p/ os 28 que a Portte pagou. Idempotente."""
import os
import re
from collections import defaultdict
from sqlalchemy import create_engine, text

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
ANO = 2026
FONTE = "backfill_portte_intrajornada_2026-07-28"


def norm(d):
    return re.sub(r"\s+", " ", (d or "").strip().upper())


def f(x):
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        return 0.0


def horas(ref):
    if not ref:
        return 0.0
    s = str(ref).strip()
    if ":" in s:
        h, mi = s.split(":")[:2]
        return round(int(h) + int(mi) / 60, 2)
    return f(s.replace(",", "."))


# (eid, mes) -> [val_diurna, val_noturna, hrs_diurna, hrs_noturna]
data = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
recebedores = set()
with eng.connect() as c:
    for m in range(1, 7):
        for eid, ear in c.execute(text(
            "SELECT employee_id::text, earnings FROM hr_payslips "
            "WHERE reference_year=:a AND reference_month=:m AND source_system='portte'"),
            {"a": ANO, "m": m}).fetchall():
            for it in (ear or []):
                du = norm(it.get("descricao") or it.get("description"))
                v = f(it.get("valor") if it.get("valor") is not None else it.get("value"))
                hr = horas(it.get("reference"))
                if "INTRAJORNADA DIURNO" in du and v > 0:
                    data[(eid, m)][0] += v
                    data[(eid, m)][2] += hr
                    recebedores.add(eid)
                elif "INTRAJORNADA NOTURNA" in du and v > 0:
                    data[(eid, m)][1] += v
                    data[(eid, m)][3] += hr
                    recebedores.add(eid)

print(f"linhas (emp×mês) com intrajornada: {len(data)} | recebedores distintos: {len(recebedores)}")

with eng.begin() as c:
    c.execute(text("""
        CREATE TABLE IF NOT EXISTS folha_intrajornada_espelho (
            employee_id uuid NOT NULL, ano int NOT NULL, mes int NOT NULL,
            valor_diurna numeric DEFAULT 0, valor_noturna numeric DEFAULT 0,
            horas_diurna numeric DEFAULT 0, horas_noturna numeric DEFAULT 0,
            fonte text, PRIMARY KEY (employee_id, ano, mes))"""))
    c.execute(text("DELETE FROM folha_intrajornada_espelho WHERE ano=:a AND fonte=:f"), {"a": ANO, "f": FONTE})
    for (eid, m), (vd, vn, hd, hn) in data.items():
        c.execute(text("""
            INSERT INTO folha_intrajornada_espelho
              (employee_id, ano, mes, valor_diurna, valor_noturna, horas_diurna, horas_noturna, fonte)
            VALUES (CAST(:e AS uuid), :a, :m, :vd, :vn, :hd, :hn, :f)"""),
            {"e": eid, "a": ANO, "m": m, "vd": round(vd, 2), "vn": round(vn, 2),
             "hd": round(hd, 2), "hn": round(hn, 2), "f": FONTE})
    # liga a flag p/ quem a Portte pagou (going-forward = direito reconhecido)
    upd = c.execute(text(
        "UPDATE employees SET recebe_intrajornada=true WHERE CAST(id AS TEXT)=ANY(:ids) "
        "AND coalesce(recebe_intrajornada,false)=false"), {"ids": list(recebedores)})
    print(f"inseridas {len(data)} linhas espelho; flag ligada em +{upd.rowcount} func (total recebedores {len(recebedores)})")
