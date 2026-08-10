"""Intrajornada não gozada no motor de preço (CCT 2026).

Derivado do HOLERITE (`hr_payslip_items.referencia`), não de modelo:
  cód. 244 INTRAJORNADA DIURNO  ref=12:00 -> x1,5   da hora normal (HE 50%)
  cód. 245 INTRAJORNADA NOTURNA ref=13:00 -> x1,799 da hora normal (1,5 x 1,20:
           HE 50% + adicional noturno 20% — bate com cct_cargos)
1h por plantão. Em 15 plantões sobre 180h/mês: 1,5x -> 12,5% do base; 1,883x -> 15,7%.

Só paga quem de fato recebe: 14 de 47 agentes de portaria. Por isso o flag da
função nasce DESLIGADO — ligar é decisão de desenho do posto (tem rendição
para o intervalo ou não), não default.
"""

import pytest

from modules.crm.services import pricing_cct

BASE = 1670.0
JORNADA = 15


def _params(**over):
    p = dict(pricing_cct._DEFAULTS)
    p.update(over)
    return p


def test_sem_flag_nao_cobra_intrajornada():
    """Comportamento de hoje preservado: função sem o flag não muda de preço."""
    p = _params()
    antes = pricing_cct.calcular(BASE, JORNADA, {}, p)
    assert antes["adic_intrajornada"] == 0.0
    # o preço tem de ser idêntico ao de uma função sem o conceito existir
    sem_conceito = pricing_cct.calcular(BASE, JORNADA, {"intrajornada": False}, p)
    assert antes["preco"] == sem_conceito["preco"]


def test_intrajornada_diurna_usa_a_taxa_diurna():
    p = _params()
    r = pricing_cct.calcular(BASE, JORNADA, {"intrajornada": True}, p)
    assert r["adic_intrajornada"] == round(BASE * p["intrajornada"], 2)


def test_intrajornada_noturna_usa_a_taxa_noturna_maior():
    """Noturna é HE 50% + noturno 20% -> tem de ser MAIOR que a diurna."""
    p = _params()
    diurna = pricing_cct.calcular(BASE, JORNADA, {"intrajornada": True}, p)
    noturna = pricing_cct.calcular(BASE, JORNADA, {"intrajornada": True, "noturno": True}, p)
    assert noturna["adic_intrajornada"] == round(BASE * p["intrajornada_noturna"], 2)
    assert noturna["adic_intrajornada"] > diurna["adic_intrajornada"]


def test_intrajornada_entra_no_bruto_e_sobe_o_preco():
    """Não basta aparecer no detalhamento — tem de entrar no custo e no preço."""
    p = _params()
    sem = pricing_cct.calcular(BASE, JORNADA, {}, p)
    com = pricing_cct.calcular(BASE, JORNADA, {"intrajornada": True}, p)
    assert com["salario_bruto"] > sem["salario_bruto"]
    assert com["custo_total"] > sem["custo_total"]
    assert com["preco"] > sem["preco"]


def test_taxas_batem_com_o_holerite():
    """1h/plantão x multiplicador, em 15 plantões sobre 180h/mês."""
    p = _params()
    assert p["intrajornada"] == pytest.approx(1.5 * 15 / 180, abs=1e-6)       # 12,50%
    assert p["intrajornada_noturna"] == pytest.approx(1.883 * 15 / 180, abs=1e-3)  # ~15,7%


@pytest.mark.parametrize("flags,esperado", [
    ({"intrajornada": True}, "Intrajornada"),
    ({"intrajornada": True, "noturno": True}, "Intrajornada not."),
    ({}, "—"),
])
def test_rotulo_dos_adicionais(flags, esperado):
    p = _params()
    r = pricing_cct.calcular(BASE, JORNADA, flags, p)
    rotulo = pricing_cct.rotulo_adicionais(flags, p)
    assert esperado in rotulo
    assert r is not None


def test_intrajornada_e_dado_INTERNO_e_nao_pode_vazar_na_cotacao():
    """O valor do adicional é composição de custo — não sai para número anônimo."""
    from modules.integrations.connectors.whatsapp import agent_service as ag

    assert "adic_intrajornada" in ag._CAMPOS_INTERNOS_COTACAO
