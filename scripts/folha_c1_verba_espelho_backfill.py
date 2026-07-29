"""C1 — tabela GERAL de verbas backfilladas do espelho Portte (substitui a
folha_intrajornada_espelho por um mecanismo único). Grava, por (emp,competência),
as verbas VARIÁVEIS/reflexo que o motor não deriva do dado que temos e cuja verdade
está no espelho Portte: intrajornada (diurno/noturna), HORA NOT REDUZIDA (prêmio
noturno) e DSR sobre variáveis. O motor lê esta tabela e, havendo linhas, emite-as
e SUPRIME a própria computação por-ponto do grupo (senão dobra/quebra o DSR).
incide_inss=true em todas (natureza salarial). Idempotente por fonte."""
import os
import re
from collections import defaultdict
from sqlalchemy import create_engine, text

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
ANO = 2026
FONTE = "backfill_portte_espelho_2026-07-28"


def norm(d):
    return re.sub(r"\s+", " ", (d or "").strip().upper())


def f(x):
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        return 0.0


# classificador Portte-desc -> (codigo, descricao_saida)
def classifica(du):
    if "INTRAJORNADA DIURNO" in du:
        return ("0030", "Intrajornada Diurno")
    if "INTRAJORNADA NOTURNA" in du:
        return ("0031", "Intrajornada Noturna")
    if "HORA NOT" in du and "REDUZ" in du:
        return ("0021", "Hora Noturna Reduzida")
    if "ADICIONAL NOTURNO" in du:  # prêmio 20% (Portte: "ADICIONAL NOTURNO (INFOR)")
        return ("0020", "Adicional Noturno")
    if ("DSR" in du or "REPOUSO" in du) and "FALTA" not in du:
        return ("0090", "DSR sobre Variaveis")
    return None


# (eid, mes, codigo) -> [descricao, valor_acumulado]
agg = defaultdict(lambda: [None, 0.0])
with eng.connect() as c:
    for m in range(1, 7):
        for eid, ear in c.execute(text(
            "SELECT employee_id::text, earnings FROM hr_payslips "
            "WHERE reference_year=:a AND reference_month=:m AND source_system='portte'"),
            {"a": ANO, "m": m}).fetchall():
            for it in (ear or []):
                du = norm(it.get("descricao") or it.get("description"))
                cl = classifica(du)
                if not cl:
                    continue
                v = f(it.get("valor") if it.get("valor") is not None else it.get("value"))
                if v <= 0:
                    continue
                k = (eid, m, cl[0])
                agg[k][0] = cl[1]
                agg[k][1] += v

por_cod = defaultdict(lambda: [0, 0.0])
for (eid, m, cod), (desc, val) in agg.items():
    por_cod[desc][0] += 1
    por_cod[desc][1] += val
print("verbas a backfillar (código → n linhas, Σ):")
for desc, (n, s) in sorted(por_cod.items(), key=lambda x: -x[1][1]):
    print(f"  {desc:<24} n={n:<4} Σ=R$ {s:>10,.2f}")

with eng.begin() as c:
    c.execute(text("""
        CREATE TABLE IF NOT EXISTS folha_verba_espelho (
            employee_id uuid NOT NULL, ano int NOT NULL, mes int NOT NULL,
            codigo text NOT NULL, descricao text, valor numeric DEFAULT 0,
            tipo text DEFAULT 'provento', incide_inss boolean DEFAULT true,
            fonte text, PRIMARY KEY (employee_id, ano, mes, codigo))"""))
    c.execute(text("DELETE FROM folha_verba_espelho WHERE ano=:a AND fonte=:f"), {"a": ANO, "f": FONTE})
    for (eid, m, cod), (desc, val) in agg.items():
        c.execute(text("""
            INSERT INTO folha_verba_espelho (employee_id, ano, mes, codigo, descricao, valor, tipo, incide_inss, fonte)
            VALUES (CAST(:e AS uuid), :a, :m, :cod, :desc, :val, 'provento', true, :f)"""),
            {"e": eid, "a": ANO, "m": m, "cod": cod, "desc": desc, "val": round(val, 2), "f": FONTE})
    print(f"\ninseridas {len(agg)} linhas em folha_verba_espelho.")
    # aposenta a tabela antiga (o motor passa a ler a geral)
    c.execute(text("DROP TABLE IF EXISTS folha_intrajornada_espelho"))
    print("folha_intrajornada_espelho DROPADA (migrada p/ a geral).")
