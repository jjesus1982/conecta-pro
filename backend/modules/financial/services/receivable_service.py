"""Service para contas a receber."""

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.financial.models.receivable_account import ReceivableAccount, ReceivableStatus
from modules.financial.models.receivable_installment import (
    InstallmentStatus,
    ReceivableInstallment,
)
from modules.financial.models.receivable_payment import PaymentStatus, ReceivablePayment
from modules.financial.repositories.receivable_repository import (
    CustomerRepository,
    ReceivableAccountRepository,
    ReceivableCategoryRepository,
    ReceivableInstallmentRepository,
    ReceivablePaymentRepository,
)
from modules.financial.schemas.receivable import (
    ReceivableAccountCreate,
    ReceivableAccountFilter,
    ReceivableAccountStats,
    ReceivableAccountUpdate,
    ReceivableBulkPaymentRequest,
    ReceivableInstallmentRenegotiateRequest,
    ReceivableInstallmentUpdate,
    ReceivablePaymentCreate,
    ReceivablePaymentReconcileRequest,
    ReceivablePaymentReverseRequest,
)

logger = logging.getLogger(__name__)


class ReceivableService:
    """Service para operacoes com contas a receber."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.account_repo = ReceivableAccountRepository(session)
        self.installment_repo = ReceivableInstallmentRepository(session)
        self.payment_repo = ReceivablePaymentRepository(session)
        self.customer_repo = CustomerRepository(session)
        self.category_repo = ReceivableCategoryRepository(session)

    # ==================== CONTAS ====================

    async def create_account(
        self,
        data: ReceivableAccountCreate,
        user_id: UUID,
    ) -> ReceivableAccount:
        """Cria uma nova conta a receber."""
        logger.info(f"Criando conta a receber: {data.description}")

        account = await self.account_repo.create(data, user_id)

        # Atualiza divida do cliente se tiver
        if account.customer_id:
            customer = await self.customer_repo.get_by_id(account.customer_id)
            if customer:
                customer.total_debt += account.net_value

        await self.session.commit()

        logger.info(f"Conta criada com sucesso: {account.id}")
        return account

    async def get_account(self, account_id: UUID) -> ReceivableAccount | None:
        """Busca conta por ID."""
        return await self.account_repo.get_by_id(account_id, with_relations=True)

    async def list_accounts(
        self,
        condominio_id: UUID | None,
        filters: ReceivableAccountFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[ReceivableAccount], int]:
        """Lista contas com filtros e paginacao."""
        accounts = await self.account_repo.list(condominio_id, filters, skip, limit)
        total = await self.account_repo.count(condominio_id, filters)
        return accounts, total

    async def update_account(
        self,
        account_id: UUID,
        data: ReceivableAccountUpdate,
        user_id: UUID,  # pylint: disable=unused-argument
    ) -> ReceivableAccount | None:
        """Atualiza uma conta a receber."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None

        if account.status in [ReceivableStatus.PAGA.value, ReceivableStatus.CANCELADA.value]:
            raise ValueError(f"Conta em status {account.status} nao pode ser alterada")

        account = await self.account_repo.update(account, data)
        await self.session.commit()

        logger.info(f"Conta atualizada: {account_id}")
        return account

    async def delete_account(  # pylint: disable=unused-argument
        self, account_id: UUID, user_id: UUID
    ) -> bool:
        """Deleta uma conta (soft delete)."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return False

        if account.status == ReceivableStatus.PAGA.value:
            raise ValueError("Conta paga nao pode ser excluida")

        # Reverte divida do cliente
        if account.customer_id:
            customer = await self.customer_repo.get_by_id(account.customer_id)
            if customer:
                customer.total_debt -= account.net_value - account.paid_value

        await self.account_repo.delete(account)
        await self.session.commit()

        logger.info(f"Conta excluida: {account_id}")
        return True

    async def get_stats(self, condominio_id: UUID) -> ReceivableAccountStats:
        """Retorna estatisticas de contas a receber."""
        return await self.account_repo.get_stats(condominio_id)

    # ==================== CANCELAMENTO/SUSPENSAO ====================

    async def cancel_account(
        self,
        account_id: UUID,
        user_id: UUID,  # pylint: disable=unused-argument
        reason: str,
    ) -> ReceivableAccount | None:
        """Cancela uma conta."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None

        if account.status in [ReceivableStatus.PAGA.value, ReceivableStatus.CANCELADA.value]:
            raise ValueError(f"Conta em status {account.status} nao pode ser cancelada")

        # Reverte divida do cliente
        if account.customer_id:
            customer = await self.customer_repo.get_by_id(account.customer_id)
            if customer:
                remaining = account.net_value - account.paid_value
                customer.total_debt -= remaining
                if account.is_overdue:
                    customer.overdue_debt -= remaining

        account.cancel(reason)
        await self.session.commit()

        logger.info(f"Conta cancelada: {account_id}")
        return account

    async def suspend_account(
        self,
        account_id: UUID,
        user_id: UUID,  # pylint: disable=unused-argument
        reason: str,
    ) -> ReceivableAccount | None:
        """Suspende uma conta."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None

        if account.status != ReceivableStatus.PENDENTE.value:
            raise ValueError("Apenas contas pendentes podem ser suspensas")

        account.suspend(reason)
        await self.session.commit()

        logger.info(f"Conta suspensa: {account_id}")
        return account

    # ==================== PROTESTO/BAIXA ====================

    async def protest_account(
        self,
        account_id: UUID,
        user_id: UUID,
        protest_number: str,
    ) -> ReceivableAccount | None:
        """Envia conta para protesto."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None

        if account.status not in [ReceivableStatus.VENCIDA.value]:
            raise ValueError("Apenas contas vencidas podem ser protestadas")

        account.protest(user_id, protest_number)
        await self.session.commit()

        logger.info(f"Conta enviada para protesto: {account_id}")
        return account

    async def write_off_account(
        self,
        account_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> ReceivableAccount | None:
        """Baixa conta (perda)."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None

        if account.status in [ReceivableStatus.PAGA.value, ReceivableStatus.CANCELADA.value]:
            raise ValueError(f"Conta em status {account.status} nao pode ser baixada")

        # Remove da divida do cliente
        if account.customer_id:
            customer = await self.customer_repo.get_by_id(account.customer_id)
            if customer:
                remaining = account.net_value - account.paid_value
                customer.total_debt -= remaining
                if account.is_overdue:
                    customer.overdue_debt -= remaining

        account.write_off(user_id, reason)
        await self.session.commit()

        logger.info(f"Conta baixada: {account_id}")
        return account

    # ==================== RECEBIMENTOS ====================

    async def register_payment(
        self,
        installment_id: UUID,
        data: ReceivablePaymentCreate,
        user_id: UUID,
    ) -> ReceivablePayment:
        """Registra recebimento de uma parcela."""
        if getattr(data, "installment_id", None) != installment_id:
            data = data.model_copy(update={"installment_id": installment_id})  # a parcela do caminho manda (08/09/2026)
        installment = await self.installment_repo.get_by_id(installment_id)
        if not installment:
            raise ValueError("Parcela nao encontrada")

        if installment.status in [
            InstallmentStatus.PAGA.value,
            InstallmentStatus.CANCELADA.value,
        ]:
            raise ValueError(f"Parcela em status {installment.status} nao pode ser paga")

        # Cria o recebimento
        payment = await self.payment_repo.create(data, user_id)
        await self.session.commit()

        logger.info(f"Recebimento registrado: {payment.id} para parcela {installment_id}")
        return payment

    async def bulk_payment(
        self,
        request: ReceivableBulkPaymentRequest,
        user_id: UUID,
    ) -> tuple[int, int, list[UUID]]:
        """Processa recebimento em lote."""
        from sqlalchemy import select as sa_select

        success_count = 0
        error_count = 0
        payment_ids = []

        # 1 query para buscar todas as parcelas — evita N+1
        result = await self.session.execute(
            sa_select(ReceivableInstallment).where(ReceivableInstallment.id.in_(request.installment_ids))
        )
        installments_map = {str(inst.id): inst for inst in result.scalars().all()}

        for installment_id in request.installment_ids:
            try:
                installment = installments_map.get(str(installment_id))
                if not installment:
                    error_count += 1
                    continue

                payment_data = ReceivablePaymentCreate(
                    installment_id=installment_id,
                    paid_value=installment.calculate_current_value(),
                    payment_date=request.payment_date,
                    payment_method_id=request.payment_method_id,
                    bank_account_id=request.bank_account_id,
                )

                payment = await self.register_payment(installment_id, payment_data, user_id)
                payment_ids.append(payment.id)
                success_count += 1

            except (ValueError, TypeError, RuntimeError) as e:
                logger.error(f"Erro ao receber parcela {installment_id}: {e}")
                error_count += 1

        return success_count, error_count, payment_ids

    async def reverse_payment(
        self,
        payment_id: UUID,
        request: ReceivablePaymentReverseRequest,
        user_id: UUID,
    ) -> ReceivablePayment | None:
        """Estorna um recebimento."""
        payment = await self.payment_repo.get_by_id(payment_id)
        if not payment:
            return None

        if payment.status != PaymentStatus.CONFIRMADO.value:
            raise ValueError("Apenas recebimentos confirmados podem ser estornados")

        payment.reverse(user_id, request.reason)

        # Reverte status da parcela
        installment = await self.installment_repo.get_by_id(payment.installment_id)
        if installment:
            installment.status = InstallmentStatus.PENDENTE.value
            installment.paid_value = Decimal("0")
            installment.payment_date = None

        # Atualiza conta
        account = await self.account_repo.get_by_id(installment.receivable_account_id)
        if account:
            account.paid_value = Decimal(account.paid_value or 0) - payment.paid_value
            if account.paid_value < account.net_value:
                account.status = ReceivableStatus.PENDENTE.value

        # Atualiza divida do cliente
        if account and account.customer_id:
            customer = await self.customer_repo.get_by_id(account.customer_id)
            if customer:
                customer.total_debt += payment.paid_value

        await self.session.commit()
        logger.info(f"Recebimento estornado: {payment_id}")
        return payment

    async def reconcile_payment(
        self,
        payment_id: UUID,
        request: ReceivablePaymentReconcileRequest,
        user_id: UUID,
    ) -> ReceivablePayment | None:
        """Concilia recebimento com extrato bancario."""
        payment = await self.payment_repo.get_by_id(payment_id)
        if not payment:
            return None

        payment.reconcile(user_id, request.notes)
        await self.session.commit()

        logger.info(f"Recebimento conciliado: {payment_id}")
        return payment

    # ==================== PARCELAS ====================

    async def get_installment(
        self,
        installment_id: UUID,
    ) -> ReceivableInstallment | None:
        """Busca parcela por ID."""
        return await self.installment_repo.get_by_id(installment_id)

    async def list_installments(
        self,
        account_id: UUID,
    ) -> list[ReceivableInstallment]:
        """Lista parcelas de uma conta."""
        return await self.installment_repo.list_by_account(account_id)

    async def update_installment(
        self,
        installment_id: UUID,
        data: ReceivableInstallmentUpdate,
    ) -> ReceivableInstallment | None:
        """Atualiza uma parcela."""
        installment = await self.installment_repo.get_by_id(installment_id)
        if not installment:
            return None

        if installment.status in [
            InstallmentStatus.PAGA.value,
            InstallmentStatus.CANCELADA.value,
        ]:
            raise ValueError(f"Parcela em status {installment.status} nao pode ser alterada")

        installment = await self.installment_repo.update(installment, data)
        await self.session.commit()
        return installment

    async def renegotiate_installment(
        self,
        installment_id: UUID,
        request: ReceivableInstallmentRenegotiateRequest,
        user_id: UUID,  # pylint: disable=unused-argument
    ) -> ReceivableInstallment | None:
        """Renegocia uma parcela."""
        installment = await self.installment_repo.get_by_id(installment_id)
        if not installment:
            return None

        if installment.status in [
            InstallmentStatus.PAGA.value,
            InstallmentStatus.CANCELADA.value,
        ]:
            raise ValueError(f"Parcela em status {installment.status} nao pode ser renegociada")

        installment.renegotiate(
            new_due_date=request.new_due_date,
            new_value=Decimal(str(request.new_value)) if request.new_value else None,
            reason=request.reason,
        )
        await self.session.commit()

        logger.info(f"Parcela renegociada: {installment_id}")
        return installment

    # ==================== CONSULTAS ====================

    async def get_overdue_accounts(
        self,
        condominio_id: UUID,
        limit: int = 100,
    ) -> list[ReceivableAccount]:
        """Retorna contas vencidas."""
        return await self.account_repo.get_overdue(condominio_id, limit)

    async def get_due_soon_accounts(
        self,
        condominio_id: UUID,
        days: int = 7,
        limit: int = 100,
    ) -> list[ReceivableAccount]:
        """Retorna contas a vencer nos proximos dias."""
        return await self.account_repo.get_due_soon(condominio_id, days, limit)

    async def get_pending_installments(
        self,
        condominio_id: UUID,
        due_date_start: date | None = None,
        due_date_end: date | None = None,
    ) -> list[ReceivableInstallment]:
        """Retorna parcelas pendentes."""
        return await self.installment_repo.get_pending(condominio_id, due_date_start, due_date_end)

    async def get_pending_reconciliation(
        self,
        condominio_id: UUID,
    ) -> list[ReceivablePayment]:
        """Retorna recebimentos pendentes de conciliacao."""
        return await self.payment_repo.get_pending_reconciliation(condominio_id)

    async def get_customer_debt(
        self,
        customer_id: UUID,
    ) -> tuple[Decimal, Decimal]:
        """Retorna divida do cliente (total, vencida)."""
        customer = await self.customer_repo.get_by_id(customer_id)
        if not customer:
            return Decimal("0"), Decimal("0")
        return customer.total_debt, customer.overdue_debt

    async def get_unit_debt(
        self,
        unidade_id: UUID,
    ) -> tuple[Decimal, Decimal]:
        """Retorna divida da unidade (total, vencida)."""
        accounts = await self.account_repo.get_by_unidade(unidade_id)
        total = Decimal("0")
        overdue = Decimal("0")

        for account in accounts:
            if account.status not in [
                ReceivableStatus.PAGA.value,
                ReceivableStatus.CANCELADA.value,
            ]:
                remaining = account.net_value - account.paid_value
                total += remaining
                if account.is_overdue:
                    overdue += remaining

        return total, overdue
