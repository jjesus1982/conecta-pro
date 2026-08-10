"""Cotação do José Luís: o preço sai da tabela CCT e o INTERNO não vaza.

O interlocutor é um número de WhatsApp ANÔNIMO. Margem/custo/encargo/lucro
saindo daqui não é erro de formatação — é vazamento de dado interno para
um prospect (ou um concorrente).
"""

import pytest

from modules.integrations.connectors.whatsapp import agent_service as ag

# Espelha o retorno REAL de pricing_cct.calcular_funcao (lido em 2026-08-09).
RESULTADO_CCT = {
    "funcao": "AGP P1 Noturno",
    "adicionais": "Noturno, Hora red.",
    "salario_base": 1670.0,
    "adic_noturno": 334.0,
    "adic_hora_reduzida": 133.6,
    "adic_ronda": 0.0,
    "adic_risco": 0.0,
    "salario_bruto": 2137.6,
    "encargos": 1309.06,
    "encargos_pct": 0.6124,
    "vt": 64.5,
    "vr": 330.0,
    "beneficios": 639.5,
    "repasse": 306.5,
    "repasse_pct": 0.075,
    "custo_total": 4392.66,
    "tributos_pct": 0.1425,
    "margem": 0.15,
    "divisor": 0.7075,
    "preco": 6208.71,
    "markup_pct": 0.4134,
    "lucro_liquido": 931.31,
}


def test_projecao_calcula_mensal_e_contrato():
    out = ag._cotacao_publica(RESULTADO_CCT, postos=3, meses=12)
    assert out["ok"] is True
    assert out["funcao"] == "AGP P1 Noturno"
    assert out["postos"] == 3
    assert out["meses"] == 12
    assert out["preco_posto_mes"] == 6208.71
    assert out["mensal"] == round(6208.71 * 3, 2)
    assert out["contrato"] == round(6208.71 * 3 * 12, 2)


def test_fixture_cobre_toda_a_lista_negra():
    """Guarda do guarda: se _CAMPOS_INTERNOS_COTACAO ganhar um campo e o fixture não,
    o teste de vazamento passaria sem testar nada."""
    faltando = ag._CAMPOS_INTERNOS_COTACAO - set(RESULTADO_CCT)
    assert not faltando, f"fixture desatualizado, faltam: {sorted(faltando)}"


def test_projecao_nao_vaza_nenhum_campo_interno():
    """A trava que importa. Se este teste cair, é vazamento — não é cosmético."""
    out = ag._cotacao_publica(RESULTADO_CCT, postos=1, meses=12)
    vazados = ag._CAMPOS_INTERNOS_COTACAO & set(out)
    assert not vazados, f"campo interno no retorno público: {sorted(vazados)}"


def test_projecao_nao_vaza_valor_interno_em_nenhum_texto():
    """Nem por chave, nem embutido numa string (ex.: instrucao com o custo dentro).

    Deriva a lista do próprio _CAMPOS_INTERNOS_COTACAO: campo novo na lista negra
    passa a ser cobrado aqui sozinho, sem ninguém lembrar de editar o teste."""
    out = ag._cotacao_publica(RESULTADO_CCT, postos=1, meses=12)
    blob = " ".join(str(v) for v in out.values())
    publicos = {str(out[k]) for k in ("preco_posto_mes", "mensal", "contrato", "postos", "meses")}
    for chave in ag._CAMPOS_INTERNOS_COTACAO:
        val = str(RESULTADO_CCT[chave])
        if val in publicos or len(val) < 4:  # números curtos colidem por acaso
            continue
        assert val not in blob, f"valor interno {chave}={val} apareceu no retorno"


@pytest.mark.parametrize(
    "postos,meses,postos_ok,meses_ok",
    [(0, 0, 1, 1), (-5, -1, 1, 1), (999, 999, 200, 60), ("3", "24", 3, 24), (None, None, 1, 12)],
)
def test_projecao_clampa_entrada_do_llm(postos, meses, postos_ok, meses_ok):
    """postos/meses vêm do LLM (portanto do cliente). Nunca confiar no valor cru."""
    out = ag._cotacao_publica(RESULTADO_CCT, postos=postos, meses=meses)
    assert out["postos"] == postos_ok
    assert out["meses"] == meses_ok
