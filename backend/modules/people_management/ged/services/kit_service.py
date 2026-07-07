"""
Servico de Kits Documentais — CRUD e operacoes de status.

Gerencia o ciclo de vida dos kits documentais mensais:
EM_MONTAGEM -> COMPLETO -> ENVIADO -> CONFERIDO -> APROVADO.
"""

import logging
import math
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.ged.models.client import GedClient
from modules.people_management.ged.models.document_kit import GedDocumentKit, KitStatus
from modules.people_management.ged.models.kit_document import KitDocument
from modules.people_management.ged.schemas.kit import (
    DocumentsSummary,
    KitCreate,
    KitListResponse,
    KitResponse,
    KitStatusCount,
    KitSummary,
    KitUpdate,
)

logger = logging.getLogger(__name__)


class KitService:
    """Servico de CRUD e gestao de ciclo de vida para kits documentais."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_kit(self, data: KitCreate) -> KitResponse:
        """Cria um novo kit documental para um cliente/mes.

        Args:
            data: Dados do kit (client_id, reference_month, notes).

        Returns:
            KitResponse com o kit criado.

        Raises:
            ValueError: Se cliente nao existe ou ja existe kit para o mes.
        """
        client = await self._get_client_or_raise(data.client_id)

        existing = await self.db.execute(
            select(GedDocumentKit).where(
                GedDocumentKit.client_id == str(data.client_id),
                GedDocumentKit.reference_month == data.reference_month,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"Ja existe um kit para o cliente '{client.name}' no mes {data.reference_month.strftime('%m/%Y')}"
            )

        kit = GedDocumentKit(
            client_id=str(data.client_id),
            reference_month=data.reference_month,
            status=KitStatus.EM_MONTAGEM,
            total_employees=data.total_employees,
            notes=data.notes,
        )

        self.db.add(kit)
        await self.db.flush()
        await self.db.refresh(kit)

        logger.info(
            "Kit criado: client=%s, mes=%s (id=%s)",
            client.name,
            data.reference_month.strftime("%m/%Y"),
            kit.id,
        )
        return await self._to_response(kit)

    async def get_kit(self, kit_id: str) -> KitResponse:
        """Retorna um kit com documentos e informacoes do cliente.

        Args:
            kit_id: UUID do kit.

        Returns:
            KitResponse com dados completos incluindo resumo de documentos.

        Raises:
            ValueError: Se kit nao encontrado.
        """
        kit = await self._get_or_raise(kit_id)
        return await self._to_response(kit, include_documents_summary=True)

    async def list_kits(
        self,
        client_id: str | None = None,
        status: str | None = None,
        year: int | None = None,
        month: int | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> KitListResponse:
        """Lista kits com filtros e paginacao.

        Args:
            client_id: Filtro por cliente.
            status: Filtro por status (em_montagem, completo, etc.).
            year: Filtro por ano de referencia.
            month: Filtro por mes de referencia.
            skip: Offset para paginacao.
            limit: Limite por pagina.

        Returns:
            KitListResponse paginado.
        """
        query = select(GedDocumentKit)
        count_query = select(func.count()).select_from(GedDocumentKit)

        filters = []
        if client_id:
            filters.append(GedDocumentKit.client_id == str(client_id))
        if status:
            filters.append(GedDocumentKit.status == status)
        if year:
            filters.append(func.extract("year", GedDocumentKit.reference_month) == year)
        if month:
            filters.append(func.extract("month", GedDocumentKit.reference_month) == month)

        for f in filters:
            query = query.where(f)
            count_query = count_query.where(f)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(GedDocumentKit.reference_month.desc(), GedDocumentKit.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        kits = result.scalars().all()

        page = (skip // limit) + 1 if limit > 0 else 1
        pages = math.ceil(total / limit) if limit > 0 else 0

        # Contadores AO VIVO em lote: uma única query agregada (sem N+1)
        counts = await self._live_doc_counts([str(kit.id) for kit in kits])
        items = []
        for kit in kits:
            items.append(await self._to_response(kit, counts=counts.get(str(kit.id), (0, 0))))

        return KitListResponse(
            items=items,
            total=total,
            page=page,
            page_size=limit,
            pages=pages,
        )

    async def update_kit(self, kit_id: str, data: KitUpdate) -> KitResponse:
        """Atualiza campos editaveis de um kit.

        Args:
            kit_id: UUID do kit.
            data: Campos a atualizar.

        Returns:
            KitResponse com dados atualizados.

        Raises:
            ValueError: Se kit nao encontrado.
        """
        kit = await self._get_or_raise(kit_id)
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(kit, field):
                setattr(kit, field, value)

        await self.db.flush()
        await self.db.refresh(kit)

        logger.info("Kit atualizado: id=%s", kit.id)
        return await self._to_response(kit)

    async def delete_kit(self, kit_id: str) -> dict:
        """Remove um kit documental.

        So permite exclusao se o status for EM_MONTAGEM.

        Args:
            kit_id: UUID do kit.

        Returns:
            Confirmacao da exclusao.

        Raises:
            ValueError: Se kit nao encontrado ou status nao permite exclusao.
        """
        kit = await self._get_or_raise(kit_id)

        if kit.status != KitStatus.EM_MONTAGEM:
            raise ValueError(
                f"Nao e possivel excluir kit com status '{kit.status}'. Somente kits em montagem podem ser removidos."
            )

        await self.db.delete(kit)
        await self.db.flush()

        logger.info("Kit removido: id=%s", kit_id)
        return {"message": "Kit removido com sucesso", "id": str(kit_id)}

    async def get_kit_summary(self, reference_month: date | None = None) -> KitSummary:
        """Retorna resumo para dashboard de kits.

        Args:
            reference_month: Mes de referencia para filtrar (opcional).

        Returns:
            KitSummary com contagens por status e metricas.
        """
        base_filter = []
        if reference_month:
            ref = reference_month.replace(day=1)
            base_filter.append(GedDocumentKit.reference_month == ref)

        # Contagem total
        total_query = select(func.count()).select_from(GedDocumentKit)
        for f in base_filter:
            total_query = total_query.where(f)
        total_result = await self.db.execute(total_query)
        total_kits = total_result.scalar() or 0

        # Contagem por status
        status_query = select(GedDocumentKit.status, func.count().label("count")).group_by(GedDocumentKit.status)
        for f in base_filter:
            status_query = status_query.where(f)
        status_result = await self.db.execute(status_query)
        status_rows = status_result.all()

        by_status = [KitStatusCount(status=row[0], count=row[1]) for row in status_rows]
        status_map = {row[0]: row[1] for row in status_rows}

        # Total de clientes com kits
        client_count_query = select(func.count(func.distinct(GedDocumentKit.client_id))).select_from(GedDocumentKit)
        for f in base_filter:
            client_count_query = client_count_query.where(f)
        client_result = await self.db.execute(client_count_query)
        total_clients = client_result.scalar() or 0

        # Kits completos nao enviados
        kits_pending_send = status_map.get(KitStatus.COMPLETO, 0)

        # Kits enviados aguardando aprovacao
        kits_pending_approval = status_map.get(KitStatus.ENVIADO, 0) + status_map.get(KitStatus.CONFERIDO, 0)

        # Media de completude dos kits em montagem — AO VIVO a partir do
        # COUNT real em ged_kit_documents (a coluna stored fica stale)
        em_montagem_query = select(GedDocumentKit.id).where(GedDocumentKit.status == KitStatus.EM_MONTAGEM)
        for f in base_filter:
            em_montagem_query = em_montagem_query.where(f)
        em_montagem_result = await self.db.execute(em_montagem_query)
        em_montagem_ids = [str(row) for row in em_montagem_result.scalars().all()]

        counts = await self._live_doc_counts(em_montagem_ids)
        pcts = []
        for kit_id in em_montagem_ids:
            total_docs, signed_docs = counts.get(kit_id, (0, 0))
            pcts.append((signed_docs / total_docs) * 100 if total_docs > 0 else 0.0)
        average_completion = Decimal(str(round(sum(pcts) / len(pcts), 2))) if pcts else Decimal("0.00")

        return KitSummary(
            total_kits=total_kits,
            by_status=by_status,
            total_clients=total_clients,
            kits_pending_send=kits_pending_send,
            kits_pending_approval=kits_pending_approval,
            average_completion=average_completion,
            reference_month=reference_month,
        )

    async def get_kits_by_month(self, reference_month: date) -> list[KitResponse]:
        """Retorna todos os kits de um mes de referencia.

        Args:
            reference_month: Data (sera normalizada para primeiro dia do mes).

        Returns:
            Lista de KitResponse.
        """
        ref = reference_month.replace(day=1)
        result = await self.db.execute(
            select(GedDocumentKit).where(GedDocumentKit.reference_month == ref).order_by(GedDocumentKit.created_at)
        )
        kits = result.scalars().all()
        # Contadores AO VIVO em lote: uma única query agregada (sem N+1)
        counts = await self._live_doc_counts([str(kit.id) for kit in kits])
        items = []
        for kit in kits:
            items.append(await self._to_response(kit, counts=counts.get(str(kit.id), (0, 0))))
        return items

    async def recalculate_kit_completion(self, kit_id: str) -> KitResponse:
        """Recalcula o percentual de completude com base nos documentos.

        Conta documentos totais e assinados, atualiza contadores e percentual.
        Se atingir 100%, muda status para COMPLETO automaticamente.

        Args:
            kit_id: UUID do kit.

        Returns:
            KitResponse atualizado.
        """
        kit = await self._get_or_raise(kit_id)

        total_result = await self.db.execute(
            select(func.count()).select_from(KitDocument).where(KitDocument.kit_id == str(kit_id))
        )
        total_docs = total_result.scalar() or 0

        signed_result = await self.db.execute(
            select(func.count())
            .select_from(KitDocument)
            .where(KitDocument.kit_id == str(kit_id), KitDocument.is_signed.is_(True))
        )
        signed_docs = signed_result.scalar() or 0

        kit.total_documents = total_docs
        kit.documents_signed = signed_docs

        if total_docs > 0:
            kit.completion_percentage = Decimal(str(round((signed_docs / total_docs) * 100, 2)))
        else:
            kit.completion_percentage = Decimal("0.00")

        if kit.completion_percentage >= Decimal("100.00") and kit.status == KitStatus.EM_MONTAGEM:
            kit.status = KitStatus.COMPLETO
            logger.info("Kit %s atingiu 100%% e foi marcado como COMPLETO", kit_id)

        await self.db.flush()
        await self.db.refresh(kit)

        logger.info(
            "Kit %s recalculado: %d/%d docs, %.2f%%",
            kit_id,
            signed_docs,
            total_docs,
            kit.completion_percentage,
        )
        return await self._to_response(kit)

    async def mark_kit_sent(
        self,
        kit_id: str,
        method: str,
        sent_to: str | None = None,
    ) -> KitResponse:
        """Marca um kit como enviado.

        Args:
            kit_id: UUID do kit.
            method: Metodo de envio (email, google_drive, portal, impresso).
            sent_to: Destinatario(s) do envio.

        Returns:
            KitResponse atualizado.

        Raises:
            ValueError: Se status nao permite envio.
        """
        kit = await self._get_or_raise(kit_id)

        allowed_statuses = [KitStatus.EM_MONTAGEM, KitStatus.COMPLETO]
        if kit.status not in allowed_statuses:
            raise ValueError(
                f"Nao e possivel enviar kit com status '{kit.status}'. Status permitidos: {', '.join(allowed_statuses)}"
            )

        kit.status = KitStatus.ENVIADO
        kit.sent_at = datetime.utcnow()
        kit.sent_method = method
        kit.sent_to = sent_to

        await self.db.flush()
        await self.db.refresh(kit)

        logger.info("Kit %s marcado como ENVIADO via %s para %s", kit_id, method, sent_to)
        return await self._to_response(kit)

    async def approve_kit(self, kit_id: str, approved_by: str) -> KitResponse:
        """Marca um kit como aprovado.

        Args:
            kit_id: UUID do kit.
            approved_by: Nome de quem aprovou.

        Returns:
            KitResponse atualizado.

        Raises:
            ValueError: Se status nao permite aprovacao.
        """
        kit = await self._get_or_raise(kit_id)

        allowed_statuses = [KitStatus.ENVIADO, KitStatus.CONFERIDO]
        if kit.status not in allowed_statuses:
            raise ValueError(
                f"Nao e possivel aprovar kit com status '{kit.status}'. Kit deve estar enviado ou conferido."
            )

        kit.status = KitStatus.APROVADO
        kit.approved_at = datetime.utcnow()
        kit.approved_by = approved_by

        await self.db.flush()
        await self.db.refresh(kit)

        logger.info("Kit %s aprovado por %s", kit_id, approved_by)
        return await self._to_response(kit)

    # --- Metodos auxiliares ---

    async def _get_or_raise(self, kit_id: str) -> GedDocumentKit:
        """Busca kit por ID ou levanta ValueError."""
        result = await self.db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))
        kit = result.scalar_one_or_none()
        if not kit:
            raise ValueError(f"Kit documental nao encontrado: {kit_id}")
        return kit

    async def _get_client_or_raise(self, client_id: str) -> GedClient:
        """Busca cliente por ID ou levanta ValueError."""
        result = await self.db.execute(select(GedClient).where(GedClient.id == client_id))
        client = result.scalar_one_or_none()
        if not client:
            raise ValueError(f"Cliente GED nao encontrado: {client_id}")
        return client

    async def _get_client_name(self, client_id: str) -> str | None:
        """Retorna o nome de um cliente pelo ID."""
        result = await self.db.execute(select(GedClient.name).where(GedClient.id == client_id))
        row = result.scalar_one_or_none()
        return row if row else None

    async def _get_documents_summary(self, kit_id: str) -> DocumentsSummary:
        """Constroi resumo de documentos para um kit."""
        result = await self.db.execute(select(KitDocument).where(KitDocument.kit_id == str(kit_id)))
        documents = result.scalars().all()

        total = len(documents)
        signed = sum(1 for d in documents if d.is_signed)
        unsigned = total - signed

        by_type: dict[str, int] = {}
        for doc in documents:
            by_type[doc.document_type] = by_type.get(doc.document_type, 0) + 1

        return DocumentsSummary(
            total=total,
            signed=signed,
            unsigned=unsigned,
            by_type=by_type,
        )

    async def _live_doc_counts(self, kit_ids: list[str]) -> dict[str, tuple[int, int]]:
        """Contadores AO VIVO por kit: (total, assinados).

        Fonte de verdade é o COUNT real em ged_kit_documents; as colunas
        stored (total_documents/documents_signed/completion_percentage)
        de ged_document_kits ficam desatualizadas. Uma única query
        agregada para o lote inteiro (sem N+1).
        """
        if not kit_ids:
            return {}
        result = await self.db.execute(
            select(
                KitDocument.kit_id,
                func.count().label("total"),
                func.count(case((KitDocument.is_signed.is_(True), 1))).label("signed"),
            )
            .where(KitDocument.kit_id.in_(kit_ids))
            .group_by(KitDocument.kit_id)
        )
        return {str(row.kit_id): (int(row.total or 0), int(row.signed or 0)) for row in result.all()}

    async def _to_response(
        self,
        kit: GedDocumentKit,
        include_documents_summary: bool = False,
        counts: tuple[int, int] | None = None,
    ) -> KitResponse:
        """Converte GedDocumentKit ORM para KitResponse."""
        client_name = await self._get_client_name(str(kit.client_id))

        documents_summary = None
        if include_documents_summary:
            documents_summary = await self._get_documents_summary(str(kit.id))

        # Contadores computados AO VIVO do COUNT real em ged_kit_documents
        # (fonte de verdade); as colunas stored do kit ficam desatualizadas.
        # Em listas, `counts` vem pré-computado por uma única query agregada.
        if counts is None:
            counts = (await self._live_doc_counts([str(kit.id)])).get(str(kit.id), (0, 0))
        total_documents, documents_signed = counts
        completion_percentage = round(documents_signed / total_documents * 100, 2) if total_documents else 0

        return KitResponse(
            id=str(kit.id),
            client_id=str(kit.client_id),
            client_name=client_name,
            reference_month=kit.reference_month,
            status=kit.status,
            total_employees=kit.total_employees,
            total_documents=total_documents,
            documents_signed=documents_signed,
            completion_percentage=completion_percentage,
            sent_at=kit.sent_at,
            sent_method=kit.sent_method,
            sent_to=kit.sent_to,
            approved_at=kit.approved_at,
            approved_by=kit.approved_by,
            zip_file_path=kit.zip_file_path,
            google_drive_link=kit.google_drive_link,
            notes=kit.notes,
            documents_summary=documents_summary,
            created_at=kit.created_at,
            updated_at=kit.updated_at,
        )
