"""
Repository: BrandVoiceConfig.

Encapsula queries do brand voice por condominio.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BrandVoiceConfig


class BrandVoiceRepository:
    """CRUD de brand voice por condominio."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_condominio(self, condominio_id: uuid.UUID) -> Optional[BrandVoiceConfig]:
        """Retorna o brand voice do condominio (None se ainda nao tem)."""
        stmt = select(BrandVoiceConfig).where(
            BrandVoiceConfig.condominio_id == condominio_id,
            BrandVoiceConfig.is_active.is_(True),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        condominio_id: uuid.UUID,
        personality: list[dict[str, Any]],
        tone_of_voice: list[dict[str, Any]],
        keywords: list[str],
        avoid_list: list[str],
        slogan: Optional[str] = None,
        updated_by_user_id: Optional[uuid.UUID] = None,
    ) -> BrandVoiceConfig:
        obj = BrandVoiceConfig(
            condominio_id=condominio_id,
            personality=personality,
            tone_of_voice=tone_of_voice,
            keywords=keywords,
            avoid_list=avoid_list,
            slogan=slogan,
            updated_by_user_id=updated_by_user_id,
        )
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update(
        self,
        obj: BrandVoiceConfig,
        *,
        updated_by_user_id: Optional[uuid.UUID] = None,
        **fields: Any,
    ) -> BrandVoiceConfig:
        """Aplica updates parciais. Ignora valores None pra permitir PATCH-like."""
        for key, value in fields.items():
            if value is not None and hasattr(obj, key):
                setattr(obj, key, value)
        if updated_by_user_id is not None:
            obj.updated_by_user_id = updated_by_user_id
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
