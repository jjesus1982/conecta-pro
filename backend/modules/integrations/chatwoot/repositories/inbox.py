"""Repository: cwi_inbox."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from ..models import CwiInbox
from .base import BaseChatwootRepository


class CwiInboxRepository(BaseChatwootRepository[CwiInbox]):
    """Espelho de inboxes Chatwoot conhecidos pelo CPro."""

    model = CwiInbox

    async def get_by_chatwoot_id(self, chatwoot_inbox_id: int) -> Optional[CwiInbox]:
        stmt = select(CwiInbox).where(CwiInbox.chatwoot_inbox_id == chatwoot_inbox_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_purpose(self, purpose: str) -> Optional[CwiInbox]:
        """Retorna inbox pra um proposito (atendimento, cobranca, etc)."""
        stmt = select(CwiInbox).where(CwiInbox.purpose == purpose).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
