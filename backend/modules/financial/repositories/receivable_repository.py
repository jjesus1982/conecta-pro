"""Repository para contas a receber."""

import builtins
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.financial.models.billing_rule import BillingRule, BillingRuleStatus
from modules.financial.models.customer import Customer, CustomerStatus
from modules.financial.models.receivable_account import (
    ReceivableAccount,
    ReceivableStatus,
)
from modules.financial.models.receivable_category import ReceivableCategory
from modules.financial.models.receivable_installment import (
    InstallmentStatus,
    ReceivableInstallment,
)
from modules.financial.models.receivable_payment import PaymentStatus, ReceivablePayment
from modules.financial.schemas.receivable import (
    BillingRuleCreate,
    BillingRuleFilter,
    BillingRuleUpdate,
    CustomerCreate,
    CustomerFilter,
    CustomerUpdate,
    ReceivableAccountCreate,
    ReceivableAccountFilter,
    ReceivableAccountStats,
    ReceivableAccountUpdate,
    ReceivableCategoryCreate,
    ReceivableCategoryUpdate,
    ReceivableInstallmentUpdate,
    ReceivablePaymentCreate,
)


class CustomerRepository:
    """Repository para operacoes com clientes."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: CustomerCreate,
        user_id: UUID | None = None,
    ) -> Customer:
        """Cria um novo cliente."""
        customer = Customer(
            **data.model_dump(),
            created_by=user_id,
        )
        self.session.add(customer)
        await self.session.flush()
        await self.session.refresh(customer)
        return customer

    async def get_by_id(self, customer_id: UUID) -> Customer | None:
        """Busca cliente por ID."""
        result = await self.session.execute(
            select(Customer).where(
                and_(
                    Customer.id == customer_id,
                    Customer.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_cpf_cnpj(
        self,
        condominio_id: UUID,
        cpf_cnpj: str,
    ) -> Customer | None:
        """Busca cliente por CPF/CNPJ."""
        result = await self.session.execute(
            select(Customer).where(
                and_(
                    Customer.condominio_id == condominio_id,
                    Customer.cpf_cnpj == cpf_cnpj,
                    Customer.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_document(self, document: str) -> Customer | None:
        """Busca cliente por CPF/CNPJ (sem filtro de condominio)."""
        result = await self.session.execute(
            select(Customer).where(
                and_(
                    Customer.cpf_cnpj == document,
                    Customer.ativo.is_(True),
                )
            )
        )
        return result.scalars().first()

    async def get_by_morador(self, morador_id: UUID) -> Customer | None:
        """Busca cliente pelo ID do morador."""
        result = await self.session.execute(
            select(Customer).where(
                and_(
                    Customer.morador_id == morador_id,
                    Customer.ativo.is_(True),
                )
            )
        )
        return result.scalars().first()

    async def get_by_unidade(
        self,
        unidade_id: UUID,
    ) -> builtins.list[Customer]:
        """Busca clientes por unidade."""
        result = await self.session.execute(
            select(Customer)
            .where(
                and_(
                    Customer.unidade_id == unidade_id,
                    Customer.ativo.is_(True),
                )
            )
            .order_by(Customer.name)
        )
        return list(result.scalars().all())

    async def get_debtors(
        self,
        condominio_id: UUID,
        only_overdue: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[Customer]:
        """Lista clientes com divida ativa."""
        debt_condition = (
            Customer.overdue_debt > 0
            if only_overdue
            else or_(Customer.overdue_debt > 0, Customer.total_debt > 0)
        )
        query = (
            select(Customer)
            .where(
                and_(
                    Customer.condominio_id == condominio_id,
                    Customer.ativo.is_(True),
                    debt_condition,
                )
            )
            .order_by(Customer.overdue_debt.desc(), Customer.total_debt.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list(
        self,
        condominio_id: UUID,
        filters: CustomerFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[Customer]:
        """Lista clientes com filtros."""
        query = select(Customer).where(
            and_(
                Customer.condominio_id == condominio_id,
                Customer.ativo.is_(True),
            )
        )

        if filters:
            query = self._apply_filters(query, filters)

        query = query.order_by(Customer.name).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    def _apply_filters(self, query, filters: CustomerFilter):
        """Aplica filtros a query."""
        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    Customer.name.ilike(search_term),
                    Customer.cpf_cnpj.ilike(search_term),
                    Customer.email.ilike(search_term),
                )
            )

        if filters.customer_type:
            query = query.where(Customer.customer_type == filters.customer_type.value)

        if filters.status:
            query = query.where(Customer.status == filters.status.value)

        if filters.is_inadimplente is not None:
            if filters.is_inadimplente:
                query = query.where(Customer.overdue_debt > 0)
            else:
                query = query.where(Customer.overdue_debt == 0)

        if filters.is_blocked is not None:
            query = query.where(Customer.is_blocked == filters.is_blocked)

        if filters.unidade_id:
            query = query.where(Customer.unidade_id == filters.unidade_id)

        return query

    async def count(
        self,
        condominio_id: UUID,
        filters: CustomerFilter | None = None,
    ) -> int:
        """Conta clientes com filtros."""
        query = select(func.count(Customer.id)).where(
            and_(
                Customer.condominio_id == condominio_id,
                Customer.ativo.is_(True),
            )
        )

        if filters:
            query = self._apply_filters(query, filters)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        customer: Customer,
        data: CustomerUpdate,
    ) -> Customer:
        """Atualiza cliente."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(customer, field):
                setattr(customer, field, value)

        customer.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(customer)
        return customer

    async def delete(self, customer: Customer) -> None:
        """Deleta cliente (soft delete)."""
        customer.ativo = False
        customer.status = CustomerStatus.INATIVO.value
        customer.updated_at = datetime.utcnow()
        await self.session.flush()


