#!/usr/bin/env python3
"""Gate: os parâmetros de preço batem com o que a FOLHA realmente paga?

Motivo de existir: em 2026-08 descobriu-se que `ronda` (10%), `noturno` (20%) e
`hora_reduzida` (8%) estavam errados havia meses, e ninguém viu porque dois dos
erros se compensavam. O José Luís cota em produção com esses números — parâmetro
errado vira contrato abaixo do custo, e contrato assinado não se desfaz.

ORÁCULO: `hr_payslip_items` (o holerite), coluna `referencia`:
  1   HORAS NORMAIS       ref=180:00 -> jornada mensal, define a hora
  246 ADICIONAL NOTURNO   ref=HH:MM  -> multiplicador tem de ser 0,20 (CCT)
  247 HORA NOT REDUZIDA   ref=HH:MM  -> 1h/plantão, x1,799 ou x2,024
  245 INTRAJORNADA NOT.   ref=HH:MM  -> idem
  244 INTRAJORNADA DIURNO ref=HH:MM  -> x1,5 (HE 50%)
  224 ADICIONAL DE RONDA  ref=15,00  -> a referência JÁ É o percentual

Padrão da casa: sem pytest, `python scripts/test_pricing_params_vs_folha.py`, só
asserts. Roda no container:
  docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
    python3 scripts/test_pricing_params_vs_folha.py
"""

import asyncio
import os
import sys

import asyncpg

# 10%: o gate existe para pegar a CLASSE de erro que realmente aconteceu — ronda 10 vs 15
# (-33%), hora_reduzida 8 vs 15,9 (-50%), noturno 20 vs 13,3 (+50%). Apertar para 2% só
# gera alarme com o ruído da folha (rescisão, mês parcial, acerto) e treina todo mundo a
# ignorar o gate — que é pior do que não ter gate.
TOL = 0.10
PLANTOES = 15  # 12x36 cheio: é o que `crm_pricing_funcoes.jornada_dias` assume p/ AGP


def _horas(ref) -> float | None:
    """'112:00' -> 112.0. Referência em percentual ('15,00') devolve None."""
    s = str(ref or "")
    if ":" not in s:
        return None
    h, m = s.split(":")
    try:
        return int(h) + int(m) / 60
    except ValueError:
        return None


async def main() -> int:
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url)
    try:
        params = {r["chave"]: float(r["valor"]) for r in await con.fetch("SELECT chave, valor FROM crm_pricing_params")}
        linhas = await con.fetch(
            """SELECT p.base_salary b,
                 max(CASE WHEN i.codigo='1'   THEN i.referencia END) hn,
                 max(CASE WHEN i.codigo='246' THEN i.referencia END) r_not,
                 max(CASE WHEN i.codigo='246' THEN i.valor      END) v_not,
                 max(CASE WHEN i.codigo='247' THEN i.referencia END) r_red,
                 max(CASE WHEN i.codigo='247' THEN i.valor      END) v_red,
                 max(CASE WHEN i.codigo='245' THEN i.referencia END) r_in,
                 max(CASE WHEN i.codigo='245' THEN i.valor      END) v_in,
                 max(CASE WHEN i.codigo='244' THEN i.referencia END) r_id,
                 max(CASE WHEN i.codigo='244' THEN i.valor      END) v_id,
                 max(CASE WHEN i.codigo='224' THEN i.valor      END) v_ron
               FROM hr_payslips p JOIN hr_payslip_items i ON i.payslip_id = p.id
               WHERE p.base_salary > 0 GROUP BY p.id, p.base_salary"""
        )
    finally:
        await con.close()

    # multiplicador de cada rubrica sobre a hora normal do próprio holerite
    mults: dict[str, list[float]] = {"not": [], "red": [], "intra_not": [], "intra_diu": []}
    ronda_pct: list[float] = []
    for r in linhas:
        hn = _horas(r["hn"])
        base = float(r["b"] or 0)
        if not hn or not base:
            continue
        hora = base / hn
        for chave, rc, vc in (
            ("not", "r_not", "v_not"), ("red", "r_red", "v_red"),
            ("intra_not", "r_in", "v_in"), ("intra_diu", "r_id", "v_id"),
        ):
            h, v = _horas(r[rc]), r[vc]
            if h and v:
                m = float(v) / (h * hora)
                if 0.05 < m < 5:  # descarta rescisão/acerto (outliers de 2 ordens)
                    mults[chave].append(m)
        if r["v_ron"]:
            ronda_pct.append(float(r["v_ron"]) / base)

    def mediana(xs: list[float]) -> float:
        """Mediana, não média: rescisão, mês parcial e acerto puxam a média e
        transformariam ruído de folha em alarme de parâmetro."""
        s = sorted(xs)
        meio = len(s) // 2
        return s[meio] if len(s) % 2 else (s[meio - 1] + s[meio]) / 2

    def media(k: str) -> float:
        assert mults[k], f"sem amostra de folha para '{k}' — o gate não pode se declarar verde às cegas"
        return mediana(mults[k])

    # Converte multiplicador de hora -> % do salário base, que é como pricing_cct aplica.
    # noturno: 8h fictícias/plantão. Os demais: 1h/plantão.
    jornada_mes = 180.0
    esperado = {
        "noturno": media("not") * (8 * PLANTOES) / jornada_mes,
        "hora_reduzida": media("red") * PLANTOES / jornada_mes,
        "intrajornada_noturna": media("intra_not") * PLANTOES / jornada_mes,
        "intrajornada": media("intra_diu") * PLANTOES / jornada_mes,
        "ronda": mediana(ronda_pct),  # a referência do holerite já é o percentual
    }

    print(f"{'parametro':22} {'no banco':>10} {'na folha':>10} {'desvio':>9}  amostra")
    falhas = []
    for chave, exp in esperado.items():
        atual = params.get(chave)
        if atual is None:
            falhas.append(f"{chave}: NÃO EXISTE em crm_pricing_params")
            continue
        desvio = abs(atual - exp) / exp if exp else 0
        n = len(ronda_pct) if chave == "ronda" else len(mults[{"noturno": "not", "hora_reduzida": "red",
                                                              "intrajornada_noturna": "intra_not",
                                                              "intrajornada": "intra_diu"}[chave]])
        print(f"  {chave:20} {atual * 100:9.3f}% {exp * 100:9.3f}% {desvio * 100:8.1f}%  n={n}")
        if desvio > TOL:
            falhas.append(f"{chave}: banco {atual * 100:.3f}% x folha {exp * 100:.3f}% (desvio {desvio * 100:.1f}%)")

    print()
    if falhas:
        print("DRIFT — o preco cotado NAO reflete a folha:")
        for f in falhas:
            print("  -", f)
        return 1
    print(f"OK — todos os parametros dentro de {TOL * 100:.0f}% do que a folha paga.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
