"""
Repository para operações de banco de dados com Commission.
"""

import builtins
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.logging import logger
from modules.crm.models.commission import (
    Commission,
    CommissionPayment,
    CommissionRule,
    CommissionStatus,
    CommissionSummary,
    CommissionTrigger,
    SellerCommissionRule,
)
from modules.crm.schemas.commission import (
    CommissionCreate,
    CommissionFilter,
    CommissionPaymentCreate,
    CommissionRuleCreate,
    CommissionRuleUpdate,
    CommissionSummaryFilter,
    CommissionUpdate,
    SellerCommissionRuleCreate,
)
from modules.crm.services.commission_service import CommissionService


class CommissionRepository:
    """Repository para operações CRUD de Commission."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.service = CommissionService()

    async def _get_next_reference_number(self) -> str:
        """Gera próximo número de referência."""
        year = date.today().year
        result = await self.db.execute(
            select(func.count(Commission.id)).where(Commission.reference_number.like(f"COM-{year}-%"))
        )
        count = result.scalar() or 0
        return self.service.generate_reference_number(count + 1)

    # ==================== Commission Rules ====================

    async def create_rule(self, data: CommissionRuleCreate, created_by_id: str | None = None) -> CommissionRule:
        """
        Cria uma nova regra de comissão.

        Args:
            data: Dados da regra
            created_by_id: ID do usuário que criou

        Returns:
            CommissionRule criada
        """
        import json  # pylint: disable=import-outside-toplevel

        rule = CommissionRule(
            id=str(uuid4()),
            name=data.name,
            description=data.description,
            commission_type=data.commission_type.value,
            base_value=data.base_value,
            min_value=data.min_value,
            max_value=data.max_value,
            progressive_scale=(
                json.dumps([t.model_dump() for t in data.progressive_scale]) if data.progressive_scale else None
            ),
            trigger=data.trigger.value,
            trigger_delay_days=data.trigger_delay_days,
            applies_to_all=data.applies_to_all,
            product_categories=(json.dumps(data.product_categories) if data.product_categories else None),
            service_types=(json.dumps(data.service_types) if data.service_types else None),
            min_sale_value=data.min_sale_value,
            max_sale_value=data.max_sale_value,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            priority=data.priority,
            is_active=True,
            created_by_id=created_by_id,
        )

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(f"CommissionRule criada: {rule.id} ({rule.name})")
        return rule

    async def get_rule_by_id(self, rule_id: str) -> CommissionRule | None:
        """Busca regra por ID."""
        result = await self.db.execute(
            select(CommissionRule).where(
                CommissionRule.id == rule_id,
                CommissionRule.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_rules(
        self, active_only: bool = True, skip: int = 0, limit: int = 100
    ) -> tuple[list[CommissionRule], int]:
        """Lista todas as regras."""
        query = select(CommissionRule)
        count_query = select(func.count(CommissionRule.id))

        if active_only:
            query = query.where(CommissionRule.is_active.is_(True))
            count_query = count_query.where(CommissionRule.is_active.is_(True))

        query = query.order_by(CommissionRule.priority.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        rules = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        return rules, total

    async def update_rule(self, rule_id: str, data: CommissionRuleUpdate) -> CommissionRule | None:
        """Atualiza regra de comissão."""
        import json  # pylint: disable=import-outside-toplevel

        rule = await self.get_rule_by_id(rule_id)
        if not rule:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "progressive_scale" and value:
                value = json.dumps([t.model_dump() for t in value])
            elif field in ("product_categories", "service_types") and value:
                value = json.dumps(value)
            elif field in ("commission_type", "trigger") and value:
                value = value.value
            setattr(rule, field, value)

        rule.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(rule)

        logger.info(f"CommissionRule atualizada: {rule.id}")
        return rule

    async def delete_rule(self, rule_id: str) -> bool:
        """Soft delete de regra."""
        rule = await self.get_rule_by_id(rule_id)
        if not rule:
            return False

        rule.is_active = False
        rule.updated_at = datetime.utcnow()
        await self.db.commit()

        logger.info(f"CommissionRule desativada: {rule_id}")
        return True

    async def get_valid_rules(self, seller_id: str | None = None) -> list[CommissionRule]:
        """Busca regras válidas, opcionalmente específicas do vendedor."""
        today = date.today()
        query = select(CommissionRule).where(
            CommissionRule.is_active.is_(True),
            CommissionRule.valid_from <= today,
            or_(
                CommissionRule.valid_until.is_(None),
                CommissionRule.valid_until >= today,
            ),
        )

        if seller_id:
            # Buscar regras específicas do vendedor
            seller_rules_query = select(SellerCommissionRule.rule_id).where(
                SellerCommissionRule.seller_id == seller_id,
                SellerCommissionRule.is_active.is_(True),
                SellerCommissionRule.valid_from <= today,
                or_(
                    SellerCommissionRule.valid_until.is_(None),
                    SellerCommissionRule.valid_until >= today,
                ),
            )
            seller_rules = await self.db.execute(seller_rules_query)
            specific_rule_ids = [r[0] for r in seller_rules.all()]

            if specific_rule_ids:
                query = query.where(
                    or_(
                        CommissionRule.id.in_(specific_rule_ids),
                        CommissionRule.applies_to_all.is_(True),
                    )
                )
            else:
                query = query.where(CommissionRule.applies_to_all.is_(True))

        query = query.order_by(CommissionRule.priority.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==================== Seller Commission Rules ====================

    async def assign_rule_to_seller(self, data: SellerCommissionRuleCreate) -> SellerCommissionRule:
        """Associa regra a vendedor."""
        seller_rule = SellerCommissionRule(
            id=str(uuid4()),
            seller_id=data.seller_id,
            rule_id=data.rule_id,
            custom_base_value=data.custom_base_value,
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            is_active=True,
        )

        self.db.add(seller_rule)
        await self.db.commit()
        await self.db.refresh(seller_rule)

        logger.info(f"Regra {data.rule_id} atribuída ao vendedor {data.seller_id}")
        return seller_rule

    async def get_seller_custom_rate(self, seller_id: str, rule_id: str) -> float | None:
        """Busca taxa customizada do vendedor para uma regra."""
        today = date.today()
        result = await self.db.execute(
            select(SellerCommissionRule).where(
                SellerCommissionRule.seller_id == seller_id,
                SellerCommissionRule.rule_id == rule_id,
                SellerCommissionRule.is_active.is_(True),
                SellerCommissionRule.valid_from <= today,
                or_(
                    SellerCommissionRule.valid_until.is_(None),
                    SellerCommissionRule.valid_until >= today,
                ),
            )
        )
        seller_rule = result.scalar_one_or_none()
        return seller_rule.custom_base_value if seller_rule else None

    # ==================== Commissions ====================

    async def create(self, data: CommissionCreate, created_by_id: str | None = None) -> Commission:
        """
        Cria uma nova comissão.

        Args:
            data: Dados da comissão
            created_by_id: ID do usuário que criou

        Returns:
            Commission criada
        """
        # Buscar regra se especificada
        rule = None
        if data.rule_id:
            rule = await self.get_rule_by_id(data.rule_id)

        # Calcular comissão se regra fornecida
        if rule and data.commission_rate is None:
            custom_rate = await self.get_seller_custom_rate(data.seller_id, rule.id)
            calculation = self.service.calculate_commission(
                rule=rule,
                sale_value=data.sale_value,
                sale_margin=data.sale_margin,
                custom_rate=custom_rate,
            )
            commission_type = calculation["commission_type"]
            commission_rate = calculation["commission_rate"]
            base_commission = calculation["base_commission"]
            trigger = calculation["trigger"]
            trigger_date = data.trigger_date or calculation["trigger_date"]
            due_date = data.due_date or calculation["due_date"]
        else:
            commission_type = data.commission_type.value if data.commission_type else "percentage"
            commission_rate = data.commission_rate or 0.0
            base_commission = data.sale_value * (commission_rate / 100)
            default_trg = CommissionTrigger.ON_FIRST_PAYMENT.value
            trigger = data.trigger.value if data.trigger else default_trg
            trigger_date = data.trigger_date or date.today()
            due_date = data.due_date or (trigger_date + timedelta(days=30))

        reference_number = await self._get_next_reference_number()

        commission = Commission(
            id=str(uuid4()),
            reference_number=reference_number,
            seller_id=data.seller_id,
            proposal_id=data.proposal_id,
            rule_id=data.rule_id,
            sale_value=data.sale_value,
            sale_margin=data.sale_margin,
            commission_type=commission_type,
            commission_rate=commission_rate,
            base_commission=base_commission,
            adjustments=0.0,
            final_commission=base_commission,
            status=CommissionStatus.PENDING.value,
            trigger=trigger,
            trigger_date=trigger_date,
            due_date=due_date,
            period_start=data.period_start,
            period_end=data.period_end,
            description=data.description,
            notes=data.notes,
            is_active=True,
            created_by_id=created_by_id,
        )

        self.db.add(commission)
        await self.db.commit()
        # refresh com ["payments"]: a serializacao (CommissionResponse) le paid_amount/
        # pending_amount, que acessam self.payments -> evita MissingGreenlet.
        await self.db.refresh(commission, ["payments"])

        logger.info(f"Commission criada: {commission.id} ({commission.reference_number})")
        return commission

    async def get_by_id(self, commission_id: str) -> Commission | None:
        """Busca comissão por ID com pagamentos."""
        result = await self.db.execute(
            select(Commission)
            .options(selectinload(Commission.payments))
            .where(
                Commission.id == commission_id,
                Commission.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_reference(self, reference_number: str) -> Commission | None:
        """Busca comissão por número de referência."""
        result = await self.db.execute(
            select(Commission).where(
                Commission.reference_number == reference_number,
                Commission.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list(  # pylint: disable=too-many-branches
        self,
        filters: CommissionFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Commission], int]:
        """Lista comissões com filtros."""
        # selectinload(payments): paid_amount/pending_amount sao @property que acessam
        # self.payments; sem eager-load -> MissingGreenlet na serializacao (CommissionResponse).
        query = (
            select(Commission)
            .where(Commission.is_active.is_(True))
            .options(selectinload(Commission.payments))
        )
        count_query = select(func.count(Commission.id)).where(Commission.is_active.is_(True))

        if filters:
            if filters.seller_id:
                query = query.where(Commission.seller_id == filters.seller_id)
                count_query = count_query.where(Commission.seller_id == filters.seller_id)
            if filters.proposal_id:
                query = query.where(Commission.proposal_id == filters.proposal_id)
                count_query = count_query.where(Commission.proposal_id == filters.proposal_id)
            if filters.status:
                query = query.where(Commission.status == filters.status.value)
                count_query = count_query.where(Commission.status == filters.status.value)
            if filters.trigger:
                query = query.where(Commission.trigger == filters.trigger.value)
                count_query = count_query.where(Commission.trigger == filters.trigger.value)
            if filters.is_overdue:
                today = date.today()
                if filters.is_overdue:
                    query = query.where(
                        and_(
                            Commission.due_date < today,
                            Commission.status != CommissionStatus.PAID.value,
                        )
                    )
            if filters.min_value:
                query = query.where(Commission.final_commission >= filters.min_value)
                count_query = count_query.where(Commission.final_commission >= filters.min_value)
            if filters.max_value:
                query = query.where(Commission.final_commission <= filters.max_value)
                count_query = count_query.where(Commission.final_commission <= filters.max_value)
            if filters.date_from:
                dt_from = datetime.combine(filters.date_from, datetime.min.time())
                query = query.where(Commission.created_at >= dt_from)
                count_query = count_query.where(Commission.created_at >= dt_from)
            if filters.date_to:
                dt_to = datetime.combine(filters.date_to, datetime.max.time())
                query = query.where(Commission.created_at <= dt_to)
                count_query = count_query.where(Commission.created_at <= dt_to)
            if filters.due_date_from:
                query = query.where(Commission.due_date >= filters.due_date_from)
                count_query = count_query.where(Commission.due_date >= filters.due_date_from)
            if filters.due_date_to:
                query = query.where(Commission.due_date <= filters.due_date_to)
                count_query = count_query.where(Commission.due_date <= filters.due_date_to)

        query = query.order_by(Commission.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        commissions = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        return commissions, total

    async def update(self, commission_id: str, data: CommissionUpdate) -> Commission | None:
        """Atualiza comissão."""
        commission = await self.get_by_id(commission_id)
        if not commission:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "adjustments" and value is not None:
                commission.adjustments = value
                commission.final_commission = commission.base_commission + value
            else:
                setattr(commission, field, value)

        commission.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(commission, ["payments"])

        logger.info(f"Commission atualizada: {commission.id}")
        return commission

    async def update_status(
        self,
        commission_id: str,
        status: CommissionStatus,
        approved_by_id: str | None = None,
        notes: str | None = None,
    ) -> Commission | None:
        """Atualiza status da comissão."""
        commission = await self.get_by_id(commission_id)
        if not commission:
            return None

        old_status = commission.status
        commission.status = status.value

        if status == CommissionStatus.APPROVED:
            commission.approved_by_id = approved_by_id
            commission.approved_at = datetime.utcnow()
        elif status == CommissionStatus.PAID:
            commission.paid_date = date.today()

        if notes:
            commission.notes = notes

        commission.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(commission, ["payments"])

        logger.info(f"Commission {commission.id} status: {old_status} -> {status.value}")
        return commission

    async def delete(self, commission_id: str) -> bool:
        """Soft delete de comissão."""
        commission = await self.get_by_id(commission_id)
        if not commission:
            return False

        commission.is_active = False
        commission.updated_at = datetime.utcnow()
        await self.db.commit()

        logger.info(f"Commission desativada: {commission_id}")
        return True

    # ==================== Payments ====================

    async def create_payment(
        self, data: CommissionPaymentCreate, created_by_id: str | None = None
    ) -> CommissionPayment | None:
        """Cria pagamento de comissão."""
        commission = await self.get_by_id(data.commission_id)
        if not commission:
            return None

        # Verificar se não excede o valor pendente
        if data.amount > commission.pending_amount:
            logger.warning(f"Tentativa de pagamento {data.amount} excede pendente {commission.pending_amount}")
            return None

        payment = CommissionPayment(
            id=str(uuid4()),
            commission_id=data.commission_id,
            amount=data.amount,
            payment_method=data.payment_method.value,
            payment_date=data.payment_date,
            payment_reference=data.payment_reference,
            bank_account=data.bank_account,
            transaction_id=data.transaction_id,
            notes=data.notes,
            is_confirmed=False,
            created_by_id=created_by_id,
        )

        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)

        logger.info(f"Payment criado: {payment.id} para comissão {data.commission_id}")
        return payment

    async def confirm_payment(
        self, payment_id: str, confirmed_by_id: str, notes: str | None = None
    ) -> CommissionPayment | None:
        """Confirma pagamento."""
        result = await self.db.execute(select(CommissionPayment).where(CommissionPayment.id == payment_id))
        payment = result.scalar_one_or_none()
        if not payment:
            return None

        payment.is_confirmed = True
        payment.confirmed_at = datetime.utcnow()
        payment.confirmed_by_id = confirmed_by_id
        if notes:
            payment.notes = notes

        # Atualizar status da comissão se totalmente pago
        commission = await self.get_by_id(payment.commission_id)
        if commission and commission.pending_amount <= 0:
            commission.status = CommissionStatus.PAID.value
            commission.paid_date = date.today()

        await self.db.commit()
        await self.db.refresh(payment)

        logger.info(f"Payment {payment_id} confirmado")
        return payment

    # ==================== Summaries ====================

    async def get_or_create_summary(self, seller_id: str, year: int, month: int) -> CommissionSummary:
        """Busca ou cria resumo mensal."""
        result = await self.db.execute(
            select(CommissionSummary).where(
                CommissionSummary.seller_id == seller_id,
                CommissionSummary.year == year,
                CommissionSummary.month == month,
            )
        )
        summary = result.scalar_one_or_none()

        if not summary:
            summary = CommissionSummary(
                id=str(uuid4()),
                seller_id=seller_id,
                year=year,
                month=month,
                total_sales=0.0,
                total_sales_count=0,
                total_commissions=0.0,
                total_paid=0.0,
                total_pending=0.0,
                bonus_earned=0.0,
                is_closed=False,
            )
            self.db.add(summary)
            await self.db.commit()
            await self.db.refresh(summary)

        return summary

    async def update_summary(self, seller_id: str, year: int, month: int) -> CommissionSummary:
        """Atualiza resumo mensal com dados das comissões."""
        summary = await self.get_or_create_summary(seller_id, year, month)

        # Buscar comissões do período
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        result = await self.db.execute(
            select(Commission).where(
                Commission.seller_id == seller_id,
                Commission.is_active.is_(True),
                Commission.created_at >= datetime.combine(start_date, datetime.min.time()),
                Commission.created_at <= datetime.combine(end_date, datetime.max.time()),
            )
        )
        commissions = list(result.scalars().all())

        # Atualizar totais
        summary = self.service.update_summary(summary, commissions)
        await self.db.commit()
        await self.db.refresh(summary)

        return summary

    async def list_summaries(self, filters: CommissionSummaryFilter | None = None) -> builtins.list[CommissionSummary]:
        """Lista resumos mensais."""
        query = select(CommissionSummary)

        if filters:
            if filters.seller_id:
                query = query.where(CommissionSummary.seller_id == filters.seller_id)
            if filters.year:
                query = query.where(CommissionSummary.year == filters.year)
            if filters.month:
                query = query.where(CommissionSummary.month == filters.month)
            if filters.is_closed is not None:
                query = query.where(CommissionSummary.is_closed == filters.is_closed)

        query = query.order_by(
            CommissionSummary.year.desc(),
            CommissionSummary.month.desc(),
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def close_summary(self, seller_id: str, year: int, month: int) -> CommissionSummary | None:
        """Fecha resumo mensal (não permite mais alterações)."""
        summary = await self.get_or_create_summary(seller_id, year, month)

        summary.is_closed = True
        summary.closed_at = datetime.utcnow()
        summary.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(summary)

        logger.info(f"Summary fechado: {seller_id} {year}/{month}")
        return summary

    # ==================== Statistics ====================

    async def get_all_for_stats(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> builtins.list[Commission]:
        """Busca todas as comissões para cálculo de estatísticas."""
        # selectinload(payments): calculate_stats acessa paid_amount/pending_amount (que
        # leem self.payments) -> evita MissingGreenlet quando ha comissoes com dados.
        query = (
            select(Commission)
            .where(Commission.is_active.is_(True))
            .options(selectinload(Commission.payments))
        )

        if date_from:
            dt_from = datetime.combine(date_from, datetime.min.time())
            query = query.where(Commission.created_at >= dt_from)
        if date_to:
            dt_to = datetime.combine(date_to, datetime.max.time())
            query = query.where(Commission.created_at <= dt_to)

        result = await self.db.execute(query)
        return list(result.scalars().all())
