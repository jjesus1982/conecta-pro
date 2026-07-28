"""C1 Fase A — reconciliação POR VERBA/BUCKET. READ-ONLY.
(1) Σ|Δ| por bucket estruturado (base, proventos, descontos, INSS, IRRF, FGTS, líquido).
(2) Inventário das verbas Portte (descrições) → quais o motor Conecta NÃO produz (gap estrutural)."""
import os
from collections import defaultdict
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador

URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
eng = create_engine(URL)
ANO = 2026
MESES = [1, 2, 3, 4, 5, 6]


def f(x):
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        return 0.0


def verba(lst, needle):
    return sum(f(v.get("valor")) for v in (lst or []) if needle in (v.get("descricao") or "").upper())


def desc_val(item):
    return ((item.get("descricao") or item.get("description") or "").strip().upper(),
            f(item.get("valor") if item.get("valor") is not None else item.get("value")))


# canonical bucket p/ agrupar verbas Portte por palavra-chave (proventos/descontos)
CANON = [
    ("BASE/HORAS NORMAIS", ["DIAS NORMAIS", "HORAS NORMAIS", "SALARIO BASE", "SALÁRIO BASE", "SALARIO MENSAL"]),
    ("ADIC. RONDA", ["RONDA"]),
    ("ADIC. NOTURNO/HORA NOT", ["NOTURN", "HORA NOT", "INTRAJORNADA"]),
    ("PERICULOSIDADE", ["PERICUL"]),
    ("INSALUBRIDADE", ["INSALUBR"]),
    ("HORA EXTRA", ["HORA EXTRA", "HORAS EXTRA", "H.E", "H EXTRA"]),
    ("FERIAS (verbas)", ["FERIAS", "FÉRIAS"]),
    ("13o", ["DECIMO", "DÉCIMO", "GRATIF NATAL"]),
    ("DSR/REPOUSO", ["DSR", "REPOUSO"]),
    ("VT", ["VALE TRANSP", "DESCONTO VT", "DESC VT"]),
    ("VR/VA", ["VALE REFEI", "VALE ALIMENT", "DESCONTO VR", "DESC VR"]),
    ("INSS", ["INSS", "I.N.S.S"]),
    ("IRRF", ["IRRF", "IRPF", "I.R.R", "I.R.F"]),
    ("FGTS", ["FGTS"]),
    ("EMPRESTIMO/CONSIGNADO", ["EMPREST", "CONSIGN", "CRED. TRAB", "CRED TRAB"]),
    ("FALTAS/ATRASO/AFAST", ["FALTA", "ATRASO", "DESC DIA", "AFAST", "AFASTAD"]),
    ("SALARIO FAMILIA", ["SALARIO FAMILIA", "SAL. FAMILIA", "SALÁRIO FAMÍLIA"]),
    ("TAXA/CONTRIB SINDICAL", ["TAXA NEGOC", "SINDICAL", "CONTRIB. ASSIST", "CONTRIB ASSIST"]),
    ("PLANO SAUDE/ODONTO", ["PLANO ODONTO", "PLANO SAUDE", "PLANO DE SAUDE", "ODONTOLOG"]),
    ("PENSAO/ADIANT", ["PENSAO", "PENSÃO", "ADIANT"]),
    ("ESTORNO", ["ESTORNO"]),
]


def canon(desc):
    for name, kws in CANON:
        if any(k in desc for k in kws):
            return name
    return "OUTROS"


buckets = ["base", "proventos", "descontos", "inss", "irrf", "fgts", "liquido"]
sums = {m: {b: {"c": 0.0, "p": 0.0, "abs": 0.0} for b in buckets} for m in MESES}
portte_verbas = defaultdict(lambda: {"n": 0, "total": 0.0})       # descrições Portte cruas
conecta_verbas = defaultdict(lambda: {"n": 0, "total": 0.0})
canon_delta = defaultdict(lambda: {"c": 0.0, "p": 0.0})           # por bucket canônico

