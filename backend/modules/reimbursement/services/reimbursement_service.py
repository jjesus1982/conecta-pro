"""Service principal para operações de reembolso."""

import logging
import os
import uuid as uuid_lib
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.reimbursement.models import (
    ReimbursementAttachment,
    ReimbursementCategory,
    ReimbursementItem,
    ReimbursementRequest,
)
from modules.reimbursement.repositories.reimbursement_repository import (
    ReimbursementRepository,
)
from modules.reimbursement.schemas import (
    ReimbursementAttachmentCreate,
    ReimbursementItemCreate,
    ReimbursementItemUpdate,
    ReimbursementRequestCreate,
    ReimbursementRequestFilter,
    ReimbursementRequestStats,
    ReimbursementRequestUpdate,
)

logger = logging.getLogger(__name__)

# Diretório para armazenar arquivos de reembolso
UPLOAD_DIR = os.getenv("REIMBURSEMENT_UPLOAD_DIR", "/opt/conecta-pro/uploads/reimbursements")


def _resolve_upload_dir() -> str:
    """Resolve um diretório de upload GRAVÁVEL.

    O default aponta para um caminho de HOST (/opt/conecta-pro/uploads/...) que
    não existe dentro do container. Tenta os candidatos na ordem e devolve o
    primeiro onde consegue de fato criar/escrever — assim o anexo funciona tanto
    no host quanto no container (mount /app/uploads) sem exigir env/rebuild.
    """
    import tempfile

    candidates = [
        UPLOAD_DIR,
        "/app/uploads/reimbursements",
        os.path.join(tempfile.gettempdir(), "reimbursements"),
    ]
    for base in candidates:
        try:
            os.makedirs(base, exist_ok=True)
            probe = os.path.join(base, ".write_test")
            with open(probe, "w") as fh:
                fh.write("ok")
            os.remove(probe)
            return base
        except Exception:  # noqa: BLE001
            continue
    return tempfile.gettempdir()


