"""Repository: cwi_conversation_link."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from ..models import CwiConversationLink
from .base import BaseChatwootRepository


class CwiConversationLinkRepository(BaseChatwootRepository[CwiConversationLink]):
    """Vinculo Chatwoot conversation <-> Contexto Conecta PRO."""

    model = CwiConversationLink

    async def get_by_chatwoot_conversation(
        self,
        chatwoot_conversation_id: int,
        chatwoot_account_id: int,
    ) -> Optional[CwiConversationLink]:
        stmt = select(CwiConversationLink).where(
            CwiConversationLink.chatwoot_conversation_id == chatwoot_conversation_id,
            CwiConversationLink.chatwoot_account_id == chatwoot_account_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
