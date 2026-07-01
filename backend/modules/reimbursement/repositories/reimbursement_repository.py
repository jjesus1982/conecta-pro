"""Repository para operações de banco de dados de reembolso."""

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.reimbursement.models import (
    ReimbursementAttachment,
    ReimbursementCategory,
    ReimbursementItem,
    ReimbursementRequest,
    ReimbursementStatus,
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


class ReimbursementRepository:
    """Repository para operações de reembolso."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    # ==================== REQUESTS ====================

    async def create_request(
        self,
        condominio_id: UUID,
        requester_id: UUID,
        data: ReimbursementRequestCreate,
    ) -> ReimbursementRequest:
        """Cria uma nova solicitação de reembolso."""
        # Gera código único
        year = date.today().year
        sequence = await self._get_next_sequence(condominio_id, year)
        code = ReimbursementRequest.generate_code(year, sequence)

        request = ReimbursementRequest(
            condominio_id=condominio_id,
            requester_id=requester_id,
            code=code,
            title=data.title,
            description=data.description,
            expense_date_start=data.expense_date_start,
            expense_date_end=data.expense_date_end,
            cost_center=data.cost_center,
            project=data.project,
            notes=data.notes,
            bank_code=data.bank_code,
            bank_agency=data.bank_agency,
            bank_account=data.bank_account,
            pix_key=data.pix_key,
            status=ReimbursementStatus.RASCUNHO.value,
        )

        self.session.add(request)
        await self.session.flush()

        # Adiciona itens se fornecidos
        total = Decimal("0.00")
        if data.items:
            for item_data in data.items:
                item = await self.create_item(request.id, item_data)
                if item and item.amount:
                    total += item.amount

        # Define total
        request.total_amount = total

        # Refresh para carregar relacionamentos
        await self.session.refresh(request, ["items", "attachments"])

        return request

    async def get_request_by_id(
        self,
        request_id: UUID,
        include_items: bool = True,
        include_attachments: bool = True,
    ) -> ReimbursementRequest | None:
        """Busca solicitação por ID."""
        query = select(ReimbursementRequest).where(
            ReimbursementRequest.id == request_id,
            ReimbursementRequest.is_active == True,  # noqa: E712
        )

        if include_items:
            query = query.options(selectinload(ReimbursementRequest.items))
        if include_attachments:
            query = query.options(selectinload(ReimbursementRequest.attachments))

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_request_by_code(self, code: str) -> ReimbursementRequest | None:
        """Busca solicitação por código."""
        query = select(ReimbursementRequest).where(
            ReimbursementRequest.code == code,
            ReimbursementRequest.is_active == True,  # noqa: E712
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_requests(
        self,
        condominio_id: UUID | None,
        filters: ReimbursementRequestFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[ReimbursementRequest], int]:
        """Lista solicitações com filtros e paginação. Se condominio_id for None, lista todos."""
        query = select(ReimbursementRequest).where(
            ReimbursementRequest.is_active == True,  # noqa: E712
        )

        # Filtra por condomínio se especificado
        if condominio_id is not None:
            query = query.where(ReimbursementRequest.condominio_id == condominio_id)

        # Aplica filtros
        if filters:
            if filters.status:
                query = query.where(ReimbursementRequest.status == filters.status)
            if filters.approval_level:
                query = query.where(ReimbursementRequest.approval_level == filters.approval_level)
            if filters.requester_id:
                query = query.where(ReimbursementRequest.requester_id == filters.requester_id)
            if filters.expense_date_start:
                query = query.where(ReimbursementRequest.expense_date_start >= filters.expense_date_start)
            if filters.expense_date_end:
                query = query.where(ReimbursementRequest.expense_date_end <= filters.expense_date_end)
            if filters.min_amount:
                query = query.where(ReimbursementRequest.total_amount >= filters.min_amount)
            if filters.max_amount:
                query = query.where(ReimbursementRequest.total_amount <= filters.max_amount)
            if filters.cost_center:
                query = query.where(ReimbursementRequest.cost_center == filters.cost_center)
            if filters.project:
                query = query.where(ReimbursementRequest.project == filters.project)
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.where(
                    or_(
                        ReimbursementRequest.code.ilike(search_term),
                        ReimbursementRequest.title.ilike(search_term),
                        ReimbursementRequest.description.ilike(search_term),
                    )
                )

        # Conta total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Aplica paginação
        query = query.order_by(ReimbursementRequest.created_at.desc())
        query = query.offset(skip).limit(limit)
        query = query.options(selectinload(ReimbursementRequest.items))

        result = await self.session.execute(query)
        requests = list(result.scalars().all())

        return requests, total

    async def list_pending_approvals(
        self,
        condominio_id: UUID,
        approval_level: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[ReimbursementRequest], int]:
        """Lista solicitações pendentes de aprovação."""
        _conds = [
            ReimbursementRequest.is_active == True,  # noqa: E712
            ReimbursementRequest.status.in_(
                [
                    ReimbursementStatus.PENDENTE.value,
                    ReimbursementStatus.EM_ANALISE.value,
                ]
            ),
        ]
        if condominio_id is not None:  # [Reembolso] admin (None) ve todas; nao filtrar IS NULL
            _conds.append(ReimbursementRequest.condominio_id == condominio_id)
        query = select(ReimbursementRequest).where(*_conds)

        if approval_level:
            query = query.where(ReimbursementRequest.approval_level == approval_level)

        # Conta total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Aplica paginação
        query = query.order_by(ReimbursementRequest.submitted_at.asc())
        query = query.offset(skip).limit(limit)
        query = query.options(selectinload(ReimbursementRequest.items))

        result = await self.session.execute(query)
        requests = list(result.scalars().all())

        return requests, total

    async def list_ready_for_payment(
        self,
        condominio_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[ReimbursementRequest], int]:
        """Lista solicitações aprovadas prontas para pagamento."""
        query = select(ReimbursementRequest).where(
            ReimbursementRequest.condominio_id == condominio_id,
            ReimbursementRequest.is_active == True,  # noqa: E712
            ReimbursementRequest.status == ReimbursementStatus.APROVADO.value,
        )

        # Conta total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Aplica paginação
        query = query.order_by(ReimbursementRequest.approved_at.asc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        requests = list(result.scalars().all())

        return requests, total

    async def update_request(
        self,
        request: ReimbursementRequest,
        data: ReimbursementRequestUpdate,
    ) -> ReimbursementRequest:
        """Atualiza uma solicitação."""
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(request, field, value)

        # Recalcula total se necessário
        request.total_amount = request.calculate_total()

        return request

    async def delete_request(self, request: ReimbursementRequest) -> None:
        """Soft delete de solicitação."""
        request.is_active = False

    async def get_stats(
        self,
        condominio_id: UUID | None,
        requester_id: UUID | None = None,
    ) -> ReimbursementRequestStats:
        """Retorna estatísticas de reembolsos. Se condominio_id for None, retorna de todos."""
        # Base conditions
        base_conditions = [ReimbursementRequest.is_active == True]  # noqa: E712
        if condominio_id is not None:
            base_conditions.append(ReimbursementRequest.condominio_id == condominio_id)
        if requester_id:
            base_conditions.append(ReimbursementRequest.requester_id == requester_id)

        base_query = select(ReimbursementRequest).where(*base_conditions)

        # Total
        count_result = await self.session.execute(select(func.count()).select_from(base_query.subquery()))
        total = count_result.scalar() or 0

        # Por status
        status_query = (
            select(
                ReimbursementRequest.status,
                func.count().label("count"),
            )
            .where(*base_conditions)
            .group_by(ReimbursementRequest.status)
        )

        status_result = await self.session.execute(status_query)
        by_status = {row.status: row.count for row in status_result}

        # Totais de valores
        values_query = select(
            func.sum(ReimbursementRequest.total_amount).label("total_amount"),
            func.sum(ReimbursementRequest.approved_amount).label("total_approved"),
            func.sum(ReimbursementRequest.paid_amount).label("total_paid"),
        ).where(*base_conditions)

        values_result = await self.session.execute(values_query)
        values_row = values_result.first()

        # Pendentes
        pending_conditions = base_conditions + [
            ReimbursementRequest.status.in_(
                [
                    ReimbursementStatus.PENDENTE.value,
                    ReimbursementStatus.EM_ANALISE.value,
                ]
            )
        ]
        pending_query = select(
            func.count().label("count"),
            func.sum(ReimbursementRequest.total_amount).label("amount"),
        ).where(*pending_conditions)

        pending_result = await self.session.execute(pending_query)
        pending_row = pending_result.first()

        # Aprovados aguardando pagamento
        approved_conditions = base_conditions + [ReimbursementRequest.status == ReimbursementStatus.APROVADO.value]
        approved_query = select(
            func.count().label("count"),
            func.sum(ReimbursementRequest.approved_amount).label("amount"),
        ).where(*approved_conditions)

        approved_result = await self.session.execute(approved_query)
        approved_row = approved_result.first()

        return ReimbursementRequestStats(
            total=total,
            by_status=by_status,
            total_amount=Decimal(str(values_row.total_amount or 0)),
            total_approved=Decimal(str(values_row.total_approved or 0)),
            total_paid=Decimal(str(values_row.total_paid or 0)),
            pending_count=pending_row.count or 0,
            pending_amount=Decimal(str(pending_row.amount or 0)),
            approved_count=approved_row.count or 0,
            approved_amount=Decimal(str(approved_row.amount or 0)),
        )

    async def _get_next_sequence(self, condominio_id: UUID, year: int) -> int:
        """Obtém próximo número de sequência para o ano.

        Conta GLOBALMENTE (o code tem UNIQUE global, não por condomínio) — contar por
        condominio_id gerava REI-AAAA-00001 colidindo entre condomínios → UniqueViolation.
        """
        query = select(func.count()).where(
            ReimbursementRequest.code.like(f"REI-{year}-%"),
        )
        result = await self.session.execute(query)
        count = result.scalar() or 0
        return count + 1

    # ==================== ITEMS ====================

    async def create_item(
        self,
        request_id: UUID,
        data: ReimbursementItemCreate,
    ) -> ReimbursementItem:
        """Cria um item de reembolso."""
        item = ReimbursementItem(
            request_id=request_id,
            category_id=data.category_id,
            category=data.category_type,
            category_type=data.category_type,
            description=data.description,
            merchant=data.merchant,
            expense_date=data.expense_date,
            amount=data.amount,
            document_type=data.document_type,
            document_number=data.document_number,
            notes=data.notes,
        )

        self.session.add(item)
        await self.session.flush()

        return item

    async def get_item_by_id(self, item_id: UUID) -> ReimbursementItem | None:
        """Busca item por ID."""
        query = select(ReimbursementItem).where(
            ReimbursementItem.id == item_id,
            ReimbursementItem.is_active == True,  # noqa: E712
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_item(
        self,
        item: ReimbursementItem,
        data: ReimbursementItemUpdate,
    ) -> ReimbursementItem:
        """Atualiza um item."""
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(item, field, value)

        return item

    async def delete_item(self, item: ReimbursementItem) -> None:
        """Soft delete de item."""
        item.is_active = False

    # ==================== ATTACHMENTS ====================

    async def create_attachment(
        self,
        request_id: UUID,
        data: ReimbursementAttachmentCreate,
        file_name: str,
        file_path: str,
        file_size_bytes: int,
        mime_type: str,
        uploaded_by: UUID,
        original_name: str | None = None,
        thumbnail_path: str | None = None,
    ) -> ReimbursementAttachment:
        """Cria um anexo de reembolso."""
        attachment = ReimbursementAttachment(
            request_id=request_id,
            item_id=data.item_id,
            attachment_type=data.attachment_type,
            file_name=file_name,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            original_name=original_name,
            description=data.description,
            uploaded_by=uploaded_by,
            thumbnail_path=thumbnail_path,
        )

        self.session.add(attachment)
        await self.session.flush()

        return attachment

    async def get_attachment_by_id(
        self,
        attachment_id: UUID,
    ) -> ReimbursementAttachment | None:
        """Busca anexo por ID."""
        query = select(ReimbursementAttachment).where(
            ReimbursementAttachment.id == attachment_id,
            ReimbursementAttachment.is_active == True,  # noqa: E712
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_attachments(
        self,
        request_id: UUID,
        item_id: UUID | None = None,
    ) -> list[ReimbursementAttachment]:
        """Lista anexos de uma solicitação ou item."""
        query = select(ReimbursementAttachment).where(
            ReimbursementAttachment.request_id == request_id,
            ReimbursementAttachment.is_active == True,  # noqa: E712
        )

        if item_id:
            query = query.where(ReimbursementAttachment.item_id == item_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_attachment(self, attachment: ReimbursementAttachment) -> None:
        """Soft delete de anexo."""
        attachment.is_active = False

    # ==================== CATEGORIES ====================

    async def list_categories(
        self,
        condominio_id: UUID | None,
    ) -> list[ReimbursementCategory]:
        """Lista categorias de reembolso. Se condominio_id for None, lista todas."""
        conditions = [ReimbursementCategory.is_active == True]  # noqa: E712
        if condominio_id is not None:
            conditions.append(ReimbursementCategory.condominio_id == condominio_id)

        query = select(ReimbursementCategory).where(*conditions).order_by(ReimbursementCategory.name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_category_by_id(
        self,
        category_id: UUID,
    ) -> ReimbursementCategory | None:
        """Busca categoria por ID."""
        query = select(ReimbursementCategory).where(
            ReimbursementCategory.id == category_id,
            ReimbursementCategory.is_active == True,  # noqa: E712
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

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
        category = ReimbursementCategory(
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

        self.session.add(category)
        await self.session.flush()

        return category