class ReceivableCategoryRepository:
    """Repository para categorias de receita."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: ReceivableCategoryCreate,
        user_id: UUID | None = None,
    ) -> ReceivableCategory:
        """Cria uma nova categoria."""
        category = ReceivableCategory(
            **data.model_dump(),
            created_by=user_id,
        )
        self.session.add(category)
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def get_by_id(self, category_id: UUID) -> ReceivableCategory | None:
        """Busca categoria por ID."""
        result = await self.session.execute(
            select(ReceivableCategory)
            .where(
                and_(
                    ReceivableCategory.id == category_id,
                    ReceivableCategory.ativo.is_(True),  # noqa: E712
                )
            )
            .options(
                selectinload(ReceivableCategory.parent),
                selectinload(ReceivableCategory.children),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID,
        search: str | None = None,
        category_type=None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[ReceivableCategory]:
        """Lista categorias com filtros opcionais."""
        conditions = [ReceivableCategory.condominio_id == condominio_id]
        if is_active is None:
            conditions.append(ReceivableCategory.ativo.is_(True))  # noqa: E712
        else:
            conditions.append(ReceivableCategory.ativo.is_(is_active))  # noqa: E712
        if search:
            conditions.append(ReceivableCategory.name.ilike(f"%{search}%"))
        if category_type is not None:
            type_value = getattr(category_type, "value", category_type)
            conditions.append(ReceivableCategory.category_type == type_value)

        result = await self.session.execute(
            select(ReceivableCategory)
            .where(and_(*conditions))
            .options(
                selectinload(ReceivableCategory.parent),
                selectinload(ReceivableCategory.children),
            )
            .order_by(ReceivableCategory.display_order, ReceivableCategory.name)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_root_categories(
        self,
        condominio_id: UUID,
    ) -> builtins.list[ReceivableCategory]:
        """Lista categorias raiz (parent_id NULL) do condominio para a arvore."""
        result = await self.session.execute(
            select(ReceivableCategory)
            .where(
                and_(
                    ReceivableCategory.condominio_id == condominio_id,
                    ReceivableCategory.parent_id.is_(None),
                    ReceivableCategory.ativo.is_(True),  # noqa: E712
                )
            )
            .options(
                selectinload(ReceivableCategory.parent),
                selectinload(ReceivableCategory.children),
            )
            .order_by(ReceivableCategory.display_order, ReceivableCategory.name)
        )
        return list(result.scalars().all())

    async def get_children(
        self,
        category_id: UUID,
    ) -> builtins.list[ReceivableCategory]:
        """Lista subcategorias de uma categoria."""
        result = await self.session.execute(
            select(ReceivableCategory)
            .where(
                and_(
                    ReceivableCategory.parent_id == category_id,
                    ReceivableCategory.ativo.is_(True),  # noqa: E712
                )
            )
            .options(
                selectinload(ReceivableCategory.parent),
                selectinload(ReceivableCategory.children),
            )
            .order_by(ReceivableCategory.display_order, ReceivableCategory.name)
        )
        return list(result.scalars().all())

    async def update(
        self,
        category: ReceivableCategory,
        data: ReceivableCategoryUpdate,
    ) -> ReceivableCategory:
        """Atualiza categoria."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(category, field):
                setattr(category, field, value)

        category.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def delete(self, category: ReceivableCategory) -> None:
        """Deleta categoria (soft delete)."""
        category.ativo = False
        category.updated_at = datetime.utcnow()
        await self.session.flush()


