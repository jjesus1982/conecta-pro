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


def test_prompt_pede_dimensionamento_como_essencial_nao_como_detalhe():
    """Baseline medido em 2026-08-10: `unidades` em 2/7 fichas (29%) e
    `postos_portaria_hoje` em 1/7 (14%). O schema da tool JÁ tinha os campos —
    o agente simplesmente não perguntava, porque o prompt listava porte como
    essencial e na frase seguinte mandava não insistir ('detalhes só se a
    conversa fluir'). Sem porte, `expected_value` é fórmula sem insumo."""
    p = ag.SYSTEM_PROMPT
    assert "PORTE" in p
    assert "unidades" in p and "postos_portaria_hoje" in p
    # a frase que anulava o pedido não pode voltar
    assert "Detalhes (motivação, sistema atual, portões, etc.) só se a conversa fluir" not in p


def test_prompt_protege_contra_interrogatorio():
    """A régua do plano irmão: capturar porte SEM virar questionário. Uma pergunta
    por vez, ancorada no que o cliente ganha — não uma bateria de campos."""
    p = ag.SYSTEM_PROMPT
    assert "UMA pergunta por vez" in p
    assert "questionário" in p  # a proibição continua no texto


def test_dimensionamento_ainda_nao_deriva_valor():
    """Ordem do plano irmão: CAPTURA primeiro, mede 2 semanas (>60%), só então
    deriva expected_value. Derivar agora seria fórmula sem insumo em ~85% dos casos."""
    p = ag.SYSTEM_PROMPT
    for proibido in ("expected_value", "valor esperado do negócio", "estime o valor do contrato"):
        assert proibido not in p


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        # o que o LLM manda de verdade (visto no E2E): texto descritivo, não número
        ({"postos_portaria_hoje": "2 postos de portaria hoje"}, {"postos_portaria_hoje": 2}),
        ({"unidades": "120 apartamentos"}, {"unidades": 120}),
        ({"blocos": "4 blocos"}, {"blocos": 4}),
        # o que já funcionava tem de continuar funcionando
        ({"unidades": 120}, {"unidades": 120}),
        ({"unidades": "120"}, {"unidades": 120}),
        ({"unidades": 120.0}, {"unidades": 120}),
        # sem número nenhum -> não grava lixo
        ({"unidades": "não sei"}, {}),
        ({"unidades": ""}, {}),  # já filtrada antes na prática; descartar é o certo
        # campo não-numérico passa intacto
        ({"segmento": "condominio"}, {"segmento": "condominio"}),
        # bool não vira número (tem_guarita tem tratamento próprio)
        ({"tem_guarita": True}, {"tem_guarita": True}),
    ],
)
def test_coercao_numerica_nao_perde_dado_em_silencio(entrada, esperado):
    """Antes: `int(float('2 postos de portaria'))` levantava e o campo era DELETADO
    sem log. O dado que o cliente deu de graça sumia, e a métrica de captura
    contaria o campo como ausente sem ninguém saber por quê. E
    `postos_portaria_hoje` nem estava na lista — entrava texto cru no JSONB."""
    d = dict(entrada)
    ag._coagir_numericos(d)
    assert d == esperado


def test_coercao_cobre_todo_campo_de_contagem():
    """Campo de contagem novo no schema tem de entrar na coerção, senão vira texto
    no JSONB e quebra a derivação de expected_value lá na frente."""
    for campo in ("unidades", "blocos", "portoes_veiculares", "entradas_pedestres", "postos_portaria_hoje"):
        assert campo in ag._CAMPOS_CONTAGEM


def test_agente_nunca_alcanca_status_humano():
    """proposal/negotiation/won/lost são do humano. A ordem do agente para em
    'qualified' — quem aplica garante o não-rebaixamento no SQL."""
    assert set(ag._ORDEM_STATUS_AGENTE) == {"new", "contacted", "qualified"}
    assert ag._ORDEM_STATUS_AGENTE["new"] < ag._ORDEM_STATUS_AGENTE["contacted"]
    assert ag._ORDEM_STATUS_AGENTE["contacted"] < ag._ORDEM_STATUS_AGENTE["qualified"]
