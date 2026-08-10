"""A qualificação move o lead no funil (elo que nunca foi ligado).

Medido em produção em 2026-08-10, antes do fix: **27 de 28 leads em
`status='new'` e 26 sem oportunidade nenhuma**. `ensure_opportunity_for_lead`
só era chamada por `lead_controller` (REST) — nunca pelo agente. Como
`pipeline_sync` sai fora quando o status não está no mapa (`new` não está),
NENHUM lead de WhatsApp podia virar oportunidade. Não era bug sutil: era
caminho inexistente. O José Luís já cota preço; sem este elo, a cotação
morre num lead parado.
"""

import pytest

from modules.integrations.connectors.whatsapp import agent_service as ag


@pytest.mark.parametrize(
    "ficha,score,esperado",
    [
        # Anderson real (67, quente) e Juan Torres (59, quente): os dois perdidos.
        ({"temperatura": "quente"}, 67, "qualified"),
        ({"temperatura": "quente"}, 59, "qualified"),
        # score alto sozinho qualifica mesmo sem 'quente' declarado
        ({"temperatura": "morno"}, 60, "qualified"),
        # Débora real (50, morno): fica em contacted, não qualifica
        ({"temperatura": "morno"}, 50, "contacted"),
        ({"temperatura": "frio"}, 10, "contacted"),
        ({}, 0, "contacted"),
        # temperatura suja não pode derrubar a regra
        ({"temperatura": "QUENTE"}, 0, "qualified"),
        ({"temperatura": None}, 61, "qualified"),
    ],
)
def test_status_que_a_ficha_justifica(ficha, score, esperado):
    assert ag._status_por_qualificacao(ficha, score) == esperado


def test_ordem_cobre_todo_status_que_a_regra_pode_devolver():
    """Se a regra devolvesse um status fora da ordem, o UPDATE levantaria KeyError
    no meio do atendimento — e o cliente ficaria sem resposta."""
    for ficha, score in (({"temperatura": "quente"}, 0), ({}, 0), ({}, 100)):
        assert ag._status_por_qualificacao(ficha, score) in ag._ORDEM_STATUS_AGENTE


def test_limiar_e_o_calibrado_nos_leads_reais():
    """60: 'quente' já vale 35 no _score_lead, então >=60 exige ficha consistente.
    Calibrado sobre os leads reais de 2026-08 (Anderson 67, Juan 59, Débora 50)."""
    assert ag._QUALIFICA_SCORE_MIN == 60


def test_agente_nunca_alcanca_status_humano():
    """proposal/negotiation/won/lost são do humano. A ordem do agente para em
    'qualified' — quem aplica garante o não-rebaixamento no SQL."""
    assert set(ag._ORDEM_STATUS_AGENTE) == {"new", "contacted", "qualified"}
    assert ag._ORDEM_STATUS_AGENTE["new"] < ag._ORDEM_STATUS_AGENTE["contacted"]
    assert ag._ORDEM_STATUS_AGENTE["contacted"] < ag._ORDEM_STATUS_AGENTE["qualified"]
