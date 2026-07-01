"""
Engine de precificação CCT 2026 (Lucro Real) — replica a Planilha_Formacao_Preco_CCT2026_ConectaMais.

PREÇO = custo_total ÷ (1 − tributos_faturamento − margem)   [método do DIVISOR, margem líquida]
custo_total = salário_bruto + encargos(~61,24%) + benefícios.  Peric. e insalub. NÃO acumulam.
Termos oficiais: AGP (Agente de Portaria), ASG (Aux. Serviços Gerais). Proibido porteiro/vigia/faxineiro.
"""

from __future__ import annotations

from sqlalchemy import text

ENCARGO_KEYS = ("inss", "rat_fap", "terceiros", "fgts", "ferias_terco", "decimo_terceiro", "rescisao")
_DEFAULTS = {  # fallback se faltar algum parâmetro no banco
    "noturno": 0.20,
    "hora_reduzida": 0.08,
    "ronda": 0.0,
    "periculosidade": 0.30,
    "insalubridade": 0.10,
    "vt_dia": 10,
    "vt_desconto": 0.04,
    "vr_dia": 22,
    "cesta": 170,
    "uniforme_epi": 55,
    "seguro": 20,
    "inss": 0.20,
    "rat_fap": 0.03,
    "terceiros": 0.058,
    "fgts": 0.08,
    "ferias_terco": 0.1111,
    "decimo_terceiro": 0.0833,
    "rescisao": 0.05,
    "repasse": 0.075,  # repasse contratual obrigatorio CCT Clausula 2a §3º
    "pis": 0.0165,
    "cofins": 0.076,
    "iss": 0.05,
    "margem": 0.15,
}


async def carregar_params(db) -> dict:
    rows = (await db.execute(text("SELECT chave, valor FROM crm_pricing_params"))).all()
    p = dict(_DEFAULTS)
    for chave, valor in rows:
        p[chave] = float(valor)
    return p


def calcular(salario_base, jornada_dias: int, flags: dict, params: dict) -> dict:
    """Calcula custo e preço de 1 colaborador/mês conforme a planilha."""
    base = float(salario_base or 0)
    p = params
    noturno = base * p["noturno"] if flags.get("noturno") else 0.0
    hora_red = base * p["hora_reduzida"] if flags.get("hora_reduzida") else 0.0
    ronda = base * p["ronda"] if flags.get("ronda") else 0.0
    # peric e insalub NÃO acumulam — periculosidade tem prioridade
    if flags.get("periculosidade"):
        risco = base * p["periculosidade"]
    elif flags.get("insalubridade"):
        risco = base * p["insalubridade"]
    else:
        risco = 0.0
    bruto = base + noturno + hora_red + ronda + risco
    enc_pct = sum(p[k] for k in ENCARGO_KEYS)
    encargos = bruto * enc_pct
    vt = max(0.0, p["vt_dia"] * jornada_dias - bruto * p["vt_desconto"])
    vr = p["vr_dia"] * jornada_dias
    beneficios = vt + vr + p["cesta"] + p["uniforme_epi"] + p["seguro"]
    # Repasse contratual obrigatorio 7,5% (CCT Clausula 2a §3º) sobre o custo
    repasse = (bruto + encargos + beneficios) * p["repasse"]
    custo = bruto + encargos + beneficios + repasse
    margem = float(flags["margem"]) if flags.get("margem") is not None else p["margem"]
    tributos = p["pis"] + p["cofins"] + p["iss"]
    divisor = 1 - tributos - margem
    preco = custo / divisor if divisor > 0 else 0.0
    return {
        "salario_base": round(base, 2),
        "adic_noturno": round(noturno, 2),
        "adic_hora_reduzida": round(hora_red, 2),
        "adic_ronda": round(ronda, 2),
        "adic_risco": round(risco, 2),
        "salario_bruto": round(bruto, 2),
        "encargos": round(encargos, 2),
        "encargos_pct": round(enc_pct, 4),
        "vt": round(vt, 2),
        "vr": round(vr, 2),
        "beneficios": round(beneficios, 2),
        "repasse": round(repasse, 2),
        "repasse_pct": round(p["repasse"], 4),
        "custo_total": round(custo, 2),
        "tributos_pct": round(tributos, 4),
        "margem": round(margem, 4),
        "divisor": round(divisor, 4),
        "preco": round(preco, 2),
        "markup_pct": round((preco / custo - 1) if custo else 0, 4),
        "lucro_liquido": round(preco * (1 - tributos) - custo, 2),
    }


async def calcular_funcao(db, row: dict, margem=None) -> dict:
    params = await carregar_params(db)
    flags = {k: row.get(k) for k in ("noturno", "hora_reduzida", "ronda", "periculosidade", "insalubridade")}
    if margem is not None:
        flags["margem"] = margem
    r = calcular(row["salario_base"], int(row["jornada_dias"]), flags, params)
    adic = []
    if flags.get("noturno"):
        adic.append("Noturno")
    if flags.get("hora_reduzida"):
        adic.append("Hora red.")
    if flags.get("ronda") and params["ronda"] > 0:
        adic.append("Ronda")
    if flags.get("periculosidade"):
        adic.append("Peric.30%")
    if flags.get("insalubridade"):
        adic.append("Insal.10%")
    r["funcao"] = row["nome"]
    r["adicionais"] = ", ".join(adic) if adic else "—"
    return r
