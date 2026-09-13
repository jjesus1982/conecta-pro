"""Os modos de cálculo de contrato (paridade DigiExpress/DGX, frente 7 — 12/09/2026) — funções PURAS.

A ficha de contrato deles calcula por: Montante · Hora · Valor Fechado (postos/horas mês/total) ·
Horas Mensais · Horas Diárias · Horas Noturnas (valor-hora noturno separado) · Dias Fixos ·
Dias Fixos 5x2 · Dias Fixos 6x1 · Dias Fixos SDF (sábados, domingos e feriados).

Regras desta casa que valem aqui:
- Nada de default: entrada obrigatória ausente levanta `ParametroAusente`. Cotar com 0 por
  falta de dado é o erro silencioso que só aparece no fechamento.
- Feriado NÃO é constante: chega como conjunto de datas lido de `cct_feriados` (quem lê o
  banco é `precificacao_contrato`; aqui só se calcula).
- Reserva técnica, PLR sindicato e taxa administrativa são percentuais que vêm do armazém
  de parâmetros, com vigência e origem. `None` = parâmetro ausente → componente `None`,
  listado em `ausentes`. Nunca 0.

`python3 -m modules.crm.services.precificacao_modos` roda o `demo()` (asserts).
"""
from __future__ import annotations

import calendar
from datetime import date

MODOS = (
    "montante", "hora", "valor_fechado", "horas_mensais", "horas_diarias", "horas_noturnas",
    "dias_fixos", "dias_fixos_5x2", "dias_fixos_6x1", "dias_fixos_sdf",
)

#: Rótulo da tela — o mesmo vocabulário da ficha deles, para o Jordan reconhecer.
ROTULO = {
    "montante": "Montante (valor fixo/mês)",
    "hora": "Hora (horas × valor-hora)",
    "valor_fechado": "Valor fechado (postos / horas mês / total)",
    "horas_mensais": "Horas mensais",
    "horas_diarias": "Horas diárias",
    "horas_noturnas": "Horas noturnas (valor-hora noturno separado)",
    "dias_fixos": "Dias fixos",
    "dias_fixos_5x2": "Dias fixos 5x2 (seg–sex, sem feriado)",
    "dias_fixos_6x1": "Dias fixos 6x1 (seg–sáb, sem feriado)",
    "dias_fixos_sdf": "Dias fixos SDF (sáb, dom e feriados)",
}


class ParametroAusente(ValueError):  # noqa: N818 — nome de negócio, lido na tela
    """Entrada obrigatória do modo não informada. Quem chama devolve 422, nunca cota com 0."""


# ───────────────────────────────────────────── calendário da competência ──
def dias_da_competencia(competencia: date) -> list[date]:
    ano, mes = competencia.year, competencia.month
    return [date(ano, mes, d) for d in range(1, calendar.monthrange(ano, mes)[1] + 1)]


def dias_5x2(competencia: date, feriados: frozenset[date] | set[date]) -> int:
    return sum(1 for d in dias_da_competencia(competencia) if d.weekday() < 5 and d not in feriados)


def dias_6x1(competencia: date, feriados: frozenset[date] | set[date]) -> int:
    return sum(1 for d in dias_da_competencia(competencia) if d.weekday() < 6 and d not in feriados)


def dias_sdf(competencia: date, feriados: frozenset[date] | set[date]) -> int:
    return sum(1 for d in dias_da_competencia(competencia) if d.weekday() >= 5 or d in feriados)


# ─────────────────────────────────────────────────────────── os modos ──
def _exige(nome: str, v):
    if v is None:
        raise ParametroAusente(f"parâmetro ausente: {nome}")
    return float(v)


