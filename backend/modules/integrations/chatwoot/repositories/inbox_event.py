"""
Repository: cwi_inbox_event.

Implementa o padrao Inbox: webhooks Chatwoot -> CPro sao persistidos
ANTES de processar, garantindo idempotencia (chatwoot_event_id UNIQUE)
e retry (status='failed' -> reprocessar).

Worker Celery (Slice 6) chama `claim_pending()` pra pegar eventos,
processa, e marca `processed` ou `failed`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..models import CwiInboxEvent
from .base import BaseChatwootRepository


class CwiInboxEventRepository(BaseChatwootRepository[CwiInboxEvent]):
    """Buffer de webhooks Chatwoot recebidos."""

    model = CwiInboxEvent

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        """Hash determinístico do payload pra idempotencia quando Chatwoot
        nao fornece um event_id explicito."""
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def record_or_duplicate(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        chatwoot_event_id: Optional[str] = None,
    ) -> tuple[CwiInboxEvent, bool]:
        """
        Persiste o evento. Retorna (evento, is_new).

        Se chatwoot_event_id e fornecido e ja existe, retorna o existente
        com is_new=False (idempotencia).
        """
        event_id = chatwoot_event_id or self._payload_hash(payload)

        # Tenta inserir; se UNIQUE constraint violar, e duplicado
        existing = await self._get_by_chatwoot_event_id(event_id)
        if existing is not None:
            return existing, False

        try:
            obj = await self.create(
                event_type=event_type,
                chatwoot_event_id=event_id,
                payload=payload,
                status="pending",
                attempts=0,
            )
            return obj, True
        except IntegrityError:
            # race condition: outro worker inseriu entre o get e o create
            await self.db.rollback()
            existing = await self._get_by_chatwoot_event_id(event_id)
            assert existing is not None
            return existing, False

    async def _get_by_chatwoot_event_id(
        self, chatwoot_event_id: str
    ) -> Optional[CwiInboxEvent]:
        stmt = select(CwiInboxEvent).where(
            CwiInboxEvent.chatwoot_event_id == chatwoot_event_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def claim_pending(self, limit: int = 10) -> Sequence[CwiInboxEvent]:
        """Pega eventos pendentes pra processar, com lock pra concorrencia."""
        stmt = (
            select(CwiInboxEvent)
            .where(CwiInboxEvent.status == "pending")
            .order_by(CwiInboxEvent.received_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def mark_processed(self, id: int) -> int:
        stmt = (
            update(CwiInboxEvent)
            .where(CwiInboxEvent.id == id)
            .values(
                status="processed",
                processed_at=datetime.now(timezone.utc),
                last_error=None,
            )
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def mark_failed(self, id: int, error: str, max_attempts: int = 5) -> int:
        obj = await self.get(id)
        if obj is None:
            return 0
        new_attempts = obj.attempts + 1
        new_status = "failed" if new_attempts >= max_attempts else "pending"
        stmt = (
            update(CwiInboxEvent)
            .where(CwiInboxEvent.id == id)
            .values(
                status=new_status,
                attempts=new_attempts,
                last_error=error[:1000],
            )
        )
        result = await self.db.execute(stmt)
        return result.rowcount or 0
