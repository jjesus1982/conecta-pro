"""Engine de calculo de folha — CCT 2026 SINDECOMPRESTS.

Calculo hibrido: sistema calcula, DP confere e ajusta.
Integra com rubricas_folha, cct_cargos e employees.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ==================== TABELAS FEDERAIS ====================
# ⚠️ VERACIDADE / RISCO JURÍDICO — AGUARDANDO CERTIFICAÇÃO DO DP/CONTÁBIL:
#   - INSS abaixo: faixa 1 = R$1.518 → valores de 2025, NÃO 2026.
#     Oficial 2026 (Portaria Interministerial MPS/MF nº 13): faixa 1 até R$1.621,
#     teto R$8.475,55, deduções 24,32/111,40/198,49.
#   - IRRF abaixo: isenção R$2.259,20 → tabela 2024, SEM a reforma da isenção-R$5.000
#     que entrou em vigor em jan/2026 (redutor progressivo até R$5.000; parcial R$5.000–7.350).
# Estes números NÃO foram trocados aqui de propósito: dependem de certificação humana
# (fonte oficial) antes de virarem base de folha real. Ver TABELAS_FEDERAIS_CERTIFICADAS.
TABELAS_FEDERAIS_CERTIFICADAS = False

FAIXAS_INSS_2026 = [
    (Decimal("1518.00"), Decimal("0.075")),
    (Decimal("2793.88"), Decimal("0.09")),
    (Decimal("4190.83"), Decimal("0.12")),
    (Decimal("8157.41"), Decimal("0.14")),
]

FAIXAS_IRRF_2026 = [
    (Decimal("2259.20"), Decimal("0"), Decimal("0")),
    (Decimal("2826.65"), Decimal("0.075"), Decimal("169.44")),
    (Decimal("3751.05"), Decimal("0.15"), Decimal("381.44")),
    (Decimal("4664.68"), Decimal("0.225"), Decimal("662.77")),
    (Decimal("99999999"), Decimal("0.275"), Decimal("896.00")),
]

# Constantes CCT 2026
VR_DIA = Decimal("22.00")
DESC_VT_PCT = Decimal("0.04")
DESC_VR_PCT = Decimal("0.01")
DESC_ODONTO = Decimal("9.00")
DESC_SEGURO = Decimal("2.00")
TAXA_NEGOCIAL = Decimal("22.00")
MESES_TAXA_NEGOCIAL = {1, 3, 5, 7, 9, 11}
FGTS_PCT = Decimal("0.08")

# Divisores por escala
DIVISOR_ESCALA = {"12x36": 180, "44h": 220}
DIAS_TRAB_ESCALA = {"12x36": 15, "44h": 22}


def _d(valor: Any) -> Decimal:
    """Converte para Decimal seguro."""
    if valor is None:
        return Decimal("0")
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_inss(base: Decimal) -> Decimal:
    """Calcula INSS progressivo 2026."""
    inss = Decimal("0")
    anterior = Decimal("0")
    for teto, aliquota in FAIXAS_INSS_2026:
        if base <= anterior:
            break
        faixa = min(base, teto) - anterior
        if faixa > 0:
            inss += faixa * aliquota
        anterior = teto
    return _d(inss)


def calcular_irrf(base: Decimal, inss: Decimal) -> Decimal:
    """Calcula IRRF progressivo 2026."""
    base_ir = base - inss
    if base_ir <= FAIXAS_IRRF_2026[0][0]:
        return Decimal("0")
    for teto, aliquota, deducao in FAIXAS_IRRF_2026:
        if base_ir <= teto:
            return _d(base_ir * aliquota - deducao)
    return Decimal("0")


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
            "SELECT id, nome, cargo, escala_padrao, salario_base, turno_padrao "
            "FROM employees WHERE CAST(id AS TEXT)=:eid AND status='ativo'"
        ),
        {"eid": employee_id},
    ).first()

    if not emp:
        return {"error": f"Colaborador {employee_id} nao encontrado ou inativo"}

    nome = emp[1]
    cargo = emp[2] or "N/A"
    escala = emp[3] or "12x36"
    salario_base = _d(emp[4])
    turno = emp[5] or "diurno"

    divisor = DIVISOR_ESCALA.get(escala, 220)
    dias_trab = DIAS_TRAB_ESCALA.get(escala, 22)
    hora_normal = _d(salario_base / divisor)

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

    # 0030 — Intrajornada nao concedida (CCT: 1h a 50% por jornada 12x36)
    intrajornada_valor = Decimal("0")
    if escala == "12x36":
        intrajornada_valor = _d(hora_normal * Decimal("1.5") * dias_trab)
        proventos.append(
            {
                "codigo": "0030",
                "descricao": "Intrajornada Nao Concedida",
                "tipo": "provento",
                "referencia": f"{dias_trab} dias",
                "valor": float(intrajornada_valor),
            }
        )

    # 0020 — Adicional noturno (se turno noturno)
    adic_noturno = Decimal("0")
    if turno == "noturno":
        horas_noturnas = Decimal(str(dias_trab * 7))
        fator_reducao = Decimal("60") / Decimal("52.5")
        horas_reduzidas = _d(horas_noturnas * fator_reducao)
        adic_noturno = _d(horas_reduzidas * hora_normal * Decimal("0.20"))
        proventos.append(
            {
                "codigo": "0020",
                "descricao": "Adicional Noturno",
                "tipo": "provento",
                "referencia": f"{horas_reduzidas}h red.",
                "valor": float(adic_noturno),
            }
        )

    # 0060 — Vale Refeicao
    vr_valor = _d(VR_DIA * dias_trab)
    proventos.append(
        {
            "codigo": "0060",
            "descricao": "Vale Refeicao",
            "tipo": "provento",
            "referencia": f"{dias_trab} dias x R$ {VR_DIA}",
            "valor": float(vr_valor),
        }
    )

    total_proventos = sum(Decimal(str(p["valor"])) for p in proventos)

    # ===== DESCONTOS =====

    # 1001 — INSS
    base_inss = salario_base + intrajornada_valor + adic_noturno
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

    # 1002 — IRRF
    irrf = calcular_irrf(base_inss, inss)
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
            "referencia": "fixo",
            "valor": float(DESC_ODONTO),
        }
    )

    # 1021 — Seguro de vida
    descontos.append(
        {
            "codigo": "1021",
            "descricao": "Seguro de Vida",
            "tipo": "desconto",
            "referencia": "fixo",
            "valor": float(DESC_SEGURO),
        }
    )

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

    total_descontos = sum(Decimal(str(d["valor"])) for d in descontos)
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
            "COALESCE(p.irrf_value,0), p.status "
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
            "status_folha": "calculada",
        }
        for r in rows
    ]


def get_dashboard_folha(db: Session, mes: int, ano: int) -> dict[str, Any]:
    """Dashboard gerencial da folha.

    Prioriza dados importados do Domínio Sistemas (hr_payslips).
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
            "fonte": "dominio_sistemas",
            "funcionarios": funcionarios,
        }

    # ── Sistema B: sem dados importados — NUNCA recalcular ───────────────────
    # Regra: sempre ler da tabela hr_payslips (Domínio Sistemas).
    # Se não há payslips importados para o período, retorna zeros.
    logger.info("get_dashboard_folha: sem dados Domínio para %d/%d — retornando zeros (sem engine_interna)", mes, ano)
    return {
        "mes": mes,
        "ano": ano,
        "total_colaboradores": 0,
        "total_proventos": 0.0,
        "total_descontos": 0.0,
        "total_liquido": 0.0,
        "total_fgts": 0.0,
        "total_inss": 0.0,
        "total_irrf": 0.0,
        "por_cargo": {},
        "rubricas_count": rubricas_count,
        "status": "sem_dados_importados",
        "fonte": "sem_dados_importados",
        "funcionarios": [],
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
