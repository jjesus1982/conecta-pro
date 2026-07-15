"""Engine de calculo de folha — CCT 2026 SINDECOMPRESTS.

Calculo hibrido: sistema calcula, DP confere e ajusta.
Integra com rubricas_folha, cct_cargos e employees.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# FONTE ÚNICA de INSS/IRRF (mesma primitiva do payroll_service — motor unificado).
# Ver clt_calculator: INSS soma-e-arredonda-no-fim; IRRF c/ desconto simplificado + redutor.
from modules.people_management.common.utils.clt_calculator import (
    calcular_inss,
    calcular_irrf,
)

logger = logging.getLogger(__name__)

# ==================== TABELAS FEDERAIS ====================
# INSS 2026: OFICIAL — Portaria Interministerial MPS/MF nº 13, vigente 01/01/2026.
#   Mínimo federal R$1.621,00 (a CCT delega o mínimo ao Governo Federal, Cl.2ª §1º).
#   ATENÇÃO: a base salarial da NOSSA categoria é o PISO da CCT (R$1.670), não o mínimo.
#   O mínimo federal só entra aqui para a faixa 1 do INSS.
# IRRF 2026: PENDENTE — a reforma da isenção-R$5.000 entrou em jan/2026 via REDUTOR
#   (isenção total até R$5.000; parcial R$5.000–7.350). Tabela tradicional inalterada.
#   O redutor exato aguarda fonte oficial + certificação (ver IRRF_CERTIFICADA).
INSS_CERTIFICADA = True  # valores oficiais Portaria nº 13/2026
IRRF_CERTIFICADA = False  # implementado oficial (Lei 15.270/2025) — aguarda certificação humana c/ casos-teste

FAIXAS_INSS_2026 = [
    (Decimal("1621.00"), Decimal("0.075")),
    (Decimal("2902.84"), Decimal("0.09")),
    (Decimal("4354.27"), Decimal("0.12")),
    (Decimal("8475.55"), Decimal("0.14")),
]

# IRRF 2026 — tabela progressiva mensal OFICIAL (Lei 15.191/2025; isenção R$2.428,80)
FAIXAS_IRRF_2026 = [
    (Decimal("2428.80"), Decimal("0"), Decimal("0")),
    (Decimal("2826.65"), Decimal("0.075"), Decimal("182.16")),
    (Decimal("3751.05"), Decimal("0.15"), Decimal("394.16")),
    (Decimal("4664.68"), Decimal("0.225"), Decimal("675.49")),
    (Decimal("99999999"), Decimal("0.275"), Decimal("908.73")),
]
DEDUCAO_DEPENDENTE_IRRF = Decimal("189.59")
DESCONTO_SIMPLIFICADO_IRRF = Decimal("607.20")
# Redutor da reforma (Lei 15.270/2025): isenção total até R$5.000, decresce linear até R$0 em R$7.350.
# redutor = 978,62 − 0,133145 × rendimento_bruto_tributável (validado no exemplo oficial R$6.000 → R$179,75).
IRRF_REDUTOR_A = Decimal("978.62")
IRRF_REDUTOR_B = Decimal("0.133145")

# Constantes CCT 2026
VR_DIA = Decimal("22.00")  # vale-refeição por dia trabalhado
VT_DIA = Decimal("10.00")  # vale-transporte por dia trabalhado
DESC_VT_PCT = Decimal("0.04")
DESC_VR_PCT = Decimal("0.01")
DESC_ODONTO = Decimal("9.00")  # valor descontado do funcionário (co-part.; empresa custeia a outra metade)
DESC_SEGURO = Decimal("2.00")
TAXA_NEGOCIAL = Decimal("22.00")
MESES_TAXA_NEGOCIAL = {1, 3, 5, 7, 9, 11}
FGTS_PCT = Decimal("0.08")

# Divisores por escala
DIVISOR_ESCALA = {"12x36": 180, "44h": 220}
DIAS_TRAB_ESCALA = {"12x36": 15, "44h": 22}


def dias_vt_vr(escala: str, mes: int, ano: int) -> tuple[int, int]:
    """Dias que geram VT e VR na competência, conforme a escala (regra da empresa).

    12x36 (AGP/Líder): trabalham dia sim/dia não — indiferente a sáb/dom/feriado; os dias
      são os da ESCALA (o piso já contempla essa modalidade). VT e VR pelos dias de escala.
    44h (comercial — ASG/Artífice/Jardineiro): seg–sex (jornada integral) + sábado (meio período).
      VT = todos os dias trabalhados (seg–sáb). VR = só seg–sex (sábado NÃO recebe VR).
    Retorna (dias_vt, dias_vr).
    """
    import calendar

    if escala == "12x36":
        d = DIAS_TRAB_ESCALA.get("12x36", 15)
        return d, d
    # comercial (44h e demais): conta dias úteis reais do mês
    seg_sex = sab = 0
    _, ndias = calendar.monthrange(ano, mes)
    for dia in range(1, ndias + 1):
        wd = calendar.weekday(ano, mes, dia)  # 0=segunda ... 5=sábado, 6=domingo
        if wd < 5:
            seg_sex += 1
        elif wd == 5:
            sab += 1
    return seg_sex + sab, seg_sex  # VT = seg–sáb; VR = seg–sex


def fator_dsr(escala: str, mes: int, ano: int) -> Decimal:
    """Fator do DSR (repouso semanal remunerado) sobre verbas variáveis.

    O DSR reflexo é obrigatório sobre adicional noturno, hora reduzida, horas
    extras e demais variáveis (Súmula 60/172 TST e CCT SINDECOMPRESTS).

    - 12x36 (AGP/Líder): proporção fixa 1/6 (a cada 6 dias trabalhados,
      1 de repouso), prática consolidada para a escala.
    - 44h (comercial): DSR = variável × (domingos) / (dias úteis seg–sáb).
      Não inclui feriados por ausência de calendário oficial no sistema
      (subestima levemente, mas nunca fabrica dado de feriado).
    """
    import calendar

    if escala == "12x36":
        return Decimal("1") / Decimal("6")
    dias_uteis = domingos = 0
    _, ndias = calendar.monthrange(ano, mes)
    for dia in range(1, ndias + 1):
        wd = calendar.weekday(ano, mes, dia)  # 0=segunda ... 6=domingo
        if wd == 6:
            domingos += 1
        else:
            dias_uteis += 1  # seg–sáb são dias úteis para o DSR do comércio
    if dias_uteis == 0:
        return Decimal("0")
    return Decimal(domingos) / Decimal(dias_uteis)


def _d(valor: Any) -> Decimal:
    """Converte para Decimal seguro."""
    if valor is None:
        return Decimal("0")
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# calcular_inss / calcular_irrf: importados de clt_calculator (FONTE ÚNICA).
# As constantes FAIXAS_*_2026 / DEDUCAO_* / REDUTOR_* acima ficam como referência
# documental da CCT; o cálculo efetivo é o do clt_calculator (idêntico ao payroll_service).


def calcular_folha_colaborador(
    db: Session,
    employee_id: str,
    mes: int,
    ano: int,
) -> dict[str, Any]:
    """Calcula holerite completo de um colaborador."""
    # Buscar dados do colaborador
    emp = db.execute(
        text(
            "SELECT e.id, e.nome, e.cargo, e.escala_padrao, e.salario_base, e.turno_padrao, "
            "COALESCE(e.periculosidade_percentual, 0), "
            "COALESCE(e.insalubridade_percentual, 0), "
            "COALESCE(e.adicional_ronda_percentual, 0), "
            "COALESCE(e.recebe_intrajornada, false) "
            "FROM employees e "
            "WHERE CAST(e.id AS TEXT)=:eid AND e.status='ativo'"
        ),
        {"eid": employee_id},
    ).first()

    if not emp:
        return {"error": f"Colaborador {employee_id} nao encontrado ou inativo"}

    nome = emp[1]
    cargo = emp[2] or "N/A"
    escala = emp[3] or "12x36"
    salario_base_cadastrado = _d(emp[4])
    turno = emp[5] or "diurno"

    # Piso oficial da CCT por cargo (cct_cargos.piso_salarial). A base salarial NUNCA pode
    # ser inferior ao piso da categoria (SINDECOMPRESTS). Se o salario_base cadastrado no
    # employee estiver abaixo do piso, usamos o piso e sinalizamos veracidade (dado a corrigir),
    # em vez de calcular o holerite sobre um valor ilegal silenciosamente.
    piso_cct = Decimal("0")
    try:
        _piso_row = db.execute(
            text(
                "SELECT piso_salarial FROM cct_cargos "
                "WHERE is_active = true AND lower(cargo_nome) = lower(:c) "
                "ORDER BY updated_at DESC NULLS LAST LIMIT 1"
            ),
            {"c": cargo},
        ).first()
        if _piso_row and _piso_row[0] is not None:
            piso_cct = _d(_piso_row[0])
    except Exception:  # noqa: BLE001 — ausência do piso não deve quebrar a folha
        piso_cct = Decimal("0")

    salario_abaixo_do_piso = bool(piso_cct > 0 and salario_base_cadastrado < piso_cct)
    # Base efetiva = MAX(cadastrado, piso). Nunca calcula sobre valor abaixo do piso.
    salario_base = max(salario_base_cadastrado, piso_cct) if piso_cct > 0 else salario_base_cadastrado
    # Adicionais POR FUNCIONÁRIO (verdade da folha real): insalubridade/periculosidade/ronda
    # são individuais (dependem do posto/atividade), NÃO do cargo. Ex.: 2 ASG no mesmo cargo,
    # só quem limpa a lixeira recebe insalubridade. Fonte: folha Domínio/Portte 05/2026.
    peric_pct = _d(emp[6]) / Decimal("100")
    insal_pct = _d(emp[7]) / Decimal("100")
    ronda_pct = _d(emp[8]) / Decimal("100")
    recebe_intrajornada = bool(emp[9])  # por-funcionário; só paga quem de fato recebe (default off)

    divisor = DIVISOR_ESCALA.get(escala, 220)
    dias_trab = DIAS_TRAB_ESCALA.get(escala, 22)
    hora_normal = _d(salario_base / divisor)

    # VT/VR concedidos conforme a escala (VT R$10/dia, VR R$22/dia; comercial não tem VR no sábado)
    _dias_vt, _dias_vr = dias_vt_vr(escala, mes, ano)
    vt_concedido = _d(VT_DIA * _dias_vt)
    vr_concedido = _d(VR_DIA * _dias_vr)

    # Horas REAIS do ponto (batidas) — alimenta noturno/intrajornada/HE. Fallback = estimativa por escala.
    from modules.people_management.ponto.services.horas_service import horas_reais_ponto

    _hp = horas_reais_ponto(db, employee_id, mes, ano)
    tem_ponto = _hp.get("tem_ponto", False)
    fonte_horas = "ponto_real" if tem_ponto else "estimativa"
    dias_reais = _hp.get("dias_trabalhados", 0) if tem_ponto else dias_trab
    horas_trab_reais = _d(str(_hp.get("horas_trabalhadas", 0)))

    proventos: list[dict[str, Any]] = []
    descontos: list[dict[str, Any]] = []

    # ===== PROVENTOS =====

    # 0001 — Salario Base
    proventos.append(
        {
            "codigo": "0001",
            "descricao": "Salario Base",
            "tipo": "provento",
            "referencia": "30 dias",
            "valor": float(salario_base),
        }
    )

    # 0030 — Intrajornada nao concedida (CCT: 1h a 50%). Só para quem REALMENTE recebe
    # (flag por-funcionário recebe_intrajornada). Sem flag → não cita (default off).
    intrajornada_valor = Decimal("0")
    if recebe_intrajornada and escala == "12x36" and dias_reais > 0:
        intrajornada_valor = _d(hora_normal * Decimal("1.5") * Decimal(str(dias_reais)))
        proventos.append(
            {
                "codigo": "0030",
                "descricao": "Intrajornada Nao Concedida",
                "tipo": "provento",
                "referencia": f"{dias_reais} dias ({fonte_horas})",
                "valor": float(intrajornada_valor),
            }
        )

    # 0040 — Horas Extras 50% (horas trabalhadas REAIS acima da jornada contratada mensal)
    horas_extras_valor = Decimal("0")
    if tem_ponto:
        jornada_mensal = Decimal(str(divisor))
        excedente = horas_trab_reais - jornada_mensal
        if excedente > 0:
            horas_extras_valor = _d(excedente * hora_normal * Decimal("1.5"))
            proventos.append(
                {
                    "codigo": "0040",
                    "descricao": "Horas Extras 50%",
                    "tipo": "provento",
                    "referencia": f"{excedente}h acima de {divisor}h (ponto_real)",
                    "valor": float(horas_extras_valor),
                }
            )

    # 0015 — Adicional de Periculosidade (por funcionário; 30% sobre o salário quando devido)
    adic_peric = Decimal("0")
    if peric_pct > 0:
        adic_peric = _d(salario_base * peric_pct)
        proventos.append(
            {
                "codigo": "0015",
                "descricao": "Adicional de Periculosidade",
                "tipo": "provento",
                "referencia": f"{int(peric_pct * 100)}%",
                "valor": float(adic_peric),
            }
        )

    # 0016 — Adicional de Insalubridade (por funcionário; NR-15, quem faz a atividade insalubre)
    adic_insal = Decimal("0")
    if insal_pct > 0:
        adic_insal = _d(salario_base * insal_pct)
        proventos.append(
            {
                "codigo": "0016",
                "descricao": "Adicional de Insalubridade",
                "tipo": "provento",
                "referencia": f"{int(insal_pct * 100)}%",
                "valor": float(adic_insal),
            }
        )

    # 0018 — Adicional de Ronda (CCT Cl.23ª: 15%, por funcionário que faz ronda no perímetro)
    adic_ronda = Decimal("0")
    if ronda_pct > 0:
        adic_ronda = _d(salario_base * ronda_pct)
        proventos.append(
            {
                "codigo": "0018",
                "descricao": "Adicional de Ronda",
                "tipo": "provento",
                "referencia": f"{int(ronda_pct * 100)}% CCT",
                "valor": float(adic_ronda),
            }
        )

    # 0020 — Adicional noturno: SÓ das horas noturnas REAIS do ponto (22h-05h). Sem
    # batidas NÃO se estima (dinheiro — líquido/INSS/FGTS — não pode sair de horas que
    # ninguém bateu; viola "nunca fabricar dado"). Sem ponto → 0 + aviso; o noturno
    # entra quando o ponto do mês for fechado (fluxo de fechamento do espelho).
    horas_not = _d(str(_hp.get("horas_noturnas", 0))) if tem_ponto else Decimal("0")
    noturno_pendente_ponto = (not tem_ponto) and (turno == "noturno")
    adic_noturno = Decimal("0")
    adic_hora_reduzida = Decimal("0")
    if horas_not > 0:
        fator_reducao = Decimal("60") / Decimal("52.5")  # hora noturna reduzida 52min30s
        horas_reduzidas = _d(horas_not * fator_reducao)
        adic_noturno = _d(horas_reduzidas * hora_normal * Decimal("0.20"))
        proventos.append(
            {
                "codigo": "0020",
                "descricao": "Adicional Noturno",
                "tipo": "provento",
                "referencia": f"{horas_not}h noturnas ({fonte_horas})",
                "valor": float(adic_noturno),
            }
        )
        # 0021 — Adicional de Hora Noturna Reduzida: paga, a 100%, as horas FICTÍCIAS
        # geradas pela redução (52'30" por hora noturna). Regra p/ TODOS que fazem noturno.
        horas_ficticias = _d(horas_reduzidas - horas_not)  # = horas_not / 7
        adic_hora_reduzida = _d(horas_ficticias * hora_normal)
        if adic_hora_reduzida > 0:
            proventos.append(
                {
                    "codigo": "0021",
                    "descricao": "Adicional de Hora Noturna Reduzida",
                    "tipo": "provento",
                    "referencia": f"{horas_ficticias}h fict. ({fonte_horas})",
                    "valor": float(adic_hora_reduzida),
                }
            )

    # 0090 — DSR sobre verbas variáveis (repouso semanal remunerado).
    # Reflexo obrigatório (Súmula 60/172 TST + CCT) sobre adicional noturno,
    # hora noturna reduzida, horas extras e intrajornada. Sem esse reflexo a
    # folha subestima a remuneração dos noturnos e gera passivo trabalhista.
    soma_variaveis = adic_noturno + adic_hora_reduzida + horas_extras_valor + intrajornada_valor
    dsr_variaveis = Decimal("0")
    if soma_variaveis > 0:
        dsr_variaveis = _d(soma_variaveis * fator_dsr(escala, mes, ano))
        if dsr_variaveis > 0:
            proventos.append(
                {
                    "codigo": "0090",
                    "descricao": "DSR sobre Verbas Variaveis",
                    "tipo": "provento",
                    "referencia": "reflexo noturno/HE/intrajornada (Sum.60/172 TST)",
                    "valor": float(dsr_variaveis),
                }
            )

    # Vale Refeição / Vale Transporte NÃO entram no holerite: vão no documento próprio
    # "Recibo de VT e VR". Aqui só a folha (proventos salariais + descontos legais/co-part.).

    total_proventos = sum(Decimal(str(p["valor"])) for p in proventos)

    # ===== DESCONTOS =====

    # 1001 — INSS (base inclui adicionais salariais: peric/insal/ronda/intrajornada/noturno)
    base_inss = (
        salario_base
        + adic_peric
        + adic_insal
        + adic_ronda
        + intrajornada_valor
        + horas_extras_valor
        + adic_noturno
        + adic_hora_reduzida
        + dsr_variaveis
    )
    inss = calcular_inss(base_inss)
    descontos.append(
        {
            "codigo": "1001",
            "descricao": "INSS",
            "tipo": "desconto",
            "referencia": f"base R$ {base_inss}",
            "valor": float(inss),
        }
    )

    # 1002 — IRRF (dependentes deduzidos — F4: antes ficavam de fora; motor unificado
    # com clt_calculator: base c/ desconto simplificado + redutor da reforma)
    try:
        _dep = db.execute(
            text("SELECT dependentes FROM employees WHERE CAST(id AS TEXT)=:e"),
            {"e": employee_id},
        ).scalar()
        dependentes = len(_dep) if isinstance(_dep, list) else 0
    except Exception:  # noqa: BLE001
        dependentes = 0
    irrf = calcular_irrf(base_inss - inss, dependentes=dependentes, rendimento_bruto=base_inss)
    if irrf > 0:
        descontos.append(
            {
                "codigo": "1002",
                "descricao": "IRRF",
                "tipo": "desconto",
                "referencia": f"base R$ {_d(base_inss - inss)}",
                "valor": float(irrf),
            }
        )

    # 1010 — Desconto VT (4%)
    desc_vt = _d(salario_base * DESC_VT_PCT)
    descontos.append(
        {
            "codigo": "1010",
            "descricao": "Desconto VT",
            "tipo": "desconto",
            "referencia": "4% salario",
            "valor": float(desc_vt),
        }
    )

    # 1011 — Desconto VR (1%)
    desc_vr = _d(salario_base * DESC_VR_PCT)
    descontos.append(
        {
            "codigo": "1011",
            "descricao": "Desconto VR",
            "tipo": "desconto",
            "referencia": "1% salario",
            "valor": float(desc_vr),
        }
    )

    # 1020 — Odontologico
    descontos.append(
        {
            "codigo": "1020",
            "descricao": "Plano Odontologico",
            "tipo": "desconto",
            "referencia": "co-part. 50%",
            "valor": float(DESC_ODONTO),
        }
    )

    # Seguro de Vida REMOVIDO: valor não vinha de dado real e não consta na folha
    # oficial do Domínio. Só re-incluir quando houver apólice/valor confirmado pelo DP.

    # 1030 — Taxa negocial (bimestral)
    if mes in MESES_TAXA_NEGOCIAL:
        descontos.append(
            {
                "codigo": "1030",
                "descricao": "Taxa Negocial CCT",
                "tipo": "desconto",
                "referencia": "bimestral",
                "valor": float(TAXA_NEGOCIAL),
            }
        )

    # 1040+ — Deduções fixas do funcionário: empréstimo consignado, pensão alimentícia (employee_deductions)
    try:
        ded_rows = db.execute(
            text(
                "SELECT tipo, descricao, valor, percentual, parcela_atual, total_parcelas "
                "FROM employee_deductions WHERE CAST(employee_id AS TEXT)=:e AND ativo=true"
            ),
            {"e": employee_id},
        ).fetchall()
        for tipo_d, desc_d, val_d, pct_d, pa, tp in ded_rows:
            base_ded = salario_base if (tipo_d or "").startswith("pensao") else total_proventos
            valor_ded = _d(base_ded * (_d(pct_d) / Decimal("100"))) if (pct_d and not val_d) else _d(val_d or 0)
            if valor_ded <= 0:
                continue
            nome_d = desc_d or ("Pensão Alimentícia" if "pensao" in (tipo_d or "") else "Empréstimo Consignado")
            ref_d = f"parc. {pa}/{tp}" if pa and tp else (f"{pct_d}%" if pct_d else "fixo")
            descontos.append(
                {
                    "codigo": "1040",
                    "descricao": nome_d,
                    "tipo": "desconto",
                    "referencia": ref_d,
                    "valor": float(valor_ded),
                }
            )
    except Exception:  # noqa: BLE001,S110
        pass

    total_descontos = sum(Decimal(str(d["valor"])) for d in descontos)
    # Líquido NUNCA é negativo: descontos não podem exceder os proventos (o excedente vira
    # saldo devedor do funcionário, NÃO desconto abaixo de zero no holerite). Sem isto, um
    # suspenso/afastado com base cheia − descontos dava líquido negativo (ex.: -R$68,99).
    if total_descontos > total_proventos:
        total_descontos = total_proventos
    liquido = _d(total_proventos - total_descontos)
    fgts = _d(base_inss * FGTS_PCT)

    return {
        "employee_id": employee_id,
        "employee_nome": nome,
        "cargo": cargo,
        "escala": escala,
        "mes": mes,
        "ano": ano,
        "salario_base": float(salario_base),
        "salario_base_cadastrado": float(salario_base_cadastrado),
        "piso_cct": float(piso_cct),
        # Veracidade: quando o salario_base do employee estiver abaixo do piso da CCT,
        # a folha é calculada sobre o PISO (max) e este flag alerta o dado a corrigir.
        "salario_abaixo_do_piso": salario_abaixo_do_piso,
        "aviso_piso_cct": (
            f"salario_base cadastrado (R$ {float(salario_base_cadastrado):.2f}) abaixo do piso CCT "
            f"do cargo '{cargo}' (R$ {float(piso_cct):.2f}); folha calculada sobre o piso"
            if salario_abaixo_do_piso
            else None
        ),
        # Fonte das horas noturnas: ponto real (batidas). Sem ponto = pendente (nunca estimado).
        "fonte_horas_noturnas": "pendente_ponto" if noturno_pendente_ponto else fonte_horas,
        "horas_noturnas": float(horas_not),
        "noturno_pendente_ponto": noturno_pendente_ponto,
        "aviso_noturno": (
            "Adicional noturno NÃO calculado: sem batidas de ponto no período. Feche o "
            "ponto do mês (espelho) para apurar o noturno REAL — nunca estimado."
            if noturno_pendente_ponto
            else None
        ),
        "horas_trabalhadas_ponto": _hp.get("horas_trabalhadas", 0),
        "dias_trabalhados": dias_reais if tem_ponto else dias_trab,
        "vr_dia": float(VR_DIA),
        "vt_dia": float(VT_DIA),
        "dias_vt": _dias_vt,
        "dias_vr": _dias_vr,
        "vt_concedido": float(vt_concedido),
        "vr_concedido": float(vr_concedido),
        "desconto_vt": float(desc_vt),
        "desconto_vr": float(desc_vr),
        "proventos": proventos,
        "descontos": descontos,
        "total_proventos": float(_d(total_proventos)),
        "total_descontos": float(_d(total_descontos)),
        "liquido": float(liquido),
        "base_inss": float(base_inss),
        "base_irrf": float(_d(base_inss - inss)),
        "base_fgts": float(base_inss),
        "fgts_empresa": float(fgts),
    }


def calcular_folha_batch(db: Session, mes: int, ano: int) -> dict[str, Any]:
    """Calcula folha para todos os colaboradores ativos."""
    employees = db.execute(text("SELECT CAST(id AS TEXT) FROM employees WHERE status='ativo' ORDER BY nome")).fetchall()

    holerites = []
    erros = []
    total_prov = Decimal("0")
    total_desc = Decimal("0")
    total_liq = Decimal("0")
    total_fgts = Decimal("0")

    for (eid,) in employees:
        result = calcular_folha_colaborador(db, eid, mes, ano)
        if "error" in result:
            erros.append({"employee_id": eid, "error": result["error"]})
            continue
        holerites.append(result)
        total_prov += Decimal(str(result["total_proventos"]))
        total_desc += Decimal(str(result["total_descontos"]))
        total_liq += Decimal(str(result["liquido"]))
        total_fgts += Decimal(str(result["fgts_empresa"]))

    return {
        "mes": mes,
        "ano": ano,
        "total_colaboradores": len(employees),
        "total_calculados": len(holerites),
        "total_erros": len(erros),
        "total_proventos": float(_d(total_prov)),
        "total_descontos": float(_d(total_desc)),
        "total_liquido": float(_d(total_liq)),
        "total_fgts": float(_d(total_fgts)),
        "erros": erros,
        "holerites": holerites,
    }


def calcular_folha_batch_com_guard(db: Session, mes: int, ano: int) -> dict[str, Any]:
    """Calcula folha batch respeitando Domínio como fonte de verdade.

    Se hr_payslips tem dados importados do Domínio Sistemas para o período,
    agrega esses dados em vez de recalcular pela engine interna.
    Engine interna só é usada quando não há dados importados.
    """
    funcionarios = _dados_dominio(db, mes, ano)
    if funcionarios:
        total_prov = _d(sum(_d(f["total_proventos"]) for f in funcionarios))
        total_desc = _d(sum(_d(f["total_descontos"]) for f in funcionarios))
        total_liq = _d(sum(_d(f["salario_liquido"]) for f in funcionarios))
        total_fgts = _d(sum(_d(f["fgts_value"]) for f in funcionarios))
        logger.info(
            "calcular_folha_batch_com_guard: usando Domínio Sistemas para %d/%d — %d funcionários",
            mes,
            ano,
            len(funcionarios),
        )
        return {
            "mes": mes,
            "ano": ano,
            "total_colaboradores": len(funcionarios),
            "total_calculados": len(funcionarios),
            "total_erros": 0,
            "total_proventos": float(total_prov),
            "total_descontos": float(total_desc),
            "total_liquido": float(total_liq),
            "total_fgts": float(total_fgts),
            "erros": [],
            "holerites": [],
        }
    logger.info(
        "calcular_folha_batch_com_guard: sem dados Domínio para %d/%d — usando engine interna",
        mes,
        ano,
    )
    return calcular_folha_batch(db, mes, ano)


def _dados_dominio(db: Session, mes: int, ano: int) -> list[dict[str, Any]]:
    """Retorna dados reais do Domínio Sistemas via hr_payslips para o mês/ano."""
    rows = db.execute(
        text(
            "SELECT e.id::text, e.nome, COALESCE(e.cargo,'N/A'), "
            "COALESCE(e.salario_base,0), "
            "COALESCE(p.total_earnings,0), COALESCE(p.total_deductions,0), "
            "COALESCE(p.net_salary,0), "
            "COALESCE(p.inss_value,0), COALESCE(p.fgts_value,0), "
            "COALESCE(p.irrf_value,0), p.status, COALESCE(p.source_system,'') "
            "FROM hr_payslips p "
            "JOIN employees e ON e.id = p.employee_id "
            "WHERE p.reference_month = :mes AND p.reference_year = :ano "
            "ORDER BY e.nome"
        ),
        {"mes": mes, "ano": ano},
    ).fetchall()

    return [
        {
            "employee_id": r[0],
            "nome": r[1],
            "cargo": r[2],
            "salario_base": float(_d(r[3])),
            "total_proventos": float(_d(r[4])),
            "total_descontos": float(_d(r[5])),
            "salario_liquido": float(_d(r[6])),
            "inss_value": float(_d(r[7])),
            "fgts_value": float(_d(r[8])),
            "irrf_value": float(_d(r[9])),
            "status": r[10] or "published",
            "source_system": r[11] or "",
            "status_folha": "calculada",
        }
        for r in rows
    ]


def _fonte_predominante(funcionarios: list[dict[str, Any]]) -> str:
    """Fonte real dos holerites a partir do source_system (não rótulo chumbado)."""
    from collections import Counter

    cont = Counter((f.get("source_system") or "").strip().lower() for f in funcionarios if f.get("source_system"))
    if not cont:
        return "importada"
    fonte = cont.most_common(1)[0][0]
    return {
        "portte": "portte_contabil",
        "dominio_sistemas": "dominio_sistemas",
    }.get(fonte, fonte)


def get_dashboard_folha(db: Session, mes: int, ano: int) -> dict[str, Any]:
    """Dashboard gerencial da folha.

    Prioriza dados importados (hr_payslips: Portte/Domínio conforme source_system).
    Recalcula pela engine interna apenas quando não há dados importados.
    """
    rubricas_count = db.execute(text("SELECT COUNT(*) FROM rubricas_folha WHERE ativo=true")).scalar() or 0

    # ── Sistema A: Domínio Sistemas ──────────────────────────────────────────
    funcionarios = _dados_dominio(db, mes, ano)
    if funcionarios:
        total_prov = _d(sum(_d(f["total_proventos"]) for f in funcionarios))
        total_desc = _d(sum(_d(f["total_descontos"]) for f in funcionarios))
        total_liq = _d(sum(_d(f["salario_liquido"]) for f in funcionarios))
        total_inss = _d(sum(_d(f["inss_value"]) for f in funcionarios))
        total_fgts = _d(sum(_d(f["fgts_value"]) for f in funcionarios))
        total_irrf = _d(sum(_d(f["irrf_value"]) for f in funcionarios))

        por_cargo: dict[str, dict[str, Any]] = {}
        for f in funcionarios:
            cargo = f["cargo"]
            if cargo not in por_cargo:
                por_cargo[cargo] = {"qtd": 0, "total_liquido": 0.0, "total_fgts": 0.0}
            por_cargo[cargo]["qtd"] += 1
            por_cargo[cargo]["total_liquido"] = round(por_cargo[cargo]["total_liquido"] + f["salario_liquido"], 2)
            por_cargo[cargo]["total_fgts"] = round(por_cargo[cargo]["total_fgts"] + f["fgts_value"], 2)

        return {
            "mes": mes,
            "ano": ano,
            "total_colaboradores": len(funcionarios),
            "total_proventos": float(total_prov),
            "total_descontos": float(total_desc),
            "total_liquido": float(total_liq),
            "total_fgts": float(total_fgts),
            "total_inss": float(total_inss),
            "total_irrf": float(total_irrf),
            "por_cargo": por_cargo,
            "rubricas_count": rubricas_count,
            "status": "calculated",
            # Fonte DINÂMICA: reflete o source_system real dos holerites (Portte, Domínio, etc.),
            # não um rótulo chumbado. Se misto, informa o predominante.
            "fonte": _fonte_predominante(funcionarios),
            "funcionarios": funcionarios,
        }

    # ── Sistema B: sem dados Domínio — FOLHA PRÓPRIA (motor CCT), a conciliar ─────
    # Jordan (2026-07-05): "já podemos começar a criar a nossa própria folha". Onde não há
    # Domínio, mostra a folha calculada pela CCT (rotulada como própria/a conciliar), em vez de zeros.
    logger.info("get_dashboard_folha: sem Domínio p/ %d/%d — usando FOLHA PRÓPRIA (motor CCT)", mes, ano)
    batch = calcular_folha_batch(db, mes, ano)
    por_cargo: dict[str, dict[str, Any]] = {}
    total_inss = Decimal("0")
    total_irrf = Decimal("0")
    func_list = []
    for h in batch.get("holerites", []):
        cargo = h.get("cargo") or "N/A"
        pc = por_cargo.setdefault(cargo, {"qtd": 0, "total_liquido": 0.0, "total_fgts": 0.0})
        pc["qtd"] += 1
        pc["total_liquido"] = round(pc["total_liquido"] + float(h.get("liquido", 0)), 2)
        pc["total_fgts"] = round(pc["total_fgts"] + float(h.get("fgts_empresa", 0)), 2)
        for d in h.get("descontos", []):
            desc = str(d.get("descricao", "")).upper()
            if "INSS" in desc:
                total_inss += _d(d.get("valor", 0))
            elif "IRRF" in desc or "IR " in desc or desc.startswith("IR"):
                total_irrf += _d(d.get("valor", 0))
        func_list.append({
            "id": h.get("employee_id") or h.get("id"), "nome": h.get("nome"),
            "cargo": cargo, "salario_base": h.get("salario_base"),
            "total_proventos": h.get("total_proventos"), "total_descontos": h.get("total_descontos"),
            "salario_liquido": h.get("liquido"), "fgts_value": h.get("fgts_empresa"),
        })
    return {
        "mes": mes,
        "ano": ano,
        "total_colaboradores": batch.get("total_calculados", 0),
        "total_proventos": batch.get("total_proventos", 0.0),
        "total_descontos": batch.get("total_descontos", 0.0),
        "total_liquido": batch.get("total_liquido", 0.0),
        "total_fgts": batch.get("total_fgts", 0.0),
        "total_inss": float(_d(total_inss)),
        "total_irrf": float(_d(total_irrf)),
        "por_cargo": por_cargo,
        "rubricas_count": rubricas_count,
        "status": "folha_propria_calculada",
        "fonte": "folha_propria_cct_a_conciliar",
        "funcionarios": func_list,
    }


def get_resumo_folha(db: Session, mes: int, ano: int) -> dict[str, Any]:
    """Resumo totalizador da folha."""
    dash = get_dashboard_folha(db, mes, ano)
    custo_total = dash["total_proventos"] + dash["total_fgts"]

    return {
        "mes": mes,
        "ano": ano,
        "total_colaboradores": dash["total_colaboradores"],
        "total_proventos": dash["total_proventos"],
        "total_descontos": dash["total_descontos"],
        "total_liquido": dash["total_liquido"],
        "total_fgts": dash["total_fgts"],
        "total_inss": dash["total_inss"],
        "total_irrf": dash["total_irrf"],
        "custo_total_empresa": custo_total,
        "fonte": dash.get("fonte", "desconhecida"),
        "funcionarios": dash.get("funcionarios", []),
    }


def get_rubricas(db: Session) -> list[dict[str, Any]]:
    """Lista todas as rubricas ativas."""
    rows = db.execute(
        text(
            "SELECT id, codigo, descricao, tipo, natureza, base_calculo, "
            "percentual, valor_fixo, incide_inss, incide_irrf, incide_fgts, ativo "
            "FROM rubricas_folha WHERE ativo=true ORDER BY codigo"
        )
    ).fetchall()

    return [
        {
            "id": r[0],
            "codigo": r[1],
            "descricao": r[2],
            "tipo": r[3],
            "natureza": r[4],
            "base_calculo": r[5],
            "percentual": float(r[6]) if r[6] else None,
            "valor_fixo": float(r[7]) if r[7] else None,
            "incide_inss": r[8],
            "incide_irrf": r[9],
            "incide_fgts": r[10],
            "ativo": r[11],
        }
        for r in rows
    ]
