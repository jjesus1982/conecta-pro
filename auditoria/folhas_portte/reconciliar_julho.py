"""extracao JSON -> load JSON do `carregar.py`. Reconcilia por CPF (pessoa) e CNPJ (condomínio).

Usa os arquivos POR CONDOMÍNIO (não o Geral): é deles que sai a atribuição condomínio↔pessoa.
O Geral serve só de conferência — a soma dos condomínios tem que bater com ele.

NUNCA inventa: só carrega o que está no PDF. Quem não casar por CPF/CNPJ é reportado, não chutado.

Uso: python3 reconciliar_julho.py <dir_extracao> <saida.json>
"""

import json
import os
import re
import sys

from sqlalchemy import create_engine, text

DIR, OUT = sys.argv[1], sys.argv[2]
# julho/2026 é a 1ª folha humanizada sob a PATRIMONIAL (o carregar.py tem a Eletrônica fixa —
# por isso o empresa_id vai explícito aqui, por competência).
EMPRESA_PATRIMONIAL = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"


def so_digitos(s):
    return re.sub(r"\D", "", s or "")


db = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "")).connect()
emp_por_cpf = {so_digitos(c): (str(i), n) for i, n, c in
               db.execute(text("SELECT id, nome, cpf FROM employees WHERE cpf IS NOT NULL")).all()}
cond_por_cnpj = {so_digitos(c): (str(i), n) for i, n, c in
                 db.execute(text("SELECT id, nome, cnpj FROM condominios WHERE cnpj IS NOT NULL")).all()}

rows, sem_pessoa, sem_cond = [], [], []
geral_liq = None
for f in sorted(os.listdir(DIR)):
    d = json.load(open(os.path.join(DIR, f)))
    if d.get("consolidado"):
        geral_liq = sum(float(e["totais"].get("liquido", 0) or 0) for e in d["empregados"])
        continue
    serv = d.get("servico") or {}
    cm = cond_por_cnpj.get(so_digitos(serv.get("cnpj")))
    if not cm:
        sem_cond.append(f"{serv.get('nome')} ({serv.get('cnpj')})")
        continue
    cond_id, _cond_nome = cm
    for e in d["empregados"]:
        pm = emp_por_cpf.get(so_digitos(e["cpf"]))
        if not pm:
            sem_pessoa.append(f"{e['nome']} ({e['cpf']})")
            continue
        eid, _ = pm
        t = e["totais"]
        earn = [r for r in e["rubricas"] if r["tipo"] == "P"]
        ded = [r for r in e["rubricas"] if r["tipo"] == "D"]
        # INSS do mês = a rubrica 998 + as de férias (812/821), como a própria folha soma
        inss_v = sum(float(r["valor"]) for r in ded if r["codigo"] in ("998", "812", "821"))
        irrf_v = sum(float(r["valor"]) for r in ded if "IRRF" in r["nome"].upper() or "RENDA" in r["nome"].upper())
        rows.append({
            "condominio_id": cond_id, "employee_id": eid, "matricula": e["matricula"],
            "employee_nome": e["nome"], "condominio_nome": serv.get("nome"),
            "base_salary": e["salario"],
            "total_earnings": t.get("proventos", "0"), "total_deductions": t.get("descontos", "0"),
            "net_salary": t.get("liquido", "0"),
            "earnings": [{"codigo": r["codigo"], "descricao": r["nome"],
                          "referencia": r["referencia"], "valor": float(r["valor"]),
                          "tipo": "provento"} for r in earn],
            "deductions": [{"codigo": r["codigo"], "descricao": r["nome"],
                            "referencia": r["referencia"], "valor": float(r["valor"]),
                            "tipo": "desconto"} for r in ded],
            "informative": {"cargo": e["cargo"], "cbo": e["cbo"], "horas_mes": e["horas_mes"],
                            "situacao": e["situacao"], "ferias_periodo": e.get("ferias_periodo"),
                            "fonte": "portte-pdf"},
            "inss_base": t.get("inss_base", "0"), "inss_value": round(inss_v, 2),
            "irrf_base": t.get("irrf_base", "0"), "irrf_value": round(irrf_v, 2),
            "fgts_base": t.get("fgts_base", "0"), "fgts_value": t.get("fgts_valor", "0"),
            "empresa_id": EMPRESA_PATRIMONIAL,
        })

soma = sum(float(r["net_salary"]) for r in rows)
print(f"{len(rows)} holerites reconciliados · líquido R$ {soma:,.2f}")
if geral_liq is not None:
    print(f"Geral (conferência):                  R$ {geral_liq:,.2f}   Δ {soma - geral_liq:+,.2f}")
if sem_pessoa:
    print(f"\nSEM CASAR POR CPF ({len(sem_pessoa)}):")
    for x in sem_pessoa:
        print("   ", x)
if sem_cond:
    print(f"\nSEM CASAR CONDOMÍNIO ({len(sem_cond)}):")
    for x in sem_cond:
        print("   ", x)

json.dump(rows, open(OUT, "w"), ensure_ascii=False, indent=1)
print(f"\n-> {OUT}")
