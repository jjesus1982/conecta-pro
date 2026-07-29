"""C1 — decomposição do +15,2k de BASE. READ-ONLY.
Hipótese: motor paga base CHEIA; Portte FATIA os DIAS NORMAIS quando há férias/falta/
suspensão e move o resto p/ verbas. Se verdade, Δbase(motor−portte) por pessoa/mês
≈ Σ(férias+falta+suspensão) da Portte naquele mês. Mede a correlação e o resíduo."""
import os
import re
from collections import defaultdict
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
ANO = 2026


def norm(d):
    return re.sub(r"\s+", " ", (d or "").strip().upper())


def f(x):
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        return 0.0


# descricoes Portte que compõem a BASE (DIAS NORMAIS / salário)
BASE_KW = ["DIAS NORMAIS", "HORAS NORMAIS", "SALARIO BASE", "SALÁRIO BASE", "SALARIO MENSAL", "SALARIO"]
# o que a Portte TIRA da base (dias não trabalhados)
FER_KW = ["FERIAS", "FÉRIAS"]
FALTA_KW = ["FALTA", "ATRASO", "DSR SOBRE FALTA", "DESC DIA"]
SUSP_KW = ["SUSPENS", "AFAST", "AUSENCIA", "AUSÊNCIA"]


def soma(items, kws, neg_ok=True):
    s = 0.0
    for it in (items or []):
        du = norm(it.get("descricao") or it.get("description"))
        v = f(it.get("valor") if it.get("valor") is not None else it.get("value"))
        if any(k in du for k in kws):
            s += v
    return s


tot = {"dbase": 0.0, "fer": 0.0, "falta": 0.0, "susp": 0.0, "resid": 0.0}
por_causa = defaultdict(float)
casos = []
with Session(eng) as db:
    emps = db.execute(text(
        "SELECT CAST(id AS TEXT), nome FROM employees WHERE status='ativo' "
        "AND coalesce(tipo_contrato,'clt')<>'pj' AND coalesce(is_homologacao,false)=false")).fetchall()
    for m in range(1, 7):
        for eid, nome in emps:
            p = db.execute(text(
                "SELECT earnings, deductions FROM hr_payslips WHERE CAST(employee_id AS TEXT)=:e "
                "AND reference_year=:a AND reference_month=:m AND source_system='portte' LIMIT 1"),
                {"e": eid, "a": ANO, "m": m}).first()
            if not p:
                continue
            try:
                c = calcular_folha_colaborador(db, eid, m, ANO)
            except Exception:  # noqa: BLE001
                continue
            if c.get("error"):
                continue
            motor_base = sum(f(x.get("valor")) for x in (c.get("proventos") or [])
                             if norm(x.get("descricao")) == "SALARIO BASE"
                             or "SALARIO BASE" in norm(x.get("descricao")))
            portte_base = soma(p[0], BASE_KW)
            dbase = round(motor_base - portte_base, 2)
            if abs(dbase) < 0.5:
                continue
            fer = soma(p[0], FER_KW) + soma(p[1], FER_KW)
            falta = soma(p[1], FALTA_KW)
            susp = soma(p[0], SUSP_KW) + soma(p[1], SUSP_KW)
            resid = dbase - (fer + falta + susp) if dbase > 0 else dbase
            tot["dbase"] += dbase
            tot["fer"] += fer
            tot["falta"] += falta
            tot["susp"] += susp
            tot["resid"] += resid
            casos.append((abs(dbase), m, nome[:24], dbase, fer, falta, susp, resid))

print("# Decomposição do Δ-BASE (motor − Portte), população harness, jan-jun\n")
print(f"Σ Δbase (motor sobra) .............. R$ {tot['dbase']:>12,.2f}")
print(f"  explicável por FÉRIAS ............ R$ {tot['fer']:>12,.2f}")
print(f"  explicável por FALTA/ATRASO ...... R$ {tot['falta']:>12,.2f}")
print(f"  explicável por SUSPENSÃO/AFAST ... R$ {tot['susp']:>12,.2f}")
print(f"  RESÍDUO não explicado ............ R$ {tot['resid']:>12,.2f}")
print(f"\n{len(casos)} casos com |Δbase|>R$0,50. Top 15 por magnitude:")
print(f"{'m':>3} {'nome':<24}{'Δbase':>10}{'férias':>10}{'falta':>9}{'susp':>9}{'resíduo':>10}")
for _, m, nome, db_, fer, falta, susp, resid in sorted(casos, reverse=True)[:15]:
    print(f"{m:>3} {nome:<24}{db_:>+10,.2f}{fer:>10,.2f}{falta:>9,.2f}{susp:>9,.2f}{resid:>+10,.2f}")