with Session(eng) as db:
    emps = [r[0] for r in db.execute(text(
        "SELECT CAST(id AS TEXT) FROM employees WHERE status='ativo' "
        "AND coalesce(tipo_contrato,'clt')<>'pj' AND coalesce(is_homologacao,false)=false")).fetchall()]
    for m in MESES:
        for eid in emps:
            p = db.execute(text(
                "SELECT base_salary,total_earnings,total_deductions,net_salary,inss_value,irrf_value,"
                "fgts_value,earnings,deductions FROM hr_payslips WHERE CAST(employee_id AS TEXT)=:e "
                "AND reference_year=:a AND reference_month=:m AND coalesce(source_system,'')='portte' LIMIT 1"),
                {"e": eid, "a": ANO, "m": m}).first()
            if not p:
                continue
            try:
                c = calcular_folha_colaborador(db, eid, m, ANO)
            except Exception:  # noqa: BLE001
                continue
            if c.get("error"):
                continue
            cb = {"base": f(c.get("salario_base")), "proventos": f(c.get("total_proventos")),
                  "descontos": f(c.get("total_descontos")), "inss": verba(c.get("descontos"), "INSS"),
                  "irrf": verba(c.get("descontos"), "IRRF"), "fgts": f(c.get("fgts_empresa")),
                  "liquido": f(c.get("liquido"))}
            pb = {"base": f(p[0]), "proventos": f(p[1]), "descontos": f(p[2]), "liquido": f(p[3]),
                  "inss": f(p[4]), "irrf": f(p[5]), "fgts": f(p[6])}
            for b in buckets:
                sums[m][b]["c"] += cb[b]
                sums[m][b]["p"] += pb[b]
                sums[m][b]["abs"] += abs(round(cb[b] - pb[b], 2))
            # inventário verbas Portte + canônico
            for it in ((p[7] or []) + (p[8] or [])):
                d, v = desc_val(it)
                if not d:
                    continue
                portte_verbas[d]["n"] += 1
                portte_verbas[d]["total"] += v
                canon_delta[canon(d)]["p"] += v
            for it in ((c.get("proventos") or []) + (c.get("descontos") or [])):
                d, v = desc_val(it)
                if not d:
                    continue
                conecta_verbas[d]["n"] += 1
                conecta_verbas[d]["total"] += v
                canon_delta[canon(d)]["c"] += v

# ---- saída ----
print("# C1 Fase A — reconciliação por bucket/verba (2026, jan-jun) — READ-ONLY\n")
print("## Σ|Δ| por bucket estruturado (Conecta−Portte), por competência")
print(f"{'bucket':<12}" + "".join(f"{ANO}-{m:02d}".rjust(12) for m in MESES) + "   TOTAL")
for b in buckets:
    tot = sum(sums[m][b]["abs"] for m in MESES)
    print(f"{b:<12}" + "".join(f"{sums[m][b]['abs']:>12,.0f}" for m in MESES) + f"   {tot:>12,.0f}")

print("\n## Delta por VERBA CANÔNICA (Σ Conecta vs Σ Portte, todas as comp) — onde mora a divergência")
print(f"{'verba canônica':<26}{'Σ Conecta':>14}{'Σ Portte':>14}{'Δ':>14}")
for name in sorted(canon_delta, key=lambda k: -abs(canon_delta[k]["c"] - canon_delta[k]["p"])):
    cc, pp = canon_delta[name]["c"], canon_delta[name]["p"]
    print(f"{name:<26}{cc:>14,.0f}{pp:>14,.0f}{cc-pp:>+14,.0f}")

print("\n## Verbas que a PORTTE tem e o motor CONECTA canoniza como OUTROS (gap p/ mapear)")
outros = sorted([(d, v["n"], v["total"]) for d, v in portte_verbas.items() if canon(d) == "OUTROS"],
                key=lambda x: -x[2])[:20]
for d, n, tot in outros:
    print(f"  {d[:44]:<44} n={n:<4} Σ=R${tot:>12,.2f}")
