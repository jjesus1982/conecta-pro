"""Atribuição de marketing: leads.source derivado do ?text= do link wa.me."""

import pytest

from modules.integrations.connectors.whatsapp.agent_service import _ORIGEM_MARCADORES, _origem_do_texto


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("Olá! Quero saber sobre Portaria Remota", "landing_portaria_remota"),
        ("Quero AGENTES DE PORTARIA para meu condomínio", "landing_agentes_portaria"),
        ("Tenho interesse em monitoramento 24h", "landing_monitoramento"),
        ("Vim pelo Instagram", "instagram_linktree"),
        ("Bom dia, preciso de um orçamento", "whatsapp"),  # sem marcador
        ("", "whatsapp"),
        (None, "whatsapp"),
        # texto vindo cru da URL (encoding variado) + acento
        ("Ol%C3%A1%21+quero+portaria+rem%C3%B4ta", "landing_portaria_remota"),
    ],
)
def test_origem_do_texto(texto, esperado):
    assert _origem_do_texto(texto) == esperado


def test_origem_e_sempre_um_leadsource_valido():
    """O webhook faz LeadSource(origem) — toda origem possível TEM que existir no enum,
    senão o LeadCreate cai no fallback de INSERT cru e a atribuição se perde."""
    from modules.crm.models.lead import LeadSource

    for _, origem in _ORIGEM_MARCADORES:
        assert LeadSource(origem)
    assert LeadSource(_origem_do_texto("sem marcador")) is LeadSource.WHATSAPP
