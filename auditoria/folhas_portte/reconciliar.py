#!/usr/bin/env python3
"""Reconcilia extração Portte (JSON) vs nosso banco → relatório + load-ready. v2.
Uso: python3 reconciliar.py <month_slug> <competencia>  (ex.: 01_janeiro 01/2026)
READ-ONLY. Regras Jordan: nome some=demitido; manter cadastro Portte (empregado que falta = criar).
v2: usa o GERAL como lista-mestra (pega os 'só-no-Geral'); condomínio via mapa cross-mês (posto estável);
match CPF→nome (fallback, flag)→marcar 'a_criar'. Nunca inventa: não-match reportado, não silenciado.
"""
import glob, json, os, re, sys, unicodedata
from decimal import Decimal

BASE = os.path.dirname(os.path.abspath(__file__))


def dig(s):
    return re.sub(r"\D", "", s or "")


def dec(s):
    try:
        return Decimal(str(s))
    except Exception:
        return Decimal("0")


def norm(nome):
    s = unicodedata.normalize("NFKD", (nome or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def name_match(pnome, our_by_norm):
    """Match por nome: igualdade normalizada, ou um é prefixo do outro (trunc), tokens>=3 iguais."""
    pn = norm(pnome)
    if pn in our_by_norm:
        return our_by_norm[pn], "exato"
    for on, emp in our_by_norm.items():
        if (pn.startswith(on) or on.startswith(pn)) and min(len(pn), len(on)) >= 12:
            return emp, "prefixo"
    return None, None


def build_cond_map():
    """CPF→(cond_slug, servico_cnpj) de TODOS os meses individualizados (posto é estável)."""
    m = {}
    for f in glob.glob(os.path.join(BASE, "extracao", "*", "*.json")):
        d = json.load(open(f))
        if d.get("consolidado"):
            continue
        scnpj = dig(d.get("servico", {}).get("cnpj"))
        for e in d.get("empregados", []):
            c = dig(e.get("cpf"))
            if c and c not in m:
                m[c] = (d.get("arquivo"), scnpj)
    return m


def main():
    month, comp = sys.argv[1], sys.argv[2]
    exdir = os.path.join(BASE, "extracao", month)
    conds = json.load(open(os.path.join(BASE, "reconciliacao", "map_condominios.json")))
    emps = json.load(open(os.path.join(BASE, "reconciliacao", "map_employees.json")))
    cond_by_cnpj = {c["cnpj_dig"]: c for c in conds}
    emp_by_cpf = {e["cpf_dig"]: e for e in emps}
    emp_by_norm = {norm(e["nome"]): e for e in emps}
    cpf_cond = build_cond_map()

    # fonte de empregados do mês: preferir GERAL (lista-mestra); se não houver, unir individualizados
    files = {json.load(open(os.path.join(exdir, f))).get("arquivo", f[:-5]): json.load(open(os.path.join(exdir, f)))
             for f in os.listdir(exdir) if f.endswith(".json")}
    geral = next((d for d in files.values() if d.get("consolidado")), None)
    # índice CPF→(empregado, servico_cnpj deste mês) dos individualizados
    indiv = {}
    for slug, d in files.items():
        if d.get("consolidado"):
            continue
        scnpj = dig(d.get("servico", {}).get("cnpj"))
        for e in d.get("empregados", []):
            indiv[dig(e.get("cpf"))] = (e, scnpj)

    master = geral.get("empregados", []) if geral else [e for _, (e, _) in indiv.items()]
    load, nc, tocreate = [], [], []
    for e in master:
        cpf = dig(e.get("cpf"))
        # dado financeiro: preferir o do individualizado (idêntico ao geral, mas garante)
        src = indiv.get(cpf, (e, None))[0]
        # condomínio: individualizado deste mês → senão mapa cross-mês
        scnpj = indiv.get(cpf, (None, None))[1] or cpf_cond.get(cpf, (None, None))[1]
        cond = cond_by_cnpj.get(scnpj or "")
        # empregado: CPF → nome
        emp = emp_by_cpf.get(cpf)
        match_kind = "cpf"
        if not emp:
            emp, mk = name_match(src.get("nome"), emp_by_norm)
            match_kind = f"nome_{mk}" if emp else None
        tot = src.get("totais", {})
        liq = float(dec(tot.get("liquido")))
        if not cond:
            nc.append(f"CONDOMINIO indefinido p/ {src.get('nome')} (CPF {src.get('cpf')}) — sem serviço mapeável (liq {liq})")
            continue
        if not emp:
            tocreate.append({"cpf": src.get("cpf"), "nome": src.get("nome"), "situacao": src.get("situacao"),
                             "admissao": src.get("admissao"), "cargo": src.get("cargo"), "cbo": src.get("cbo"),
                             "condominio_id": cond["id"], "condominio_nome": cond["nome"], "liquido": liq})
            nc.append(f"A_CRIAR (Portte, sem match): {src.get('nome')} CPF {src.get('cpf')} sit={src.get('situacao')} liq={liq} → {cond['nome']}")
            continue
        if match_kind and match_kind.startswith("nome"):
            nc.append(f"MATCH POR NOME ({match_kind}): Portte '{src.get('nome')}' CPF {src.get('cpf')} → nosso '{emp['nome']}' CPF {emp['cpf']} (CPF DIVERGE — manter Portte)")
        earn, ded, info = [], [], []
        for r in src.get("rubricas", []):
            item = {"code": r.get("codigo"), "value": float(dec(r.get("valor"))),
                    "reference": r.get("referencia"), "description": r.get("nome")}
            t = (r.get("tipo") or "").upper()
            (earn if t == "P" else ded if t == "D" else info).append(item)
        inss = sum(Decimal(str(x["value"])) for x in ded if x.get("code") == "998")
        load.append({
            "employee_id": emp["id"], "employee_nome": emp["nome"], "match": match_kind,
            "condominio_id": cond["id"], "condominio_nome": cond["nome"],
            "competencia": comp, "cpf": src.get("cpf"), "portte_nome": src.get("nome"), "matricula": src.get("matricula"),
            "base_salary": float(dec(src.get("salario"))),
            "total_earnings": float(dec(tot.get("proventos"))), "total_deductions": float(dec(tot.get("descontos"))),
            "net_salary": liq, "inss_base": float(dec(tot.get("inss_base"))), "inss_value": float(inss),
            "irrf_base": float(dec(tot.get("irrf_base"))), "irrf_value": float(dec(tot.get("irrf_valor"))),
            "fgts_base": float(dec(tot.get("fgts_base"))), "fgts_value": float(dec(tot.get("fgts_valor"))),
            "earnings": earn, "deductions": ded, "informative": info,
        })
    soma = sum(Decimal(str(p["net_salary"])) for p in load)
    tocreate_liq = sum(Decimal(str(t["liquido"])) for t in tocreate)
    geral_liq = dec(geral.get("resumo_servico", {}).get("liquido")) if geral else Decimal("0")
    json.dump(load, open(os.path.join(BASE, "reconciliacao", f"{month}_load.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(tocreate, open(os.path.join(BASE, "reconciliacao", f"{month}_tocreate.json"), "w"), ensure_ascii=False, indent=1)
    print(f"OK {month}: master={len(master)} · load={len(load)} · a_criar={len(tocreate)} (liq {tocreate_liq}) · nc={len(nc)}")
    print(f"cross-check: load+tocreate = {soma+tocreate_liq} vs geral = {geral_liq} (diff {soma+tocreate_liq-geral_liq})")
    for x in nc[:25]:
        print("  -", x)


if __name__ == "__main__":
    main()
