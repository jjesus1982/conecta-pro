"""Repository para contas a pagar."""

import builtins
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.financial.models.payable_account import (
    PayableAccount,
    PayableStatus,
)
from modules.financial.models.payable_category import PayableCategory
from modules.financial.models.payable_installment import InstallmentStatus, PayableInstallment
from modules.financial.models.payable_payment import PayablePayment, PaymentStatus
from modules.financial.models.supplier import Supplier
from modules.financial.schemas.payable import (
    PayableAccountCreate,
    PayableAccountFilter,
    PayableAccountStats,
    PayableAccountUpdate,
    PayableInstallmentUpdate,
    PayablePaymentCreate,
)


class PayableAccountRepository:
    """Repository para operações com contas a pagar."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: PayableAccountCreate,
        user_id: UUID | None = None,
    ) -> PayableAccount:
        """Cria uma nova conta a pagar."""
        # Calcula retenções totais
        total_withholdings = (
            data.withhold_iss
            + data.withhold_ir
            + data.withhold_pis
            + data.withhold_cofins
            + data.withhold_csll
            + data.withhold_inss
        )

        # Calcula valor líquido
        net_value = data.gross_value - data.discount_value + data.addition_value - total_withholdings

        dump = data.model_dump()
        # FIN-03: supplier_name é coluna denormalizada de PayableAccount — o nome
        # digitado no modal flui direto para a coluna (sem criar fornecedor fake,
        # que exigiria cpf_cnpj NOT NULL/único). A coluna Fornecedor lê isto.
        if dump.get("supplier_name"):
            dump["supplier_name"] = dump["supplier_name"].strip() or None
        # issue_date é NOT NULL no banco mas opcional no schema → default p/ hoje quando não vem
        # (senão INSERT viola not-null e o create dá 500).
        if not dump.get("issue_date"):
            dump["issue_date"] = date.today()

        payable = PayableAccount(
            **dump,
            net_value=net_value,
            remaining_value=net_value,
            total_withholdings=total_withholdings,
            created_by=user_id,
        )
        self.session.add(payable)
        await self.session.flush()
        await self.session.refresh(payable)

        # Cria parcelas se necessário
        if data.total_installments > 1:
            await self._create_installments(payable, data.total_installments)

        return payable

    async def _create_installments(
        self,
        payable: PayableAccount,
        total: int,
    ) -> None:
        """Cria parcelas para a conta."""
        installment_value = payable.net_value / total

        for i in range(1, total + 1):
            # Calcula data de vencimento (mensal)
            due_date = payable.due_date
            if i > 1:
                month = payable.due_date.month + (i - 1)
                year = payable.due_date.year
                while month > 12:
                    month -= 12
                    year += 1
                day = min(payable.due_date.day, 28)  # Evita problemas com fev
                due_date = date(year, month, day)

            installment = PayableInstallment(
                payable_account_id=payable.id,
                condominio_id=payable.condominio_id,
                installment_number=i,
                total_installments=total,
                original_value=installment_value,
                current_value=installment_value,
                due_date=due_date,
            )
            self.session.add(installment)

        await self.session.flush()

    async def get_by_id(
        self,
        payable_id: UUID,
        with_relations: bool = False,
    ) -> PayableAccount | None:
        """Busca conta a pagar por ID."""
        query = select(PayableAccount).where(
            and_(
                PayableAccount.id == payable_id,
                PayableAccount.ativo.is_(True),  # noqa: E712
            )
        )

        if with_relations:
            query = query.options(
                selectinload(PayableAccount.supplier),
                selectinload(PayableAccount.category),
                selectinload(PayableAccount.installments),
            )

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID | None,
        filters: PayableAccountFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PayableAccount]:
        """Lista contas a pagar com filtros."""
        base_conditions = [PayableAccount.ativo.is_(True)]  # noqa: E712
        if condominio_id is not None:
            base_conditions.append(PayableAccount.condominio_id == condominio_id)
        query = select(PayableAccount).where(and_(*base_conditions))

        if filters:
            query = self._apply_filters(query, filters)

        query = (
            query.options(
                selectinload(PayableAccount.supplier),
                selectinload(PayableAccount.category),
            )
            .order_by(PayableAccount.due_date)
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    def _apply_filters(  # pylint: disable=too-many-branches
        self, query, filters: PayableAccountFilter
    ):
        """Aplica filtros à query."""
        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    PayableAccount.description.ilike(search_term),
                    PayableAccount.document_number.ilike(search_term),
                    PayableAccount.code.ilike(search_term),
                )
            )

        if filters.supplier_id:
            query = query.where(PayableAccount.supplier_id == filters.supplier_id)

        if filters.category_id:
            query = query.where(PayableAccount.category_id == filters.category_id)

        if filters.status:
            query = query.where(PayableAccount.status == filters.status.value)

        if filters.payable_type:
            query = query.where(PayableAccount.payable_type == filters.payable_type.value)

        if filters.priority:
            query = query.where(PayableAccount.priority == filters.priority.value)

        if filters.due_date_start:
            query = query.where(PayableAccount.due_date >= filters.due_date_start)

        if filters.due_date_end:
            query = query.where(PayableAccount.due_date <= filters.due_date_end)

        if filters.payment_date_start:
            query = query.where(PayableAccount.payment_date >= filters.payment_date_start)

        if filters.payment_date_end:
            query = query.where(PayableAccount.payment_date <= filters.payment_date_end)

        if filters.is_overdue:
            today = date.today()
            query = query.where(
                and_(
                    PayableAccount.due_date < today,
                    PayableAccount.status.notin_(
                        [
                            PayableStatus.PAGA.value,
                            PayableStatus.CANCELADA.value,
                        ]
                    ),
                )
            )

        if filters.cost_center:
            query = query.where(PayableAccount.cost_center == filters.cost_center)

        if filters.project:
            query = query.where(PayableAccount.project == filters.project)

        if filters.min_value:
            query = query.where(PayableAccount.net_value >= filters.min_value)

        if filters.max_value:
            query = query.where(PayableAccount.net_value <= filters.max_value)

        if filters.tags:
            for tag in filters.tags:
                query = query.where(PayableAccount.tags.contains([tag]))

        return query

    async def count(
        self,
        condominio_id: UUID | None,
        filters: PayableAccountFilter | None = None,
    ) -> int:
        """Conta contas a pagar com filtros."""
        base_conditions = [PayableAccount.ativo.is_(True)]  # noqa: E712
        if condominio_id is not None:
            base_conditions.append(PayableAccount.condominio_id == condominio_id)
        query = select(func.count(PayableAccount.id)).where(and_(*base_conditions))

        if filters:
            query = self._apply_filters(query, filters)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        payable: PayableAccount,
        data: PayableAccountUpdate,
    ) -> PayableAccount:
        """Atualiza conta a pagar."""
        update_data = data.model_dump(exclude_unset=True)

        # Recalcula valores se necessário
        recalculate = False
        for field in ["gross_value", "discount_value", "addition_value"]:
            if field in update_data:
                recalculate = True
                break

        for field, value in update_data.items():
            if hasattr(payable, field):
                setattr(payable, field, value)

        if recalculate:
            payable.net_value = payable.calculate_net_value()
            payable.remaining_value = payable.net_value - payable.paid_value

        payable.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(payable)
        return payable

    async def delete(self, payable: PayableAccount) -> None:
        """Deleta conta a pagar (soft delete)."""
        payable.ativo = False
        payable.status = PayableStatus.CANCELADA.value
        payable.updated_at = datetime.utcnow()
        await self.session.flush()

    async def get_overdue(
        self,
        condominio_id: UUID,
        limit: int = 100,
    ) -> builtins.list[PayableAccount]:
        """Busca contas vencidas."""
        today = date.today()
        result = await self.session.execute(
            select(PayableAccount)
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),  # noqa: E712
                    PayableAccount.due_date < today,
                    PayableAccount.status.notin_(
                        [
                            PayableStatus.PAGA.value,
                            PayableStatus.CANCELADA.value,
                        ]
                    ),
                )
            )
            .options(selectinload(PayableAccount.supplier))
            .order_by(PayableAccount.due_date)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_due_soon(
        self,
        condominio_id: UUID | None,
        days: int = 7,
        limit: int = 100,
    ) -> builtins.list[PayableAccount]:
        """Busca contas a vencer em X dias."""
        today = date.today()
        end_date = today + timedelta(days=days)

        conditions = [
            PayableAccount.ativo.is_(True),  # noqa: E712
            PayableAccount.due_date >= today,
            PayableAccount.due_date <= end_date,
            PayableAccount.status.notin_([PayableStatus.PAGA.value, PayableStatus.CANCELADA.value]),
        ]
        if condominio_id is not None:
            conditions.append(PayableAccount.condominio_id == condominio_id)

        result = await self.session.execute(
            select(PayableAccount)
            .where(and_(*conditions))
            .options(selectinload(PayableAccount.supplier))
            .order_by(PayableAccount.due_date)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_supplier(
        self,
        supplier_id: UUID,
        status: PayableStatus | None = None,
        limit: int = 100,
    ) -> builtins.list[PayableAccount]:
        """Busca contas por fornecedor."""
        query = select(PayableAccount).where(
            and_(
                PayableAccount.supplier_id == supplier_id,
                PayableAccount.ativo.is_(True),  # noqa: E712
            )
        )

        if status:
            query = query.where(PayableAccount.status == status.value)

        query = query.order_by(PayableAccount.due_date.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_stats(  # pylint: disable=too-many-locals
        self, condominio_id: UUID
    ) -> PayableAccountStats:
        """Retorna estatísticas de contas a pagar."""
        today = date.today()

        # Totais por status
        status_query = (
            select(
                PayableAccount.status,
                func.count(PayableAccount.id).label("count"),
                func.sum(PayableAccount.net_value).label("total"),
            )
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),  # noqa: E712
                )
            )
            .group_by(PayableAccount.status)
        )

        status_result = await self.session.execute(status_query)
        status_data = {}
        total_count = 0
        total_value = Decimal("0")
        total_paid = Decimal("0")
        total_pending = Decimal("0")

        for row in status_result:
            status_data[row.status] = {
                "count": row.count,
                "value": float(row.total or 0),
            }
            total_count += row.count
            total_value += row.total or Decimal("0")
            if row.status == PayableStatus.PAGA.value:
                total_paid += row.total or Decimal("0")
            elif row.status not in [PayableStatus.CANCELADA.value]:
                total_pending += row.total or Decimal("0")

        # Total vencido
        overdue_query = select(
            func.count(PayableAccount.id).label("count"),
            func.sum(PayableAccount.net_value - PayableAccount.paid_value).label("total"),
        ).where(
            and_(
                PayableAccount.condominio_id == condominio_id,
                PayableAccount.ativo.is_(True),  # noqa: E712
                PayableAccount.due_date < today,
                PayableAccount.status.notin_(
                    [
                        PayableStatus.PAGA.value,
                        PayableStatus.CANCELADA.value,
                    ]
                ),
            )
        )

        overdue_result = await self.session.execute(overdue_query)
        overdue_row = overdue_result.one()

        # Por categoria
        category_query = (
            select(
                PayableCategory.name,
                func.count(PayableAccount.id).label("count"),
                func.sum(PayableAccount.net_value).label("total"),
            )
            .join(
                PayableCategory,
                PayableAccount.category_id == PayableCategory.id,
            )
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),  # noqa: E712
                )
            )
            .group_by(PayableCategory.name)
        )

        category_result = await self.session.execute(category_query)
        category_data = {row.name: {"count": row.count, "value": float(row.total or 0)} for row in category_result}

        # Por fornecedor (top 10)
        supplier_query = (
            select(
                Supplier.name,
                func.count(PayableAccount.id).label("count"),
                func.sum(PayableAccount.net_value).label("total"),
            )
            .join(
                Supplier,
                PayableAccount.supplier_id == Supplier.id,
            )
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),  # noqa: E712
                )
            )
            .group_by(Supplier.name)
            .order_by(func.sum(PayableAccount.net_value).desc())
            .limit(10)
        )

        supplier_result = await self.session.execute(supplier_query)
        supplier_data = {row.name: {"count": row.count, "value": float(row.total or 0)} for row in supplier_result}

        # Por prioridade
        priority_query = (
            select(
                PayableAccount.priority,
                func.count(PayableAccount.id).label("count"),
            )
            .where(
                and_(
                    PayableAccount.condominio_id == condominio_id,
                    PayableAccount.ativo.is_(True),  # noqa: E712
                )
            )
            .group_by(PayableAccount.priority)
        )

        priority_result = await self.session.execute(priority_query)
        priority_data = {row.priority: row.count for row in priority_result}

        return PayableAccountStats(
            total_count=total_count,
            total_value=total_value,
            total_paid=total_paid,
            total_pending=total_pending,
            total_overdue=Decimal(str(overdue_row.total or 0)),
            overdue_count=overdue_row.count or 0,
            by_status=status_data,
            by_category=category_data,
            by_supplier=supplier_data,
            by_priority=priority_data,
        )


class PayableInstallmentRepository:
    """Repository para parcelas."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def get_by_id(self, installment_id: UUID) -> PayableInstallment | None:
        """Busca parcela por ID."""
        result = await self.session.execute(
            select(PayableInstallment)
            .where(
                and_(
                    PayableInstallment.id == installment_id,
                    PayableInstallment.ativo.is_(True),  # noqa: E712
                )
            )
            .options(selectinload(PayableInstallment.payments))
        )
        return result.scalar_one_or_none()

    async def list_by_account(
        self,
        payable_account_id: UUID,
    ) -> list[PayableInstallment]:
        """Lista parcelas de uma conta."""
        result = await self.session.execute(
            select(PayableInstallment)
            .where(
                and_(
                    PayableInstallment.payable_account_id == payable_account_id,
                    PayableInstallment.ativo.is_(True),  # noqa: E712
                )
            )
            .order_by(PayableInstallment.installment_number)
        )
        return list(result.scalars().all())

    async def get_pending(
        self,
        condominio_id: UUID,
        due_date_start: date | None = None,
        due_date_end: date | None = None,
        limit: int = 100,
    ) -> list[PayableInstallment]:
        """Busca parcelas pendentes."""
        query = select(PayableInstallment).where(
            and_(
                PayableInstallment.condominio_id == condominio_id,
                PayableInstallment.ativo.is_(True),  # noqa: E712
                PayableInstallment.status.in_(
                    [
                        InstallmentStatus.PENDENTE.value,
                        InstallmentStatus.VENCIDA.value,
                        InstallmentStatus.PARCIAL.value,
                    ]
                ),
            )
        )

        if due_date_start:
            query = query.where(PayableInstallment.due_date >= due_date_start)

        if due_date_end:
            query = query.where(PayableInstallment.due_date <= due_date_end)

        query = query.order_by(PayableInstallment.due_date).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        installment: PayableInstallment,
        data: PayableInstallmentUpdate,
    ) -> PayableInstallment:
        """Atualiza parcela."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(installment, field):
                setattr(installment, field, value)

        installment.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(installment)
        return installment


class PayablePaymentRepository:
    """Repository para pagamentos."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: PayablePaymentCreate,
        user_id: UUID | None = None,
    ) -> PayablePayment:
        """Cria um novo pagamento."""
        # Busca a parcela
        installment_result = await self.session.execute(
            select(PayableInstallment).where(PayableInstallment.id == data.installment_id)
        )
        installment = installment_result.scalar_one_or_none()
        if not installment:
            raise ValueError("Parcela não encontrada")

        # Calcula valor líquido
        net_value = data.paid_value - data.discount_value + data.interest_value + data.penalty_value + data.fee_value

        payment = PayablePayment(
            installment_id=data.installment_id,
            condominio_id=installment.condominio_id,
            paid_value=data.paid_value,
            discount_value=data.discount_value,
            interest_value=data.interest_value,
            penalty_value=data.penalty_value,
            fee_value=data.fee_value,
            net_value=net_value,
            payment_date=data.payment_date,
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
        payable_result = await self.session.execute(
            select(PayableAccount).where(PayableAccount.id == installment.payable_account_id)
        )
        payable = payable_result.scalar_one()
        payable.register_payment(data.paid_value, data.payment_date)

        await self.session.flush()
        await self.session.refresh(payment)
        return payment

    async def get_by_id(self, payment_id: UUID) -> PayablePayment | None:
        """Busca pagamento por ID."""
        result = await self.session.execute(
            select(PayablePayment).where(
                and_(
                    PayablePayment.id == payment_id,
                    PayablePayment.ativo.is_(True),  # noqa: E712
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_installment(
        self,
        installment_id: UUID,
    ) -> list[PayablePayment]:
        """Lista pagamentos de uma parcela."""
        result = await self.session.execute(
            select(PayablePayment)
            .where(
                and_(
                    PayablePayment.installment_id == installment_id,
                    PayablePayment.ativo.is_(True),  # noqa: E712
                )
            )
            .order_by(PayablePayment.payment_date)
        )
        return list(result.scalars().all())

    async def get_by_date_range(
        self,
        condominio_id: UUID,
        start_date: date,
        end_date: date,
        limit: int = 500,
    ) -> list[PayablePayment]:
        """Busca pagamentos por período."""
        result = await self.session.execute(
            select(PayablePayment)
            .where(
                and_(
                    PayablePayment.condominio_id == condominio_id,
                    PayablePayment.ativo.is_(True),  # noqa: E712
                    PayablePayment.payment_date >= start_date,
                    PayablePayment.payment_date <= end_date,
                )
            )
            .order_by(PayablePayment.payment_date)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending_reconciliation(
        self,
        condominio_id: UUID,
        limit: int = 100,
    ) -> list[PayablePayment]:
        """Busca pagamentos pendentes de conciliação."""
        result = await self.session.execute(
            select(PayablePayment)
            .where(
                and_(
                    PayablePayment.condominio_id == condominio_id,
                    PayablePayment.ativo.is_(True),  # noqa: E712
                    PayablePayment.is_reconciled.is_(False),  # noqa: E712
                    PayablePayment.status == PaymentStatus.CONFIRMADO.value,
                )
            )
            .order_by(PayablePayment.payment_date)
            .limit(limit)
        )
        return list(result.scalars().all())
