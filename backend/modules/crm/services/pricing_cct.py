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
    # Intrajornada não gozada = 1h/plantão paga como hora extra. Lida do HOLERITE
    # (hr_payslip_items.referencia): cód. 244 diurno x1,5 (HE 50%, bate com
    # cct_cargos.horas_extras_percentual) e cód. 245 noturno x1,883 médio
    # (x1,799 = 1,5 x 1,20, HE 50% + adicional noturno 20%; e um grupo em x2,024
    # que ninguém consegue derivar — ver FOLHA_noturno_escala_2026-08-04.md).
    # Em 15 plantões sobre 180h/mês: 1,5 x 15/180 = 12,5% · 1,883 x 15/180 = 15,7%.
    "intrajornada": 0.125,
    "intrajornada_noturna": 0.156958,
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


#: A empresa que emprega os agentes de portaria. `crm_pricing_params` não tem coluna de
#: empresa — é UMA tabela para as duas — então a comparação abaixo precisa saber de quem
#: estamos falando. Mesmo CNPJ que `precificacao_controller.EMPRESA_MAO_DE_OBRA`.
CNPJ_MAO_DE_OBRA = "66014833000110"


async def _encargo_da_empresa(db) -> tuple[float | None, str | None]:
    """Encargo de folha da empresa que emprega, e o motivo quando não dá para saber.

    UMA consulta assíncrona pela sessão que já está aberta, e a função PURA
    `encargos.encargo_pct` em cima do resultado.

    A primeira versão desta função (27/09, manhã) chamava `encargo_pct_da_empresa`, que
    abre uma conexão psycopg2 SÍNCRONA — de dentro de código async, e duas vezes por
    `carregar_params`. Como `/pricing/funcoes` chama `carregar_params` uma vez por função,
    eram ~20 bloqueios do event loop por requisição, numa rota de cotação. O dado que
    faltava cabia em um SELECT na sessão que já existia.

    `crm_pricing_params` guarda os sete encargos numa tabela SEM coluna de empresa, e a
    soma deles é 0,6124 — o conjunto de Lucro Real, com os 5,8% de terceiros. A empresa que
    emprega os agentes é Simples Anexo IV: 0,5544.

    Devolver None NÃO é default silencioso: o motivo volta junto e vai para a ficha.
    """
    from modules.financial.services.encargos import (  # noqa: PLC0415
        AnexoNaoDeterminadoError,
        encargo_pct,
    )

    r = (
        await db.execute(
            text(
                "SELECT regime_tributario, anexo_simples FROM empresas "
                " WHERE regexp_replace(coalesce(cnpj,''),'[^0-9]','','g') = :c"
            ),
            {"c": CNPJ_MAO_DE_OBRA},
        )
    ).first()
    if not r:
        return None, f"empresa {CNPJ_MAO_DE_OBRA} não está no cadastro"
    try:
        return float(encargo_pct(r[0], r[1])), None
    except AnexoNaoDeterminadoError as e:
        return None, f"encargo da empresa não determinado: {e}"


def _aviso_de_regime(p: dict, real: float | None, motivo: str | None) -> str | None:
    """Diz em voz alta o que nos parâmetros não é desta empresa.

    Síncrona e PURA de propósito: recebe o que já foi lido e não toca no banco.

    O encargo já vem da empresa (acima). O que sobra são os TRIBUTOS: a tabela cobra
    PIS 1,65% + COFINS 7,60% + ISS 5% = 14,25% por fora, e no Simples eles estão dentro de
    um DAS só, cuja alíquota depende do RBT12 — NULO nas duas empresas, e cujas duas guias
    dão respostas incompatíveis (~R$ 208 mil pela de 07/2026, ~R$ 827 mil pela de 08/2026).

    Enquanto isso não fechar, o preço sai ALTO, que é o lado seguro de errar numa cotação —
    e diz que sai. Derrubar a cotação com uma recusa tiraria do José Luís a única
    ferramenta de preço que ele tem no WhatsApp.
    """
    if real is None:
        return f"{motivo}. Encargo e tributos vindos da tabela global (Lucro Real)."
    da_tabela = sum(float(p.get(k, 0) or 0) for k in ENCARGO_KEYS)
    dif = (
        f"O encargo já é o desta empresa ({real:.2%}); a tabela global diria {da_tabela:.2%}. "
        if abs(real - da_tabela) >= 1e-6
        else ""
    )
    return (
        dif + "Os TRIBUTOS ainda vêm da tabela global (PIS+COFINS+ISS por fora, 14,25%): no "
        "Simples eles estão dentro de um DAS só, e a alíquota depende do RBT12, que não "
        "está cadastrado. O preço sai ALTO — confirmar antes de fechar."
    )


