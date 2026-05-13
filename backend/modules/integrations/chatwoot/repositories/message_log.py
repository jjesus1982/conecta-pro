"""Repository: cwi_message_log."""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select

from ..models import CwiMessageLog
from .base import BaseChatwootRepository


class CwiMessageLogRepository(BaseChatwootRepository[CwiMessageLog]):
    """Log de auditoria de mensagens."""

    model = CwiMessageLog

    async def get_by_chatwoot_message(
        self,
        chatwoot_message_id: int,
    ) -> Optional[CwiMessageLog]:
        stmt = select(CwiMessageLog).where(
            CwiMessageLog.chatwoot_message_id == chatwoot_message_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_module(
        self,
        module: str,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[CwiMessageLog]:
        """Lista mensagens disparadas por um modulo (CRM, financeiro, etc)."""
        stmt = (
            select(CwiMessageLog)
            .where(CwiMessageLog.triggered_by_module == module)
            .order_by(CwiMessageLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
