"""Repository para DocumentTag."""

import logging

from sqlalchemy import and_, delete, func, insert, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ged.models.document_tag import DocumentTag, TagType, document_tag_association
from modules.ged.schemas.document_tag import (
    DocumentTagCreate,
    DocumentTagFilter,
    DocumentTagUpdate,
)

logger = logging.getLogger(__name__)


class DocumentTagRepository:
    """Repository para operações de DocumentTag."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, data: DocumentTagCreate) -> DocumentTag:
        """Cria uma nova tag."""
        tag = DocumentTag(
            slug=DocumentTag.generate_slug(data.name),
            **data.model_dump(),
        )
        self.session.add(tag)
        await self.session.flush()
        return tag

    async def get_by_id(self, tag_id: str) -> DocumentTag | None:
        """Busca tag por ID."""
        result = await self.session.execute(select(DocumentTag).where(DocumentTag.id == tag_id))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str, condominium_id: str = None) -> DocumentTag | None:
        """Busca tag por slug."""
        query = select(DocumentTag).where(DocumentTag.slug == slug)
        if condominium_id:
            query = query.where(
                or_(
                    DocumentTag.condominium_id == condominium_id,
                    DocumentTag.is_global.is_(True),
                )
            )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str, condominium_id: str = None) -> DocumentTag | None:
        """Busca tag por nome."""
        query = select(DocumentTag).where(DocumentTag.name == name)
        if condominium_id:
            query = query.where(
                or_(
                    DocumentTag.condominium_id == condominium_id,
                    DocumentTag.is_global.is_(True),
                )
            )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update(self, tag_id: str, data: DocumentTagUpdate) -> DocumentTag | None:
        """Atualiza uma tag."""
        tag = await self.get_by_id(tag_id)
        if not tag:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Atualiza slug se nome mudou
        if "name" in update_data:
            update_data["slug"] = DocumentTag.generate_slug(update_data["name"])

        for field, value in update_data.items():
            setattr(tag, field, value)

        await self.session.flush()
        return tag

    async def delete(self, tag_id: str) -> bool:
        """Remove tag."""
        tag = await self.get_by_id(tag_id)
        if not tag or tag.is_system:
            return False

        await self.session.delete(tag)
        await self.session.flush()
        return True

    async def soft_delete(self, tag_id: str) -> bool:
        """Desativa tag (soft delete)."""
        tag = await self.get_by_id(tag_id)
        if not tag or tag.is_system:
            return False

        tag.deactivate()
        await self.session.flush()
        return True

    async def list_with_filters(
        self,
        filters: DocumentTagFilter | None = None,
        skip: int = 0,
        limit: int = 50,
        order_by: str = "name",
        order_desc: bool = False,
    ) -> tuple[list[DocumentTag], int]:
        """Lista tags com filtros e paginação."""
        query = select(DocumentTag)

        if filters:
            if filters.tag_type:
                query = query.where(DocumentTag.tag_type == filters.tag_type)
            if filters.parent_id:
                query = query.where(DocumentTag.parent_id == filters.parent_id)
            if filters.condominium_id:
                query = query.where(
                    or_(
                        DocumentTag.condominium_id == filters.condominium_id,
                        DocumentTag.is_global.is_(True),
                    )
                )
            if filters.is_global is not None:
                query = query.where(DocumentTag.is_global == filters.is_global)
            if filters.is_active is not None:
                query = query.where(DocumentTag.is_active == filters.is_active)
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.where(
                    or_(
                        DocumentTag.name.ilike(search_term),
                        DocumentTag.description.ilike(search_term),
                    )
                )

        # Contagem total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenação
        _valid_order_column_cols = {c.key for c in sa_inspect(DocumentTag).mapper.column_attrs}
        order_column = getattr(DocumentTag, order_by if order_by in _valid_order_column_cols else "name")
        if order_desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        # Paginação
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        tags = result.scalars().all()

        return list(tags), total

    async def get_tree(self, condominium_id: str = None) -> list[DocumentTag]:
        """Retorna todas as tags para montagem de arvore."""
        query = select(DocumentTag).where(DocumentTag.is_active.is_(True))
        if condominium_id:
            query = query.where(
                or_(
                    DocumentTag.condominium_id == condominium_id,
                    DocumentTag.is_global.is_(True),
                )
            )
        result = await self.session.execute(query.order_by(DocumentTag.order, DocumentTag.name))
        return list(result.scalars().all())

    async def get_root_tags(self, condominium_id: str = None) -> list[DocumentTag]:
        """Retorna tags raiz (sem pai)."""
        query = select(DocumentTag).where(
            and_(
                DocumentTag.parent_id.is_(None),
                DocumentTag.is_active.is_(True),
            )
        )
        if condominium_id:
            query = query.where(
                or_(
                    DocumentTag.condominium_id == condominium_id,
                    DocumentTag.is_global.is_(True),
                )
            )

        result = await self.session.execute(query.order_by(DocumentTag.order, DocumentTag.name))
        return list(result.scalars().all())

    async def get_children(self, tag_id: str) -> list[DocumentTag]:
        """Retorna tags filhas."""
        query = (
            select(DocumentTag)
            .where(
                and_(
                    DocumentTag.parent_id == tag_id,
                    DocumentTag.is_active.is_(True),
                )
            )
            .order_by(DocumentTag.order, DocumentTag.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_type(self, tag_type: TagType, condominium_id: str = None) -> list[DocumentTag]:
        """Retorna tags por tipo."""
        query = select(DocumentTag).where(
            and_(
                DocumentTag.tag_type == tag_type,
                DocumentTag.is_active.is_(True),
            )
        )
        if condominium_id:
            query = query.where(
                or_(
                    DocumentTag.condominium_id == condominium_id,
                    DocumentTag.is_global.is_(True),
                )
            )

        result = await self.session.execute(query.order_by(DocumentTag.name))
        return list(result.scalars().all())

    async def assign_to_document(self, document_id: str, tag_id: str, created_by: str) -> bool:
        """Atribui tag a documento."""
        tag = await self.get_by_id(tag_id)
        if not tag:
            return False

        stmt = insert(document_tag_association).values(
            document_id=document_id,
            tag_id=tag_id,
            created_by=created_by,
        )
        await self.session.execute(stmt)
        tag.increment_usage()
        await self.session.flush()
        return True

    async def remove_from_document(self, document_id: str, tag_id: str) -> bool:
        """Remove tag de documento."""
        tag = await self.get_by_id(tag_id)
        if not tag:
            return False

        stmt = delete(document_tag_association).where(
            and_(
                document_tag_association.c.document_id == document_id,
                document_tag_association.c.tag_id == tag_id,
            )
        )
        await self.session.execute(stmt)
        tag.decrement_usage()
        await self.session.flush()
        return True

    async def get_document_tags(self, document_id: str) -> list[DocumentTag]:
        """Retorna tags de um documento."""
        query = (
            select(DocumentTag)
            .join(document_tag_association)
            .where(document_tag_association.c.document_id == document_id)
            .order_by(DocumentTag.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_documents_by_tag(self, tag_id: str, skip: int = 0, limit: int = 50) -> list[str]:
        """Retorna IDs de documentos com a tag."""
        query = (
            select(document_tag_association.c.document_id)
            .where(document_tag_association.c.tag_id == tag_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return [row[0] for row in result.fetchall()]

    async def is_associated(self, tag_id: str, document_id: str) -> bool:
        """Verifica se uma tag está associada a um documento."""
        query = select(document_tag_association).where(
            and_(
                document_tag_association.c.tag_id == tag_id,
                document_tag_association.c.document_id == document_id,
            )
        )
        result = await self.session.execute(query)
        return result.first() is not None

    async def deactivate(self, tag_id: str) -> DocumentTag | None:
        """Desativa tag."""
        tag = await self.get_by_id(tag_id)
        if not tag or tag.is_system:
            return None
        tag.deactivate()
        await self.session.flush()
        return tag

    async def activate(self, tag_id: str) -> DocumentTag | None:
        """Ativa tag."""
        tag = await self.get_by_id(tag_id)
        if not tag:
            return None
        tag.activate()
        await self.session.flush()
        return tag

    async def get_most_used(self, condominium_id: str = None, limit: int = 10) -> list[DocumentTag]:
        """Retorna tags mais usadas."""
        query = select(DocumentTag).where(DocumentTag.is_active.is_(True))
        if condominium_id:
            query = query.where(
                or_(
                    DocumentTag.condominium_id == condominium_id,
                    DocumentTag.is_global.is_(True),
                )
            )
        query = query.order_by(DocumentTag.usage_count.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_recently_used(self, limit: int = 10) -> list[DocumentTag]:
        """Retorna tags usadas recentemente."""
        query = (
            select(DocumentTag)
            .where(
                and_(
                    DocumentTag.is_active.is_(True),
                    DocumentTag.last_used_at.isnot(None),
                )
            )
            .order_by(DocumentTag.last_used_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def search(self, query_str: str, condominium_id: str = None, limit: int = 10) -> list[DocumentTag]:
        """Busca tags por texto."""
        search_term = f"%{query_str}%"
        query = (
            select(DocumentTag)
            .where(
                and_(
                    DocumentTag.is_active.is_(True),
                    or_(
                        DocumentTag.name.ilike(search_term),
                        DocumentTag.description.ilike(search_term),
                    ),
                )
            )
            .limit(limit)
        )
        if condominium_id:
            query = query.where(
                or_(
                    DocumentTag.condominium_id == condominium_id,
                    DocumentTag.is_global.is_(True),
                )
            )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def set_document_tags(
        self, document_id: str, tag_ids: list[str], created_by: str | None = None
    ) -> bool:
        """Deixa o documento com EXATAMENTE estas tags — tira as que sobram, põe as que faltam.

        `document_tag_service.set_document_tags` já chamava este método; ele nunca existiu
        aqui, então a rota respondia com AttributeError. Reuso `assign_to_document` e
        `remove_from_document` em vez de escrever SQL novo: os dois já mantêm o
        `usage_count` da tag em dia, e duplicar essa contagem era como ela ia divergir.
        """
        atuais = {t.id for t in await self.get_document_tags(document_id)}
        alvo = set(tag_ids)
        for tag_id in atuais - alvo:
            await self.remove_from_document(document_id, tag_id)
        for tag_id in alvo - atuais:
            await self.assign_to_document(document_id, tag_id, created_by)
        return True

    async def merge_tags(self, source_tag_id: str, target_tag_id: str) -> int:
        """Move os documentos da tag ORIGEM para a tag DESTINO. Devolve quantos moveu.

        Quem já tinha as duas não vira linha duplicada — a associação tem chave primária
        (document_id, tag_id), e um INSERT cego estouraria IntegrityError na primeira
        sobreposição, justamente o caso mais provável numa mesclagem.
        """
        movidos = 0
        for document_id in await self.get_documents_by_tag(source_tag_id, 0, 10_000):
            if not await self.is_associated(target_tag_id, document_id):
                await self.assign_to_document(document_id, target_tag_id, None)
                movidos += 1
            await self.remove_from_document(document_id, source_tag_id)
        return movidos

    async def get_stats(self, condominium_id: str = None) -> dict:
        """Retorna estatísticas de tags."""
        query = select(DocumentTag)
        if condominium_id:
            query = query.where(
                or_(
                    DocumentTag.condominium_id == condominium_id,
                    DocumentTag.is_global.is_(True),
                )
            )

        result = await self.session.execute(query)
        tags = result.scalars().all()

        stats = {
            "total_tags": len(tags),
            "active_tags": 0,
            "by_type": {},
            "most_used": [],
            "recently_used": [],
        }

        for tag in tags:
            if tag.is_active:
                stats["active_tags"] += 1

            tag_type = tag.tag_type.value
            stats["by_type"][tag_type] = stats["by_type"].get(tag_type, 0) + 1

        # Top 5 mais usadas
        sorted_tags = sorted(tags, key=lambda t: t.usage_count, reverse=True)[:5]
        stats["most_used"] = [{"id": t.id, "name": t.name, "count": t.usage_count} for t in sorted_tags]

        return stats
