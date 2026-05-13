"""
Schemas Pydantic para eventos de webhook do Chatwoot (Sec. 7.1 do PRD T5 v1.0).

Slice 1: apenas o enum de tipos e o schema generico de evento entrante (`CwiInboxEvent`).
Slice 2+: schemas detalhados de cada tipo de evento (message_created, conversation_*, etc).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatwootWebhookEventType(str, Enum):
    """Tipos de evento que o Chatwoot envia via webhook (Sec. 7.1 do PRD)."""

    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_UPDATED = "conversation_updated"
    CONVERSATION_RESOLVED = "conversation_resolved"
    MESSAGE_CREATED = "message_created"
    CONTACT_CREATED = "contact_created"
    CONTACT_UPDATED = "contact_updated"


class CwiInboxEvent(BaseModel):
    """
    Evento entrante (Chatwoot -> Conecta PRO) — entidade que vai ser persistida
    na tabela `cwi_inbox_event` (Sec. 6.1) pra garantir idempotencia + retry.

    O processamento real (extrair tipo, despachar pra handler) acontece num
    worker Celery (Slice 5). Aqui so o contrato.
    """

    model_config = ConfigDict(extra="allow")  # Chatwoot pode adicionar campos novos

    event: ChatwootWebhookEventType = Field(
        ...,
        description="Tipo do evento (Sec. 7.1)",
    )
    chatwoot_event_id: Optional[str] = Field(
        default=None,
        description="ID do evento se Chatwoot fornecer; senao hash do payload",
    )
    received_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp da recepcao no Conecta PRO",
    )
    payload: dict[str, Any] = Field(
        ...,
        description="Payload completo do webhook do Chatwoot (json)",
    )
