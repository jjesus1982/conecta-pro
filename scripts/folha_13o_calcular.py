"""13º salário REGULAR — cálculo das duas parcelas. READ-ONLY (não grava, não paga).

Por que existe: o 13º regular é o próximo marco real da substituição da Portte —
1ª parcela vence 30/11 e 2ª em 20/12. Até jun/2026 só houve 13º de RESCISÃO, então
o ciclo regular nunca rodou aqui.

Reusa o que já está validado:
  · `calcular_13_proporcional` — batido centavo a centavo contra 4 casos reais da Portte
  · `_avos_ano_civil` — regra CLT/Súmula 461 (mês com >= 15 dias conta 1 avo)
  · `folha_verba_espelho` — média das verbas VARIÁVEIS (art. 457 §1º: HE, noturno,
    intrajornada e DSR integram a base do 13º)

Regras aplicadas:
  1ª parcela (até 30/11) = 50% da base, SEM INSS/IRRF (Lei 4.749/65 art. 2º)
  2ª parcela (até 20/12) = integral − 1ª parcela − INSS − IRRF (descontos só na 2ª)

NUNCA fabrica: se faltar salário ou admissão, o colaborador entra na lista de pendências
com o motivo — não é estimado.

Uso: python3 folha_13o_calcular.py [--ano 2026] [--parcela 1|2]
"""

import os
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text

sys.path.insert(0, "/app")
from modules.people_management.common.utils.clt_calculator import (  # noqa: E402
    _avos_ano_civil,
    calcular_13_proporcional,
    calcular_inss,
    calcular_irrf,
)

import json
import uuid

ANO = int(sys.argv[sys.argv.index("--ano") + 1]) if "--ano" in sys.argv else date.today().year
PERSIST = "--persist" in sys.argv
PDF = "--pdf" in sys.argv
PARCELA = int(sys.argv[sys.argv.index("--parcela") + 1]) if "--parcela" in sys.argv else 1

# Verbas VARIÁVEIS que integram a base do 13º (art. 457 §1º CLT). Férias/faltas/descontos
# ficam de fora: não são "habitualidade remuneratória" somável à base.
COD_VARIAVEIS = ("0020", "0021", "0030", "0031", "0070", "0090")

eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))


def brl(v) -> str:
    return f"R$ {float(v):>10,.2f}"


with eng.connect() as c:
    emps = c.execute(text(
        "SELECT id::text, nome, salario_base, data_admissao FROM employees "
        "WHERE status = 'ativo' AND COALESCE(LOWER(tipo_contrato),'') <> 'pj' ORDER BY nome"
    )).fetchall()

    print(f"# 13º salário {ANO} — {PARCELA}ª parcela (READ-ONLY, nada gravado)\n")
    linhas, pendencias, registros = [], [], []
    tot_int = tot_parc = tot_inss = tot_irrf = Decimal("0")

    for eid, nome, sal, adm in emps:
        if not sal or Decimal(str(sal)) <= 0:
            pendencias.append((nome, "sem salario_base cadastrado"))
            continue
        if not adm:
            pendencias.append((nome, "sem data_admissao — avos não apurável"))
            continue

        base_fixa = Decimal(str(sal))
        # Média das variáveis do ano (do espelho já reconciliado com a Portte).
        media = c.execute(text(
            "SELECT COALESCE(sum(valor),0) / 12 FROM folha_verba_espelho "
            "WHERE employee_id = CAST(:e AS uuid) AND ano = :a AND codigo = ANY(:cods) "
            "AND tipo = 'provento'"
        ), {"e": eid, "a": ANO, "cods": list(COD_VARIAVEIS)}).scalar() or Decimal("0")
        media = Decimal(str(media)).quantize(Decimal("0.01"))
        base_13 = base_fixa + media

        # Avos do ano civil: 31/12 como referência (empregado ativo trabalha o ano todo);
        # admissão no meio do ano reduz os avos — a própria função já trata.
        avos = _avos_ano_civil(date(ANO, 12, 31), adm)
        integral = Decimal(str(calcular_13_proporcional(base_13, avos)))

        primeira = (integral / 2).quantize(Decimal("0.01"))
        if PARCELA == 1:
            valor, inss, irrf = primeira, Decimal("0"), Decimal("0")  # 1ª não tem desconto
        else:
            inss = Decimal(str(calcular_inss(integral)))
            irrf = Decimal(str(calcular_irrf(integral - inss, 0)))
            valor = (integral - primeira - inss - irrf).quantize(Decimal("0.01"))

        linhas.append((nome, avos, base_fixa, media, integral, valor, inss, irrf))
        registros.append({
            "employee_id": eid, "nome": nome, "avos": avos, "base": base_13,
            "integral": integral, "valor": valor, "inss": inss, "irrf": irrf,
            "media_variaveis": media, "base_fixa": base_fixa,
        })
        tot_int += integral
        tot_parc += valor
        tot_inss += inss
        tot_irrf += irrf

    print(f"{'Colaborador':30}{'avos':>5}{'base fixa':>14}{'média var':>12}{'13º integral':>15}{'a pagar':>14}")
    for nome, avos, bf, mv, integ, val, _i, _r in linhas:
        print(f"{nome[:29]:30}{avos:>5}{brl(bf):>14}{brl(mv):>12}{brl(integ):>15}{brl(val):>14}")

    print(f"\n{'TOTAL':30}{'':>5}{'':>14}{'':>12}{brl(tot_int):>15}{brl(tot_parc):>14}")
    if PARCELA == 2:
        print(f"{'  INSS retido':30}{brl(tot_inss):>46}")
        print(f"{'  IRRF retido':30}{brl(tot_irrf):>46}")
    print(f"\nColaboradores: {len(linhas)}")

    if pendencias:
        print(f"\n## PENDÊNCIAS ({len(pendencias)}) — não calculados, nada foi estimado")
        for nome, motivo in pendencias:
            print(f"  - {nome}: {motivo}")

    print("\n> 1ª parcela vence 30/11; 2ª em 20/12. INSS/IRRF incidem SÓ na 2ª, "
          "calculados sobre o 13º INTEGRAL (Lei 4.749/65 art. 2º; IN RFB).")


