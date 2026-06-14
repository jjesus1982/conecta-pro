"""
Repositório para Gestão de Contratos.

CRUD e operações de banco de dados para:
- Contratos
- Templates
- Aditivos
- Relatórios SLA
"""

import builtins
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.crm.models.contract import (
    AddendumType,
    Contract,
    ContractAddendum,
    ContractItem,
    ContractSLAReport,
    ContractStatus,
    ContractTemplate,
    ContractType,
)
from modules.crm.schemas.contract import (
    ContractAddendumCreate,
    ContractCreate,
    ContractFilter,
    ContractItemCreate,
    ContractItemUpdate,
    ContractSLAReportCreate,
    ContractStats,
    ContractTemplateCreate,
    ContractTemplateUpdate,
    ContractUpdate,
)


class ContractRepository:
    """Repositório para operações de contrato."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============== Contract CRUD ==============

    async def create(
        self,
        data: ContractCreate,
        created_by_id: str,
    ) -> Contract:
        """Cria um novo contrato."""
        # Gerar número do contrato
        sequence = await self._get_next_contract_sequence()
        contract_number = Contract.generate_number(sequence)

        # Calcular total se não informado
        total_value = data.total_value
        if total_value is None and data.end_date:
            months = self._calculate_months(data.start_date, data.end_date)
            total_value = data.monthly_value * Decimal(str(months))

        contract = Contract(
            id=uuid.uuid4(),
            contract_number=contract_number,
            client_id=uuid.UUID(data.client_id),
            opportunity_id=uuid.UUID(data.opportunity_id) if data.opportunity_id else None,
            proposal_id=uuid.UUID(data.proposal_id) if data.proposal_id else None,
            template_id=uuid.UUID(data.template_id) if data.template_id else None,
            contract_type=data.contract_type,
            status=ContractStatus.DRAFT,
            name=data.name,
            description=data.description,
            monthly_value=data.monthly_value,
            total_value=total_value or Decimal("0"),
            setup_fee=data.setup_fee,
            start_date=data.start_date,
            end_date=data.end_date,
            grace_period_days=data.grace_period_days,
            notice_period_days=data.notice_period_days,
            auto_renewal=data.auto_renewal,
            renewal_period_months=data.renewal_period_months,
            renewal_notification_days=data.renewal_notification_days,
            adjustment_enabled=data.adjustment_enabled,
            adjustment_index=data.adjustment_index,
            adjustment_fixed_percent=data.adjustment_fixed_percent,
            adjustment_base_date=data.adjustment_base_date or data.start_date,
            has_sla=data.has_sla,
            sla_config=data.sla_config,
            content=data.content,
            clauses=data.clauses,
            signature_required=data.signature_required,
            signature_provider=data.signature_provider,
            commercial_manager_id=data.commercial_manager_id,
            account_manager_id=data.account_manager_id,
            created_by=created_by_id,
        )

        # Calcular próxima data de reajuste
        if contract.adjustment_enabled:
            contract.next_adjustment_date = contract.calculate_next_adjustment_date()

        self.db.add(contract)
        await self.db.commit()
        # Eager-load das relacoes serializadas (items/addendums) dentro do greenlet,
        # senao ContractDetailResponse.model_validate faz lazy-load async -> MissingGreenlet 500.
        await self.db.refresh(contract, ["items", "addendums"])

        return contract

    async def get_by_id(self, contract_id: str) -> Contract | None:
        """Busca contrato por ID com itens."""
        result = await self.db.execute(
            select(Contract)
            .options(
                selectinload(Contract.items),
                selectinload(Contract.addendums),
            )
            .where(
                and_(
                    Contract.id == uuid.UUID(contract_id),
                    Contract.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_number(self, contract_number: str) -> Contract | None:
        """Busca contrato pelo número."""
        result = await self.db.execute(
            select(Contract)
            .options(selectinload(Contract.items))
            .where(
                and_(
                    Contract.contract_number == contract_number,
                    Contract.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(  # pylint: disable=too-many-branches
        self,
        filters: ContractFilter | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Contract], int]:
        """Lista contratos com filtros e paginação."""
        query = select(Contract).where(Contract.is_active.is_(True))

        if filters:
            if filters.status:
                query = query.where(Contract.status == filters.status)
            if filters.contract_type:
                query = query.where(Contract.contract_type == filters.contract_type)
            if filters.client_id:
                query = query.where(Contract.client_id == uuid.UUID(filters.client_id))
            if filters.commercial_manager_id:
                query = query.where(Contract.commercial_manager_id == uuid.UUID(filters.commercial_manager_id))
            if filters.account_manager_id:
                query = query.where(Contract.account_manager_id == uuid.UUID(filters.account_manager_id))
            if filters.has_sla is not None:
                query = query.where(Contract.has_sla == filters.has_sla)
            if filters.min_value is not None:
                query = query.where(Contract.monthly_value >= filters.min_value)
            if filters.max_value is not None:
                query = query.where(Contract.monthly_value <= filters.max_value)
            if filters.start_date_from:
                query = query.where(Contract.start_date >= filters.start_date_from)
            if filters.start_date_to:
                query = query.where(Contract.start_date <= filters.start_date_to)
            if filters.end_date_from:
                query = query.where(Contract.end_date >= filters.end_date_from)
            if filters.end_date_to:
                query = query.where(Contract.end_date <= filters.end_date_to)
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.where(
                    or_(
                        Contract.name.ilike(search_term),
                        Contract.contract_number.ilike(search_term),
                        Contract.description.ilike(search_term),
                    )
                )

        # Total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginação
        query = query.order_by(Contract.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        contracts = list(result.scalars().all())

        return contracts, total

    async def update(
        self,
        contract_id: str,
        data: ContractUpdate,
    ) -> Contract | None:
        """Atualiza um contrato."""
        contract = await self.get_by_id(contract_id)

        if not contract:
            return None

        # Apenas rascunhos podem ser editados completamente
        if contract.status not in [ContractStatus.DRAFT, ContractStatus.SUSPENDED]:
            # Contratos ativos permitem apenas algumas atualizações
            if contract.status == ContractStatus.ACTIVE:
                allowed_fields = [
                    "description",
                    "account_manager_id",
                    "commercial_manager_id",
                    "sla_config",
                ]
                for field, value in data.model_dump(exclude_unset=True).items():
                    if field in allowed_fields and value is not None:
                        setattr(contract, field, value)
            else:
                return None
        else:
            # Atualiza todos os campos
            for field, value in data.model_dump(exclude_unset=True).items():
                if value is not None:
                    if field.endswith("_id") and value:
                        value = uuid.UUID(value)
                    setattr(contract, field, value)

        contract.updated_at = datetime.utcnow()

        # Recalcular próxima data de reajuste se necessário
        if data.adjustment_enabled is not None or data.adjustment_index is not None:
            contract.next_adjustment_date = contract.calculate_next_adjustment_date()

        await self.db.commit()
        # PUT retorna ContractDetailResponse (serializa items) -> eager-load no greenlet.
        await self.db.refresh(contract, ["items", "addendums"])

        return contract

    async def update_status(
        self,
        contract_id: str,
        new_status: ContractStatus,
        user_id: str | None = None,  # pylint: disable=unused-argument
    ) -> Contract | None:
        """Atualiza status do contrato."""
        contract = await self.get_by_id(contract_id)

        if not contract:
            return None

        # Validar transição de status
        valid_transitions = {
            ContractStatus.DRAFT: [ContractStatus.PENDING_SIGNATURE, ContractStatus.CANCELLED],
            ContractStatus.PENDING_SIGNATURE: [
                ContractStatus.ACTIVE,
                ContractStatus.DRAFT,
                ContractStatus.CANCELLED,
            ],
            ContractStatus.ACTIVE: [
                ContractStatus.SUSPENDED,
                ContractStatus.TERMINATED,
                ContractStatus.CANCELLED,
            ],
            ContractStatus.SUSPENDED: [ContractStatus.ACTIVE, ContractStatus.TERMINATED],
        }

        if new_status not in valid_transitions.get(contract.status, []):
            return None

        contract.status = new_status
        contract.updated_at = datetime.utcnow()

        if new_status == ContractStatus.ACTIVE and contract.signature_required:
            contract.signed_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(contract)

        return contract

    async def delete(self, contract_id: str) -> bool:
        """Remove contrato (soft delete)."""
        contract = await self.get_by_id(contract_id)

        if not contract:
            return False

        # Apenas rascunhos podem ser excluídos
        if contract.status != ContractStatus.DRAFT:
            return False

        contract.is_active = False
        contract.updated_at = datetime.utcnow()

        await self.db.commit()
        return True

    async def get_stats(  # pylint: disable=too-many-locals
        self,
        client_id: str | None = None,
        commercial_manager_id: str | None = None,
    ) -> ContractStats:
        """Calcula estatísticas de contratos."""
        base_query = select(Contract).where(Contract.is_active.is_(True))

        if client_id:
            base_query = base_query.where(Contract.client_id == uuid.UUID(client_id))
        if commercial_manager_id:
            base_query = base_query.where(Contract.commercial_manager_id == uuid.UUID(commercial_manager_id))

        result = await self.db.execute(base_query)
        contracts = list(result.scalars().all())

        total = len(contracts)
        active = len([c for c in contracts if c.status == ContractStatus.ACTIVE])
        total_revenue = sum(c.monthly_value for c in contracts if c.status == ContractStatus.ACTIVE)
        avg_value = total_revenue / active if active > 0 else Decimal("0")
        expiring = len([c for c in contracts if c.is_expiring_soon])
        needs_adj = len([c for c in contracts if c.needs_adjustment])

        by_status = {}
        for status in ContractStatus:
            count = len([c for c in contracts if c.status == status])
            if count > 0:
                by_status[status.value] = count

        by_type = {}
        for ctype in ContractType:
            count = len([c for c in contracts if c.contract_type == ctype])
            if count > 0:
                by_type[ctype.value] = count

        return ContractStats(
            total_contracts=total,
            active_contracts=active,
            total_monthly_revenue=total_revenue,
            average_contract_value=avg_value,
            expiring_soon=expiring,
            needs_adjustment=needs_adj,
            by_status=by_status,
            by_type=by_type,
        )

    # ============== Contract Item ==============

    async def add_item(
        self,
        contract_id: str,
        data: ContractItemCreate,
    ) -> ContractItem | None:
        """Adiciona item ao contrato."""
        contract = await self.get_by_id(contract_id)

        if not contract or contract.status != ContractStatus.DRAFT:
            return None

        total_price = Decimal(str(data.quantity)) * data.unit_price

        item = ContractItem(
            id=uuid.uuid4(),
            contract_id=contract.id,
            service_type=data.service_type,
            service_name=data.service_name,
            description=data.description,
            quantity=data.quantity,
            unit_price=data.unit_price,
            total_price=total_price,
            notes=data.notes,
        )

        self.db.add(item)

        # Atualizar valor mensal do contrato
        contract.monthly_value += total_price
        contract.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(item)

        return item

    async def update_item(
        self,
        contract_id: str,
        item_id: str,
        data: ContractItemUpdate,
    ) -> ContractItem | None:
        """Atualiza item do contrato."""
        contract = await self.get_by_id(contract_id)

        if not contract or contract.status != ContractStatus.DRAFT:
            return None

        result = await self.db.execute(
            select(ContractItem).where(
                and_(
                    ContractItem.id == uuid.UUID(item_id),
                    ContractItem.contract_id == uuid.UUID(contract_id),
                    ContractItem.is_active.is_(True),
                )
            )
        )
        item = result.scalar_one_or_none()

        if not item:
            return None

        old_total = item.total_price

        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(item, field, value)

        # Recalcular total
        item.total_price = Decimal(str(item.quantity)) * item.unit_price
        item.updated_at = datetime.utcnow()

        # Atualizar valor do contrato
        contract.monthly_value = contract.monthly_value - old_total + item.total_price
        contract.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(item)

        return item

    async def remove_item(self, contract_id: str, item_id: str) -> bool:
        """Remove item do contrato."""
        contract = await self.get_by_id(contract_id)

        if not contract or contract.status != ContractStatus.DRAFT:
            return False

        result = await self.db.execute(
            select(ContractItem).where(
                and_(
                    ContractItem.id == uuid.UUID(item_id),
                    ContractItem.contract_id == uuid.UUID(contract_id),
                    ContractItem.is_active.is_(True),
                )
            )
        )
        item = result.scalar_one_or_none()

        if not item:
            return False

        # Atualizar valor do contrato
        contract.monthly_value -= item.total_price
        contract.updated_at = datetime.utcnow()

        item.is_active = False
        item.updated_at = datetime.utcnow()

        await self.db.commit()
        return True

    # ============== Contract Addendum ==============

    async def create_addendum(
        self,
        contract_id: str,
        data: ContractAddendumCreate,
        created_by_id: str,
    ) -> ContractAddendum | None:
        """Cria aditivo do contrato."""
        contract = await self.get_by_id(contract_id)

        if not contract or contract.status != ContractStatus.ACTIVE:
            return None

        sequence = await self._get_next_addendum_sequence(contract_id)
        addendum_number = ContractAddendum.generate_number(sequence)

        addendum = ContractAddendum(
            id=uuid.uuid4(),
            contract_id=contract.id,
            addendum_number=addendum_number,
            addendum_type=data.addendum_type,
            previous_value=contract.monthly_value,
            new_value=data.new_value,
            adjustment_percent=data.adjustment_percent,
            adjustment_index=data.adjustment_index,
            effective_date=data.effective_date,
            description=data.description,
            reason=data.reason,
            created_by=uuid.UUID(created_by_id),
        )

        self.db.add(addendum)
        await self.db.commit()
        await self.db.refresh(addendum)

        return addendum

    async def sign_addendum(
        self,
        addendum_id: str,
        signature_document_id: str,
    ) -> ContractAddendum | None:
        """Assina aditivo e aplica alterações."""
        result = await self.db.execute(
            select(ContractAddendum)
            .options(selectinload(ContractAddendum.contract))
            .where(
                and_(
                    ContractAddendum.id == uuid.UUID(addendum_id),
                    ContractAddendum.is_active.is_(True),
                )
            )
        )
        addendum = result.scalar_one_or_none()

        if not addendum or addendum.signed:
            return None

        contract = addendum.contract

        addendum.signed = True
        addendum.signed_at = datetime.utcnow()
        addendum.signature_document_id = signature_document_id
        addendum.updated_at = datetime.utcnow()

        # Aplicar alterações ao contrato
        if addendum.addendum_type == AddendumType.ADJUSTMENT and addendum.new_value:
            contract.monthly_value = addendum.new_value
            contract.last_adjustment_date = addendum.effective_date
            contract.next_adjustment_date = contract.calculate_next_adjustment_date()

        contract.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(addendum)

        return addendum

    async def list_addendums(self, contract_id: str) -> builtins.list[ContractAddendum]:
        """Lista aditivos do contrato."""
        result = await self.db.execute(
            select(ContractAddendum)
            .where(
                and_(
                    ContractAddendum.contract_id == uuid.UUID(contract_id),
                    ContractAddendum.is_active.is_(True),
                )
            )
            .order_by(ContractAddendum.created_at.desc())
        )
        return list(result.scalars().all())

    # ============== Contract Template ==============

    async def create_template(self, data: ContractTemplateCreate) -> ContractTemplate:
        """Cria template de contrato."""
        template = ContractTemplate(
            id=uuid.uuid4(),
            name=data.name,
            description=data.description,
            service_type=data.service_type,
            content_template=data.content_template,
            clauses=data.clauses,
            variables=data.variables,
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        return template

    async def get_template_by_id(self, template_id: str) -> ContractTemplate | None:
        """Busca template por ID."""
        result = await self.db.execute(
            select(ContractTemplate).where(
                and_(
                    ContractTemplate.id == uuid.UUID(template_id),
                    ContractTemplate.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        service_type: str | None = None,
        approved_only: bool = False,
    ) -> builtins.list[ContractTemplate]:
        """Lista templates disponíveis."""
        query = select(ContractTemplate).where(ContractTemplate.is_active.is_(True))

        if service_type:
            query = query.where(ContractTemplate.service_type == service_type)
        if approved_only:
            query = query.where(ContractTemplate.approved_by_legal.is_(True))

        query = query.order_by(ContractTemplate.name)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_template(
        self,
        template_id: str,
        data: ContractTemplateUpdate,
    ) -> ContractTemplate | None:
        """Atualiza template."""
        template = await self.get_template_by_id(template_id)

        if not template:
            return None

        for field, value in data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(template, field, value)

        # Incrementa versão se conteúdo mudou
        if data.content_template is not None:
            template.version += 1
            template.approved_by_legal = False
            template.approved_at = None
            template.approved_by = None

        template.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(template)

        return template

    async def approve_template(
        self,
        template_id: str,
        approved_by_id: str,
    ) -> ContractTemplate | None:
        """Aprova template juridicamente."""
        template = await self.get_template_by_id(template_id)

        if not template:
            return None

        template.approved_by_legal = True
        template.approved_at = datetime.utcnow()
        template.approved_by = uuid.UUID(approved_by_id)
        template.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(template)

        return template

    async def delete_template(self, template_id: str) -> bool:
        """Remove template (soft delete)."""
        template = await self.get_template_by_id(template_id)

        if not template:
            return False

        template.is_active = False
        template.updated_at = datetime.utcnow()

        await self.db.commit()
        return True

    # ============== SLA Reports ==============

    async def create_sla_report(
        self,
        contract_id: str,
        data: ContractSLAReportCreate,
        generated_by_id: str,
    ) -> ContractSLAReport | None:
        """Cria relatório de SLA mensal."""
        contract = await self.get_by_id(contract_id)

        if not contract or not contract.has_sla:
            return None

        # Verificar se já existe relatório para o período
        existing = await self.db.execute(
            select(ContractSLAReport).where(
                and_(
                    ContractSLAReport.contract_id == uuid.UUID(contract_id),
                    ContractSLAReport.year == data.year,
                    ContractSLAReport.month == data.month,
                    ContractSLAReport.is_active.is_(True),
                )
            )
        )
        if existing.scalar_one_or_none():
            return None

        report = ContractSLAReport(
            id=uuid.uuid4(),
            contract_id=contract.id,
            year=data.year,
            month=data.month,
            indicators=[i.model_dump() for i in data.indicators],
            overall_score=data.overall_score,
            penalty_applied=data.penalty_applied,
            penalty_percent=data.penalty_percent or Decimal("0"),
            penalty_amount=data.penalty_amount or Decimal("0"),
            status="draft",
            generated_by=uuid.UUID(generated_by_id),
        )

        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        return report

    async def approve_sla_report(
        self,
        report_id: str,
        approved_by_id: str,
        disputed: bool = False,
    ) -> ContractSLAReport | None:
        """Aprova ou disputa relatório de SLA."""
        result = await self.db.execute(
            select(ContractSLAReport).where(
                and_(
                    ContractSLAReport.id == uuid.UUID(report_id),
                    ContractSLAReport.is_active.is_(True),
                )
            )
        )
        report = result.scalar_one_or_none()

        if not report or report.status != "draft":
            return None

        report.status = "disputed" if disputed else "approved"
        report.approved_at = datetime.utcnow()
        report.approved_by = uuid.UUID(approved_by_id)

        await self.db.commit()
        await self.db.refresh(report)

        return report

    async def list_sla_reports(
        self,
        contract_id: str,
        year: int | None = None,
    ) -> builtins.list[ContractSLAReport]:
        """Lista relatórios de SLA do contrato."""
        query = select(ContractSLAReport).where(
            and_(
                ContractSLAReport.contract_id == uuid.UUID(contract_id),
                ContractSLAReport.is_active.is_(True),
            )
        )

        if year:
            query = query.where(ContractSLAReport.year == year)

        query = query.order_by(
            ContractSLAReport.year.desc(),
            ContractSLAReport.month.desc(),
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ============== Helpers ==============

    async def _get_next_contract_sequence(self) -> int:
        """Obtém próximo número de sequência para contrato."""
        year = date.today().year
        pattern = f"CONT-{year}-%"

        result = await self.db.execute(
            select(func.count()).select_from(Contract).where(Contract.contract_number.like(pattern))
        )
        count = result.scalar() or 0
        return count + 1

    async def _get_next_addendum_sequence(self, contract_id: str) -> int:
        """Obtém próximo número de sequência para aditivo."""
        result = await self.db.execute(
            select(func.count())
            .select_from(ContractAddendum)
            .where(ContractAddendum.contract_id == uuid.UUID(contract_id))
        )
        count = result.scalar() or 0
        return count + 1

    def _calculate_months(self, start: date, end: date) -> int:
        """Calcula número de meses entre datas."""
        return (end.year - start.year) * 12 + (end.month - start.month) + 1
