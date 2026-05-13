"""Repository: cwi_contact_link."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from ..models import CwiContactLink
from .base import BaseChatwootRepository


class CwiContactLinkRepository(BaseChatwootRepository[CwiContactLink]):
    """Vinculo Chatwoot contact <-> Entidade Conecta PRO."""

    model = CwiContactLink

    async def get_by_chatwoot_contact(
        self,
        chatwoot_contact_id: int,
        chatwoot_account_id: int,
    ) -> Optional[CwiContactLink]:
        stmt = select(CwiContactLink).where(
            CwiContactLink.chatwoot_contact_id == chatwoot_contact_id,
            CwiContactLink.chatwoot_account_id == chatwoot_account_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone_number: str) -> Optional[CwiContactLink]:
        """Busca um vinculo existente pelo telefone (normalizado E.164)."""
        stmt = (
            select(CwiContactLink)
            .where(CwiContactLink.phone_number == phone_number)
            .order_by(CwiContactLink.last_synced_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