class ReceivableAccountRepository:
    """Repository para operacoes com contas a receber."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: ReceivableAccountCreate,
        user_id: UUID | None = None,
    ) -> ReceivableAccount:
        """Cria uma nova conta a receber."""
        # Calcula valor liquido
        net_value = data.gross_value - data.discount_value + data.addition_value

        receivable = ReceivableAccount(
            condominio_id=data.condominio_id,
            description=data.description,
            document_number=data.document_number,
            receivable_type=data.receivable_type.value,
            priority=data.priority.value,
            customer_id=data.customer_id,
            unidade_id=data.unidade_id,
            morador_id=data.morador_id,
            category_id=data.category_id,
            gross_value=data.gross_value,
            discount_value=data.discount_value,
            addition_value=data.addition_value,
            net_value=net_value,
            remaining_value=net_value,
            interest_rate=data.interest_rate,
            penalty_rate=data.penalty_rate,
            grace_days=data.grace_days,
            issue_date=data.issue_date,
            due_date=data.due_date,
            competence_date=data.competence_date,
            total_installments=data.total_installments,
            is_recurring=data.is_recurring,
            recurrence_type=data.recurrence_type,
            recurrence_end_date=data.recurrence_end_date,
            cost_center=data.cost_center,
            tags=data.tags,
            notes=data.notes,
            created_by=user_id,
        )
        self.session.add(receivable)
        await self.session.flush()
        await self.session.refresh(receivable)

        # Cria parcelas se necessario
        if data.total_installments > 1:
            await self._create_installments(receivable, data.total_installments)

        return receivable

    async def _create_installments(
        self,
        receivable: ReceivableAccount,
        total: int,
    ) -> None:
        """Cria parcelas para a conta."""
        installment_value = receivable.net_value / total

        for i in range(1, total + 1):
            # Calcula data de vencimento (mensal)
            due_date = receivable.due_date
            if i > 1:
                month = receivable.due_date.month + (i - 1)
                year = receivable.due_date.year
                while month > 12:
                    month -= 12
                    year += 1
                day = min(receivable.due_date.day, 28)
                due_date = date(year, month, day)

            installment = ReceivableInstallment(
                receivable_account_id=receivable.id,
                condominio_id=receivable.condominio_id,
                installment_number=i,
                total_installments=total,
                original_value=installment_value,
                current_value=installment_value,
                due_date=due_date,
                interest_rate=receivable.interest_rate,
                penalty_rate=receivable.penalty_rate,
                grace_days=receivable.grace_days,
            )
            self.session.add(installment)

        await self.session.flush()

    async def get_by_id(
        self,
        receivable_id: UUID,
        with_relations: bool = False,
    ) -> ReceivableAccount | None:
        """Busca conta a receber por ID."""
        query = select(ReceivableAccount).where(
            and_(
                ReceivableAccount.id == receivable_id,
                ReceivableAccount.ativo.is_(True),  # noqa: E712
            )
        )

        if with_relations:
            query = query.options(
                selectinload(ReceivableAccount.customer),
                selectinload(ReceivableAccount.category),
                selectinload(ReceivableAccount.installments),
            )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID | None,
        filters: ReceivableAccountFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[ReceivableAccount]:
        """Lista contas a receber com filtros."""
        base_conditions = [ReceivableAccount.ativo.is_(True)]  # noqa: E712
        if condominio_id is not None:
            base_conditions.append(ReceivableAccount.condominio_id == condominio_id)
        query = select(ReceivableAccount).where(and_(*base_conditions))

        if filters:
            query = self._apply_filters(query, filters)

        query = (
            query.options(
                selectinload(ReceivableAccount.customer),
                selectinload(ReceivableAccount.category),
            )
            .order_by(ReceivableAccount.due_date)
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    def _apply_filters(self, query, filters: ReceivableAccountFilter):
        """Aplica filtros a query."""
        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    ReceivableAccount.description.ilike(search_term),
                    ReceivableAccount.document_number.ilike(search_term),
                    ReceivableAccount.code.ilike(search_term),
                )
            )

        if filters.customer_id:
            query = query.where(ReceivableAccount.customer_id == filters.customer_id)

        if filters.unidade_id:
            query = query.where(ReceivableAccount.unidade_id == filters.unidade_id)

        if filters.category_id:
            query = query.where(ReceivableAccount.category_id == filters.category_id)

        if filters.status:
            query = query.where(ReceivableAccount.status == filters.status.value)

        if filters.receivable_type:
            query = query.where(ReceivableAccount.receivable_type == filters.receivable_type.value)

        if filters.priority:
            query = query.where(ReceivableAccount.priority == filters.priority.value)

        if filters.due_date_start:
            query = query.where(ReceivableAccount.due_date >= filters.due_date_start)

        if filters.due_date_end:
            query = query.where(ReceivableAccount.due_date <= filters.due_date_end)

        if filters.payment_date_start:
            query = query.where(ReceivableAccount.payment_date >= filters.payment_date_start)

        if filters.payment_date_end:
            query = query.where(ReceivableAccount.payment_date <= filters.payment_date_end)

        if filters.is_overdue:
            today = date.today()
            query = query.where(
                and_(
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                        ]
                    ),
                )
            )

        if filters.has_boleto is not None:
            query = query.where(ReceivableAccount.boleto_generated == filters.has_boleto)

        if filters.has_pix is not None:
            query = query.where(ReceivableAccount.pix_generated == filters.has_pix)

        if filters.cost_center:
            query = query.where(ReceivableAccount.cost_center == filters.cost_center)

        if filters.min_value:
            query = query.where(ReceivableAccount.net_value >= filters.min_value)

        if filters.max_value:
            query = query.where(ReceivableAccount.net_value <= filters.max_value)

        if filters.tags:
            for tag in filters.tags:
                query = query.where(ReceivableAccount.tags.contains([tag]))

        return query

    async def count(
        self,
        condominio_id: UUID | None,
        filters: ReceivableAccountFilter | None = None,
    ) -> int:
        """Conta contas a receber com filtros."""
        base_conditions = [ReceivableAccount.ativo.is_(True)]  # noqa: E712
        if condominio_id is not None:
            base_conditions.append(ReceivableAccount.condominio_id == condominio_id)
        query = select(func.count(ReceivableAccount.id)).where(and_(*base_conditions))

        if filters:
            query = self._apply_filters(query, filters)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        receivable: ReceivableAccount,
        data: ReceivableAccountUpdate,
    ) -> ReceivableAccount:
        """Atualiza conta a receber."""
        update_data = data.model_dump(exclude_unset=True)

        recalculate = False
        for field in ["gross_value", "discount_value", "addition_value"]:
            if field in update_data:
                recalculate = True
                break

        for field, value in update_data.items():
            if hasattr(receivable, field):
                setattr(receivable, field, value)

        if recalculate:
            receivable.net_value = receivable.calculate_net_value()
            receivable.remaining_value = receivable.net_value - receivable.paid_value

        receivable.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(receivable)
        return receivable

    async def delete(self, receivable: ReceivableAccount) -> None:
        """Deleta conta a receber (soft delete)."""
        receivable.ativo = False
        receivable.status = ReceivableStatus.CANCELADA.value
        receivable.updated_at = datetime.utcnow()
        await self.session.flush()

    async def get_overdue(
        self,
        condominio_id: UUID,
        limit: int = 100,
    ) -> builtins.list[ReceivableAccount]:
        """Busca contas vencidas."""
        today = date.today()
        result = await self.session.execute(
            select(ReceivableAccount)
            .where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),  # noqa: E712
                    ReceivableAccount.due_date < today,
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                        ]
                    ),
                )
            )
            .options(selectinload(ReceivableAccount.customer))
            .order_by(ReceivableAccount.due_date)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_due_soon(
        self,
        condominio_id: UUID,
        days: int = 7,
        limit: int = 100,
    ) -> builtins.list[ReceivableAccount]:
        """Busca contas a vencer em X dias."""
        today = date.today()
        end_date = today + timedelta(days=days)

        result = await self.session.execute(
            select(ReceivableAccount)
            .where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),  # noqa: E712
                    ReceivableAccount.due_date >= today,
                    ReceivableAccount.due_date <= end_date,
                    ReceivableAccount.status.notin_(
                        [
                            ReceivableStatus.PAGA.value,
                            ReceivableStatus.CANCELADA.value,
                        ]
                    ),
                )
            )
            .options(selectinload(ReceivableAccount.customer))
            .order_by(ReceivableAccount.due_date)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_customer(
        self,
        customer_id: UUID,
        status: ReceivableStatus | None = None,
        limit: int = 100,
    ) -> builtins.list[ReceivableAccount]:
        """Busca contas por cliente."""
        query = select(ReceivableAccount).where(
            and_(
                ReceivableAccount.customer_id == customer_id,
                ReceivableAccount.ativo.is_(True),  # noqa: E712
            )
        )

        if status:
            query = query.where(ReceivableAccount.status == status.value)

        query = query.order_by(ReceivableAccount.due_date.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_unidade(
        self,
        unidade_id: UUID,
        status: ReceivableStatus | None = None,
        limit: int = 100,
    ) -> builtins.list[ReceivableAccount]:
        """Busca contas por unidade."""
        query = select(ReceivableAccount).where(
            and_(
                ReceivableAccount.unidade_id == unidade_id,
                ReceivableAccount.ativo.is_(True),  # noqa: E712
            )
        )

        if status:
            query = query.where(ReceivableAccount.status == status.value)

        query = query.order_by(ReceivableAccount.due_date.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_stats(self, condominio_id: UUID) -> ReceivableAccountStats:
        """Retorna estatisticas de contas a receber."""
        today = date.today()

        # Totais por status
        status_query = (
            select(
                ReceivableAccount.status,
                func.count(ReceivableAccount.id).label("count"),
                func.sum(ReceivableAccount.net_value).label("total"),
            )
            .where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),  # noqa: E712
                )
            )
            .group_by(ReceivableAccount.status)
        )

        status_result = await self.session.execute(status_query)
        status_data = {}
        total_count = 0
        total_value = Decimal("0")
        total_received = Decimal("0")
        total_pending = Decimal("0")

        for row in status_result:
            status_data[row.status] = {
                "count": row.count,
                "value": float(row.total or 0),
            }
            total_count += row.count
            total_value += row.total or Decimal("0")
            if row.status == ReceivableStatus.PAGA.value:
                total_received += row.total or Decimal("0")
            elif row.status not in [ReceivableStatus.CANCELADA.value]:
                total_pending += row.total or Decimal("0")

        # Total vencido
        overdue_query = select(
            func.count(ReceivableAccount.id).label("count"),
            func.sum(ReceivableAccount.net_value - ReceivableAccount.paid_value).label("total"),
        ).where(
            and_(
                ReceivableAccount.condominio_id == condominio_id,
                ReceivableAccount.ativo.is_(True),  # noqa: E712
                ReceivableAccount.due_date < today,
                ReceivableAccount.status.notin_(
                    [
                        ReceivableStatus.PAGA.value,
                        ReceivableStatus.CANCELADA.value,
                    ]
                ),
            )
        )

        overdue_result = await self.session.execute(overdue_query)
        overdue_row = overdue_result.one()

        # Por categoria
        category_query = (
            select(
                ReceivableCategory.name,
                func.count(ReceivableAccount.id).label("count"),
                func.sum(ReceivableAccount.net_value).label("total"),
            )
            .join(
                ReceivableCategory,
                ReceivableAccount.category_id == ReceivableCategory.id,
            )
            .where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),  # noqa: E712
                )
            )
            .group_by(ReceivableCategory.name)
        )

        category_result = await self.session.execute(category_query)
        category_data = {row.name: {"count": row.count, "value": float(row.total or 0)} for row in category_result}

        # Por prioridade
        priority_query = (
            select(
                ReceivableAccount.priority,
                func.count(ReceivableAccount.id).label("count"),
            )
            .where(
                and_(
                    ReceivableAccount.condominio_id == condominio_id,
                    ReceivableAccount.ativo.is_(True),  # noqa: E712
                )
            )
            .group_by(ReceivableAccount.priority)
        )

        priority_result = await self.session.execute(priority_query)
        priority_data = {row.priority: row.count for row in priority_result}

        return ReceivableAccountStats(
            total_count=total_count,
            total_value=total_value,
            total_received=total_received,
            total_pending=total_pending,
            total_overdue=Decimal(str(overdue_row.total or 0)),
            overdue_count=overdue_row.count or 0,
            by_status=status_data,
            by_category=category_data,
            by_priority=priority_data,
        )


class ReceivableInstallmentRepository:
    """Repository para parcelas."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def get_by_id(self, installment_id: UUID) -> ReceivableInstallment | None:
        """Busca parcela por ID."""
        result = await self.session.execute(
            select(ReceivableInstallment)
            .where(
                and_(
                    ReceivableInstallment.id == installment_id,
                    ReceivableInstallment.ativo.is_(True),  # noqa: E712
                )
            )
            .options(selectinload(ReceivableInstallment.payments))
        )
        return result.scalar_one_or_none()

    async def list_by_account(
        self,
        receivable_account_id: UUID,
    ) -> builtins.list[ReceivableInstallment]:
        """Lista parcelas de uma conta."""
        result = await self.session.execute(
            select(ReceivableInstallment)
            .where(
                and_(
                    ReceivableInstallment.receivable_account_id == receivable_account_id,
                    ReceivableInstallment.ativo.is_(True),  # noqa: E712
                )
            )
            .order_by(ReceivableInstallment.installment_number)
        )
        return list(result.scalars().all())

    async def get_pending(
        self,
        condominio_id: UUID,
        due_date_start: date | None = None,
        due_date_end: date | None = None,
        limit: int = 100,
    ) -> builtins.list[ReceivableInstallment]:
        """Busca parcelas pendentes."""
        query = select(ReceivableInstallment).where(
            and_(
                ReceivableInstallment.condominio_id == condominio_id,
                ReceivableInstallment.ativo.is_(True),  # noqa: E712
                ReceivableInstallment.status.in_(
                    [
                        InstallmentStatus.PENDENTE.value,
                        InstallmentStatus.VENCIDA.value,
                        InstallmentStatus.PARCIAL.value,
                    ]
                ),
            )
        )

        if due_date_start:
            query = query.where(ReceivableInstallment.due_date >= due_date_start)

        if due_date_end:
            query = query.where(ReceivableInstallment.due_date <= due_date_end)

        query = query.order_by(ReceivableInstallment.due_date).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_for_billing(
        self,
        condominio_id: UUID,
        days_before: int = 5,
    ) -> builtins.list[ReceivableInstallment]:
        """Busca parcelas para geracao de boleto."""
        today = date.today()
        target_date = today + timedelta(days=days_before)

        result = await self.session.execute(
            select(ReceivableInstallment)
            .where(
                and_(
                    ReceivableInstallment.condominio_id == condominio_id,
                    ReceivableInstallment.ativo.is_(True),  # noqa: E712
                    ReceivableInstallment.due_date <= target_date,
                    ReceivableInstallment.due_date >= today,
                    ReceivableInstallment.boleto_generated.is_(False),  # noqa: E712
                    ReceivableInstallment.status == InstallmentStatus.PENDENTE.value,
                )
            )
            .order_by(ReceivableInstallment.due_date)
        )
        return list(result.scalars().all())

    async def update(
        self,
        installment: ReceivableInstallment,
        data: ReceivableInstallmentUpdate,
    ) -> ReceivableInstallment:
        """Atualiza parcela."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(installment, field):
                setattr(installment, field, value)

        installment.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(installment)
        return installment


class ReceivablePaymentRepository:
    """Repository para recebimentos."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: ReceivablePaymentCreate,
        user_id: UUID | None = None,
    ) -> ReceivablePayment:
        """Cria um novo recebimento."""
        # Busca a parcela
        installment_result = await self.session.execute(
            select(ReceivableInstallment).where(ReceivableInstallment.id == data.installment_id)
        )
        installment = installment_result.scalar_one_or_none()
        if not installment:
            raise ValueError("Parcela nao encontrada")

        # Calcula valor liquido
        net_value = data.paid_value - data.discount_value - data.fee_value + data.interest_value + data.penalty_value

        payment = ReceivablePayment(
            installment_id=data.installment_id,
            condominio_id=installment.condominio_id,
            paid_value=data.paid_value,
            discount_value=data.discount_value,
            interest_value=data.interest_value,
            penalty_value=data.penalty_value,
            fee_value=data.fee_value,
            net_value=net_value,
            payment_date=data.payment_date,
            origin=data.origin.value,
            payment_method_id=data.payment_method_id,
            bank_account_id=data.bank_account_id,
            receipt_number=data.receipt_number,
            receipt_url=data.receipt_url,
            authentication_code=data.authentication_code,
            notes=data.notes,
            status=PaymentStatus.CONFIRMADO.value,
            created_by=user_id,
        )
        self.session.add(payment)

        # Atualiza parcela
        installment.register_payment(data.paid_value, data.payment_date)

        # Atualiza conta principal
        receivable_result = await self.session.execute(
            select(ReceivableAccount).where(ReceivableAccount.id == installment.receivable_account_id)
        )
        receivable = receivable_result.scalar_one()
        receivable.register_payment(data.paid_value, data.payment_date)

        # Atualiza divida do cliente
        if receivable.customer_id:
            customer_result = await self.session.execute(select(Customer).where(Customer.id == receivable.customer_id))
            customer = customer_result.scalar_one_or_none()
            if customer:
                customer.total_debt -= data.paid_value
                if installment.is_overdue:
                    customer.overdue_debt -= data.paid_value

        await self.session.flush()
        await self.session.refresh(payment)
        return payment

    async def get_by_id(self, payment_id: UUID) -> ReceivablePayment | None:
        """Busca recebimento por ID."""
        result = await self.session.execute(
            select(ReceivablePayment).where(
                and_(
                    ReceivablePayment.id == payment_id,
                    ReceivablePayment.ativo.is_(True),  # noqa: E712
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_installment(
        self,
        installment_id: UUID,
    ) -> builtins.list[ReceivablePayment]:
        """Lista recebimentos de uma parcela."""
        result = await self.session.execute(
            select(ReceivablePayment)
            .where(
                and_(
                    ReceivablePayment.installment_id == installment_id,
                    ReceivablePayment.ativo.is_(True),  # noqa: E712
                )
            )
            .order_by(ReceivablePayment.payment_date)
        )
        return list(result.scalars().all())

    async def get_by_date_range(
        self,
        condominio_id: UUID,
        start_date: date,
        end_date: date,
        limit: int = 500,
    ) -> builtins.list[ReceivablePayment]:
        """Busca recebimentos por periodo."""
        result = await self.session.execute(
            select(ReceivablePayment)
            .where(
                and_(
                    ReceivablePayment.condominio_id == condominio_id,
                    ReceivablePayment.ativo.is_(True),  # noqa: E712
                    ReceivablePayment.payment_date >= start_date,
                    ReceivablePayment.payment_date <= end_date,
                )
            )
            .order_by(ReceivablePayment.payment_date)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending_reconciliation(
        self,
        condominio_id: UUID,
        limit: int = 100,
    ) -> builtins.list[ReceivablePayment]:
        """Busca recebimentos pendentes de conciliacao."""
        result = await self.session.execute(
            select(ReceivablePayment)
            .where(
                and_(
                    ReceivablePayment.condominio_id == condominio_id,
                    ReceivablePayment.ativo.is_(True),  # noqa: E712
                    ReceivablePayment.is_reconciled.is_(False),  # noqa: E712
                    ReceivablePayment.status == PaymentStatus.CONFIRMADO.value,
                )
            )
            .order_by(ReceivablePayment.payment_date)
            .limit(limit)
        )
        return list(result.scalars().all())


class BillingRuleRepository:
    """Repository para regras de cobranca."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: BillingRuleCreate,
        user_id: UUID | None = None,
    ) -> BillingRule:
        """Cria uma nova regra de cobranca."""
        rule = BillingRule(
            **data.model_dump(),
            created_by=user_id,
        )
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def get_by_id(self, rule_id: UUID) -> BillingRule | None:
        """Busca regra por ID."""
        result = await self.session.execute(
            select(BillingRule).where(
                and_(
                    BillingRule.id == rule_id,
                    BillingRule.ativo.is_(True),  # noqa: E712
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID | None,
        filters: BillingRuleFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> builtins.list[BillingRule]:
        """Lista regras de cobranca com filtros."""
        query = select(BillingRule).where(BillingRule.ativo.is_(True))  # noqa: E712
        if condominio_id is not None:
            query = query.where(BillingRule.condominio_id == condominio_id)

        if filters:
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.where(
                    or_(
                        BillingRule.name.ilike(search_term),
                        BillingRule.description.ilike(search_term),
                    )
                )

            if filters.billing_type:
                query = query.where(BillingRule.billing_type == filters.billing_type.value)

            if filters.status:
                query = query.where(BillingRule.status == filters.status.value)

            if filters.frequency:
                query = query.where(BillingRule.frequency == filters.frequency.value)

            if filters.is_active is not None:
                today = date.today()
                if filters.is_active:
                    query = query.where(
                        and_(
                            BillingRule.status == BillingRuleStatus.ATIVA.value,
                            BillingRule.start_date <= today,
                            or_(
                                BillingRule.end_date.is_(None),
                                BillingRule.end_date >= today,
                            ),
                        )
                    )

        query = query.order_by(BillingRule.name).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active(
        self,
        condominio_id: UUID | None,
    ) -> builtins.list[BillingRule]:
        """Busca todas as regras ativas do condominio."""
        q = select(BillingRule).where(
            and_(
                BillingRule.ativo.is_(True),  # noqa: E712
                BillingRule.status == BillingRuleStatus.ATIVA.value,
            )
        )
        if condominio_id is not None:
            q = q.where(BillingRule.condominio_id == condominio_id)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_active_for_today(
        self,
        condominio_id: UUID,
    ) -> builtins.list[BillingRule]:
        """Busca regras ativas para execucao hoje."""
        today = date.today()

        result = await self.session.execute(
            select(BillingRule).where(
                and_(
                    BillingRule.condominio_id == condominio_id,
                    BillingRule.ativo.is_(True),  # noqa: E712
                    BillingRule.status == BillingRuleStatus.ATIVA.value,
                    BillingRule.start_date <= today,
                    or_(
                        BillingRule.end_date.is_(None),
                        BillingRule.end_date >= today,
                    ),
                    BillingRule.generation_day == today.day,
                )
            )
        )
        return list(result.scalars().all())

    async def get_due_for_generation(
        self,
        condominio_id: UUID | None,
    ) -> builtins.list[BillingRule]:
        """Busca regras ativas com geracao pendente (next_run_at <= hoje)."""
        today = date.today()

        query = select(BillingRule).where(
            and_(
                BillingRule.ativo.is_(True),  # noqa: E712
                BillingRule.status == BillingRuleStatus.ATIVA.value,
                or_(
                    BillingRule.next_run_at.is_(None),
                    BillingRule.next_run_at <= today,
                ),
                BillingRule.start_date <= today,
                or_(
                    BillingRule.end_date.is_(None),
                    BillingRule.end_date >= today,
                ),
            )
        )
        if condominio_id is not None:
            query = query.where(BillingRule.condominio_id == condominio_id)

        query = query.order_by(BillingRule.next_run_at)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        rule: BillingRule,
        data: BillingRuleUpdate,
    ) -> BillingRule:
        """Atualiza regra de cobranca."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(rule, field):
                setattr(rule, field, value)

        rule.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def delete(self, rule: BillingRule) -> None:
        """Deleta regra (soft delete)."""
        rule.ativo = False
        rule.status = BillingRuleStatus.INATIVA.value
        rule.updated_at = datetime.utcnow()
        await self.session.flush()
