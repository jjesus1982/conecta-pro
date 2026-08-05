"""Atribuição de marketing: leads.source derivado do ?text= do link wa.me."""

import pytest

from modules.integrations.connectors.whatsapp.agent_service import _origem_do_texto


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