class ReimbursementService:
    """Service para operações de reembolso."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.repo = ReimbursementRepository(session)

    # ==================== REQUESTS ====================

    async def create_request(
        self,
        condominio_id: UUID,
        requester_id: UUID,
        data: ReimbursementRequestCreate,
    ) -> ReimbursementRequest:
        """Cria uma nova solicitação de reembolso."""
        logger.info(f"Criando solicitação de reembolso para usuário {requester_id}")

        request = await self.repo.create_request(condominio_id, requester_id, data)
        await self.session.commit()
        await self.session.refresh(request, ["items", "attachments"])

        logger.info(f"Solicitação criada: {request.code}")
        return request

    async def get_request(
        self,
        request_id: UUID,
        include_items: bool = True,
        include_attachments: bool = True,
    ) -> ReimbursementRequest | None:
        """Busca solicitação por ID."""
        return await self.repo.get_request_by_id(
            request_id,
            include_items=include_items,
            include_attachments=include_attachments,
        )

    async def get_request_by_code(self, code: str) -> ReimbursementRequest | None:
        """Busca solicitação por código."""
        return await self.repo.get_request_by_code(code)

    async def list_requests(
        self,
        condominio_id: UUID | None,
        filters: ReimbursementRequestFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[ReimbursementRequest], int]:
        """Lista solicitações com filtros. Se condominio_id for None, lista todos."""
        return await self.repo.list_requests(condominio_id, filters, skip, limit)

    async def list_my_requests(
        self,
        condominio_id: UUID | None,
        requester_id: UUID,
        filters: ReimbursementRequestFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[ReimbursementRequest], int]:
        """Lista solicitações do usuário."""
        if filters is None:
            filters = ReimbursementRequestFilter()
        filters.requester_id = requester_id

        return await self.repo.list_requests(condominio_id, filters, skip, limit)

    async def update_request(
        self,
        request_id: UUID,
        data: ReimbursementRequestUpdate,
        user_id: UUID,
    ) -> ReimbursementRequest | None:
        """Atualiza uma solicitação (apenas rascunho)."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        if not request.can_edit:
            raise ValueError(f"Solicitação em status {request.status} não pode ser editada")

        request = await self.repo.update_request(request, data)
        await self.session.commit()

        logger.info(f"Solicitação atualizada: {request.code} por {user_id}")
        return request

    async def delete_request(
        self,
        request_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Deleta uma solicitação (apenas rascunho)."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return False

        if not request.can_edit:
            raise ValueError(f"Solicitação em status {request.status} não pode ser excluída")

        await self.repo.delete_request(request)
        await self.session.commit()

        logger.info(f"Solicitação excluída: {request.code} por {user_id}")
        return True

    async def submit_request(
        self,
        request_id: UUID,
        user_id: UUID,
        notes: str | None = None,
    ) -> ReimbursementRequest | None:
        """Submete solicitação para aprovação."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        if request.requester_id != user_id:
            raise ValueError("Apenas o solicitante pode submeter a solicitação")

        request.submit()

        if notes:
            request.notes = (request.notes or "") + f"\n[Submissão] {notes}"

        await self.session.commit()

        logger.info(f"Solicitação submetida: {request.code}")
        return request

    async def cancel_request(
        self,
        request_id: UUID,
        user_id: UUID,
        reason: str | None = None,
    ) -> ReimbursementRequest | None:
        """Cancela uma solicitação."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        request.cancel(reason)
        await self.session.commit()

        logger.info(f"Solicitação cancelada: {request.code} por {user_id}")
        return request

    async def get_stats(
        self,
        condominio_id: UUID | None,
        requester_id: UUID | None = None,
    ) -> ReimbursementRequestStats:
        """Retorna estatísticas. Se condominio_id for None, retorna stats de todos."""
        return await self.repo.get_stats(condominio_id, requester_id)

    # ==================== ITEMS ====================

    async def add_item(
        self,
        request_id: UUID,
        data: ReimbursementItemCreate,
        user_id: UUID,
    ) -> ReimbursementItem | None:
        """Adiciona item a uma solicitação."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        if not request.can_edit:
            raise ValueError("Itens só podem ser adicionados em rascunho")

        item = await self.repo.create_item(request_id, data)

        # Recalcula total
        request.total_amount = request.calculate_total()

        await self.session.commit()

        logger.info(f"Item adicionado à solicitação {request.code}")
        return item

    async def update_item(
        self,
        request_id: UUID,
        item_id: UUID,
        data: ReimbursementItemUpdate,
        user_id: UUID,
    ) -> ReimbursementItem | None:
        """Atualiza um item."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        if not request.can_edit:
            raise ValueError("Itens só podem ser editados em rascunho")

        item = await self.repo.get_item_by_id(item_id)
        if not item or item.request_id != request_id:
            return None

        item = await self.repo.update_item(item, data)

        # Recalcula total
        request.total_amount = request.calculate_total()

        await self.session.commit()

        logger.info(f"Item {item_id} atualizado na solicitação {request.code}")
        return item

    async def delete_item(
        self,
        request_id: UUID,
        item_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Remove um item."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return False

        if not request.can_edit:
            raise ValueError("Itens só podem ser removidos em rascunho")

        item = await self.repo.get_item_by_id(item_id)
        if not item or item.request_id != request_id:
            return False

        await self.repo.delete_item(item)

        # Recalcula total
        request.total_amount = request.calculate_total()

        await self.session.commit()

        logger.info(f"Item {item_id} removido da solicitação {request.code}")
        return True

    # ==================== ATTACHMENTS ====================

    async def add_attachment(
        self,
        request_id: UUID,
        data: ReimbursementAttachmentCreate,
        file_content: bytes,
        original_filename: str,
        mime_type: str,
        user_id: UUID,
    ) -> ReimbursementAttachment | None:
        """Adiciona anexo a uma solicitação."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        # Gera nome único para o arquivo
        file_ext = os.path.splitext(original_filename)[1]
        unique_name = f"{uuid_lib.uuid4()}{file_ext}"

        # Cria diretório se não existir (resolve base gravável — host ou container)
        request_dir = os.path.join(_resolve_upload_dir(), str(request_id))
        os.makedirs(request_dir, exist_ok=True)

        # Salva arquivo
        file_path = os.path.join(request_dir, unique_name)
        with open(file_path, "wb") as f:
            f.write(file_content)

        # Cria registro no banco
        attachment = await self.repo.create_attachment(
            request_id=request_id,
            data=data,
            file_name=unique_name,
            file_path=file_path,
            file_size_bytes=len(file_content),
            mime_type=mime_type,
            uploaded_by=user_id,
            original_name=original_filename,
        )

        await self.session.commit()

        logger.info(f"Anexo adicionado à solicitação {request.code}: {original_filename}")
        return attachment

    async def list_attachments(
        self,
        request_id: UUID,
        item_id: UUID | None = None,
    ) -> list[ReimbursementAttachment]:
        """Lista anexos de uma solicitação."""
        return await self.repo.list_attachments(request_id, item_id)

    async def get_attachment(
        self,
        attachment_id: UUID,
    ) -> ReimbursementAttachment | None:
        """Busca anexo por ID."""
        return await self.repo.get_attachment_by_id(attachment_id)

    async def delete_attachment(
        self,
        attachment_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Remove um anexo."""
        attachment = await self.repo.get_attachment_by_id(attachment_id)
        if not attachment:
            return False

        request = await self.repo.get_request_by_id(attachment.request_id)
        if not request:
            return False

        # Verifica se pode editar (apenas em rascunho ou se for o próprio usuário)
        if not request.can_edit:
            raise ValueError("Anexos não podem ser removidos após submissão")

        await self.repo.delete_attachment(attachment)
        await self.session.commit()

        logger.info(f"Anexo {attachment_id} removido da solicitação {request.code}")
        return True

    # ==================== CATEGORIES ====================

    async def list_categories(
        self,
        condominio_id: UUID | None,
    ) -> list[ReimbursementCategory]:
        """Lista categorias de reembolso. Se condominio_id for None, lista todas."""
        return await self.repo.list_categories(condominio_id)

    async def get_category(
        self,
        category_id: UUID,
    ) -> ReimbursementCategory | None:
        """Busca categoria por ID."""
        return await self.repo.get_category_by_id(category_id)

    async def create_category(
        self,
        condominio_id: UUID,
        code: str,
        name: str,
        description: str | None = None,
        default_limit_per_request: Decimal | None = None,
        default_limit_monthly: Decimal | None = None,
        requires_receipt: bool = True,
        auto_approve_below: Decimal | None = None,
        accounting_account: str | None = None,
        cost_center: str | None = None,
    ) -> ReimbursementCategory:
        """Cria uma categoria de reembolso."""
        category = await self.repo.create_category(
            condominio_id=condominio_id,
            code=code,
            name=name,
            description=description,
            default_limit_per_request=default_limit_per_request,
            default_limit_monthly=default_limit_monthly,
            requires_receipt=requires_receipt,
            auto_approve_below=auto_approve_below,
            accounting_account=accounting_account,
            cost_center=cost_center,
        )
        await self.session.commit()

        logger.info(f"Categoria criada: {category.code} - {category.name}")
        return category
