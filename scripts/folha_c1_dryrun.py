"""C1 dry-run — roda o motor Conecta (independente) nas 6 competências e concilia
centavo-a-centavo vs a folha Portte (hr_payslips source='portte'). READ-ONLY: nenhuma escrita.
Saída: relatório em auditoria/folha_c1_dryrun.md + resumo no stdout."""
import os
from decimal import Decimal
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador

URL = os.environ["DATABASE_URL"].replace("+asyncpg", "")
eng = create_engine(URL)


def verba(lst, needle):
    for v in (lst or []):
        if needle in (v.get("descricao") or "").upper():
            return float(v.get("valor") or 0)
    return 0.0


def f(x):
    return float(x) if x is not None else 0.0


ANO = 2026
MESES = [1, 2, 3, 4, 5, 6]
TOL = 0.005  # centavo

rows_out = []
resumo = {m: {"n": 0, "match_liq": 0, "sum_abs_liq": 0.0, "sum_irrf_conecta": 0.0,
              "sum_liq_conecta": 0.0, "sum_liq_portte": 0.0, "erros": 0} for m in MESES}

with Session(eng) as db:
    emps = db.execute(text(
        "SELECT CAST(id AS TEXT), nome FROM employees "
        "WHERE status='ativo' AND coalesce(tipo_contrato,'clt') <> 'pj' "
        "AND coalesce(is_homologacao,false)=false ORDER BY nome")).fetchall()
    for m in MESES:
        for eid, nome in emps:
            # Portte (espelho) da competência
            p = db.execute(text(
                "SELECT net_salary, total_earnings, total_deductions, inss_value, irrf_value, fgts_value "
                "FROM hr_payslips WHERE CAST(employee_id AS TEXT)=:e AND reference_year=:a "
                "AND reference_month=:m AND coalesce(source_system,'')='portte' LIMIT 1"),
                {"e": eid, "a": ANO, "m": m}).first()
            if not p:
                continue  # sem espelho Portte nessa comp p/ esse func → fora da conciliação
            r = resumo[m]
            r["n"] += 1
            try:
                c = calcular_folha_colaborador(db, eid, m, ANO)
            except Exception as e:  # noqa: BLE001
                r["erros"] += 1
                rows_out.append((m, nome, "ERRO", str(e)[:60], 0, 0, 0, 0))
                continue
            if c.get("error"):
                r["erros"] += 1
                continue
            c_liq = f(c.get("liquido"))
            c_prov = f(c.get("total_proventos"))
            c_desc = f(c.get("total_descontos"))
            c_inss = verba(c.get("descontos"), "INSS")
            c_irrf = verba(c.get("descontos"), "IRRF")
            c_fgts = f(c.get("fgts_empresa"))
            p_liq, p_prov, p_desc, p_inss, p_irrf, p_fgts = (f(p[0]), f(p[1]), f(p[2]), f(p[3]), f(p[4]), f(p[5]))
            d_liq = round(c_liq - p_liq, 2)
            r["sum_abs_liq"] += abs(d_liq)
            r["sum_irrf_conecta"] += c_irrf
            r["sum_liq_conecta"] += c_liq
            r["sum_liq_portte"] += p_liq
            if abs(d_liq) < TOL:
                r["match_liq"] += 1
            rows_out.append((m, nome, round(c_liq, 2), round(p_liq, 2), d_liq,
                             round(c_inss - p_inss, 2), round(c_irrf - p_irrf, 2), round(c_fgts - p_fgts, 2)))

# ---- relatório ----
lines = ["# C1 dry-run — folha Conecta (motor) × Portte (espelho) — 2026-07-28",
         "", "READ-ONLY: nada foi escrito. Delta = Conecta − Portte (R$). IRRF Portte=0 (delta esperado).", ""]
lines.append("## Resumo por competência")
lines.append("| Comp | Func | Líquido bate (≤R$0,01) | Σ|Δlíquido| | Σ IRRF Conecta (Portte=0) | Σ líq Conecta | Σ líq Portte | Erros |")
lines.append("|---|---|---|---|---|---|---|---|")
for m in MESES:
    r = resumo[m]
    if r["n"] == 0:
        continue
    lines.append(f"| {ANO}-{m:02d} | {r['n']} | {r['match_liq']}/{r['n']} | "
                 f"R$ {r['sum_abs_liq']:,.2f} | R$ {r['sum_irrf_conecta']:,.2f} | "
                 f"R$ {r['sum_liq_conecta']:,.2f} | R$ {r['sum_liq_portte']:,.2f} | {r['erros']} |")
# maiores divergências de líquido (excl. IRRF, que é esperado)
lines += ["", "## 20 maiores divergências de LÍQUIDO (|Δ| desc)"]
lines.append("| Comp | Colaborador | Líq Conecta | Líq Portte | Δlíquido | ΔINSS | ΔIRRF | ΔFGTS |")
lines.append("|---|---|---|---|---|---|---|---|")
top = sorted([x for x in rows_out if x[2] != "ERRO"], key=lambda x: -abs(x[4]))[:20]
for m, nome, cl, pl, dl, di, dr, dfg in top:
    lines.append(f"| {ANO}-{m:02d} | {nome[:28]} | {cl:,.2f} | {pl:,.2f} | **{dl:+,.2f}** | {di:+,.2f} | {dr:+,.2f} | {dfg:+,.2f} |")

# stdout resumo PRIMEIRO (garante saída mesmo se o write falhar)
print("\n".join(lines[:4]))
for m in MESES:
    r = resumo[m]
    if r["n"]:
        print(f"  {ANO}-{m:02d}: {r['match_liq']}/{r['n']} líquido bate · Σ|Δlíq|=R${r['sum_abs_liq']:,.2f} · "
              f"IRRF Conecta=R${r['sum_irrf_conecta']:,.2f} · erros={r['erros']}")
print("\n=== TOP divergências ===")
for m, nome, cl, pl, dl, di, dr, dfg in top:
    print(f"  {ANO}-{m:02d} {nome[:26]:<26} líqC={cl:>10,.2f} líqP={pl:>10,.2f} Δ={dl:>+10,.2f} ΔINSS={di:>+8,.2f} ΔIRRF={dr:>+8,.2f}")
try:
    open("/tmp/folha_c1_dryrun.md", "w").write("\n".join(lines))
    print("\nrelatório: /tmp/folha_c1_dryrun.md")
except Exception as e:  # noqa: BLE001
    print("write falhou:", e)
