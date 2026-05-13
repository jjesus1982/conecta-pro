"""Repository: cwi_account_config."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from ..models import CwiAccountConfig
from .base import BaseChatwootRepository


class CwiAccountConfigRepository(BaseChatwootRepository[CwiAccountConfig]):
    """CRUD da configuracao da instancia Chatwoot."""

    model = CwiAccountConfig

    async def get_active(self) -> Optional[CwiAccountConfig]:
        """Retorna a config ativa (so deve haver 1 ativa por vez)."""
        stmt = select(CwiAccountConfig).where(CwiAccountConfig.active.is_(True)).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
