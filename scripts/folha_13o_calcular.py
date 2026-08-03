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

ANO = int(sys.argv[sys.argv.index("--ano") + 1]) if "--ano" in sys.argv else date.today().year
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
    linhas, pendencias = [], []
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
