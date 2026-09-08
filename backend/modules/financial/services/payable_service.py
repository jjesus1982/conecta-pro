"""Service para contas a pagar."""

import logging
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from dateutil.relativedelta import relativedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.financial.models.payable_account import PayableAccount, PayableStatus
from modules.financial.models.payable_installment import InstallmentStatus, PayableInstallment
from modules.financial.models.payable_payment import PayablePayment, PaymentStatus
from modules.financial.repositories.payable_repository import (
    PayableAccountRepository,
    PayableInstallmentRepository,
    PayablePaymentRepository,
)
from modules.financial.schemas.payable import (
    PayableAccountCreate,
    PayableAccountFilter,
    PayableAccountStats,
    PayableAccountUpdate,
    PayableBulkApproveRequest,
    PayableBulkPaymentRequest,
    PayableInstallmentRenegotiateRequest,
    PayableInstallmentUpdate,
    PayablePaymentCreate,
    PayablePaymentReconcileRequest,
    PayablePaymentReverseRequest,
    PayableScheduleRequest,
)

logger = logging.getLogger(__name__)


class PayableService:
    """Service para operações com contas a pagar."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.account_repo = PayableAccountRepository(session)
        self.installment_repo = PayableInstallmentRepository(session)
        self.payment_repo = PayablePaymentRepository(session)

    # ==================== CONTAS ====================

    async def create_account(
        self,
        data: PayableAccountCreate,
        user_id: UUID,
    ) -> PayableAccount:
        """Cria uma nova conta a pagar."""
        logger.info(f"Criando conta a pagar: {data.description}")

        account = await self.account_repo.create(data, user_id)
        await self.session.commit()

        logger.info(f"Conta criada com sucesso: {account.id}")
        return account

    async def get_account(self, account_id: UUID) -> PayableAccount | None:
        """Busca conta por ID."""
        return await self.account_repo.get_by_id(account_id)

    async def list_accounts(
        self,
        condominio_id: UUID | None,
        filters: PayableAccountFilter | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[PayableAccount], int]:
        """Lista contas com filtros e paginação."""
        accounts = await self.account_repo.list(condominio_id, filters, skip, limit)
        total = await self.account_repo.count(condominio_id, filters)
        return accounts, total

    async def update_account(
        self,
        account_id: UUID,
        data: PayableAccountUpdate,
        user_id: UUID,  # pylint: disable=unused-argument
    ) -> PayableAccount | None:
        """Atualiza uma conta a pagar."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None

        if account.status in [PayableStatus.PAGA.value, PayableStatus.CANCELADA.value]:
            raise ValueError(f"Conta em status {account.status} não pode ser alterada")

        account = await self.account_repo.update(account, data)
        await self.session.commit()

        logger.info(f"Conta atualizada: {account_id}")
        return account

    async def delete_account(self, account_id: UUID, user_id: UUID) -> bool:  # pylint: disable=unused-argument
        """Deleta uma conta (soft delete)."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return False

        if account.status == PayableStatus.PAGA.value:
            raise ValueError("Conta paga não pode ser excluída")

        await self.account_repo.delete(account)
        await self.session.commit()

        logger.info(f"Conta excluída: {account_id}")
        return True

    async def get_stats(self, condominio_id: UUID) -> PayableAccountStats:
        """Retorna estatísticas de contas a pagar."""
        return await self.account_repo.get_stats(condominio_id)

    # ==================== APROVAÇÃO ====================

    async def approve_account(
        self,
        account_id: UUID,
        user_id: UUID,
        notes: str | None = None,
    ) -> PayableAccount | None:
        """Aprova uma conta para pagamento."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None

        if account.status != PayableStatus.PENDENTE.value:
            raise ValueError("Apenas contas pendentes podem ser aprovadas")

        account.approve(user_id)
        if notes:
            account.notes = (account.notes or "") + f"\n[Aprovação] {notes}"

        await self.session.commit()
        logger.info(f"Conta aprovada: {account_id}")
        return account

    async def bulk_approve(
        self,
        request: PayableBulkApproveRequest,
        user_id: UUID,
    ) -> tuple[int, int]:
        """Aprova múltiplas contas."""
        success_count = 0
        error_count = 0

        for account_id in request.account_ids:
            try:
                result = await self.approve_account(account_id, user_id, request.notes)
                if result:
                    success_count += 1
                else:
                    error_count += 1
            except (ValueError, TypeError, RuntimeError) as e:
                logger.error(f"Erro ao aprovar conta {account_id}: {e}")
                error_count += 1

        return success_count, error_count

    async def reject_account(
        self,
        account_id: UUID,
        user_id: UUID,  # pylint: disable=unused-argument
        reason: str,
    ) -> PayableAccount | None:
        """Rejeita uma conta."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None

        if account.status != PayableStatus.PENDENTE.value:
            raise ValueError("Apenas contas pendentes podem ser rejeitadas")

        account.cancel(reason)
        await self.session.commit()

        logger.info(f"Conta rejeitada: {account_id}")
        return account

    # ==================== AGENDAMENTO ====================

    async def schedule_payment(
        self,
        account_id: UUID,
        request: PayableScheduleRequest,
        user_id: UUID,
    ) -> PayableAccount | None:
        """Agenda pagamento de uma conta."""
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            return None

        if account.status not in [PayableStatus.APROVADA.value, PayableStatus.PENDENTE.value]:
            raise ValueError(f"Conta em status {account.status} não pode ser agendada")

        account.schedule_payment(
            scheduled_date=request.scheduled_date,
            payment_method_id=request.payment_method_id,
            user_id=user_id,
        )
        await self.session.commit()

        logger.info(f"Conta agendada para {request.scheduled_date}: {account_id}")
        return account

    # ==================== PAGAMENTOS ====================

    async def register_payment(
        self,
        installment_id: UUID,
        data: PayablePaymentCreate,
        user_id: UUID,
    ) -> PayablePayment:
        """Registra pagamento de uma parcela."""
        if getattr(data, "installment_id", None) != installment_id:
            data = data.model_copy(update={"installment_id": installment_id})  # a parcela do caminho manda (08/09/2026)
        installment = await self.installment_repo.get_by_id(installment_id)
        if not installment:
            raise ValueError("Parcela não encontrada")

        if installment.status in [InstallmentStatus.PAGA.value, InstallmentStatus.CANCELADA.value]:
            raise ValueError(f"Parcela em status {installment.status} não pode ser paga")

        # Cria o pagamento
        payment = await self.payment_repo.create(
            data=data,
            user_id=user_id,
        )
        await self.session.commit()

        logger.info(f"Pagamento registrado: {payment.id} para parcela {installment_id}")
        return payment

    async def bulk_payment(
        self,
        request: PayableBulkPaymentRequest,
        user_id: UUID,
    ) -> tuple[int, int, list[UUID]]:
        """Processa pagamento em lote."""
        from sqlalchemy import select as sa_select

        success_count = 0
        error_count = 0
        payment_ids = []

        # 1 query para buscar todas as parcelas — evita N+1
        result = await self.session.execute(
            sa_select(PayableInstallment).where(PayableInstallment.id.in_(request.installment_ids))
        )
        installments_map = {str(inst.id): inst for inst in result.scalars().all()}

        for installment_id in request.installment_ids:
            try:
                # Parcela já carregada em memória — sem query adicional
                installment = installments_map.get(str(installment_id))
                if not installment:
                    error_count += 1
                    continue

                payment_data = PayablePaymentCreate(
                    installment_id=installment_id,
                    payment_method_id=request.payment_method_id,
                    amount=str(installment.calculate_current_value()),
                    payment_date=request.payment_date,
                )

                payment = await self.register_payment(installment_id, payment_data, user_id)
                payment_ids.append(payment.id)
                success_count += 1

            except (ValueError, TypeError, RuntimeError) as e:
                logger.error(f"Erro ao pagar parcela {installment_id}: {e}")
                error_count += 1

        return success_count, error_count, payment_ids

    async def reverse_payment(
        self,
        payment_id: UUID,
        request: PayablePaymentReverseRequest,
        user_id: UUID,
    ) -> PayablePayment | None:
        """Estorna um pagamento."""
        payment = await self.payment_repo.get_by_id(payment_id)
        if not payment:
            return None

        if payment.status != PaymentStatus.CONFIRMADO.value:
            raise ValueError("Apenas pagamentos confirmados podem ser estornados")

        payment.reverse(user_id, request.reason)

        # Reverte status da parcela
        installment = await self.installment_repo.get_by_id(payment.installment_id)
        if installment:
            installment.status = InstallmentStatus.PENDENTE.value
            installment.paid_amount = Decimal("0")
            installment.payment_date = None

        # Atualiza conta
        account = await self.account_repo.get_by_id(installment.payable_account_id)
        if account:
            account.paid_value = Decimal(account.paid_value or 0) - payment.paid_value
            if account.paid_value < account.net_value:
                account.status = PayableStatus.APROVADA.value

        await self.session.commit()
        logger.info(f"Pagamento estornado: {payment_id}")
        return payment

    async def reconcile_payment(
        self,
        payment_id: UUID,
        request: PayablePaymentReconcileRequest,
        user_id: UUID,
    ) -> PayablePayment | None:
        """Reconcilia pagamento com extrato bancário."""
        payment = await self.payment_repo.get_by_id(payment_id)
        if not payment:
            return None

        payment.reconcile(
            bank_transaction_id=request.bank_transaction_id,
            reconciled_date=request.reconciled_date,
            user_id=user_id,
        )
        await self.session.commit()

        logger.info(f"Pagamento reconciliado: {payment_id}")
        return payment

    # ==================== PARCELAS ====================

    async def get_installment(
        self,
        installment_id: UUID,
    ) -> PayableInstallment | None:
        """Busca parcela por ID."""
        return await self.installment_repo.get_by_id(installment_id)

    async def list_installments(
        self,
        account_id: UUID,
    ) -> list[PayableInstallment]:
        """Lista parcelas de uma conta."""
        return await self.installment_repo.list_by_account(account_id)

    async def update_installment(
        self,
        installment_id: UUID,
        data: PayableInstallmentUpdate,
    ) -> PayableInstallment | None:
        """Atualiza uma parcela."""
        installment = await self.installment_repo.get_by_id(installment_id)
        if not installment:
            return None

        if installment.status in [InstallmentStatus.PAGA.value, InstallmentStatus.CANCELADA.value]:
            raise ValueError(f"Parcela em status {installment.status} não pode ser alterada")

        installment = await self.installment_repo.update(installment, data)
        await self.session.commit()
        return installment

    async def renegotiate_installment(
        self,
        installment_id: UUID,
        request: PayableInstallmentRenegotiateRequest,
        user_id: UUID,  # pylint: disable=unused-argument
    ) -> PayableInstallment | None:
        """Renegocia uma parcela."""
        installment = await self.installment_repo.get_by_id(installment_id)
        if not installment:
            return None

        if installment.status in [InstallmentStatus.PAGA.value, InstallmentStatus.CANCELADA.value]:
            raise ValueError(f"Parcela em status {installment.status} não pode ser renegociada")

        installment.renegotiate(
            new_due_date=request.new_due_date,
            new_value=Decimal(request.new_value),
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
    ) -> list[PayableAccount]:
        """Retorna contas vencidas."""
        return await self.account_repo.get_overdue(condominio_id, limit)

    async def get_due_soon_accounts(
        self,
        condominio_id: UUID | None,
        days: int = 7,
        limit: int = 100,
    ) -> list[PayableAccount]:
        """Retorna contas a vencer nos próximos dias."""
        return await self.account_repo.get_due_soon(condominio_id, days, limit)

    async def get_pending_installments(
        self,
        condominio_id: UUID,
        due_date_start: date | None = None,
        due_date_end: date | None = None,
    ) -> list[PayableInstallment]:
        """Retorna parcelas pendentes."""
        return await self.installment_repo.get_pending(condominio_id, due_date_start, due_date_end)

    async def get_pending_reconciliation(
        self,
        condominio_id: UUID,
    ) -> list[PayablePayment]:
        """Retorna pagamentos pendentes de reconciliação."""
        return await self.payment_repo.get_pending_reconciliation(condominio_id)

    # ==================== RECORRÊNCIA ====================

    async def process_recurring_accounts(
        self,
        condominio_id: UUID,
        reference_date: date | None = None,
    ) -> list[PayableAccount]:
        """Processa contas recorrentes e gera novas."""
        if reference_date is None:
            reference_date = date.today()

        # Busca contas recorrentes ativas
        filters = PayableAccountFilter(
            is_recurring=True,
            status=PayableStatus.PAGA.value,
        )
        accounts, _ = await self.list_accounts(condominio_id, filters)

        created_accounts = []
        for account in accounts:
            if not account.recurrence_type:
                continue

            next_date = self._calculate_next_recurrence_date(
                account.recurrence_type.value,
                account.due_date,
            )

            if next_date and next_date <= reference_date + timedelta(days=30):
                # Cria nova conta baseada na recorrente
                ja_existe = (await self.session.execute(text(
                    "SELECT 1 FROM payable_accounts WHERE parent_recurrence_id = :pai AND due_date = :venc LIMIT 1"
                ), {"pai": account.parent_recurrence_id or account.id, "venc": next_date})).first()
                if ja_existe:  # cada chamada duplicava a conta do mês (08/09/2026)
                    continue
                new_data = PayableAccountCreate(
                    condominio_id=condominio_id,
                    supplier_id=account.supplier_id,
                    category_id=account.category_id,
                    description=account.description,
                    document_number=None,
                    gross_value=str(account.gross_value),
                    issue_date=date.today(),
                    due_date=next_date,
                    payment_method_id=account.payment_method_id,
                    is_recurring=True,
                    recurrence_type=account.recurrence_type,
                    parent_recurrence_id=account.parent_recurrence_id or account.id,
                )

                new_account = await self.account_repo.create(new_data, account.created_by)
                created_accounts.append(new_account)

        if created_accounts:
            await self.session.commit()
            logger.info(f"Criadas {len(created_accounts)} contas recorrentes para {condominio_id}")

        return created_accounts

    def _calculate_next_recurrence_date(
        self,
        recurrence_type: str,
        last_date: date,
    ) -> date | None:
        """Calcula próxima data de recorrência."""
        recurrence_map = {
            "DIARIO": relativedelta(days=1),
            "SEMANAL": relativedelta(weeks=1),
            "QUINZENAL": relativedelta(weeks=2),
            "MENSAL": relativedelta(months=1),
            "BIMESTRAL": relativedelta(months=2),
            "TRIMESTRAL": relativedelta(months=3),
            "SEMESTRAL": relativedelta(months=6),
            "ANUAL": relativedelta(years=1),
        }

        delta = recurrence_map.get(recurrence_type)
        if delta:
            return last_date + delta
        return None
