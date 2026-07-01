"""Repository para Document."""

import logging
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ged.models.document import Document, DocumentStatus
from modules.ged.schemas.document import DocumentCreate, DocumentFilter, DocumentUpdate

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Repository para operações de Document."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    def _generate_code(self) -> str:
        """Gera código único para documento."""
        return f"DOC-{str(uuid4())[:8].upper()}"

    async def create(self, data: DocumentCreate) -> Document:
        """Cria um novo documento."""
        document = Document(
            code=self._generate_code(),
            **data.model_dump(),
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def get_by_id(self, document_id: str) -> Document | None:
        """Busca documento por ID."""
        result = await self.session.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Document | None:
        """Busca documento por código."""
        result = await self.session.execute(select(Document).where(Document.code == code))
        return result.scalar_one_or_none()

    async def get_by_checksum(self, checksum: str) -> Document | None:
        """Busca documento por checksum."""
        result = await self.session.execute(select(Document).where(Document.checksum == checksum))
        return result.scalar_one_or_none()

    async def update(self, document_id: str, data: DocumentUpdate) -> Document | None:
        """Atualiza um documento."""
        document = await self.get_by_id(document_id)
        if not document:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(document, field, value)

        await self.session.flush()
        return document

    async def soft_delete(self, document_id: str) -> bool:
        """Remove documento (soft delete)."""
        document = await self.get_by_id(document_id)
        if not document:
            return False
        document.soft_delete()
        await self.session.flush()
        return True

    async def list_with_filters(  # pylint: disable=too-many-branches
        self,
        filters: DocumentFilter | None = None,
        skip: int = 0,
        limit: int = 20,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> tuple[list[Document], int]:
        """Lista documentos com filtros e paginação."""
        query = select(Document).where(Document.status != DocumentStatus.EXCLUIDO)

        if filters:
            if filters.folder_id:
                query = query.where(Document.folder_id == filters.folder_id)
            if filters.document_type:
                query = query.where(Document.document_type == filters.document_type)
            if filters.category:
                query = query.where(Document.category == filters.category)
            if filters.status:
                query = query.where(Document.status == filters.status)
            if filters.confidentiality:
                query = query.where(Document.confidentiality == filters.confidentiality)
            if filters.file_type:
                query = query.where(Document.file_type == filters.file_type)
            if filters.condominium_id:
                query = query.where(Document.condominium_id == filters.condominium_id)
            if filters.contract_id:
                query = query.where(Document.contract_id == filters.contract_id)
            if filters.owner_id:
                query = query.where(Document.owner_id == filters.owner_id)
            if filters.is_public is not None:
                query = query.where(Document.is_public == filters.is_public)
            if filters.is_signed is not None:
                query = query.where(Document.is_signed == filters.is_signed)
            if filters.requires_approval is not None:
                query = query.where(Document.requires_approval == filters.requires_approval)
            if filters.requires_signature is not None:
                query = query.where(Document.requires_signature == filters.requires_signature)
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.where(
                    or_(
                        Document.title.ilike(search_term),
                        Document.description.ilike(search_term),
                        Document.code.ilike(search_term),
                        Document.file_name.ilike(search_term),
                        Document.ocr_text.ilike(search_term),
                    )
                )
            if filters.created_from:
                query = query.where(Document.created_at >= filters.created_from)
            if filters.created_to:
                query = query.where(Document.created_at <= filters.created_to)

        # Contagem total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenação
        _valid_order_column_cols = {c.key for c in sa_inspect(Document).mapper.column_attrs}
        order_column = getattr(Document, order_by if order_by in _valid_order_column_cols else "created_at")
        if order_desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        # Paginação
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        documents = result.scalars().all()

        return list(documents), total

    async def get_by_folder(self, folder_id: str, skip: int = 0, limit: int = 50) -> list[Document]:
        """Retorna documentos de uma pasta."""
        query = (
            select(Document)
            .where(
                and_(
                    Document.folder_id == folder_id,
                    Document.status != DocumentStatus.EXCLUIDO,
                )
            )
            .order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_pending_approval(self, condominium_id: str = None, skip: int = 0, limit: int = 20) -> list[Document]:
        """Retorna documentos pendentes de aprovação."""
        query = select(Document).where(Document.status == DocumentStatus.PENDENTE_APROVACAO)
        if condominium_id:
            query = query.where(Document.condominium_id == condominium_id)

        query = query.order_by(Document.created_at.asc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_pending_signature(self, condominium_id: str = None, skip: int = 0, limit: int = 20) -> list[Document]:
        """Retorna documentos pendentes de assinatura."""
        query = select(Document).where(
            and_(
                Document.requires_signature.is_(True),
                Document.is_signed.is_(False),
                Document.status != DocumentStatus.EXCLUIDO,
            )
        )
        if condominium_id:
            query = query.where(Document.condominium_id == condominium_id)

        query = query.order_by(Document.signature_deadline.asc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_expired(self, condominium_id: str = None, skip: int = 0, limit: int = 20) -> list[Document]:
        """Retorna documentos expirados."""
        query = select(Document).where(Document.status == DocumentStatus.EXPIRADO)
        if condominium_id:
            query = query.where(Document.condominium_id == condominium_id)

        query = query.order_by(Document.valid_until.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_expiring_soon(self, days: int = 30, condominium_id: str = None) -> list[Document]:
        """Retorna documentos prestes a expirar."""
        expiry_date = date.today() + timedelta(days=days)
        query = select(Document).where(
            and_(
                Document.valid_until <= expiry_date,
                Document.valid_until >= date.today(),
                Document.is_perpetual.is_(False),
                Document.status.notin_([DocumentStatus.EXCLUIDO, DocumentStatus.EXPIRADO]),
            )
        )
        if condominium_id:
            query = query.where(Document.condominium_id == condominium_id)

        result = await self.session.execute(query.order_by(Document.valid_until.asc()))
        return list(result.scalars().all())

    async def approve(self, document_id: str, approved_by: str) -> Document | None:
        """Aprova documento."""
        document = await self.get_by_id(document_id)
        if not document:
            return None
        document.approve(approved_by)
        await self.session.flush()
        return document

    async def reject(self, document_id: str, reason: str) -> Document | None:
        """Rejeita documento."""
        document = await self.get_by_id(document_id)
        if not document:
            return None
        document.reject(reason)
        await self.session.flush()
        return document

    async def publish(self, document_id: str) -> Document | None:
        """Publica documento."""
        document = await self.get_by_id(document_id)
        if not document:
            return None
        document.publish()
        await self.session.flush()
        return document

    async def archive(self, document_id: str, archived_by: str) -> Document | None:
        """Arquiva documento."""
        document = await self.get_by_id(document_id)
        if not document:
            return None
        document.archive(archived_by)
        await self.session.flush()
        return document

    async def unarchive(self, document_id: str) -> Document | None:
        """Desarquiva documento."""
        document = await self.get_by_id(document_id)
        if not document:
            return None
        document.unarchive()
        await self.session.flush()
        return document

    async def move(self, document_id: str, folder_id: str) -> Document | None:
        """Move documento para outra pasta."""
        document = await self.get_by_id(document_id)
        if not document:
            return None
        document.folder_id = folder_id
        await self.session.flush()
        return document

    async def increment_view(self, document_id: str) -> None:
        """Incrementa visualizações."""
        document = await self.get_by_id(document_id)
        if document:
            document.increment_view()
            await self.session.flush()

    async def increment_download(self, document_id: str) -> None:
        """Incrementa downloads."""
        document = await self.get_by_id(document_id)
        if document:
            document.increment_download()
            await self.session.flush()

    async def set_ocr_result(self, document_id: str, text: str, confidence: float) -> Document | None:
        """Define resultado do OCR."""
        document = await self.get_by_id(document_id)
        if not document:
            return None
        document.set_ocr_result(text, confidence)
        await self.session.flush()
        return document

    async def mark_as_indexed(self, document_id: str, keywords: list[str] = None) -> Document | None:
        """Marca como indexado."""
        document = await self.get_by_id(document_id)
        if not document:
            return None
        document.mark_as_indexed(keywords)
        await self.session.flush()
        return document

    async def search_fulltext(self, query: str, condominium_id: str = None, limit: int = 20) -> list[Document]:
        """Busca full-text em documentos."""
        search_term = f"%{query}%"
        stmt = select(Document).where(
            and_(
                Document.status != DocumentStatus.EXCLUIDO,
                or_(
                    Document.title.ilike(search_term),
                    Document.description.ilike(search_term),
                    Document.ocr_text.ilike(search_term),
                    Document.file_name.ilike(search_term),
                ),
            )
        )
        if condominium_id:
            stmt = stmt.where(Document.condominium_id == condominium_id)

        result = await self.session.execute(stmt.order_by(Document.view_count.desc()).limit(limit))
        return list(result.scalars().all())

    async def get_stats(self, condominium_id: str = None) -> dict:
        """Retorna estatísticas de documentos."""
        # [Veracidade] ged_documents estava VAZIO (0); os documentos reais vivem em ged_kit_documents (2046).
        # Raw SQL na tabela real (sem tocar o model Document, que segue no CRUD). ged_kit_documents nao tem
        # status/category/confidentiality -> usamos is_signed; category/confidentiality vazios honestos.
        from sqlalchemy import text as _text

        total = int((await self.session.execute(_text("SELECT count(*) FROM ged_kit_documents"))).scalar() or 0)
        signed = int(
            (await self.session.execute(_text("SELECT count(*) FROM ged_kit_documents WHERE is_signed"))).scalar() or 0
        )
        size = int(
            (
                await self.session.execute(_text("SELECT COALESCE(SUM(file_size_bytes), 0) FROM ged_kit_documents"))
            ).scalar()
            or 0
        )
        by_type_rows = (
            await self.session.execute(
                _text("SELECT document_type, count(*) FROM ged_kit_documents GROUP BY document_type")
            )
        ).all()
        return {
            "total_documents": total,
            "by_status": {"assinado": signed, "pendente": total - signed},
            "by_type": {r[0]: r[1] for r in by_type_rows},
            "by_category": {},
            "by_confidentiality": {},
            "total_size_bytes": size,
            "total_size_mb": round(size / (1024 * 1024), 2),
            "pending_approval": 0,
            "pending_signature": total - signed,
            "expired": 0,
            "expiring_soon": 0,
            "avg_views": 0,
            "avg_downloads": 0,
        }
