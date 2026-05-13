"""
Repository: cwi_outbox.

Implementa o padrao Outbox: fila duravel de mensagens pendentes de envio
ao Chatwoot. Workers Celery (Slice 6) chamam `claim_pending()` pra pegar
um lote, processam, e marcam como `sent` ou `failed`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select, update

from ..models import CwiOutbox
from .base import BaseChatwootRepository


class CwiOutboxRepository(BaseChatwootRepository[CwiOutbox]):
    """Fila outgoing — mensagens pra Chatwoot."""

    model = CwiOutbox

    async def enqueue(
        self,
        *,
        chatwoot_inbox_id: int,
        triggered_by_module: str,
        triggered_by_event: str,
        triggered_by_entity_id: Optional[int] = None,
        chatwoot_conversation_id: Optional[int] = None,
        chatwoot_contact_id: Optional[int] = None,
        content: Optional[str] = None,
        attachments: Optional[dict[str, Any]] = None,
        message_type: str = "outgoing",
        template_id: Optional[str] = None,
    ) -> CwiOutbox:
        """Enfileira uma nova mensagem outgoing."""
        if chatwoot_conversation_id is None and chatwoot_contact_id is None:
            raise ValueError(
                "outbox precisa de chatwoot_conversation_id OU chatwoot_contact_id"
            )
        return await self.create(
            chatwoot_inbox_id=chatwoot_inbox_id,
            chatwoot_conversation_id=chatwoot_conversation_id,
            chatwoot_contact_id=chatwoot_contact_id,
            content=content,
            attachments=attachments,
            message_type=message_type,
            template_id=template_id,
            status="pending",
            attempts=0,
            triggered_by_module=triggered_by_module,
            triggered_by_event=triggered_by_event,
            triggered_by_entity_id=triggered_by_entity_id,
        )

    async def claim_pending(self, limit: int = 10) -> Sequence[CwiOutbox]:
        """
        Pega ate `limit` mensagens pendentes, usando SELECT ... FOR UPDATE SKIP LOCKED
        pra permitir multiplos workers em paralelo sem race conditions.
        """
        stmt = (
            select(CwiOutbox)
            .where(CwiOutbox.status == "pending")
            .order_by(CwiOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def mark_sent(self, id: int, chatwoot_message_id: int) -> int:
        stmt = (
            update(CwiOutbox)
            .where(CwiOutbox.id == id)
            .values(
                status="sent",
                sent_at=datetime.now(timezone.utc),
                chatwoot_message_id=chatwoot_message_id,
                last_error=None,
            )
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def mark_failed(self, id: int, error: str, max_attempts: int = 5) -> int:
        """
        Marca como `failed` permanentemente (se excedeu max_attempts) ou
        deixa em `pending` com last_error preenchido pra retry.
        """
        # Le state atual primeiro pra decidir
        obj = await self.get(id)
        if obj is None:
            return 0
        new_attempts = obj.attempts + 1
        new_status = "failed" if new_attempts >= max_attempts else "pending"
        stmt = (
            update(CwiOutbox)
            .where(CwiOutbox.id == id)
            .values(
                status=new_status,
                attempts=new_attempts,
                last_error=error[:1000],  # cap pra nao explodir
            )
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def cancel(self, id: int, reason: Optional[str] = None) -> int:
        stmt = (
            update(CwiOutbox)
            .where(CwiOutbox.id == id, CwiOutbox.status == "pending")
            .values(status="cancelled", last_error=reason)
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0
