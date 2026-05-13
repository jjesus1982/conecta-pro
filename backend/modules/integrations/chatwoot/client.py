"""
Cliente HTTP para a API REST do Chatwoot fazer.ai (PRD Sec. 7.2).

Slice 2 - implementacao funcional com:
- httpx.AsyncClient (timeout configuravel)
- Retry exponencial inline (sem dep externa)
- Logging estruturado
- Custom exceptions

Nao chama Chatwoot real - precisa de instancia provisionada (Slice
futuro, depende do Jordan). Validavel via tests unitarios.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from .config import ChatwootSettings, get_chatwoot_settings

logger = logging.getLogger(__name__)


class ChatwootError(Exception):
    """Erro generico ao falar com a API do Chatwoot."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ChatwootTransientError(ChatwootError):
    """Erro transitorio - vale a pena tentar de novo (5xx, timeout, conn)."""


class ChatwootClient:
    """
    Cliente HTTP para Chatwoot fazer.ai.

    Uso:
        async with ChatwootClient() as client:
            contact = await client.search_contact_by_phone("+5592999990000")

    Ou via DI:
        client = ChatwootClient.from_settings(settings)
        try:
            ...
        finally:
            await client.close()
    """

    # Status considerados transitorios pra retry
    _RETRY_STATUSES = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str,
        api_token: str,
        account_id: int,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        retry_backoff_base: float = 0.5,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.account_id = account_id
        self._max_retries = max_retries
        self._retry_backoff_base = retry_backoff_base
        self._http = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/v1/accounts/{account_id}",
            headers={
                "api_access_token": api_token,
                "Content-Type": "application/json",
            },
            timeout=timeout_seconds,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Optional[ChatwootSettings] = None) -> "ChatwootClient":
        """Constroi a partir do ChatwootSettings (le env vars)."""
        cfg = settings or get_chatwoot_settings()
        return cls(
            base_url=cfg.base_url,
            api_token=cfg.api_token.get_secret_value(),
            account_id=cfg.account_id,
            timeout_seconds=cfg.http_timeout_seconds,
            max_retries=cfg.http_max_retries,
            retry_backoff_base=cfg.http_retry_backoff_base_seconds,
        )

    async def __aenter__(self) -> "ChatwootClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    # ---------------------------------------------------------------- Internal

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Faz uma chamada HTTP com retry exponencial."""
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                response = await self._http.request(
                    method=method,
                    url=path,
                    json=json,
                    params=params,
                )
                if response.status_code in self._RETRY_STATUSES:
                    msg = (
                        f"Chatwoot {method} {path} retornou {response.status_code} "
                        f"(tentativa {attempt + 1}/{self._max_retries})"
                    )
                    logger.warning(msg)
                    last_exc = ChatwootTransientError(msg, response.status_code)
                else:
                    if response.status_code >= 400:
                        raise ChatwootError(
                            f"Chatwoot {method} {path} falhou: {response.status_code} "
                            f"- {response.text[:200]}",
                            response.status_code,
                        )
                    if response.status_code == 204 or not response.content:
                        return None
                    return response.json()
            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
                last_exc = ChatwootTransientError(
                    f"Erro de conexao ao Chatwoot {method} {path}: {exc}"
                )
                logger.warning(
                    "Falha transitoria Chatwoot %s %s (tentativa %d/%d): %s",
                    method,
                    path,
                    attempt + 1,
                    self._max_retries,
                    exc,
                )

            if attempt < self._max_retries - 1:
                backoff = self._retry_backoff_base * (2**attempt)
                await asyncio.sleep(backoff)

        assert last_exc is not None
        raise last_exc

    # ---------------------------------------------------------------- Contatos

    async def create_contact(
        self,
        name: str,
        phone: str,
        email: Optional[str] = None,
        custom_attrs: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "phone_number": phone}
        if email:
            body["email"] = email
        if custom_attrs:
            body["custom_attributes"] = custom_attrs
        return await self._request("POST", "/contacts", json=body)

    async def update_contact(self, contact_id: int, **fields: Any) -> dict[str, Any]:
        return await self._request("PATCH", f"/contacts/{contact_id}", json=fields)

    async def search_contact_by_phone(self, phone: str) -> Optional[dict[str, Any]]:
        result = await self._request(
            "GET", "/contacts/search", params={"q": phone, "include": "phone_number"}
        )
        payload = (result or {}).get("payload") or []
        return payload[0] if payload else None

    # ---------------------------------------------------------------- Conversas

    async def create_conversation(
        self,
        contact_id: int,
        inbox_id: int,
        message: Optional[str] = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "source_id": str(contact_id),
            "inbox_id": inbox_id,
            "contact_id": contact_id,
        }
        if message:
            body["message"] = {"content": message}
        return await self._request("POST", "/conversations", json=body)

    async def assign_conversation(self, conversation_id: int, agent_id: int) -> None:
        await self._request(
            "POST",
            f"/conversations/{conversation_id}/assignments",
            json={"assignee_id": agent_id},
        )

    async def add_label(self, conversation_id: int, label: str) -> None:
        await self._request(
            "POST",
            f"/conversations/{conversation_id}/labels",
            json={"labels": [label]},
        )

    async def remove_label(self, conversation_id: int, label: str) -> None:
        # Chatwoot espera reenviar a lista atual sem o label.
        # Slice 3 vai ler labels atuais antes; aqui versao simples remove tudo.
        await self._request(
            "POST",
            f"/conversations/{conversation_id}/labels",
            json={"labels": []},
        )
        # TODO Slice 3: GET labels atuais, filtrar, reenviar

    async def resolve_conversation(self, conversation_id: int) -> None:
        await self._request(
            "POST",
            f"/conversations/{conversation_id}/toggle_status",
            json={"status": "resolved"},
        )

    # ---------------------------------------------------------------- Mensagens

    async def send_message(
        self,
        conversation_id: int,
        content: str,
        attachments: Optional[list[dict[str, Any]]] = None,
        private: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "content": content,
            "message_type": "outgoing",
            "private": private,
        }
        if attachments:
            body["attachments"] = attachments
        return await self._request(
            "POST",
            f"/conversations/{conversation_id}/messages",
            json=body,
        )

    async def send_template_message(
        self,
        conversation_id: int,
        template_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Cloud API only (Slice >= 6)."""
        raise NotImplementedError("Cloud API templates - Slice >= 6")

    # ---------------------------------------------------------------- Atributos

    async def set_contact_custom_attribute(
        self,
        contact_id: int,
        key: str,
        value: Any,
    ) -> None:
        await self._request(
            "PATCH",
            f"/contacts/{contact_id}",
            json={"custom_attributes": {key: value}},
        )

    async def set_conversation_custom_attribute(
        self,
        conversation_id: int,
        key: str,
        value: Any,
    ) -> None:
        await self._request(
            "POST",
            f"/conversations/{conversation_id}/custom_attributes",
            json={"custom_attributes": {key: value}},
        )