def _holerite_13(r: dict, parcela: int, ano: int) -> dict:
    """Monta o dict no MESMO formato de calcular_folha_colaborador para reusar o
    gerador de holerite padrão-ouro (montar_holerite_pdf) — sem duplicar layout."""
    desc_parcela = "1ª Parcela (adiantamento)" if parcela == 1 else "2ª Parcela"
    proventos = [{
        "codigo": "0070" if parcela == 1 else "0071",
        "descricao": f"13º Salário — {desc_parcela}",
        "referencia": f"{r['avos']}/12 avos",
        "valor": float(r["integral"] / 2 if parcela == 1 else r["integral"] - r["integral"] / 2),
    }]
    descontos = []
    if parcela == 2:
        if r["inss"] > 0:
            descontos.append({"codigo": "1001", "descricao": "INSS s/ 13º Salário",
                              "referencia": "", "valor": float(r["inss"])})
        if r["irrf"] > 0:
            descontos.append({"codigo": "1002", "descricao": "IRRF s/ 13º Salário",
                              "referencia": "", "valor": float(r["irrf"])})
    tot_prov = sum(p["valor"] for p in proventos)
    tot_desc = sum(d["valor"] for d in descontos)
    return {
        "employee_nome": r["nome"], "cargo": r.get("cargo", "—"), "escala": "—",
        "mes": 11 if parcela == 1 else 12, "ano": ano,
        "proventos": proventos, "descontos": descontos,
        "total_proventos": tot_prov, "total_descontos": tot_desc,
        "liquido": tot_prov - tot_desc,
        "base_inss": float(r["integral"]) if parcela == 2 else 0,
        "base_irrf": float(r["integral"] - r["inss"]) if parcela == 2 else 0,
        "base_fgts": float(r["integral"]), "fgts_empresa": float(r["integral"]) * 0.08,
        "salario_base": float(r["base_fixa"]),
    }


if PERSIST or PDF:
    from sqlalchemy import text as _t
    tipo = f"decimo_terceiro_{PARCELA}a"
    mes_ref = 11 if PARCELA == 1 else 12
    with eng.begin() as c2:
        if PERSIST:
            n = c2.execute(_t(
                "DELETE FROM hr_payslips WHERE reference_year=:a AND payslip_type=:t "
                "AND source_system='conecta'"), {"a": ANO, "t": tipo}).rowcount
            if n:
                print(f"\n(idempotência: {n} linhas '{tipo}' anteriores removidas)")
        alvo = c2.execute(_t(
            "SELECT condominio_id::text, empresa_id::text FROM hr_payslips "
            "WHERE source_system='portte' LIMIT 1")).first()
        cond_id, emp_id = (alvo[0], alvo[1]) if alvo else (None, None)
        gravados = 0
        for seq, r in enumerate(registros, start=1):
            h = _holerite_13(r, PARCELA, ANO)
            if PERSIST and cond_id:
                c2.execute(_t("""
                    INSERT INTO hr_payslips (id, condominio_id, employee_id, payslip_code,
                      payslip_type, status, reference_year, reference_month, reference_period,
                      base_salary, total_earnings, total_deductions, net_salary,
                      earnings, deductions, informative, inss_base, irrf_base, fgts_base,
                      view_count, download_count, source_system, empresa_id, created_at, updated_at)
                    VALUES (:id,:c,:e,:code,:tp,'draft',:a,:m,:comp,:base,:tp_v,:td,:liq,
                      CAST(:ear AS jsonb), CAST(:ded AS jsonb),'[]'::jsonb,:bi,:bir,:bf,
                      0,0,'conecta',:emp, now(), now())"""), {
                    "id": str(uuid.uuid4()), "c": cond_id, "e": r["employee_id"],
                    "code": f"13O-{ANO}-P{PARCELA}-{seq}", "tp": tipo, "a": ANO, "m": mes_ref,
                    "comp": f"{ANO}-{mes_ref:02d}", "base": float(r["base_fixa"]),
                    "tp_v": h["total_proventos"], "td": h["total_descontos"], "liq": h["liquido"],
                    "ear": json.dumps(h["proventos"], ensure_ascii=False),
                    "ded": json.dumps(h["descontos"], ensure_ascii=False),
                    "bi": h["base_inss"], "bir": h["base_irrf"], "bf": h["base_fgts"],
                    "emp": emp_id})
                gravados += 1
        if PERSIST:
            print(f"PERSISTIDAS {gravados} linhas '{tipo}' (source_system='conecta', status=draft)")

    if PDF and registros:
        from modules.people_management.folha.services.holerite_pdf import montar_holerite_pdf
        r0 = registros[0]
        pdf = montar_holerite_pdf(_holerite_13(r0, PARCELA, ANO), {"nome": r0["nome"]})
        destino = f"/app/uploads/13o_recibo_{ANO}_P{PARCELA}_{r0['nome'].split()[0]}.pdf"
        with open(destino, "wb") as fh:
            fh.write(pdf)
        print(f"RECIBO gerado: {destino} ({len(pdf)} bytes) — {r0['nome']}")