async def carregar_params(db) -> dict:
    rows = (await db.execute(text("SELECT chave, valor FROM crm_pricing_params"))).all()
    p = dict(_DEFAULTS)
    for chave, valor in rows:
        p[chave] = float(valor)
    enc, motivo = await _encargo_da_empresa(db)
    p["_encargo_empresa"] = enc
    p["_regime_aviso"] = _aviso_de_regime(p, enc, motivo)
    return p


def calcular(salario_base, jornada_dias: int, flags: dict, params: dict) -> dict:
    """Calcula custo e preço de 1 colaborador/mês conforme a planilha."""
    base = float(salario_base or 0)
    p = params
    noturno = base * p["noturno"] if flags.get("noturno") else 0.0
    hora_red = base * p["hora_reduzida"] if flags.get("hora_reduzida") else 0.0
    ronda = base * p["ronda"] if flags.get("ronda") else 0.0
    # Intrajornada não gozada: só quem NÃO tem rendição para o intervalo. Não é
    # default (14 de 47 agentes de portaria recebem) — vem do flag da função.
    # A taxa noturna é maior porque a HE leva o adicional noturno em cima.
    intra = (
        base * (p["intrajornada_noturna"] if flags.get("noturno") else p["intrajornada"])
        if flags.get("intrajornada")
        else 0.0
    )
    # peric e insalub NÃO acumulam — periculosidade tem prioridade
    if flags.get("periculosidade"):
        risco = base * p["periculosidade"]
    elif flags.get("insalubridade"):
        risco = base * p["insalubridade"]
    else:
        risco = 0.0
    bruto = base + noturno + hora_red + ronda + intra + risco
    # O encargo da EMPRESA quando se sabe qual é; a soma da tabela global como último
    # recurso — e nesse caso `regime_aviso` diz que não se soube.
    enc_pct = p.get("_encargo_empresa")
    if enc_pct is None:
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
        "adic_intrajornada": round(intra, 2),
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
        # None quando os parâmetros batem com o regime de quem paga. Ver `_aviso_de_regime`.
        "regime_aviso": params.get("_regime_aviso"),
    }


FLAGS_FUNCAO = ("noturno", "hora_reduzida", "ronda", "intrajornada", "periculosidade", "insalubridade")


def rotulo_adicionais(flags: dict, params: dict) -> str:
    """Rótulo legível dos adicionais da função. Fora de calcular_funcao p/ ser
    testável sem banco (calcular_funcao precisa de db só para carregar_params)."""
    adic = []
    if flags.get("noturno"):
        adic.append("Noturno")
    if flags.get("hora_reduzida"):
        adic.append("Hora red.")
    if flags.get("ronda") and params["ronda"] > 0:
        adic.append("Ronda")
    if flags.get("intrajornada"):
        adic.append("Intrajornada not." if flags.get("noturno") else "Intrajornada")
    if flags.get("periculosidade"):
        adic.append("Peric.30%")
    if flags.get("insalubridade"):
        adic.append("Insal.10%")
    return ", ".join(adic) if adic else "—"


async def calcular_funcao(db, row: dict, margem=None) -> dict:
    params = await carregar_params(db)
    flags = {k: row.get(k) for k in FLAGS_FUNCAO}
    if margem is not None:
        flags["margem"] = margem
    r = calcular(row["salario_base"], int(row["jornada_dias"]), flags, params)
    r["funcao"] = row["nome"]
    r["adicionais"] = rotulo_adicionais(flags, params)
    return r