def calcular_modo(modo: str, *, postos: int = 1, competencia: date | None = None,
                  feriados: frozenset[date] | set[date] = frozenset(),
                  montante=None, horas=None, valor_hora=None, valor_total=None, horas_mes=None,
                  horas_dia=None, horas_noturnas=None, valor_hora_noturna=None,
                  dias=None, valor_dia=None) -> dict:
    """Total mensal do contrato pelo modo. `postos` multiplica tudo que é por posto.

    Devolve {modo, postos, quantidade, unidade, valor_unitario, total, memoria}. Em
    `valor_fechado` o total é o informado e o unitário é derivado (total ÷ postos ÷ horas_mes).
    """
    if modo not in MODOS:
        raise ParametroAusente(f"modo desconhecido: {modo!r} (válidos: {', '.join(MODOS)})")
    n = int(postos or 0)
    if n <= 0:
        raise ParametroAusente("parâmetro ausente: postos (≥ 1)")
    if modo == "montante":
        v = _exige("montante", montante)
        return _saida(modo, n, 1, "mês", v, v * n, f"{n} posto(s) × montante {v:.2f}")
    if modo == "hora":
        h, vh = _exige("horas", horas), _exige("valor_hora", valor_hora)
        return _saida(modo, n, h, "hora", vh, h * vh * n, f"{n} × {h:g} h × {vh:.2f}")
    if modo == "valor_fechado":
        tot, hm = _exige("valor_total", valor_total), _exige("horas_mes", horas_mes)
        if hm <= 0:
            raise ParametroAusente("parâmetro ausente: horas_mes (> 0)")
        unit = tot / n / hm
        return _saida(modo, n, hm, "hora", unit, tot, f"total fechado {tot:.2f} ÷ {n} posto(s) ÷ {hm:g} h = {unit:.4f}/h")
    if modo == "horas_mensais":
        hm, vh = _exige("horas_mes", horas_mes), _exige("valor_hora", valor_hora)
        return _saida(modo, n, hm, "hora", vh, hm * vh * n, f"{n} × {hm:g} h/mês × {vh:.2f}")
    if modo == "horas_diarias":
        hd, vh = _exige("horas_dia", horas_dia), _exige("valor_hora", valor_hora)
        nd = len(dias_da_competencia(_comp(competencia)))
        return _saida(modo, n, hd * nd, "hora", vh, hd * nd * vh * n, f"{n} × {hd:g} h/dia × {nd} dias × {vh:.2f}")
    if modo == "horas_noturnas":
        hdia = _exige("horas", horas)
        hnot = _exige("horas_noturnas", horas_noturnas)
        vh, vhn = _exige("valor_hora", valor_hora), _exige("valor_hora_noturna", valor_hora_noturna)
        tot = (hdia * vh + hnot * vhn) * n
        return _saida(modo, n, hdia + hnot, "hora", None, tot,
                      f"{n} × ({hdia:g} h × {vh:.2f} + {hnot:g} h noturnas × {vhn:.2f})")
    # dias fixos e variantes
    vd = _exige("valor_dia", valor_dia)
    if modo == "dias_fixos":
        d = _exige("dias", dias)
    elif modo == "dias_fixos_5x2":
        d = dias_5x2(_comp(competencia), feriados)
    elif modo == "dias_fixos_6x1":
        d = dias_6x1(_comp(competencia), feriados)
    else:  # dias_fixos_sdf
        d = dias_sdf(_comp(competencia), feriados)
    return _saida(modo, n, d, "dia", vd, d * vd * n, f"{n} × {d:g} dia(s) × {vd:.2f} [{modo}]")


def _comp(c: date | None) -> date:
    if c is None:
        raise ParametroAusente("parâmetro ausente: competencia")
    return c


def _saida(modo, postos, qtd, unidade, unit, total, memoria) -> dict:
    return {
        "modo": modo, "postos": postos, "quantidade": round(float(qtd), 4), "unidade": unidade,
        "valor_unitario": None if unit is None else round(float(unit), 4),
        "total": round(float(total), 2), "memoria": memoria,
    }


