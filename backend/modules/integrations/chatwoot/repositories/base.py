"""
Repository base generico pros models cwi_*.

Reduz duplicacao de CRUD comum (get, list, create, update, delete)
entre os 7 repositories. Cada repo especifico estende e adiciona
metodos customizados (lookup, claim, etc).
"""
from __future__ import annotations

from typing import Any, Generic, Optional, Sequence, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.base import Base

T = TypeVar("T", bound=Base)


class BaseChatwootRepository(Generic[T]):
    """CRUD generico — subclasses definem `model` e adicionam metodos."""

    model: type[T]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, id: int) -> Optional[T]:
        return await self.db.get(self.model, id)

    async def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        **filters: Any,
    ) -> Sequence[T]:
        stmt = select(self.model)
        for col, value in filters.items():
            stmt = stmt.where(getattr(self.model, col) == value)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create(self, **kwargs: Any) -> T:
        obj = self.model(**kwargs)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update_by_id(self, id: int, **kwargs: Any) -> int:
        """Atualiza por id. Retorna numero de rows afetadas."""
        stmt = update(self.model).where(self.model.id == id).values(**kwargs)
        result = await self.db.execute(stmt)
        return result.rowcount or 0

    async def delete_by_id(self, id: int) -> int:
        stmt = delete(self.model).where(self.model.id == id)
        result = await self.db.execute(stmt)
        return result.rowcount or 0
