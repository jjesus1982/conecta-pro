"""
Servico de Acesso a Kits Documentais do Portal do Cliente.

Permite que clientes listem, visualizem e baixem seus kits
documentais mensais e documentos individuais.
"""

import logging
import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.client_portal.schemas.kit import (
    PortalDocumentResponse,
    PortalKitListResponse,
    PortalKitResponse,
)
from modules.people_management.ged.models.access_log import (
    AccessAction,
    ActorType,
    KitAccessLog,
)
from modules.people_management.ged.models.client import GedClient
from modules.people_management.ged.models.document_kit import GedDocumentKit
from modules.people_management.ged.models.kit_document import KitDocument

logger = logging.getLogger(__name__)


class PortalKitAccessService:
    """Servico de acesso a kits documentais pelo portal do cliente.

    Fornece metodos para listagem, detalhamento e download de kits
    e documentos, com registro completo de auditoria.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_kits(
        self,
        client_id: str,
        skip: int = 0,
        limit: int = 20,
        status_filter: str | None = None,
    ) -> PortalKitListResponse:
        """Lista kits documentais do cliente com paginacao.

        Args:
            client_id: UUID do cliente autenticado.
            skip: Offset para paginacao.
            limit: Limite de registros por pagina.
            status_filter: Filtro opcional por status do kit.

        Returns:
            PortalKitListResponse com kits paginados.
        """
        base_filter = GedDocumentKit.client_id == client_id
        query = select(GedDocumentKit).where(base_filter)
        count_query = select(func.count()).select_from(GedDocumentKit).where(base_filter)

        if status_filter:
            query = query.where(GedDocumentKit.status == status_filter)
            count_query = count_query.where(GedDocumentKit.status == status_filter)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(GedDocumentKit.reference_month.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        kits = result.scalars().unique().all()

        page = (skip // limit) + 1 if limit > 0 else 1
        pages = math.ceil(total / limit) if limit > 0 else 0

        items = [self._kit_to_response(kit) for kit in kits]

        return PortalKitListResponse(
            items=items,
            total=total,
            page=page,
            page_size=limit,
            pages=pages,
        )

    async def get_kit(self, client_id: str, kit_id: str) -> PortalKitResponse:
        """Retorna detalhes de um kit documental especifico.

        Registra um log de acesso (viewed) automaticamente.

        Args:
            client_id: UUID do cliente autenticado.
            kit_id: UUID do kit a ser consultado.

        Returns:
            PortalKitResponse com dados do kit e documentos.

        Raises:
            ValueError: Se kit nao encontrado ou nao pertence ao cliente.
        """
        kit = await self._get_kit_or_raise(client_id, kit_id)

        await self._log_access(
            kit_id=str(kit.id),
            client_id=client_id,
            action=AccessAction.VIEWED,
        )

        return self._kit_to_response(kit)

    async def list_documents(
        self,
        client_id: str,
        kit_id: str,
    ) -> list[PortalDocumentResponse]:
        """Lista documentos de um kit especifico.

        Args:
            client_id: UUID do cliente autenticado.
            kit_id: UUID do kit.

        Returns:
            Lista de PortalDocumentResponse.

        Raises:
            ValueError: Se kit nao encontrado ou nao pertence ao cliente.
        """
        kit = await self._get_kit_or_raise(client_id, kit_id)

        # Só lista documentos com arquivo LOCAL real (materializados em /app/uploads).
        # Filtra os registros antigos placeholder/quebrados sem deletá-los.
        result = await self.db.execute(
            select(KitDocument)
            .where(KitDocument.kit_id == str(kit.id))
            .where(KitDocument.file_path.like("/app/uploads/%"))
            .order_by(KitDocument.document_type, KitDocument.document_name)
        )
        documents = result.scalars().all()

        return [self._document_to_response(doc) for doc in documents]

    async def get_document_for_download(
        self,
        client_id: str,
        kit_id: str,
        document_id: str,
    ) -> dict:
        """Retorna dados do documento para download.

        Valida que o documento pertence ao kit do cliente e
        registra um log de download.

        Args:
            client_id: UUID do cliente autenticado.
            kit_id: UUID do kit.
            document_id: UUID do documento.

        Returns:
            Dict com file_path, file_name, mime_type e file_size_bytes.

        Raises:
            ValueError: Se documento nao encontrado ou acesso negado.
        """
        kit = await self._get_kit_or_raise(client_id, kit_id)

        result = await self.db.execute(
            select(KitDocument).where(
                KitDocument.id == document_id,
                KitDocument.kit_id == str(kit.id),
            )
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(f"Documento nao encontrado: {document_id}")

        if not document.file_path:
            raise ValueError(f"Arquivo nao disponivel para o documento: {document.document_name}")

        await self._log_access(
            kit_id=str(kit.id),
            client_id=client_id,
            action=AccessAction.DOWNLOADED,
            notes=f"Download do documento: {document.document_name}",
        )

        return {
            "file_path": document.file_path,
            "file_name": document.document_name,
            "mime_type": document.mime_type or "application/octet-stream",
            "file_size_bytes": document.file_size_bytes,
        }

    async def _get_kit_or_raise(self, client_id: str, kit_id: str) -> GedDocumentKit:
        """Busca kit por ID garantindo que pertence ao cliente.

        Args:
            client_id: UUID do cliente autenticado.
            kit_id: UUID do kit.

        Returns:
            GedDocumentKit com documentos carregados.

        Raises:
            ValueError: Se kit nao encontrado ou nao pertence ao cliente.
        """
        result = await self.db.execute(
            select(GedDocumentKit).where(
                GedDocumentKit.id == kit_id,
                GedDocumentKit.client_id == client_id,
            )
        )
        kit = result.scalar_one_or_none()

        if not kit:
            raise ValueError(f"Kit documental nao encontrado: {kit_id}")

        return kit

    async def _log_access(
        self,
        kit_id: str,
        client_id: str,
        action: str,
        notes: str | None = None,
    ) -> None:
        """Registra um log de acesso ao kit pelo portal.

        Args:
            kit_id: UUID do kit acessado.
            client_id: UUID do cliente que acessou.
            action: Acao realizada (viewed, downloaded, etc).
            notes: Observacoes adicionais.
        """
        client_result = await self.db.execute(select(GedClient.name).where(GedClient.id == client_id))
        client_name = client_result.scalar_one_or_none() or "Cliente Portal"

        log_entry = KitAccessLog(
            kit_id=kit_id,
            action=action,
            actor_type=ActorType.CLIENT,
            actor_id=client_id,
            actor_name=client_name,
            notes=notes,
        )
        self.db.add(log_entry)
        await self.db.flush()

        logger.info(
            "Acesso portal registrado: kit_id=%s, client_id=%s, action=%s",
            kit_id,
            client_id,
            action,
        )

    @staticmethod
    def _kit_to_response(kit: GedDocumentKit) -> PortalKitResponse:
        """Converte GedDocumentKit ORM para PortalKitResponse."""
        documents = []

        return PortalKitResponse(
            id=str(kit.id),
            client_id=str(kit.client_id),
            reference_month=kit.reference_month,
            status=kit.status,
            total_employees=kit.total_employees,
            total_documents=kit.total_documents,
            documents_signed=kit.documents_signed,
            completion_percentage=kit.completion_percentage,
            sent_at=kit.sent_at,
            sent_method=kit.sent_method,
            zip_file_path=kit.zip_file_path,
            google_drive_link=kit.google_drive_link,
            notes=kit.notes,
            created_at=kit.created_at,
            updated_at=kit.updated_at,
            documents=documents,
        )

    @staticmethod
    def _document_to_response(doc: KitDocument) -> PortalDocumentResponse:
        """Converte KitDocument ORM para PortalDocumentResponse."""
        return PortalDocumentResponse(
            id=str(doc.id),
            document_type=doc.document_type,
            document_name=doc.document_name,
            file_size_bytes=doc.file_size_bytes,
            mime_type=doc.mime_type,
            is_signed=doc.is_signed,
            created_at=doc.created_at,
        )
