#!/usr/bin/env python3
"""Reconcilia extração Portte (JSON) contra nosso banco (maps CPF/CNPJ) → relatório + load-ready.
Uso: python3 reconciliar.py <month_slug> <competencia>  (ex.: 01_janeiro 01/2026)
READ-ONLY (só lê os JSON de extração + os maps; não toca banco). Nunca inventa: não-match = reporta.
"""
import json, os, re, sys
from decimal import Decimal

BASE = os.path.dirname(os.path.abspath(__file__))


def dig(s):
    return re.sub(r"\D", "", s or "")


def dec(s):
    try:
        return Decimal(str(s))
    except Exception:
        return Decimal("0")


def main():
    month, comp = sys.argv[1], sys.argv[2]
    exdir = os.path.join(BASE, "extracao", month)
    conds = json.load(open(os.path.join(BASE, "reconciliacao", "map_condominios.json")))
    emps = json.load(open(os.path.join(BASE, "reconciliacao", "map_employees.json")))
    cond_by_cnpj = {c["cnpj_dig"]: c for c in conds}
    emp_by_cpf = {e["cpf_dig"]: e for e in emps}

    files = sorted(f for f in os.listdir(exdir) if f.endswith(".json"))
    load, nc = [], []  # load-ready payslips; nao-conformidades
    servicos = []
    geral = None
    for fn in files:
        d = json.load(open(os.path.join(exdir, fn)))
        if d.get("consolidado"):
            geral = d
            continue
        slug = d.get("arquivo", fn[:-5])
        scnpj = dig(d.get("servico", {}).get("cnpj"))
        cond = cond_by_cnpj.get(scnpj)
        if not cond:
            nc.append(f"CONDOMINIO nao mapeado: {slug} (serviço CNPJ {d.get('servico',{}).get('cnpj')}) — sem match nos condominios")
        servicos.append((slug, cond, d))
        for e in d.get("empregados", []):
            cpf = dig(e.get("cpf"))
            emp = emp_by_cpf.get(cpf)
            if not emp:
                nc.append(f"EMPREGADO sem match (CPF {e.get('cpf')}): {e.get('nome')} — condomínio {slug}")
                continue
            if not cond:
                continue  # ja reportado
            # separa rubricas P/D
            earn, ded, info = [], [], []
            for r in e.get("rubricas", []):
                item = {"code": r.get("codigo"), "value": float(dec(r.get("valor"))),
                        "reference": r.get("referencia"), "description": r.get("nome")}
                t = (r.get("tipo") or "").upper()
                (earn if t == "P" else ded if t == "D" else info).append(item)
            tot = e.get("totais", {})
            load.append({
                "employee_id": emp["id"], "employee_nome": emp["nome"],
                "condominio_id": cond["id"], "condominio_nome": cond["nome"],
                "competencia": comp, "cpf": e.get("cpf"), "portte_nome": e.get("nome"),
                "matricula": e.get("matricula"), "cargo": e.get("cargo"), "cbo": e.get("cbo"),
                "base_salary": float(dec(e.get("salario"))),
                "total_earnings": float(dec(tot.get("proventos"))),
                "total_deductions": float(dec(tot.get("descontos"))),
                "net_salary": float(dec(tot.get("liquido"))),
                "inss_base": float(dec(tot.get("inss_base"))), "inss_value": None,
                "irrf_base": float(dec(tot.get("irrf_base"))), "irrf_value": float(dec(tot.get("irrf_valor"))),
                "fgts_base": float(dec(tot.get("fgts_base"))), "fgts_value": float(dec(tot.get("fgts_valor"))),
                "earnings": earn, "deductions": ded, "informative": info,
            })
    # cross-check: soma liquidos load vs geral
    soma_liq = sum(Decimal(str(p["net_salary"])) for p in load)
    geral_liq = dec(geral.get("resumo_servico", {}).get("liquido")) if geral else Decimal("0")
    # extrai inss_value das rubricas D com code 998 (I.N.S.S.)
    for p in load:
        inss = sum(Decimal(str(r["value"])) for r in p["deductions"] if r.get("code") == "998")
        p["inss_value"] = float(inss)

    # relatorio
    rep = [f"# Reconciliação folha Portte — {comp} ({month})\n"]
    rep.append(f"- Condomínios individualizados: {len(servicos)}")
    rep.append(f"- Payslips prontos p/ carga (empregado+condomínio casados): **{len(load)}**")
    rep.append(f"- Não-conformidades: **{len(nc)}**")
    rep.append(f"- Cross-check líquido: soma load = R$ {soma_liq} · Geral (só individualizados casados) — comparar manual c/ Geral R$ {geral_liq}")
    rep.append("")
    if nc:
        rep.append("## Não-conformidades (surfaçadas, NÃO resolvidas automaticamente)")
        for x in nc:
            rep.append(f"- {x}")
    rep.append("")
    rep.append("## Cobertura por condomínio")
    for slug, cond, d in servicos:
        n_emp = len(d.get("empregados", []))
        n_ok = sum(1 for p in load if p["condominio_nome"] == (cond or {}).get("nome"))
        rep.append(f"- {slug} → {(cond or {}).get('nome','SEM MATCH')} : {n_ok}/{n_emp} empregados casados")
    outmd = os.path.join(BASE, "reconciliacao", f"{month}.md")
    open(outmd, "w").write("\n".join(rep))
    outjson = os.path.join(BASE, "reconciliacao", f"{month}_load.json")
    json.dump(load, open(outjson, "w"), ensure_ascii=False, indent=1)
    print(f"OK {month}: {len(load)} payslips prontos, {len(nc)} não-conformidades. Relatório: {outmd}")
    print(f"cross-check líquido: load={soma_liq} vs geral={geral_liq} (diff {soma_liq-geral_liq})")
    if nc:
        print("NÃO-CONFORMIDADES:")
        for x in nc[:20]:
            print("  -", x)


if __name__ == "__main__":
    main()
