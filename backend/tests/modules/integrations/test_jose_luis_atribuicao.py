"""Atribuição de campanha no link do wa.me (Task 3+4 do plano irmão).

Estado medido em 2026-08-10: **0 de 20 leads com utm_campaign**. Não é bug do
parser — é que o LINK não emite marcador. Parser sem emissor é parser para dado
que nunca chega, então isto é metade de um contrato de 2 pontas:

  (1) marketing embute `[c:<slug>]` no `?text=` do wa.me   ← PENDÊNCIA DO JORDAN
  (2) José Luís parseia e grava                            ← esta metade

E a subcontagem (Task 4): `metricas_jose_luis` filtrava `source='whatsapp'`
exato, deixando fora todo lead que o próprio agente captou por landing ou
Instagram. Hoje o efeito é ZERO (16 vs 16, nenhum lead tem essas origens) —
é correção latente, que passa a valer no primeiro lead de landing.
"""

import pytest

from modules.integrations.connectors.whatsapp import agent_service as ag


def test_origem_continua_funcionando_como_antes():
    """Compat: os 8 casos do teste antigo passam pelo wrapper sem mudar."""
    assert ag._origem_do_texto("Olá! Quero saber sobre Portaria Remota") == "landing_portaria_remota"
    assert ag._origem_do_texto("Bom dia, preciso de um orçamento") == "whatsapp"
    assert ag._origem_do_texto(None) == "whatsapp"


def test_sem_marcador_nao_inventa_utm():
    """Regra da casa: nunca fabricar dado. Sem `[c:...]` as chaves nem existem —
    não vêm vazias, não vêm 'organic', não vêm nada."""
    a = ag._atribuicao_do_texto("Bom dia, quero um orçamento")
    assert a == {"source": "whatsapp"}
    assert "utm_campaign" not in a


@pytest.mark.parametrize(
    "texto,campanha",
    [
        ("Vim pelo site [c:lote2_portaria]", "lote2_portaria"),
        ("[C:PORTARIA_REMOTA_MANAUS_2026] quero saber mais", "portaria_remota_manaus_2026"),
        ("oi [c:ig-stories-ago]", "ig-stories-ago"),
        # texto cru da URL, como chega do wa.me
        ("Ol%C3%A1%21+quero+portaria+remota+%5Bc%3Alote2%5D", "lote2"),
    ],
)
def test_marcador_de_campanha_vira_utm(texto, campanha):
    a = ag._atribuicao_do_texto(texto)
    assert a["utm_campaign"] == campanha
    assert a["utm_source"] == "whatsapp"
    assert a["utm_medium"] == "link"


def test_marcador_convive_com_a_origem_da_landing():
    a = ag._atribuicao_do_texto("Quero portaria remota [c:lote2]")
    assert a["source"] == "landing_portaria_remota"
    assert a["utm_campaign"] == "lote2"


def test_marcador_malformado_nao_grava_lixo():
    for ruim in ("[c:]", "[c: ]", "[campanha:x]", "[c:" + "x" * 61 + "]"):
        a = ag._atribuicao_do_texto(f"oi {ruim}")
        assert "utm_campaign" not in a, f"aceitou marcador inválido: {ruim!r}"


def test_origens_do_jose_luis_cobre_as_5_fontes():
    """Fonte ÚNICA da métrica. `source='whatsapp'` solto era o bug de subcontagem:
    lead que o agente captou por landing/Instagram ficava fora do número dele."""
    assert "whatsapp" in ag.ORIGENS_JOSE_LUIS
    for _, origem in ag._ORIGEM_MARCADORES:
        assert origem in ag.ORIGENS_JOSE_LUIS
    assert len(ag.ORIGENS_JOSE_LUIS) == len(ag._ORIGEM_MARCADORES) + 1


def test_toda_origem_e_um_leadsource_valido():
    """O webhook faz LeadSource(origem) — origem fora do enum derruba o LeadCreate
    e o lead cai no INSERT de fallback, perdendo a atribuição."""
    from modules.crm.models.lead import LeadSource

    for origem in ag.ORIGENS_JOSE_LUIS:
        assert LeadSource(origem)
