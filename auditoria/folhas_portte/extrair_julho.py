"""Extrai a folha da Portte (PDF) para o JSON que `carregar.py` consome.

Mesmo esquema dos meses jan-jun já extraídos em `extracao/`. Lê por COORDENADA: o texto cru
do PDF sai com rótulo e valor intercalados (`8781 DIAS NORMAIS` … `937` … `1.100,13 D`),
e reconstruir por linha é o que torna o parse confiável.

Layout de uma linha de rubrica: DUAS rubricas por linha (provento à esquerda, desconto à
direita), cada uma no formato  CODIGO NOME... REFERENCIA VALOR TIPO(P|D).
O corte é o token 'P'/'D' sozinho — dele para trás: valor, referência, nome, e o 1º token
do grupo é o código.

Uso:  python3 extrair_julho.py <dir_pdfs> <saida_dir>
"""

import json
import os
import re
import sys
from collections import defaultdict

import fitz

DIR_PDF, DIR_OUT = sys.argv[1], sys.argv[2]
NUM = re.compile(r"^[\d.]+,\d{2}$")


def _val(s: str) -> str:
    """'1.742,52' -> '1742.52' (o carregar.py espera decimal com ponto)."""
    return s.replace(".", "").replace(",", ".")


def linhas(pg):
    L = defaultdict(list)
    for x0, y0, _x1, _y1, w, *_ in pg.get_text("words"):
        L[round(y0)].append((x0, w))
    return [[w for _, w in sorted(L[y])] for y in sorted(L)]


def rubricas_da_linha(t: list[str]) -> list[dict]:
    """Corta a linha nos marcadores P/D. Uma linha traz 1 ou 2 rubricas."""
    out, buf = [], []
    for tok in t:
        if tok in ("P", "D") and len(buf) >= 3 and NUM.match(buf[-1] or ""):
            out.append({
                "codigo": buf[0],
                "nome": " ".join(buf[1:-2]),
                "referencia": buf[-2],
                "valor": _val(buf[-1]),
                "tipo": tok,
            })
            buf = []
        else:
            buf.append(tok)
    return out


def extrai(path: str) -> dict:
    doc = fitz.open(path)
    d = {"competencia": "", "arquivo": os.path.basename(path), "consolidado": False,
         "empresa": {}, "servico": {}, "emissao": "", "empregados": []}
    atual = None
    for pg in doc:
        for t in linhas(pg):
            s = " ".join(t)
            if t[:1] == ["Competência:"] or "Competência:" in s:
                m = re.search(r"(\d{2}/\d{4})", s)
                if m and not d["competencia"]:
                    d["competencia"] = m.group(1)
            if s.startswith("Emissão:") and not d["emissao"]:
                d["emissao"] = t[1] if len(t) > 1 else ""
            if "CONECTAMAIS" in s and not d["empresa"]:
                m = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", s)
                d["empresa"] = {"nome": re.sub(r"^\d+\s*-\s*", "", s.split(" CNPJ")[0]).strip(),
                                "cnpj": m.group(1) if m else ""}
            if s.startswith("Serviço:") and not d["servico"]:
                m = re.match(r"Serviço:\s*(\d+)\s*-\s*(.+?)\s*-\s*CNPJ:\s*([\d./-]+)\s*-\s*(.*)", s)
                if m:
                    d["servico"] = {"codigo": m.group(1), "nome": m.group(2),
                                    "cnpj": m.group(3), "endereco": m.group(4)}
            if t[0] == "Empr.:":
                nome = []
                for w in t[2:]:
                    if w == "Situação:":
                        break
                    nome.append(w)
                atual = {"matricula": t[1], "nome": " ".join(nome), "cpf": "", "situacao": "",
                         "admissao": "", "vinculo": "", "cargo": "", "cbo": "",
                         "horas_mes": "", "salario": "", "rubricas": [], "totais": {}}
                d["empregados"].append(atual)
                for k, campo in (("CPF:", "cpf"), ("Adm:", "admissao"), ("Situação:", "situacao")):
                    if k in t:
                        atual[campo] = t[t.index(k) + 1]
                continue
            if atual is None:
                continue
            if "Horas" in t and "Mês:" in t:
                atual["horas_mes"] = t[t.index("Mês:") + 1]
                if "Vínculo:" in t:
                    atual["vinculo"] = t[t.index("Vínculo:") + 1]
            if t[0] == "Cargo:":
                fim = t.index("C.B.O:") if "C.B.O:" in t else len(t)
                atual["cargo"] = " ".join(t[1:fim])
                if "C.B.O:" in t:
                    atual["cbo"] = t[t.index("C.B.O:") + 1]
                if "Salário:" in t:
                    atual["salario"] = _val(t[t.index("Salário:") + 1])
                continue
            if t[0] == "ND:":
                for k, campo in (("Proventos:", "proventos"), ("Descontos:", "descontos"),
                                 ("Líquido:", "liquido")):
                    if k in t:
                        atual["totais"][campo] = _val(t[t.index(k) + 1])
                continue
            if t[0] == "NF:":
                for k, campo in (("INSS:", "inss_base"), ("FGTS:", "fgts_base"), ("IRRF:", "irrf_base")):
                    if k in t:
                        atual["totais"][campo] = _val(t[t.index(k) + 1])
                # 'Valor FGTS: 177,54' — o par (Valor, FGTS:) aparece DEPOIS de 'Base FGTS:'
                for i in range(len(t) - 2):
                    if t[i] == "Valor" and t[i + 1] == "FGTS:":
                        atual["totais"]["fgts_valor"] = _val(t[i + 2])
                continue
            if s.startswith("FERIAS DE"):
                atual["ferias_periodo"] = s.replace("FERIAS DE ", "")
                continue
            # O PDF fecha com "Resumo por Rubrica" — os TOTAIS do arquivo, no mesmo formato
            # das rubricas individuais. Sem este corte eles eram atribuídos ao ÚLTIMO
            # empregado (KALEL saía com 42 rubricas, incluindo 'DIAS NORMAIS 2.671,86' que é
            # o total do arquivo). O líquido continuava batendo porque vem de `totais` —
            # por isso a soma das rubricas TRIPLICAVA sem nada acusar.
            if "Resumo por Rubrica" in s:
                atual = None
                continue
            atual["rubricas"].extend(rubricas_da_linha(t))
    return d


os.makedirs(DIR_OUT, exist_ok=True)
tot_emp = tot_rub = 0
for f in sorted(os.listdir(DIR_PDF)):
    if not f.lower().endswith(".pdf"):
        continue
    d = extrai(os.path.join(DIR_PDF, f))
    d["consolidado"] = "Geral" in f
    slug = re.sub(r"[^a-z0-9]+", "_", f.lower().replace(".pdf", "").split("_")[-1]).strip("_")
    with open(os.path.join(DIR_OUT, f"{slug}.json"), "w") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    nr = sum(len(e["rubricas"]) for e in d["empregados"])
    tot_emp += len(d["empregados"])
    tot_rub += nr
    liq = sum(float(e["totais"].get("liquido", 0) or 0) for e in d["empregados"])
    print(f"{slug:<28} {len(d['empregados']):>3} empregados  {nr:>4} rubricas  líquido R$ {liq:>12,.2f}")
print(f"\nTOTAL (com o Geral, que repete todo mundo): {tot_emp} empregados, {tot_rub} rubricas")
