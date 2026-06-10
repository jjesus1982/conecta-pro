"""
Repository para operacoes de banco de dados com Proposal.
"""

import builtins
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.logging import logger
from modules.crm.models.opportunity import Opportunity
from modules.crm.models.proposal import (
    ApprovalAction,
    Proposal,
    ProposalApproval,
    ProposalItem,
    ProposalStatus,
    ProposalTemplate,
    ProposalTermOption,
)
from modules.crm.schemas.proposal import (
    ProposalApprovalRequest,
    ProposalCreate,
    ProposalCreateFromOpportunity,
    ProposalFilter,
    ProposalItemCreate,
    ProposalStats,
    ProposalTemplateCreate,
    ProposalTemplateUpdate,
    ProposalUpdate,
)


class ProposalRepository:
    """Repository para operacoes CRUD de Proposal."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _generate_proposal_number(self) -> str:
        """Gera numero unico para proposta."""
        now = datetime.utcnow()
        return f"PROP-{now.strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"

    async def create(self, data: ProposalCreate, created_by_id: str | None = None) -> Proposal:
        """
        Cria uma nova proposta.

        Args:
            data: Dados da proposta
            created_by_id: ID do usuario que criou

        Returns:
            Proposal criada
        """
        # Calcular validade padrao se nao fornecida
        valid_until = data.valid_until
        if not valid_until:
            # Buscar template para pegar validity_days
            if data.template_id:
                template = await self.get_template_by_id(data.template_id)
                if template:
                    valid_until = date.today() + timedelta(days=template.validity_days)
            if not valid_until:
                valid_until = date.today() + timedelta(days=30)

        proposal = Proposal(
            id=str(uuid4()),
            number=self._generate_proposal_number(),
            version=1,
            opportunity_id=data.opportunity_id,
            template_id=data.template_id,
            client_name=data.client_name,
            client_email=data.client_email,
            client_phone=data.client_phone,
            client_company=data.client_company,
            client_document=data.client_document,
            client_address=data.client_address,
            title=data.title,
            description=data.description,
            proposal_type=data.proposal_type.value,
            terms_conditions=data.terms_conditions,
            payment_terms=data.payment_terms,
            payment_conditions=data.payment_conditions,
            installments=data.installments,
            notes=data.notes,
            discount_type=data.discount_type.value if data.discount_type else None,
            discount_value=data.discount_value,
            discount_reason=data.discount_reason,
            taxes=data.taxes,
            valid_until=valid_until,
            status=ProposalStatus.DRAFT.value,
            created_by_id=created_by_id,
        )

        # Itens em memória — _create_item já calcula item.total (sem IO)
        items = [self._create_item(proposal.id, item_data, i) for i, item_data in enumerate(data.items)]

        # Opções de prazo em memória (sprint94) — espelha o loop de items, sem IO
        term_options = [self._create_term_option(proposal.id, t, i) for i, t in enumerate(data.term_options)]

        # Atribui as coleções em memória e calcula os totais SEM lazy-load async
        # (calculate_totals lê proposal.items da memória, não do banco -> sem MissingGreenlet)
        proposal.items = items
        proposal.term_options = term_options
        proposal.billing_type = data.billing_type
        proposal.reference_number = data.reference_number
        proposal.calculate_totals()

        # Persiste tudo de uma vez (ATÔMICO): cascade='all, delete-orphan' adiciona itens e term_options.
        # Commit ÚNICO no fim -> qualquer falha antes do commit não deixa proposta parcial.
        self.db.add(proposal)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        # Eager-load dos relacionamentos dentro do greenlet (evita lazy-load na serializacao da resposta)
        await self.db.refresh(proposal, ["items", "term_options"])

        logger.info(f"Proposal criada: {proposal.id} ({proposal.number})")
        return proposal

    async def create_from_opportunity(
        self, data: ProposalCreateFromOpportunity, created_by_id: str | None = None
    ) -> Proposal | None:
        """
        Cria proposta a partir de uma opportunity.

        Args:
            data: Dados com opportunity_id e informacoes adicionais
            created_by_id: ID do usuario que criou

        Returns:
            Proposal criada ou None se opportunity nao encontrada
        """
        # Buscar opportunity
        result = await self.db.execute(
            select(Opportunity).where(
                Opportunity.id == data.opportunity_id,
                Opportunity.is_active.is_(True),
            )
        )
        opportunity = result.scalar_one_or_none()

        if not opportunity:
            return None

        # Buscar template para validade
        valid_until = data.valid_until
        if not valid_until:
            if data.template_id:
                template = await self.get_template_by_id(data.template_id)
                if template:
                    valid_until = date.today() + timedelta(days=template.validity_days)
            if not valid_until:
                valid_until = date.today() + timedelta(days=30)

        proposal = Proposal(
            id=str(uuid4()),
            number=self._generate_proposal_number(),
            version=1,
            opportunity_id=opportunity.id,
            template_id=data.template_id,
            client_name=opportunity.contact_name,
            client_email=opportunity.contact_email,
            client_phone=opportunity.contact_phone,
            client_company=opportunity.company_name,
            title=data.title,
            description=data.description,
            valid_until=valid_until,
            status=ProposalStatus.DRAFT.value,
            created_by_id=created_by_id,
        )

        self.db.add(proposal)
        await self.db.flush()

        # Adicionar itens
        for i, item_data in enumerate(data.items):
            item = self._create_item(proposal.id, item_data, i)
            self.db.add(item)

        await self.db.commit()
        await self.db.refresh(proposal, ["items", "term_options"])

        proposal.calculate_totals()
        await self.db.commit()

        logger.info(f"Proposal criada de Opportunity: {proposal.id} (opp: {opportunity.id})")
        return proposal

    def _create_item(self, proposal_id: str, data: ProposalItemCreate, sort_order: int) -> ProposalItem:
        """Cria item de proposta."""
        item = ProposalItem(
            id=str(uuid4()),
            proposal_id=proposal_id,
            code=data.code,
            name=data.name,
            description=data.description,
            unit=data.unit,
            quantity=data.quantity,
            unit_price=data.unit_price,
            discount_percent=data.discount_percent,
            is_optional=data.is_optional,
            sort_order=data.sort_order if data.sort_order else sort_order,
        )
        item.calculate_total()
        return item

    def _create_term_option(self, proposal_id: str, data, sort_order: int) -> ProposalTermOption:
        """Cria opção de prazo/mensalidade da proposta (multi-prazo) — sprint94."""
        return ProposalTermOption(
            id=str(uuid4()),
            proposal_id=proposal_id,
            term_months=data.term_months,
            monthly_value=data.monthly_value,
            composition=data.composition,
            is_recommended=data.is_recommended,
            sort_order=data.sort_order if data.sort_order else sort_order,
        )

    async def get_by_id(self, proposal_id: str) -> Proposal | None:
        """
        Busca proposta por ID.

        Args:
            proposal_id: ID da proposta

        Returns:
            Proposal ou None
        """
        result = await self.db.execute(
            select(Proposal)
            .options(selectinload(Proposal.items), selectinload(Proposal.term_options))
            .where(Proposal.id == proposal_id, Proposal.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_by_number(self, number: str) -> Proposal | None:
        """Busca proposta por numero."""
        result = await self.db.execute(
            select(Proposal)
            .options(selectinload(Proposal.items))
            .where(Proposal.number == number, Proposal.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        filters: ProposalFilter | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Proposal], int]:
        """
        Lista propostas com filtros e paginacao.

        Args:
            filters: Filtros de busca
            page: Pagina atual
            page_size: Itens por pagina

        Returns:
            Tupla (proposals, total)
        """
        query = select(Proposal).where(Proposal.is_active.is_(True))

        if filters:
            query = self._apply_filters(query, filters)

        # Count total
        count_query = select(func.count(Proposal.id)).where(Proposal.is_active.is_(True))
        if filters:
            count_query = self._apply_filters(count_query, filters)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(Proposal.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        proposals = list(result.scalars().all())

        return proposals, total

    def _apply_filters(self, query, filters: ProposalFilter):  # pylint: disable=too-many-branches
        """Aplica filtros a query."""
        if filters.status:
            query = query.where(Proposal.status == filters.status.value)

        if filters.proposal_type:
            query = query.where(Proposal.proposal_type == filters.proposal_type.value)

        if filters.opportunity_id:
            query = query.where(Proposal.opportunity_id == filters.opportunity_id)

        if filters.created_by_id:
            query = query.where(Proposal.created_by_id == filters.created_by_id)

        if filters.is_expired is not None:
            today = date.today()
            if filters.is_expired:
                query = query.where(Proposal.valid_until < today)
            else:
                query = query.where(or_(Proposal.valid_until >= today, Proposal.valid_until.is_(None)))

        if filters.min_value is not None:
            query = query.where(Proposal.total >= filters.min_value)

        if filters.max_value is not None:
            query = query.where(Proposal.total <= filters.max_value)

        if filters.client_name:
            query = query.where(Proposal.client_name.ilike(f"%{filters.client_name}%"))

        if filters.date_from:
            query = query.where(Proposal.issue_date >= filters.date_from)

        if filters.date_to:
            query = query.where(Proposal.issue_date <= filters.date_to)

        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    Proposal.number.ilike(search_term),
                    Proposal.title.ilike(search_term),
                    Proposal.client_name.ilike(search_term),
                    Proposal.client_email.ilike(search_term),
                    Proposal.client_company.ilike(search_term),
                )
            )

        return query

    async def update(self, proposal_id: str, data: ProposalUpdate) -> Proposal | None:
        """
        Atualiza uma proposta.

        Args:
            proposal_id: ID da proposta
            data: Dados para atualizacao

        Returns:
            Proposal atualizada ou None
        """
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            return None

        # Nao permitir edicao de propostas fechadas
        if proposal.is_closed:
            logger.warning(f"Tentativa de editar proposta fechada: {proposal_id}")
            return None

        # Atualizar campos
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "proposal_type" and value or field == "discount_type" and value:
                setattr(proposal, field, value.value)
            else:
                setattr(proposal, field, value)

        proposal.updated_at = datetime.utcnow()

        # Recalcular totais
        proposal.calculate_totals()

        await self.db.commit()
        await self.db.refresh(proposal, ["items", "term_options"])

        logger.info(f"Proposal atualizada: {proposal.id}")
        return proposal

    async def add_item(self, proposal_id: str, item_data: ProposalItemCreate) -> ProposalItem | None:
        """Adiciona item a proposta."""
        proposal = await self.get_by_id(proposal_id)
        if not proposal or proposal.is_closed:
            return None

        sort_order = len(proposal.items) if proposal.items else 0
        item = self._create_item(proposal_id, item_data, sort_order)
        self.db.add(item)

        await self.db.commit()
        await self.db.refresh(item)

        # Recalcular totais da proposta
        proposal.calculate_totals()
        await self.db.commit()

        logger.info(f"Item adicionado a proposta {proposal_id}: {item.id}")
        return item

    async def remove_item(self, proposal_id: str, item_id: str) -> bool:
        """Remove item da proposta."""
        proposal = await self.get_by_id(proposal_id)
        if not proposal or proposal.is_closed:
            return False

        result = await self.db.execute(
            select(ProposalItem).where(
                ProposalItem.id == item_id,
                ProposalItem.proposal_id == proposal_id,
            )
        )
        item = result.scalar_one_or_none()

        if not item:
            return False

        await self.db.delete(item)
        await self.db.commit()

        # Recalcular totais
        await self.db.refresh(proposal, ["items", "term_options"])
        proposal.calculate_totals()
        await self.db.commit()

        logger.info(f"Item removido da proposta {proposal_id}: {item_id}")
        return True

    async def update_status(
        self,
        proposal_id: str,
        status: ProposalStatus,
        notes: str | None = None,
        user_id: str | None = None,  # pylint: disable=unused-argument
    ) -> Proposal | None:
        """
        Atualiza status da proposta.

        Args:
            proposal_id: ID da proposta
            status: Novo status
            notes: Observacoes
            user_id: ID do usuario que alterou

        Returns:
            Proposal atualizada ou None
        """
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            return None

        old_status = proposal.status
        proposal.status = status.value

        # Atualizar campos especificos por status
        if status == ProposalStatus.SENT:
            proposal.sent_at = datetime.utcnow()
        elif status == ProposalStatus.VIEWED:
            proposal.viewed_at = datetime.utcnow()
        elif status in (ProposalStatus.ACCEPTED, ProposalStatus.REJECTED):
            proposal.responded_at = datetime.utcnow()
            if status == ProposalStatus.REJECTED and notes:
                proposal.rejection_reason = notes

        proposal.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(proposal, ["items", "term_options"])

        logger.info(f"Proposal {proposal_id} status: {old_status} -> {status.value}")
        return proposal

    async def submit_for_approval(
        self,
        proposal_id: str,
        user_id: str | None = None,  # pylint: disable=unused-argument
    ) -> Proposal | None:
        """Submete proposta para aprovacao."""
        proposal = await self.get_by_id(proposal_id)
        if not proposal or not proposal.is_draft:
            return None

        proposal.status = ProposalStatus.PENDING_APPROVAL.value
        proposal.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(proposal, ["items", "term_options"])

        logger.info(f"Proposal {proposal_id} submetida para aprovacao")
        return proposal

    async def process_approval(
        self,
        proposal_id: str,
        data: ProposalApprovalRequest,
        user_id: str,
    ) -> Proposal | None:
        """
        Processa aprovacao/rejeicao de proposta.

        Args:
            proposal_id: ID da proposta
            data: Dados da aprovacao
            user_id: ID do aprovador

        Returns:
            Proposal atualizada ou None
        """
        proposal = await self.get_by_id(proposal_id)
        if not proposal or not proposal.is_pending:
            return None

        # Registrar aprovacao
        approval = ProposalApproval(
            id=str(uuid4()),
            proposal_id=proposal_id,
            user_id=user_id,
            action=data.action.value,
            comments=data.comments,
        )
        self.db.add(approval)

        # Atualizar status baseado na acao
        if data.action == ApprovalAction.APPROVE:
            proposal.status = ProposalStatus.APPROVED.value
            proposal.approved_by_id = user_id
            proposal.approved_at = datetime.utcnow()
        elif data.action == ApprovalAction.REJECT:
            proposal.status = ProposalStatus.DRAFT.value
            if data.comments:
                existing = proposal.notes or ""
                proposal.notes = f"{existing}\n[REVISAO] {data.comments}".strip()
        elif data.action == ApprovalAction.REQUEST_CHANGES:
            proposal.status = ProposalStatus.PENDING_REVIEW.value

        proposal.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(proposal, ["items", "term_options"])

        logger.info(f"Proposal {proposal_id} aprovacao: {data.action.value}")
        return proposal

    async def create_new_version(self, proposal_id: str, created_by_id: str | None = None) -> Proposal | None:
        """
        Cria nova versao da proposta.

        Args:
            proposal_id: ID da proposta original
            created_by_id: ID do usuario

        Returns:
            Nova versao da proposta
        """
        original = await self.get_by_id(proposal_id)
        if not original:
            return None

        # Criar copia
        new_proposal = Proposal(
            id=str(uuid4()),
            number=original.number,  # Mesmo numero
            version=original.version + 1,
            parent_id=original.id,
            opportunity_id=original.opportunity_id,
            template_id=original.template_id,
            client_name=original.client_name,
            client_email=original.client_email,
            client_phone=original.client_phone,
            client_company=original.client_company,
            client_document=original.client_document,
            client_address=original.client_address,
            title=original.title,
            description=original.description,
            proposal_type=original.proposal_type,
            terms_conditions=original.terms_conditions,
            payment_terms=original.payment_terms,
            payment_conditions=original.payment_conditions,
            installments=original.installments,
            notes=original.notes,
            discount_type=original.discount_type,
            discount_value=original.discount_value,
            discount_reason=original.discount_reason,
            taxes=original.taxes,
            valid_until=date.today() + timedelta(days=30),
            status=ProposalStatus.DRAFT.value,
            created_by_id=created_by_id,
        )

        self.db.add(new_proposal)
        await self.db.flush()

        # Copiar itens
        for item in original.items:
            new_item = ProposalItem(
                id=str(uuid4()),
                proposal_id=new_proposal.id,
                code=item.code,
                name=item.name,
                description=item.description,
                unit=item.unit,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount_percent=item.discount_percent,
                total=item.total,
                sort_order=item.sort_order,
                is_optional=item.is_optional,
            )
            self.db.add(new_item)

        await self.db.commit()
        await self.db.refresh(new_proposal, ["items", "term_options"])

        new_proposal.calculate_totals()
        await self.db.commit()

        logger.info(f"Nova versao criada: {new_proposal.id} (v{new_proposal.version})")
        return new_proposal

    async def delete(self, proposal_id: str) -> bool:
        """Soft delete de proposta."""
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            return False

        proposal.is_active = False
        proposal.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(f"Proposal deletada (soft): {proposal.id}")
        return True

    async def get_stats(  # pylint: disable=too-many-locals
        self, created_by_id: str | None = None
    ) -> ProposalStats:
        """
        Obtem estatisticas de propostas.

        Args:
            created_by_id: Filtrar por criador

        Returns:
            Estatisticas
        """
        base_query = select(Proposal).where(Proposal.is_active.is_(True))

        if created_by_id:
            base_query = base_query.where(Proposal.created_by_id == created_by_id)

        result = await self.db.execute(base_query)
        proposals = list(result.scalars().all())

        if not proposals:
            return ProposalStats(
                total_proposals=0,
                draft_count=0,
                pending_count=0,
                sent_count=0,
                accepted_count=0,
                rejected_count=0,
                expired_count=0,
                total_value=0.0,
                accepted_value=0.0,
                pending_value=0.0,
                acceptance_rate=0.0,
                avg_proposal_value=0.0,
                avg_response_time_days=0.0,
                by_status={},
                by_type={},
            )

        # Calcular estatisticas
        draft = pending = sent = accepted = rejected = expired = 0
        total_value = accepted_value = pending_value = 0.0
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        response_times = []

        for p in proposals:
            total_value += p.total

            by_status[p.status] = by_status.get(p.status, 0) + 1
            by_type[p.proposal_type] = by_type.get(p.proposal_type, 0) + 1

            if p.status == ProposalStatus.DRAFT.value:
                draft += 1
            elif p.status in (
                ProposalStatus.PENDING_REVIEW.value,
                ProposalStatus.PENDING_APPROVAL.value,
            ):
                pending += 1
                pending_value += p.total
            elif p.status in (ProposalStatus.SENT.value, ProposalStatus.VIEWED.value):
                sent += 1
                pending_value += p.total
            elif p.status == ProposalStatus.ACCEPTED.value:
                accepted += 1
                accepted_value += p.total
                if p.sent_at and p.responded_at:
                    days = (p.responded_at - p.sent_at).days
                    response_times.append(days)
            elif p.status == ProposalStatus.REJECTED.value:
                rejected += 1
                if p.sent_at and p.responded_at:
                    days = (p.responded_at - p.sent_at).days
                    response_times.append(days)
            elif p.status == ProposalStatus.EXPIRED.value:
                expired += 1

        total_responded = accepted + rejected
        acceptance_rate = (accepted / total_responded * 100) if total_responded > 0 else 0.0
        avg_value = total_value / len(proposals) if proposals else 0.0
        avg_response = sum(response_times) / len(response_times) if response_times else 0.0

        return ProposalStats(
            total_proposals=len(proposals),
            draft_count=draft,
            pending_count=pending,
            sent_count=sent,
            accepted_count=accepted,
            rejected_count=rejected,
            expired_count=expired,
            total_value=total_value,
            accepted_value=accepted_value,
            pending_value=pending_value,
            acceptance_rate=acceptance_rate,
            avg_proposal_value=avg_value,
            avg_response_time_days=avg_response,
            by_status=by_status,
            by_type=by_type,
        )

    # ============== Template Methods ==============

    async def create_template(self, data: ProposalTemplateCreate) -> ProposalTemplate:
        """Cria template de proposta."""
        template = ProposalTemplate(
            id=str(uuid4()),
            name=data.name,
            description=data.description,
            default_title=data.default_title,
            default_description=data.default_description,
            terms_conditions=data.terms_conditions,
            payment_terms=data.payment_terms,
            validity_days=data.validity_days,
            proposal_type=data.proposal_type.value,
            header_html=data.header_html,
            footer_html=data.footer_html,
            css_styles=data.css_styles,
            is_default=data.is_default,
        )

        # Se for default, remover flag dos outros
        if data.is_default:
            await self.db.execute(select(ProposalTemplate).where(ProposalTemplate.is_default.is_(True)))
            # Reset all defaults
            result = await self.db.execute(select(ProposalTemplate).where(ProposalTemplate.is_default.is_(True)))
            for t in result.scalars().all():
                t.is_default = False

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"Template criado: {template.id} ({template.name})")
        return template

    async def get_template_by_id(self, template_id: str) -> ProposalTemplate | None:
        """Busca template por ID."""
        result = await self.db.execute(
            select(ProposalTemplate).where(
                ProposalTemplate.id == template_id,
                ProposalTemplate.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_templates(self) -> builtins.list[ProposalTemplate]:
        """Lista todos os templates ativos."""
        result = await self.db.execute(
            select(ProposalTemplate).where(ProposalTemplate.is_active.is_(True)).order_by(ProposalTemplate.name)
        )
        return list(result.scalars().all())

    async def update_template(self, template_id: str, data: ProposalTemplateUpdate) -> ProposalTemplate | None:
        """Atualiza template."""
        template = await self.get_template_by_id(template_id)
        if not template:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "proposal_type" and value:
                setattr(template, field, value.value)
            else:
                setattr(template, field, value)

        template.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"Template atualizado: {template.id}")
        return template

    async def delete_template(self, template_id: str) -> bool:
        """Soft delete de template."""
        template = await self.get_template_by_id(template_id)
        if not template:
            return False

        template.is_active = False
        template.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(f"Template deletado (soft): {template.id}")
        return True
