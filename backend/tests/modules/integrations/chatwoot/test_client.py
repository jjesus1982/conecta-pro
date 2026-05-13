"""
Testes unitarios do ChatwootClient (Slice 2).

Usa httpx.MockTransport (nativo httpx) - nao depende de respx ou outras libs.
Cobertura: caminhos felizes + retry + erros permanentes + 204 no content.
"""
from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

from modules.integrations.chatwoot.client import (
    ChatwootClient,
    ChatwootError,
    ChatwootTransientError,
)


def build_client(handler: Callable[[httpx.Request], httpx.Response]) -> ChatwootClient:
    """Constroi ChatwootClient com transport mockado."""
    return ChatwootClient(
        base_url="https://chat.test.local",
        api_token="test-token",
        account_id=1,
        timeout_seconds=1.0,
        max_retries=3,
        retry_backoff_base=0.0,  # zero backoff pra tests rapidos
        transport=httpx.MockTransport(handler),
    )


# ---------------------------------------------------------------- Caminho feliz


@pytest.mark.asyncio
async def test_search_contact_by_phone_retorna_primeiro_resultado() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/contacts/search" in str(request.url)
        assert request.headers["api_access_token"] == "test-token"
        return httpx.Response(
            200,
            json={"payload": [{"id": 42, "name": "Joao", "phone_number": "+5592999990000"}]},
        )

    async with build_client(handler) as client:
        result = await client.search_contact_by_phone("+5592999990000")
        assert result == {"id": 42, "name": "Joao", "phone_number": "+5592999990000"}


@pytest.mark.asyncio
async def test_search_contact_sem_resultado_retorna_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"payload": []})

    async with build_client(handler) as client:
        assert await client.search_contact_by_phone("+5599999990000") is None


@pytest.mark.asyncio
async def test_create_contact_envia_body_correto() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json={"id": 99, "name": "Maria"})

    async with build_client(handler) as client:
        result = await client.create_contact(
            name="Maria",
            phone="+5592999990001",
            email="maria@test.local",
            custom_attrs={"conecta_pro_lead_id": 7},
        )

    assert captured["method"] == "POST"
    assert captured["path"].endswith("/contacts")
    assert captured["body"] == {
        "name": "Maria",
        "phone_number": "+5592999990001",
        "email": "maria@test.local",
        "custom_attributes": {"conecta_pro_lead_id": 7},
    }
    assert result == {"id": 99, "name": "Maria"}


@pytest.mark.asyncio
async def test_send_message_outgoing() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 555})

    async with build_client(handler) as client:
        await client.send_message(conversation_id=10, content="Ola!")

    assert captured["body"]["content"] == "Ola!"
    assert captured["body"]["message_type"] == "outgoing"
    assert captured["body"]["private"] is False


@pytest.mark.asyncio
async def test_resolve_conversation_204_no_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    async with build_client(handler) as client:
        # nao deve lancar e nao deve falhar ao parsear body vazio
        result = await client.resolve_conversation(conversation_id=1)
        assert result is None


# ---------------------------------------------------------------- Retry


@pytest.mark.asyncio
async def test_retry_sucesso_apos_503() -> None:
    """Apos 2 falhas 503 transitorias, a 3a tentativa volta 200."""
    chamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json={"id": 1})

    async with build_client(handler) as client:
        result = await client.update_contact(contact_id=1, name="X")
        assert result == {"id": 1}
        assert chamadas["n"] == 3


@pytest.mark.asyncio
async def test_retry_esgotado_levanta_transient_error() -> None:
    """Todas as tentativas falham com 503 - levanta ChatwootTransientError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with build_client(handler) as client:
        with pytest.raises(ChatwootTransientError):
            await client.update_contact(contact_id=1, name="X")


# ---------------------------------------------------------------- Erros permanentes


@pytest.mark.asyncio
async def test_400_nao_retenta_e_levanta_chatwoot_error() -> None:
    chamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(400, text="Bad Request: phone invalid")

    async with build_client(handler) as client:
        with pytest.raises(ChatwootError) as exc_info:
            await client.create_contact(name="X", phone="invalid")

    assert exc_info.value.status_code == 400
    assert chamadas["n"] == 1  # nao tentou retry em 400


@pytest.mark.asyncio
async def test_404_levanta_chatwoot_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    async with build_client(handler) as client:
        with pytest.raises(ChatwootError) as exc_info:
            await client.update_contact(contact_id=9999, name="X")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------- Headers / autenticacao


@pytest.mark.asyncio
async def test_header_api_access_token_enviado() -> None:
    visto: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        visto["token"] = request.headers.get("api_access_token")
        visto["ct"] = request.headers.get("Content-Type")
        return httpx.Response(200, json={"payload": []})

    async with build_client(handler) as client:
        await client.search_contact_by_phone("+5592999990000")

    assert visto["token"] == "test-token"
    assert visto["ct"] == "application/json"