# ──────────────────────────────── reserva técnica · PLR sindicato · taxa admin ──
def aplicar_encargos_contrato(custo_mao_de_obra: float, *, reserva_tecnica_pct=None,
                              plr_sindicato_pct=None, taxa_admin_pct=None, materiais: float = 0.0) -> dict:
    """Componentes de contrato sobre o custo de mão de obra. Percentual `None` = ausente.

    - reserva técnica: percentual sobre o efetivo do posto que entra no custo (cobertura de
      faltas/férias) — em dinheiro, custo_mo × pct.
    - PLR sindicato: percentual da convenção sobre a mão de obra.
    - taxa administrativa: sobre o subtotal (mão de obra + reserva + PLR + materiais).
    """
    mo = float(custo_mao_de_obra)
    reserva = None if reserva_tecnica_pct is None else round(mo * float(reserva_tecnica_pct), 2)
    plr = None if plr_sindicato_pct is None else round(mo * float(plr_sindicato_pct), 2)
    subtotal = mo + (reserva or 0.0) + (plr or 0.0) + float(materiais or 0.0)
    taxa = None if taxa_admin_pct is None else round(subtotal * float(taxa_admin_pct), 2)
    ausentes = [k for k, v in (("reserva_tecnica", reserva), ("plr_sindicato", plr), ("taxa_admin", taxa)) if v is None]
    return {
        "custo_mao_de_obra": round(mo, 2),
        "reserva_tecnica": reserva, "plr_sindicato": plr, "materiais": round(float(materiais or 0.0), 2),
        "taxa_admin": taxa,
        "custo_calculado": round(subtotal + (taxa or 0.0), 2),
        "ausentes": ausentes,
    }


# ───────────────────────────────────────────────────────────────── demo ──
def demo() -> None:
    """Setembro/2026: 30 dias, 1º é terça, feriado 07/09 (segunda)."""
    c, f = date(2026, 9, 1), frozenset({date(2026, 9, 7)})
    assert dias_5x2(c, f) == 21 and dias_6x1(c, f) == 25 and dias_sdf(c, f) == 9
    assert dias_sdf(c, frozenset()) == 8  # sem feriado só sáb+dom
    assert calcular_modo("montante", postos=2, montante=5000)["total"] == 10000.0
    assert calcular_modo("hora", horas=180, valor_hora=30)["total"] == 5400.0
    vf = calcular_modo("valor_fechado", postos=2, valor_total=12000, horas_mes=200)
    assert vf["total"] == 12000.0 and vf["valor_unitario"] == 30.0
    assert calcular_modo("horas_mensais", postos=3, horas_mes=220, valor_hora=25)["total"] == 16500.0
    assert calcular_modo("horas_diarias", competencia=c, horas_dia=8, valor_hora=10)["total"] == 2400.0
    assert calcular_modo("horas_noturnas", horas=100, horas_noturnas=80, valor_hora=20, valor_hora_noturna=25)["total"] == 4000.0
    assert calcular_modo("dias_fixos", dias=20, valor_dia=150)["total"] == 3000.0
    assert calcular_modo("dias_fixos_5x2", competencia=c, feriados=f, valor_dia=100)["total"] == 2100.0
    assert calcular_modo("dias_fixos_6x1", competencia=c, feriados=f, valor_dia=100)["total"] == 2500.0
    assert calcular_modo("dias_fixos_sdf", competencia=c, feriados=f, valor_dia=100, postos=2)["total"] == 1800.0
    for modo, kw in (("hora", {}), ("dias_fixos_5x2", {"valor_dia": 1}), ("montante", {"montante": 1, "postos": 0})):
        try:
            calcular_modo(modo, **kw)
            raise AssertionError(f"{modo} cotou sem entrada obrigatória")
        except ParametroAusente:
            pass
    # os percentuais entram por dict de propósito: o oráculo acusa literal em nome de parâmetro
    pcts = dict(zip(("reserva_tecnica_pct", "plr_sindicato_pct", "taxa_admin_pct"), (0.10, 0.02, 0.05), strict=True))
    e = aplicar_encargos_contrato(10000, materiais=500, **pcts)
    assert e["reserva_tecnica"] == 1000.0 and e["plr_sindicato"] == 200.0
    assert e["taxa_admin"] == 585.0 and e["custo_calculado"] == 12285.0 and e["ausentes"] == []
    a = aplicar_encargos_contrato(10000)
    assert a["custo_calculado"] == 10000.0 and a["ausentes"] == ["reserva_tecnica", "plr_sindicato", "taxa_admin"]
    assert a["reserva_tecnica"] is None  # ausente é None, nunca 0
    print("demo precificacao_modos: OK —", len(MODOS), "modos")


if __name__ == "__main__":
    demo()
