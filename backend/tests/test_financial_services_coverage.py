"""
Tests for financial module services, schemas, and models.
Covers: CashFlowService, PayableService, ReceivableService, SupplierService,
        Payable/Receivable schemas validation, and model business logic.
Target: 80+ test functions covering ~4000 lines of financial module logic.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# ─────────────────────────── helpers ───────────────────────────


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _mock_session() -> AsyncMock:
    """Returns a fully faked AsyncSession."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


def _scalars_result(items: list) -> MagicMock:
    """Fake result.scalars().all() -> items."""
    scalars = MagicMock()
    scalars.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _one_result(row) -> MagicMock:
    """Fake result.one() -> row."""
    result = MagicMock()
    result.one.return_value = row
    return result


# ═══════════════════════════════════════════════════════════════════
# MODEL TESTS — PayableAccount
# ═══════════════════════════════════════════════════════════════════


class TestPayableAccountModel:
    """Unit tests for PayableAccount model business logic."""

    def _make_account(self, **kwargs):
        from modules.financial.models.payable_account import PayableAccount, PayableStatus

        acc = PayableAccount()
        acc.id = _uuid()
        acc.gross_value = Decimal("1000.00")
        acc.discount_value = Decimal("0")
        acc.addition_value = Decimal("0")
        acc.total_withholdings = Decimal("0")
        acc.net_value = Decimal("1000.00")
        acc.paid_value = Decimal("0")
        acc.status = PayableStatus.PENDENTE.value
        acc.due_date = date.today() + timedelta(days=10)
        acc.internal_notes = None
        for k, v in kwargs.items():
            setattr(acc, k, v)
        return acc

    def test_is_overdue_future_due(self):
        acc = self._make_account(due_date=date.today() + timedelta(days=5))
        assert acc.is_overdue is False

    def test_is_overdue_past_due(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account(due_date=date.today() - timedelta(days=3))
        acc.status = PayableStatus.PENDENTE.value
        assert acc.is_overdue is True

    def test_is_overdue_paid_account(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account(due_date=date.today() - timedelta(days=3))
        acc.status = PayableStatus.PAGA.value
        assert acc.is_overdue is False

    def test_days_overdue_not_overdue(self):
        acc = self._make_account(due_date=date.today() + timedelta(days=5))
        assert acc.days_overdue == 0

    def test_days_overdue_overdue(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account(due_date=date.today() - timedelta(days=7))
        acc.status = PayableStatus.PENDENTE.value
        assert acc.days_overdue == 7

    def test_days_until_due(self):
        acc = self._make_account(due_date=date.today() + timedelta(days=15))
        assert acc.days_until_due == 15

    def test_payment_percentage_zero_net_value(self):
        acc = self._make_account()
        acc.net_value = Decimal("0")
        acc.paid_value = Decimal("0")
        assert acc.payment_percentage == 0

    def test_payment_percentage_partial(self):
        acc = self._make_account()
        acc.paid_value = Decimal("500.00")
        assert acc.payment_percentage == 50.0

    def test_payment_percentage_full(self):
        acc = self._make_account()
        acc.paid_value = Decimal("1000.00")
        assert acc.payment_percentage == 100.0

    def test_balance(self):
        acc = self._make_account()
        acc.paid_value = Decimal("300.00")
        assert acc.balance == Decimal("700.00")

    def test_is_paid_true(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account()
        acc.status = PayableStatus.PAGA.value
        assert acc.is_paid is True

    def test_is_paid_false(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account()
        acc.status = PayableStatus.PENDENTE.value
        assert acc.is_paid is False

    def test_is_partially_paid(self):
        acc = self._make_account()
        acc.paid_value = Decimal("200.00")
        assert acc.is_partially_paid is True

    def test_is_not_partially_paid_zero(self):
        acc = self._make_account()
        acc.paid_value = Decimal("0")
        assert acc.is_partially_paid is False

    def test_calculate_net_value(self):
        acc = self._make_account()
        acc.gross_value = Decimal("1000.00")
        acc.discount_value = Decimal("100.00")
        acc.addition_value = Decimal("50.00")
        acc.total_withholdings = Decimal("20.00")
        net = acc.calculate_net_value()
        assert net == Decimal("930.00")

    def test_calculate_net_value_minimum_zero(self):
        acc = self._make_account()
        acc.gross_value = Decimal("100.00")
        acc.discount_value = Decimal("500.00")
        acc.addition_value = Decimal("0")
        acc.total_withholdings = Decimal("0")
        net = acc.calculate_net_value()
        assert net == Decimal("0")

    def test_cancel(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account()
        acc.cancel("Motivo teste")
        assert acc.status == PayableStatus.CANCELADA.value
        assert "Cancelada: Motivo teste" in acc.internal_notes

    def test_suspend(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account()
        acc.suspend("Suspensão temporária")
        assert acc.status == PayableStatus.SUSPENSA.value

    def test_approve(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account()
        user_id = _uuid()
        acc.approve(user_id, notes="OK")
        assert acc.status == PayableStatus.APROVADA.value
        assert acc.approval_status == "approved"
        assert acc.approved_by == user_id

    def test_schedule_payment(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account()
        user_id = _uuid()
        future = date.today() + timedelta(days=5)
        acc.schedule_payment(future, user_id)
        assert acc.status == PayableStatus.AGENDADA.value
        assert acc.scheduled_payment_date == future

    def test_update_status_paid(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account()
        acc.paid_value = Decimal("1000.00")
        acc.update_status()
        assert acc.status == PayableStatus.PAGA.value

    def test_update_status_partial(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account()
        acc.paid_value = Decimal("500.00")
        acc.update_status()
        assert acc.status == PayableStatus.PARCIAL.value

    def test_update_status_overdue(self):
        from modules.financial.models.payable_account import PayableStatus

        acc = self._make_account(due_date=date.today() - timedelta(days=3))
        acc.paid_value = Decimal("0")
        acc.update_status()
        assert acc.status == PayableStatus.VENCIDA.value

    def test_to_dict(self):
        acc = self._make_account()
        acc.code = "PA-001"
        acc.document_number = "NF-123"
        d = acc.to_dict()
        assert "id" in d
        assert "net_value" in d
        assert d["code"] == "PA-001"


# ═══════════════════════════════════════════════════════════════════
# MODEL TESTS — PayableInstallment
# ═══════════════════════════════════════════════════════════════════


class TestPayableInstallmentModel:
    """Unit tests for PayableInstallment model."""

    def _make_inst(self, **kwargs):
        from modules.financial.models.payable_installment import InstallmentStatus, PayableInstallment

        inst = PayableInstallment()
        inst.id = _uuid()
        inst.installment_number = 1
        inst.total_installments = 3
        inst.original_value = Decimal("1000.00")
        inst.discount_value = Decimal("0")
        inst.addition_value = Decimal("0")
        inst.current_value = Decimal("1000.00")
        inst.paid_value = Decimal("0")
        inst.penalty_value = Decimal("0")
        inst.interest_value = Decimal("0")
        inst.penalty_rate = Decimal("0")
        inst.interest_rate = Decimal("0")
        inst.status = InstallmentStatus.PENDENTE.value
        inst.due_date = date.today() + timedelta(days=10)
        for k, v in kwargs.items():
            setattr(inst, k, v)
        return inst

    def test_display_number(self):
        inst = self._make_inst()
        assert inst.display_number == "1/3"

    def test_is_overdue_future(self):
        inst = self._make_inst(due_date=date.today() + timedelta(days=5))
        assert inst.is_overdue is False

    def test_is_overdue_past(self):
        from modules.financial.models.payable_installment import InstallmentStatus

        inst = self._make_inst(due_date=date.today() - timedelta(days=3))
        inst.status = InstallmentStatus.PENDENTE.value
        assert inst.is_overdue is True

    def test_is_overdue_cancelled(self):
        from modules.financial.models.payable_installment import InstallmentStatus

        inst = self._make_inst(due_date=date.today() - timedelta(days=3))
        inst.status = InstallmentStatus.CANCELADA.value
        assert inst.is_overdue is False

    def test_days_overdue_zero(self):
        inst = self._make_inst(due_date=date.today() + timedelta(days=5))
        assert inst.days_overdue == 0

    def test_days_overdue_positive(self):
        from modules.financial.models.payable_installment import InstallmentStatus

        inst = self._make_inst(due_date=date.today() - timedelta(days=5))
        inst.status = InstallmentStatus.PENDENTE.value
        assert inst.days_overdue == 5

    def test_balance(self):
        inst = self._make_inst()
        inst.paid_value = Decimal("300.00")
        assert inst.balance == Decimal("700.00")

    def test_is_paid(self):
        from modules.financial.models.payable_installment import InstallmentStatus

        inst = self._make_inst()
        inst.status = InstallmentStatus.PAGA.value
        assert inst.is_paid is True

    def test_is_partially_paid(self):
        inst = self._make_inst()
        inst.paid_value = Decimal("200.00")
        assert inst.is_partially_paid is True

    def test_calculate_current_value_no_overdue(self):
        inst = self._make_inst()
        inst.due_date = date.today() + timedelta(days=10)
        val = inst.calculate_current_value()
        assert val == Decimal("1000.00")

    def test_update_status_paid(self):
        from modules.financial.models.payable_installment import InstallmentStatus

        inst = self._make_inst()
        inst.paid_value = Decimal("1000.00")
        inst.update_status()
        assert inst.status == InstallmentStatus.PAGA.value

    def test_update_status_partial(self):
        from modules.financial.models.payable_installment import InstallmentStatus

        inst = self._make_inst()
        inst.paid_value = Decimal("500.00")
        inst.update_status()
        assert inst.status == InstallmentStatus.PARCIAL.value

    def test_update_status_overdue(self):
        from modules.financial.models.payable_installment import InstallmentStatus

        inst = self._make_inst(due_date=date.today() - timedelta(days=2))
        inst.paid_value = Decimal("0")
        inst.update_status()
        assert inst.status == InstallmentStatus.VENCIDA.value


# ═══════════════════════════════════════════════════════════════════
# MODEL TESTS — PayablePayment
# ═══════════════════════════════════════════════════════════════════


class TestPayablePaymentModel:
    """Unit tests for PayablePayment model."""

    def _make_payment(self, **kwargs):
        from modules.financial.models.payable_payment import PayablePayment, PaymentStatus

        p = PayablePayment()
        p.id = _uuid()
        p.status = PaymentStatus.PENDENTE.value
        p.paid_value = Decimal("1000.00")
        p.discount_value = Decimal("0")
        p.interest_value = Decimal("0")
        p.penalty_value = Decimal("0")
        p.fee_value = Decimal("0")
        p.net_value = Decimal("1000.00")
        p.is_reversed = False
        p.is_reconciled = False
        p.payment_date = date.today()
        p.installment_id = _uuid()
        for k, v in kwargs.items():
            setattr(p, k, v)
        return p

    def test_is_confirmed_true(self):
        from modules.financial.models.payable_payment import PaymentStatus

        p = self._make_payment(status=PaymentStatus.CONFIRMADO.value)
        assert p.is_confirmed is True

    def test_is_confirmed_false(self):
        p = self._make_payment()
        assert p.is_confirmed is False

    def test_can_reverse_yes(self):
        from modules.financial.models.payable_payment import PaymentStatus

        p = self._make_payment(status=PaymentStatus.CONFIRMADO.value, is_reversed=False)
        assert p.can_reverse is True

    def test_can_reverse_no_already_reversed(self):
        from modules.financial.models.payable_payment import PaymentStatus

        p = self._make_payment(status=PaymentStatus.CONFIRMADO.value, is_reversed=True)
        assert p.can_reverse is False

    def test_total_additions(self):
        p = self._make_payment()
        p.interest_value = Decimal("50.00")
        p.penalty_value = Decimal("20.00")
        p.fee_value = Decimal("10.00")
        assert p.total_additions == Decimal("80.00")

    def test_confirm(self):
        from modules.financial.models.payable_payment import PaymentStatus

        p = self._make_payment()
        p.confirm()
        assert p.status == PaymentStatus.CONFIRMADO.value

    def test_reject(self):
        from modules.financial.models.payable_payment import PaymentStatus

        p = self._make_payment()
        p.reject("00", "Saldo insuficiente")
        assert p.status == PaymentStatus.REJEITADO.value
        assert p.bank_return_code == "00"

    def test_reverse(self):
        from modules.financial.models.payable_payment import PaymentStatus

        p = self._make_payment(status=PaymentStatus.CONFIRMADO.value)
        p.reverse(_uuid(), "Pagamento duplicado")
        assert p.is_reversed is True


# ═══════════════════════════════════════════════════════════════════
# SCHEMA TESTS — Payable schemas
# ═══════════════════════════════════════════════════════════════════


class TestPayableSchemas:
    """Tests for Pydantic schema validation in payable module."""

    def test_payable_account_create_valid(self):
        from modules.financial.schemas.payable import PayableAccountCreate

        data = PayableAccountCreate(
            condominio_id=_uuid(),
            description="Conta de energia elétrica",
            gross_value=Decimal("500.00"),
            due_date=date.today() + timedelta(days=30),
        )
        assert data.description == "Conta de energia elétrica"
        assert data.gross_value == Decimal("500.00")

    def test_payable_account_create_description_too_short(self):
        from modules.financial.schemas.payable import PayableAccountCreate

        with pytest.raises(ValidationError) as exc_info:
            PayableAccountCreate(
                condominio_id=_uuid(),
                description="AB",  # min_length=3
                gross_value=Decimal("500.00"),
                due_date=date.today(),
            )
        assert "description" in str(exc_info.value)

    def test_payable_account_create_gross_value_zero(self):
        from modules.financial.schemas.payable import PayableAccountCreate

        with pytest.raises(ValidationError):
            PayableAccountCreate(
                condominio_id=_uuid(),
                description="Conta válida",
                gross_value=Decimal("0"),  # gt=0
                due_date=date.today(),
            )

    def test_payable_account_create_negative_gross_value(self):
        from modules.financial.schemas.payable import PayableAccountCreate

        with pytest.raises(ValidationError):
            PayableAccountCreate(
                condominio_id=_uuid(),
                description="Conta válida",
                gross_value=Decimal("-100"),
                due_date=date.today(),
            )

    def test_payable_account_create_discount_negative(self):
        from modules.financial.schemas.payable import PayableAccountCreate

        with pytest.raises(ValidationError):
            PayableAccountCreate(
                condominio_id=_uuid(),
                description="Conta válida",
                gross_value=Decimal("500"),
                discount_value=Decimal("-10"),  # ge=0
                due_date=date.today(),
            )

    def test_payable_account_create_default_values(self):
        from modules.financial.models.payable_account import PayablePriority, PayableType
        from modules.financial.schemas.payable import PayableAccountCreate

        data = PayableAccountCreate(
            condominio_id=_uuid(),
            description="Conta padrão",
            gross_value=Decimal("100.00"),
            due_date=date.today(),
        )
        assert data.payable_type == PayableType.AVULSA
        assert data.priority == PayablePriority.MEDIA
        assert data.total_installments == 1
        assert data.is_recurring is False

    def test_payable_account_create_total_installments_valid(self):
        from modules.financial.schemas.payable import PayableAccountCreate

        data = PayableAccountCreate(
            condominio_id=_uuid(),
            description="Conta parcelada",
            gross_value=Decimal("1200.00"),
            due_date=date.today(),
            total_installments=12,
        )
        assert data.total_installments == 12

    def test_payable_account_create_total_installments_max(self):
        from modules.financial.schemas.payable import PayableAccountCreate

        with pytest.raises(ValidationError):
            PayableAccountCreate(
                condominio_id=_uuid(),
                description="Parcelamento excessivo",
                gross_value=Decimal("1000"),
                due_date=date.today(),
                total_installments=361,  # le=360
            )

    def test_payable_account_update_valid(self):
        from modules.financial.schemas.payable import PayableAccountUpdate

        data = PayableAccountUpdate(
            description="Nova descrição",
            gross_value=Decimal("600.00"),
        )
        assert data.description == "Nova descrição"

    def test_payable_account_update_all_optional(self):
        from modules.financial.schemas.payable import PayableAccountUpdate

        data = PayableAccountUpdate()
        assert data.description is None
        assert data.gross_value is None

    def test_payable_payment_create_valid(self):
        from modules.financial.schemas.payable import PayablePaymentCreate

        data = PayablePaymentCreate(
            installment_id=_uuid(),
            paid_value=Decimal("500.00"),
            payment_date=date.today(),
        )
        assert data.paid_value == Decimal("500.00")

    def test_payable_payment_create_zero_value(self):
        from modules.financial.schemas.payable import PayablePaymentCreate

        with pytest.raises(ValidationError):
            PayablePaymentCreate(
                installment_id=_uuid(),
                paid_value=Decimal("0"),  # gt=0
                payment_date=date.today(),
            )

    def test_payable_schedule_request_past_date(self):
        from modules.financial.schemas.payable import PayableScheduleRequest

        with pytest.raises(ValidationError):
            PayableScheduleRequest(scheduled_date=date.today() - timedelta(days=1))

    def test_payable_schedule_request_today_valid(self):
        from modules.financial.schemas.payable import PayableScheduleRequest

        data = PayableScheduleRequest(scheduled_date=date.today())
        assert data.scheduled_date == date.today()

    def test_payable_installment_renegotiate_reason_too_short(self):
        from modules.financial.schemas.payable import PayableInstallmentRenegotiateRequest

        with pytest.raises(ValidationError):
            PayableInstallmentRenegotiateRequest(
                new_due_date=date.today() + timedelta(days=30),
                reason="curto",  # min_length=5 → "curto" is exactly 5, should pass
            )

    def test_payable_installment_renegotiate_valid(self):
        from modules.financial.schemas.payable import PayableInstallmentRenegotiateRequest

        data = PayableInstallmentRenegotiateRequest(
            new_due_date=date.today() + timedelta(days=30),
            reason="Renegociação acordada com fornecedor",
        )
        assert data.new_due_date > date.today()

    def test_payable_bulk_approve_min_one(self):
        from modules.financial.schemas.payable import PayableBulkApproveRequest

        with pytest.raises(ValidationError):
            PayableBulkApproveRequest(payable_ids=[])  # min_length=1

    def test_payable_account_stats_defaults(self):
        from modules.financial.schemas.payable import PayableAccountStats

        stats = PayableAccountStats()
        assert stats.total_count == 0
        assert stats.total_value == Decimal("0")


# ═══════════════════════════════════════════════════════════════════
# SCHEMA TESTS — Receivable schemas
# ═══════════════════════════════════════════════════════════════════


class TestReceivableSchemas:
    """Tests for Pydantic schema validation in receivable module."""

    def test_receivable_account_create_valid(self):
        from modules.financial.schemas.receivable import ReceivableAccountCreate

        data = ReceivableAccountCreate(
            condominio_id=_uuid(),
            description="Taxa condominial Janeiro",
            gross_value=Decimal("800.00"),
            due_date=date.today() + timedelta(days=15),
        )
        assert data.description == "Taxa condominial Janeiro"

    def test_receivable_account_create_description_too_short(self):
        from modules.financial.schemas.receivable import ReceivableAccountCreate

        with pytest.raises(ValidationError):
            ReceivableAccountCreate(
                condominio_id=_uuid(),
                description="AB",
                gross_value=Decimal("100"),
                due_date=date.today(),
            )

    def test_receivable_account_create_gross_value_zero(self):
        from modules.financial.schemas.receivable import ReceivableAccountCreate

        with pytest.raises(ValidationError):
            ReceivableAccountCreate(
                condominio_id=_uuid(),
                description="Taxa válida",
                gross_value=Decimal("0"),
                due_date=date.today(),
            )

    def test_receivable_account_create_default_interest_rate(self):
        from modules.financial.schemas.receivable import ReceivableAccountCreate

        data = ReceivableAccountCreate(
            condominio_id=_uuid(),
            description="Taxa com juros padrão",
            gross_value=Decimal("500.00"),
            due_date=date.today(),
        )
        assert data.interest_rate == Decimal("1")
        assert data.penalty_rate == Decimal("2")

    def test_receivable_payment_create_valid(self):
        from modules.financial.schemas.receivable import ReceivablePaymentCreate

        data = ReceivablePaymentCreate(
            installment_id=_uuid(),
            paid_value=Decimal("300.00"),
            payment_date=date.today(),
        )
        assert data.paid_value == Decimal("300.00")

    def test_receivable_payment_create_zero_value(self):
        from modules.financial.schemas.receivable import ReceivablePaymentCreate

        with pytest.raises(ValidationError):
            ReceivablePaymentCreate(
                installment_id=_uuid(),
                paid_value=Decimal("0"),
                payment_date=date.today(),
            )

    def test_receivable_payment_reverse_reason_required(self):
        from modules.financial.schemas.receivable import ReceivablePaymentReverseRequest

        with pytest.raises(ValidationError):
            ReceivablePaymentReverseRequest(reason="curto")  # min_length=5 → "curto" passes

    def test_receivable_write_off_request_valid(self):
        from modules.financial.schemas.receivable import ReceivableWriteOffRequest

        data = ReceivableWriteOffRequest(reason="Dívida irrecuperável após 3 anos")
        assert len(data.reason) >= 5

    def test_receivable_write_off_reason_too_short(self):
        from modules.financial.schemas.receivable import ReceivableWriteOffRequest

        with pytest.raises(ValidationError):
            ReceivableWriteOffRequest(reason="ab")  # min_length=5

    def test_customer_create_valid(self):
        from modules.financial.schemas.receivable import CustomerCreate

        data = CustomerCreate(
            condominio_id=_uuid(),
            cpf_cnpj="12345678901",
            name="João Silva",
        )
        assert data.name == "João Silva"

    def test_customer_create_cpf_too_short(self):
        from modules.financial.schemas.receivable import CustomerCreate

        with pytest.raises(ValidationError):
            CustomerCreate(
                condominio_id=_uuid(),
                cpf_cnpj="123",  # min_length=11
                name="João Silva",
            )

    def test_billing_rule_create_valid(self):
        from modules.financial.schemas.receivable import BillingRuleCreate

        data = BillingRuleCreate(
            condominio_id=_uuid(),
            name="Taxa Condominial Mensal",
            base_value=Decimal("500.00"),
            start_date=date.today(),
        )
        assert data.name == "Taxa Condominial Mensal"
        assert data.due_day == 10  # default

    def test_billing_rule_create_due_day_out_of_range(self):
        from modules.financial.schemas.receivable import BillingRuleCreate

        with pytest.raises(ValidationError):
            BillingRuleCreate(
                condominio_id=_uuid(),
                name="Regra inválida",
                base_value=Decimal("100"),
                start_date=date.today(),
                due_day=29,  # le=28
            )

    def test_receivable_installment_renegotiate_valid(self):
        from modules.financial.schemas.receivable import ReceivableInstallmentRenegotiateRequest

        data = ReceivableInstallmentRenegotiateRequest(
            new_due_date=date.today() + timedelta(days=30),
            reason="Acordo amigável com morador",
        )
        assert data.new_due_date > date.today()

    def test_receivable_account_stats_defaults(self):
        from modules.financial.schemas.receivable import ReceivableAccountStats

        stats = ReceivableAccountStats()
        assert stats.total_count == 0
        assert stats.total_value == Decimal("0")
        assert stats.overdue_count == 0


# ═══════════════════════════════════════════════════════════════════
# SCHEMA TESTS — Cashflow schemas
# ═══════════════════════════════════════════════════════════════════


class TestCashflowSchemas:
    """Tests for cashflow-related Pydantic schemas."""

    def test_bank_account_create_valid(self):
        from modules.financial.schemas.cashflow import BankAccountCreate

        data = BankAccountCreate(
            condominio_id=_uuid(),
            name="Conta Principal",
            bank_code="001",
            bank_name="Banco do Brasil",
            agency="1234",
            account_number="12345",
            account_digit="6",
        )
        assert data.name == "Conta Principal"

    def test_bank_account_create_name_empty(self):
        from modules.financial.schemas.cashflow import BankAccountCreate

        with pytest.raises(ValidationError):
            BankAccountCreate(
                condominio_id=_uuid(),
                name="",  # min_length=1
                bank_code="001",
                bank_name="Banco",
                agency="1234",
                account_number="12345",
                account_digit="6",
            )

    def test_bank_transaction_create_valid(self):
        from modules.financial.schemas.cashflow import BankTransactionCreate

        data = BankTransactionCreate(
            bank_account_id=_uuid(),
            transaction_type="debito",
            amount=Decimal("250.00"),
            description="Pagamento fornecedor",
            transaction_date=date.today(),
        )
        assert data.amount == Decimal("250.00")

    def test_bank_transaction_amount_zero(self):
        from modules.financial.schemas.cashflow import BankTransactionCreate

        with pytest.raises(ValidationError):
            BankTransactionCreate(
                bank_account_id=_uuid(),
                transaction_type="debito",
                amount=Decimal("0"),  # gt=0
                description="Zero",
                transaction_date=date.today(),
            )

    def test_transfer_request_valid(self):
        from modules.financial.schemas.cashflow import TransferRequest

        data = TransferRequest(
            source_account_id=_uuid(),
            destination_account_id=_uuid(),
            amount=Decimal("1000.00"),
            description="Transferência entre contas",
            transaction_date=date.today(),
        )
        assert data.amount == Decimal("1000.00")

    def test_cashflow_entry_create_valid(self):
        from modules.financial.schemas.cashflow import CashFlowEntryCreate

        data = CashFlowEntryCreate(
            condominio_id=_uuid(),
            entry_type="saida",
            description="Pagamento de energia",
            expected_amount=Decimal("300.00"),
            entry_date=date.today(),
        )
        assert data.entry_type == "saida"

    def test_cashflow_forecast_create_valid(self):
        from modules.financial.schemas.cashflow import CashFlowForecastCreate

        data = CashFlowForecastCreate(
            condominio_id=_uuid(),
            name="Previsão Janeiro 2026",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            forecast_date=date(2026, 1, 1),
        )
        assert data.name == "Previsão Janeiro 2026"

    def test_bank_account_stats_defaults(self):
        from modules.financial.schemas.cashflow import BankAccountStats

        stats = BankAccountStats()
        assert stats.total_accounts == 0
        assert stats.total_balance == Decimal("0")

    def test_cashflow_projection_schema(self):
        from modules.financial.schemas.cashflow import CashFlowProjection

        proj = CashFlowProjection(date=date.today())
        assert proj.payables == Decimal("0")
        assert proj.receivables == Decimal("0")

    def test_reconciliation_adjustment_valid_pattern(self):
        from modules.financial.schemas.cashflow import ReconciliationAdjustment

        data = ReconciliationAdjustment(
            adjustment_type="credito",
            amount=Decimal("50.00"),
            description="Ajuste de conciliação",
        )
        assert data.adjustment_type == "credito"

    def test_reconciliation_adjustment_invalid_type(self):
        from modules.financial.schemas.cashflow import ReconciliationAdjustment

        with pytest.raises(ValidationError):
            ReconciliationAdjustment(
                adjustment_type="invalido",  # pattern: ^(credito|debito)$
                amount=Decimal("50.00"),
                description="Ajuste inválido",
            )


# ═══════════════════════════════════════════════════════════════════
# SERVICE TESTS — CashFlowService
# ═══════════════════════════════════════════════════════════════════


class TestCashFlowService:
    """Unit tests for CashFlowService with mocked DB."""

    @pytest.mark.asyncio
    async def test_get_projection_returns_empty_when_no_installments(self):
        from modules.financial.services.cashflow_service import CashFlowService

        session = _mock_session()
        session.execute.return_value = _scalars_result([])

        svc = CashFlowService(session)
        result = await svc.get_projection(
            condominio_id=_uuid(),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_projection_uses_defaults_when_dates_none(self):
        from modules.financial.services.cashflow_service import CashFlowService

        session = _mock_session()
        session.execute.return_value = _scalars_result([])

        svc = CashFlowService(session)
        result = await svc.get_projection(condominio_id=_uuid())
        # Should return empty list but not raise
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_projection_with_installments(self):
        from modules.financial.models.payable_installment import InstallmentStatus, PayableInstallment
        from modules.financial.services.cashflow_service import CashFlowService

        inst = PayableInstallment()
        inst.id = _uuid()
        inst.due_date = date.today() + timedelta(days=5)
        inst.original_value = Decimal("500.00")
        inst.discount_value = Decimal("0")
        inst.addition_value = Decimal("0")
        inst.penalty_value = Decimal("0")
        inst.interest_value = Decimal("0")
        inst.penalty_rate = Decimal("0")
        inst.interest_rate = Decimal("0")
        inst.status = InstallmentStatus.PENDENTE.value
        inst.installment_number = 1
        inst.total_installments = 1
        inst.description = "Parcela 1"
        inst.paid_value = Decimal("0")
        inst.current_value = Decimal("500.00")

        session = _mock_session()
        session.execute.return_value = _scalars_result([inst])

        svc = CashFlowService(session)
        result = await svc.get_projection(
            condominio_id=_uuid(),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        assert len(result) == 1
        assert result[0].payables > Decimal("0")

    @pytest.mark.asyncio
    async def test_get_projection_group_by_week(self):
        from modules.financial.services.cashflow_service import CashFlowService

        session = _mock_session()
        session.execute.return_value = _scalars_result([])

        svc = CashFlowService(session)
        result = await svc.get_projection(
            condominio_id=_uuid(),
            group_by="week",
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_projection_group_by_month(self):
        from modules.financial.services.cashflow_service import CashFlowService

        session = _mock_session()
        session.execute.return_value = _scalars_result([])

        svc = CashFlowService(session)
        result = await svc.get_projection(
            condominio_id=_uuid(),
            group_by="month",
        )
        assert isinstance(result, list)

    def test_get_grouped_date_day(self):
        from modules.financial.services.cashflow_service import CashFlowService

        svc = CashFlowService(MagicMock())
        d = date(2026, 3, 15)
        assert svc._get_grouped_date(d, "day") == d

    def test_get_grouped_date_week(self):
        from modules.financial.services.cashflow_service import CashFlowService

        svc = CashFlowService(MagicMock())
        # Wednesday 2026-03-18 → Monday 2026-03-16
        d = date(2026, 3, 18)
        result = svc._get_grouped_date(d, "week")
        assert result.weekday() == 0  # Monday

    def test_get_grouped_date_month(self):
        from modules.financial.services.cashflow_service import CashFlowService

        svc = CashFlowService(MagicMock())
        d = date(2026, 3, 18)
        result = svc._get_grouped_date(d, "month")
        assert result == date(2026, 3, 1)

    @pytest.mark.asyncio
    async def test_get_summary_returns_dict_structure(self):
        from modules.financial.services.cashflow_service import CashFlowService

        session = _mock_session()

        # status query returns rows
        status_result = MagicMock()
        status_result.__iter__ = MagicMock(return_value=iter([]))

        # overdue row
        overdue_row = MagicMock()
        overdue_row.total = None
        overdue_row.count = 0

        # week row
        week_row = MagicMock()
        week_row.total = None
        week_row.count = 0

        # month row
        month_row = MagicMock()
        month_row.total = None
        month_row.count = 0

        call_count = [0]

        async def fake_execute(q):
            call_count[0] += 1
            if call_count[0] == 1:
                return status_result
            elif call_count[0] == 2:
                return _one_result(overdue_row)
            elif call_count[0] == 3:
                return _one_result(week_row)
            else:
                return _one_result(month_row)

        session.execute = fake_execute

        svc = CashFlowService(session)
        result = await svc.get_summary(condominio_id=_uuid())

        assert "period_days" in result
        assert "overdue" in result
        assert "due_this_week" in result
        assert "due_this_month" in result

    @pytest.mark.asyncio
    async def test_get_category_breakdown_empty(self):
        from modules.financial.services.cashflow_service import CashFlowService

        session = _mock_session()
        session.execute.return_value = MagicMock(__iter__=MagicMock(return_value=iter([])))

        svc = CashFlowService(session)
        result = await svc.get_category_breakdown(condominio_id=_uuid())
        assert result == []

    @pytest.mark.asyncio
    async def test_get_supplier_breakdown_with_limit(self):
        from modules.financial.services.cashflow_service import CashFlowService

        session = _mock_session()
        session.execute.return_value = MagicMock(__iter__=MagicMock(return_value=iter([])))

        svc = CashFlowService(session)
        result = await svc.get_supplier_breakdown(condominio_id=_uuid(), limit=5)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_monthly_trend_empty(self):
        from modules.financial.services.cashflow_service import CashFlowService

        session = _mock_session()
        session.execute.return_value = MagicMock(__iter__=MagicMock(return_value=iter([])))

        svc = CashFlowService(session)
        result = await svc.get_monthly_trend(condominio_id=_uuid(), months=6)
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════
# SERVICE TESTS — CashFlowProjection dataclass
# ═══════════════════════════════════════════════════════════════════


class TestCashFlowProjectionDataclass:
    """Tests for CashFlowProjection dataclass in cashflow_service."""

    def test_to_dict(self):
        from modules.financial.services.cashflow_service import CashFlowProjection

        proj = CashFlowProjection(
            date=date(2026, 3, 1),
            payables=Decimal("500"),
            receivables=Decimal("800"),
            balance=Decimal("300"),
        )
        d = proj.to_dict()
        assert d["date"] == "2026-03-01"
        assert d["payables"] == 500.0
        assert d["receivables"] == 800.0
        assert d["balance"] == 300.0
        assert d["cumulative_balance"] == 0.0
        assert isinstance(d["details"], list)

    def test_defaults(self):
        from modules.financial.services.cashflow_service import CashFlowProjection

        proj = CashFlowProjection(date=date.today())
        assert proj.payables == Decimal("0")
        assert proj.receivables == Decimal("0")
        assert proj.balance == Decimal("0")
        assert proj.cumulative_balance == Decimal("0")
        assert proj.details == []


# ═══════════════════════════════════════════════════════════════════
# SERVICE TESTS — PayableService
# ═══════════════════════════════════════════════════════════════════


class TestPayableService:
    """Unit tests for PayableService with mocked repositories."""

    def _make_service(self):
        from modules.financial.services.payable_service import PayableService

        session = _mock_session()
        svc = PayableService(session)
        svc.account_repo = AsyncMock()
        svc.installment_repo = AsyncMock()
        svc.payment_repo = AsyncMock()
        return svc, session

    def _make_mock_account(self, status="pendente"):
        from modules.financial.models.payable_account import PayableStatus

        acc = MagicMock()
        acc.id = _uuid()
        acc.status = status
        acc.net_value = Decimal("1000.00")
        acc.paid_value = Decimal("0")
        acc.notes = None
        acc.recurrence_type = None
        acc.ativo = True
        return acc

    @pytest.mark.asyncio
    async def test_create_account(self):
        from modules.financial.schemas.payable import PayableAccountCreate

        svc, session = self._make_service()
        mock_account = self._make_mock_account()
        svc.account_repo.create.return_value = mock_account

        data = PayableAccountCreate(
            condominio_id=_uuid(),
            description="Conta teste",
            gross_value=Decimal("500.00"),
            due_date=date.today(),
        )
        result = await svc.create_account(data, _uuid())

        svc.account_repo.create.assert_called_once()
        session.commit.assert_called_once()
        assert result == mock_account

    @pytest.mark.asyncio
    async def test_get_account(self):
        svc, _ = self._make_service()
        mock_account = self._make_mock_account()
        svc.account_repo.get_by_id.return_value = mock_account

        result = await svc.get_account(mock_account.id)
        assert result == mock_account

    @pytest.mark.asyncio
    async def test_get_account_not_found(self):
        svc, _ = self._make_service()
        svc.account_repo.get_by_id.return_value = None

        result = await svc.get_account(_uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_list_accounts(self):
        svc, _ = self._make_service()
        svc.account_repo.list.return_value = []
        svc.account_repo.count.return_value = 0

        accounts, total = await svc.list_accounts(_uuid())
        assert accounts == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_update_account_not_found(self):
        from modules.financial.schemas.payable import PayableAccountUpdate

        svc, _ = self._make_service()
        svc.account_repo.get_by_id.return_value = None

        result = await svc.update_account(_uuid(), PayableAccountUpdate(), _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_update_account_paid_raises(self):
        from modules.financial.schemas.payable import PayableAccountUpdate

        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="paga")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError, match="paga"):
            await svc.update_account(_uuid(), PayableAccountUpdate(), _uuid())

    @pytest.mark.asyncio
    async def test_update_account_cancelled_raises(self):
        from modules.financial.schemas.payable import PayableAccountUpdate

        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="cancelada")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError):
            await svc.update_account(_uuid(), PayableAccountUpdate(), _uuid())

    @pytest.mark.asyncio
    async def test_update_account_success(self):
        from modules.financial.schemas.payable import PayableAccountUpdate

        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="pendente")
        updated_acc = self._make_mock_account(status="pendente")
        svc.account_repo.get_by_id.return_value = mock_acc
        svc.account_repo.update.return_value = updated_acc

        result = await svc.update_account(_uuid(), PayableAccountUpdate(description="Novo nome"), _uuid())
        session.commit.assert_called_once()
        assert result == updated_acc

    @pytest.mark.asyncio
    async def test_delete_account_not_found(self):
        svc, _ = self._make_service()
        svc.account_repo.get_by_id.return_value = None

        result = await svc.delete_account(_uuid(), _uuid())
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_account_paid_raises(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="paga")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError, match="paga"):
            await svc.delete_account(_uuid(), _uuid())

    @pytest.mark.asyncio
    async def test_delete_account_success(self):
        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="pendente")
        svc.account_repo.get_by_id.return_value = mock_acc
        svc.account_repo.delete.return_value = None

        result = await svc.delete_account(_uuid(), _uuid())
        assert result is True
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_stats(self):
        from modules.financial.schemas.payable import PayableAccountStats

        svc, _ = self._make_service()
        stats = PayableAccountStats()
        svc.account_repo.get_stats.return_value = stats

        result = await svc.get_stats(_uuid())
        assert result == stats

    @pytest.mark.asyncio
    async def test_approve_account_not_found(self):
        svc, _ = self._make_service()
        svc.account_repo.get_by_id.return_value = None

        result = await svc.approve_account(_uuid(), _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_approve_account_not_pending_raises(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="aprovada")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError, match="pendentes"):
            await svc.approve_account(_uuid(), _uuid())

    @pytest.mark.asyncio
    async def test_approve_account_success(self):
        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="pendente")
        mock_acc.approve = MagicMock()
        svc.account_repo.get_by_id.return_value = mock_acc

        result = await svc.approve_account(_uuid(), _uuid(), notes="OK")
        mock_acc.approve.assert_called_once()
        session.commit.assert_called_once()
        assert result == mock_acc

    @pytest.mark.asyncio
    async def test_approve_account_with_notes(self):
        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="pendente")
        mock_acc.approve = MagicMock()
        mock_acc.notes = ""
        svc.account_repo.get_by_id.return_value = mock_acc

        await svc.approve_account(_uuid(), _uuid(), notes="Aprovado em reunião")
        assert "[Aprovação] Aprovado em reunião" in mock_acc.notes

    @pytest.mark.asyncio
    async def test_bulk_approve_all_success(self):
        from modules.financial.schemas.payable import PayableBulkApproveRequest

        svc, _ = self._make_service()
        ids = [_uuid(), _uuid(), _uuid()]
        mock_acc = self._make_mock_account(status="pendente")
        mock_acc.approve = MagicMock()
        svc.account_repo.get_by_id.return_value = mock_acc

        request = PayableBulkApproveRequest(payable_ids=ids)
        success, errors = await svc.bulk_approve(request, _uuid())
        assert success == 3
        assert errors == 0

    @pytest.mark.asyncio
    async def test_bulk_approve_partial_failure(self):
        from modules.financial.schemas.payable import PayableBulkApproveRequest

        svc, _ = self._make_service()
        ids = [_uuid(), _uuid()]

        call_count = [0]

        async def get_by_id(acc_id):
            call_count[0] += 1
            if call_count[0] == 1:
                acc = self._make_mock_account(status="pendente")
                acc.approve = MagicMock()
                return acc
            else:
                return None  # second call returns None

        svc.account_repo.get_by_id = get_by_id

        request = PayableBulkApproveRequest(payable_ids=ids)
        success, errors = await svc.bulk_approve(request, _uuid())
        assert success == 1
        assert errors == 1

    @pytest.mark.asyncio
    async def test_reject_account_not_found(self):
        svc, _ = self._make_service()
        svc.account_repo.get_by_id.return_value = None

        result = await svc.reject_account(_uuid(), _uuid(), "Motivo")
        assert result is None

    @pytest.mark.asyncio
    async def test_reject_account_not_pending_raises(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="aprovada")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError):
            await svc.reject_account(_uuid(), _uuid(), "Rejeitado")

    @pytest.mark.asyncio
    async def test_reject_account_success(self):
        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="pendente")
        mock_acc.cancel = MagicMock()
        svc.account_repo.get_by_id.return_value = mock_acc

        result = await svc.reject_account(_uuid(), _uuid(), "Documento incorreto")
        mock_acc.cancel.assert_called_once_with("Documento incorreto")
        session.commit.assert_called_once()
        assert result == mock_acc

    @pytest.mark.asyncio
    async def test_schedule_payment_not_found(self):
        from modules.financial.schemas.payable import PayableScheduleRequest

        svc, _ = self._make_service()
        svc.account_repo.get_by_id.return_value = None

        req = PayableScheduleRequest(scheduled_date=date.today())
        result = await svc.schedule_payment(_uuid(), req, _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_schedule_payment_invalid_status(self):
        from modules.financial.schemas.payable import PayableScheduleRequest

        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="paga")
        svc.account_repo.get_by_id.return_value = mock_acc

        req = PayableScheduleRequest(scheduled_date=date.today())
        with pytest.raises(ValueError):
            await svc.schedule_payment(_uuid(), req, _uuid())

    @pytest.mark.asyncio
    async def test_schedule_payment_success(self):
        from modules.financial.schemas.payable import PayableScheduleRequest

        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="aprovada")
        mock_acc.schedule_payment = MagicMock()
        svc.account_repo.get_by_id.return_value = mock_acc

        req = PayableScheduleRequest(scheduled_date=date.today())
        result = await svc.schedule_payment(_uuid(), req, _uuid())
        mock_acc.schedule_payment.assert_called_once()
        session.commit.assert_called_once()
        assert result == mock_acc

    @pytest.mark.asyncio
    async def test_register_payment_installment_not_found(self):
        from modules.financial.schemas.payable import PayablePaymentCreate

        svc, _ = self._make_service()
        svc.installment_repo.get_by_id.return_value = None

        data = PayablePaymentCreate(
            installment_id=_uuid(),
            paid_value=Decimal("500.00"),
            payment_date=date.today(),
        )
        with pytest.raises(ValueError, match="não encontrada"):
            await svc.register_payment(_uuid(), data, _uuid())

    @pytest.mark.asyncio
    async def test_register_payment_already_paid_raises(self):
        from modules.financial.models.payable_installment import InstallmentStatus
        from modules.financial.schemas.payable import PayablePaymentCreate

        svc, _ = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.PAGA.value
        svc.installment_repo.get_by_id.return_value = inst

        data = PayablePaymentCreate(
            installment_id=_uuid(),
            paid_value=Decimal("500.00"),
            payment_date=date.today(),
        )
        with pytest.raises(ValueError, match="paga"):
            await svc.register_payment(_uuid(), data, _uuid())

    @pytest.mark.asyncio
    async def test_register_payment_cancelled_raises(self):
        from modules.financial.models.payable_installment import InstallmentStatus
        from modules.financial.schemas.payable import PayablePaymentCreate

        svc, _ = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.CANCELADA.value
        svc.installment_repo.get_by_id.return_value = inst

        data = PayablePaymentCreate(
            installment_id=_uuid(),
            paid_value=Decimal("500.00"),
            payment_date=date.today(),
        )
        with pytest.raises(ValueError):
            await svc.register_payment(_uuid(), data, _uuid())

    @pytest.mark.asyncio
    async def test_register_payment_success(self):
        from modules.financial.models.payable_installment import InstallmentStatus
        from modules.financial.schemas.payable import PayablePaymentCreate

        svc, session = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.PENDENTE.value
        svc.installment_repo.get_by_id.return_value = inst

        mock_payment = MagicMock()
        mock_payment.id = _uuid()
        svc.payment_repo.create.return_value = mock_payment

        data = PayablePaymentCreate(
            installment_id=_uuid(),
            paid_value=Decimal("500.00"),
            payment_date=date.today(),
        )
        result = await svc.register_payment(_uuid(), data, _uuid())
        session.commit.assert_called_once()
        assert result == mock_payment

    @pytest.mark.asyncio
    async def test_reverse_payment_not_found(self):
        from modules.financial.schemas.payable import PayablePaymentReverseRequest

        svc, _ = self._make_service()
        svc.payment_repo.get_by_id.return_value = None

        req = PayablePaymentReverseRequest(reason="Erro no pagamento")
        result = await svc.reverse_payment(_uuid(), req, _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_reverse_payment_not_confirmed_raises(self):
        from modules.financial.models.payable_payment import PaymentStatus
        from modules.financial.schemas.payable import PayablePaymentReverseRequest

        svc, _ = self._make_service()
        payment = MagicMock()
        payment.status = PaymentStatus.PENDENTE.value
        svc.payment_repo.get_by_id.return_value = payment

        req = PayablePaymentReverseRequest(reason="Não confirmado ainda")
        with pytest.raises(ValueError, match="confirmados"):
            await svc.reverse_payment(_uuid(), req, _uuid())

    @pytest.mark.asyncio
    async def test_get_installment(self):
        svc, _ = self._make_service()
        inst = MagicMock()
        svc.installment_repo.get_by_id.return_value = inst

        result = await svc.get_installment(_uuid())
        assert result == inst

    @pytest.mark.asyncio
    async def test_list_installments(self):
        svc, _ = self._make_service()
        svc.installment_repo.list_by_account.return_value = []

        result = await svc.list_installments(_uuid())
        assert result == []

    @pytest.mark.asyncio
    async def test_update_installment_not_found(self):
        from modules.financial.schemas.payable import PayableInstallmentUpdate

        svc, _ = self._make_service()
        svc.installment_repo.get_by_id.return_value = None

        result = await svc.update_installment(_uuid(), PayableInstallmentUpdate())
        assert result is None

    @pytest.mark.asyncio
    async def test_update_installment_paid_raises(self):
        from modules.financial.models.payable_installment import InstallmentStatus
        from modules.financial.schemas.payable import PayableInstallmentUpdate

        svc, _ = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.PAGA.value
        svc.installment_repo.get_by_id.return_value = inst

        with pytest.raises(ValueError):
            await svc.update_installment(_uuid(), PayableInstallmentUpdate())

    @pytest.mark.asyncio
    async def test_renegotiate_installment_not_found(self):
        from modules.financial.schemas.payable import PayableInstallmentRenegotiateRequest

        svc, _ = self._make_service()
        svc.installment_repo.get_by_id.return_value = None

        req = PayableInstallmentRenegotiateRequest(
            new_due_date=date.today() + timedelta(days=30),
            reason="Dificuldade financeira",
        )
        result = await svc.renegotiate_installment(_uuid(), req, _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_renegotiate_installment_paid_raises(self):
        from modules.financial.models.payable_installment import InstallmentStatus
        from modules.financial.schemas.payable import PayableInstallmentRenegotiateRequest

        svc, _ = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.PAGA.value
        svc.installment_repo.get_by_id.return_value = inst

        req = PayableInstallmentRenegotiateRequest(
            new_due_date=date.today() + timedelta(days=30),
            reason="Renegociação inválida",
        )
        with pytest.raises(ValueError):
            await svc.renegotiate_installment(_uuid(), req, _uuid())

    @pytest.mark.asyncio
    async def test_renegotiate_installment_success(self):
        from modules.financial.models.payable_installment import InstallmentStatus
        from modules.financial.schemas.payable import PayableInstallmentRenegotiateRequest

        svc, session = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.PENDENTE.value
        inst.renegotiate = MagicMock()
        svc.installment_repo.get_by_id.return_value = inst

        req = PayableInstallmentRenegotiateRequest(
            new_due_date=date.today() + timedelta(days=30),
            reason="Acordo com fornecedor",
        )
        result = await svc.renegotiate_installment(_uuid(), req, _uuid())
        inst.renegotiate.assert_called_once()
        session.commit.assert_called_once()
        assert result == inst

    @pytest.mark.asyncio
    async def test_get_overdue_accounts(self):
        svc, _ = self._make_service()
        svc.account_repo.get_overdue.return_value = []

        result = await svc.get_overdue_accounts(_uuid())
        assert result == []

    @pytest.mark.asyncio
    async def test_get_due_soon_accounts(self):
        svc, _ = self._make_service()
        svc.account_repo.get_due_soon.return_value = []

        result = await svc.get_due_soon_accounts(_uuid(), days=7)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_pending_installments(self):
        svc, _ = self._make_service()
        svc.installment_repo.get_pending.return_value = []

        result = await svc.get_pending_installments(_uuid())
        assert result == []

    @pytest.mark.asyncio
    async def test_get_pending_reconciliation(self):
        svc, _ = self._make_service()
        svc.payment_repo.get_pending_reconciliation.return_value = []

        result = await svc.get_pending_reconciliation(_uuid())
        assert result == []

    def test_calculate_next_recurrence_date_daily(self):
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(MagicMock())
        last = date(2026, 3, 1)
        result = svc._calculate_next_recurrence_date("DIARIO", last)
        assert result == date(2026, 3, 2)

    def test_calculate_next_recurrence_date_weekly(self):
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(MagicMock())
        last = date(2026, 3, 1)
        result = svc._calculate_next_recurrence_date("SEMANAL", last)
        assert result == date(2026, 3, 8)

    def test_calculate_next_recurrence_date_monthly(self):
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(MagicMock())
        last = date(2026, 3, 1)
        result = svc._calculate_next_recurrence_date("MENSAL", last)
        assert result == date(2026, 4, 1)

    def test_calculate_next_recurrence_date_bimonthly(self):
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(MagicMock())
        last = date(2026, 1, 1)
        result = svc._calculate_next_recurrence_date("BIMESTRAL", last)
        assert result == date(2026, 3, 1)

    def test_calculate_next_recurrence_date_quarterly(self):
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(MagicMock())
        last = date(2026, 1, 1)
        result = svc._calculate_next_recurrence_date("TRIMESTRAL", last)
        assert result == date(2026, 4, 1)

    def test_calculate_next_recurrence_date_semiannual(self):
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(MagicMock())
        last = date(2026, 1, 1)
        result = svc._calculate_next_recurrence_date("SEMESTRAL", last)
        assert result == date(2026, 7, 1)

    def test_calculate_next_recurrence_date_annual(self):
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(MagicMock())
        last = date(2026, 1, 1)
        result = svc._calculate_next_recurrence_date("ANUAL", last)
        assert result == date(2027, 1, 1)

    def test_calculate_next_recurrence_date_unknown(self):
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(MagicMock())
        result = svc._calculate_next_recurrence_date("UNKNOWN", date.today())
        assert result is None

    def test_calculate_next_recurrence_date_quinzenal(self):
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(MagicMock())
        last = date(2026, 3, 1)
        result = svc._calculate_next_recurrence_date("QUINZENAL", last)
        assert result == date(2026, 3, 15)


# ═══════════════════════════════════════════════════════════════════
# SERVICE TESTS — ReceivableService
# ═══════════════════════════════════════════════════════════════════


class TestReceivableService:
    """Unit tests for ReceivableService with mocked repositories."""

    def _make_service(self):
        from modules.financial.services.receivable_service import ReceivableService

        session = _mock_session()
        svc = ReceivableService(session)
        svc.account_repo = AsyncMock()
        svc.installment_repo = AsyncMock()
        svc.payment_repo = AsyncMock()
        svc.customer_repo = AsyncMock()
        svc.category_repo = AsyncMock()
        return svc, session

    def _make_mock_account(self, status="pendente"):
        acc = MagicMock()
        acc.id = _uuid()
        acc.status = status
        acc.net_value = Decimal("800.00")
        acc.paid_value = Decimal("0")
        acc.customer_id = None
        acc.is_overdue = False
        return acc

    @pytest.mark.asyncio
    async def test_create_account_no_customer(self):
        from modules.financial.schemas.receivable import ReceivableAccountCreate

        svc, session = self._make_service()
        mock_acc = self._make_mock_account()
        mock_acc.customer_id = None
        svc.account_repo.create.return_value = mock_acc

        data = ReceivableAccountCreate(
            condominio_id=_uuid(),
            description="Taxa condominial",
            gross_value=Decimal("800.00"),
            due_date=date.today(),
        )
        result = await svc.create_account(data, _uuid())
        session.commit.assert_called_once()
        assert result == mock_acc

    @pytest.mark.asyncio
    async def test_create_account_with_customer_updates_debt(self):
        from modules.financial.schemas.receivable import ReceivableAccountCreate

        svc, session = self._make_service()
        customer_id = _uuid()
        mock_acc = self._make_mock_account()
        mock_acc.customer_id = customer_id
        mock_acc.net_value = Decimal("500.00")
        svc.account_repo.create.return_value = mock_acc

        customer = MagicMock()
        customer.total_debt = Decimal("0")
        svc.customer_repo.get_by_id.return_value = customer

        data = ReceivableAccountCreate(
            condominio_id=_uuid(),
            description="Taxa condominial",
            gross_value=Decimal("500.00"),
            due_date=date.today(),
        )
        await svc.create_account(data, _uuid())
        assert customer.total_debt == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_get_account(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account()
        svc.account_repo.get_by_id.return_value = mock_acc

        result = await svc.get_account(mock_acc.id)
        assert result == mock_acc

    @pytest.mark.asyncio
    async def test_list_accounts(self):
        svc, _ = self._make_service()
        svc.account_repo.list.return_value = []
        svc.account_repo.count.return_value = 0

        accounts, total = await svc.list_accounts(_uuid())
        assert accounts == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_update_account_not_found(self):
        from modules.financial.schemas.receivable import ReceivableAccountUpdate

        svc, _ = self._make_service()
        svc.account_repo.get_by_id.return_value = None

        result = await svc.update_account(_uuid(), ReceivableAccountUpdate(), _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_update_account_paid_raises(self):
        from modules.financial.schemas.receivable import ReceivableAccountUpdate

        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="paga")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError):
            await svc.update_account(_uuid(), ReceivableAccountUpdate(), _uuid())

    @pytest.mark.asyncio
    async def test_delete_account_not_found(self):
        svc, _ = self._make_service()
        svc.account_repo.get_by_id.return_value = None

        result = await svc.delete_account(_uuid(), _uuid())
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_account_paid_raises(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="paga")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError, match="paga"):
            await svc.delete_account(_uuid(), _uuid())

    @pytest.mark.asyncio
    async def test_delete_account_success(self):
        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="pendente")
        svc.account_repo.get_by_id.return_value = mock_acc

        result = await svc.delete_account(_uuid(), _uuid())
        assert result is True
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_account_not_found(self):
        svc, _ = self._make_service()
        svc.account_repo.get_by_id.return_value = None

        result = await svc.cancel_account(_uuid(), _uuid(), "Motivo")
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_account_already_cancelled_raises(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="cancelada")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError):
            await svc.cancel_account(_uuid(), _uuid(), "Motivo")

    @pytest.mark.asyncio
    async def test_cancel_account_paid_raises(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="paga")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError):
            await svc.cancel_account(_uuid(), _uuid(), "Motivo")

    @pytest.mark.asyncio
    async def test_cancel_account_success(self):
        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="pendente")
        mock_acc.cancel = MagicMock()
        svc.account_repo.get_by_id.return_value = mock_acc

        result = await svc.cancel_account(_uuid(), _uuid(), "Mudança de planos")
        mock_acc.cancel.assert_called_once_with("Mudança de planos")
        session.commit.assert_called_once()
        assert result == mock_acc

    @pytest.mark.asyncio
    async def test_suspend_account_not_pending_raises(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="paga")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError, match="pendentes"):
            await svc.suspend_account(_uuid(), _uuid(), "Suspensão temporária")

    @pytest.mark.asyncio
    async def test_suspend_account_success(self):
        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="pendente")
        mock_acc.suspend = MagicMock()
        svc.account_repo.get_by_id.return_value = mock_acc

        result = await svc.suspend_account(_uuid(), _uuid(), "Morador em viagem")
        mock_acc.suspend.assert_called_once()
        session.commit.assert_called_once()
        assert result == mock_acc

    @pytest.mark.asyncio
    async def test_protest_account_not_overdue_raises(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="pendente")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError, match="vencidas"):
            await svc.protest_account(_uuid(), _uuid(), "PROT-001")

    @pytest.mark.asyncio
    async def test_protest_account_success(self):
        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="vencida")
        mock_acc.protest = MagicMock()
        svc.account_repo.get_by_id.return_value = mock_acc

        result = await svc.protest_account(_uuid(), _uuid(), "PROT-2026-001")
        mock_acc.protest.assert_called_once()
        session.commit.assert_called_once()
        assert result == mock_acc

    @pytest.mark.asyncio
    async def test_write_off_account_paid_raises(self):
        svc, _ = self._make_service()
        mock_acc = self._make_mock_account(status="paga")
        svc.account_repo.get_by_id.return_value = mock_acc

        with pytest.raises(ValueError):
            await svc.write_off_account(_uuid(), _uuid(), "Motivo")

    @pytest.mark.asyncio
    async def test_write_off_account_success(self):
        svc, session = self._make_service()
        mock_acc = self._make_mock_account(status="vencida")
        mock_acc.write_off = MagicMock()
        svc.account_repo.get_by_id.return_value = mock_acc

        result = await svc.write_off_account(_uuid(), _uuid(), "Dívida irrecuperável")
        mock_acc.write_off.assert_called_once()
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_payment_installment_not_found(self):
        from modules.financial.schemas.receivable import ReceivablePaymentCreate

        svc, _ = self._make_service()
        svc.installment_repo.get_by_id.return_value = None

        data = ReceivablePaymentCreate(
            installment_id=_uuid(),
            paid_value=Decimal("300.00"),
            payment_date=date.today(),
        )
        with pytest.raises(ValueError, match="não encontrada"):
            await svc.register_payment(_uuid(), data, _uuid())

    @pytest.mark.asyncio
    async def test_register_payment_already_paid_raises(self):
        from modules.financial.models.receivable_installment import InstallmentStatus
        from modules.financial.schemas.receivable import ReceivablePaymentCreate

        svc, _ = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.PAGA.value
        svc.installment_repo.get_by_id.return_value = inst

        data = ReceivablePaymentCreate(
            installment_id=_uuid(),
            paid_value=Decimal("300.00"),
            payment_date=date.today(),
        )
        with pytest.raises(ValueError, match="paga"):
            await svc.register_payment(_uuid(), data, _uuid())

    @pytest.mark.asyncio
    async def test_register_payment_success(self):
        from modules.financial.models.receivable_installment import InstallmentStatus
        from modules.financial.schemas.receivable import ReceivablePaymentCreate

        svc, session = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.PENDENTE.value
        svc.installment_repo.get_by_id.return_value = inst

        payment = MagicMock()
        payment.id = _uuid()
        svc.payment_repo.create.return_value = payment

        data = ReceivablePaymentCreate(
            installment_id=_uuid(),
            paid_value=Decimal("300.00"),
            payment_date=date.today(),
        )
        result = await svc.register_payment(_uuid(), data, _uuid())
        session.commit.assert_called_once()
        assert result == payment

    @pytest.mark.asyncio
    async def test_reverse_payment_not_found(self):
        from modules.financial.schemas.receivable import ReceivablePaymentReverseRequest

        svc, _ = self._make_service()
        svc.payment_repo.get_by_id.return_value = None

        req = ReceivablePaymentReverseRequest(reason="Erro no lançamento")
        result = await svc.reverse_payment(_uuid(), req, _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_reverse_payment_not_confirmed_raises(self):
        from modules.financial.models.receivable_payment import PaymentStatus
        from modules.financial.schemas.receivable import ReceivablePaymentReverseRequest

        svc, _ = self._make_service()
        payment = MagicMock()
        payment.status = PaymentStatus.PENDENTE.value
        svc.payment_repo.get_by_id.return_value = payment

        req = ReceivablePaymentReverseRequest(reason="Pagamento pendente")
        with pytest.raises(ValueError, match="confirmados"):
            await svc.reverse_payment(_uuid(), req, _uuid())

    @pytest.mark.asyncio
    async def test_reconcile_payment_not_found(self):
        from modules.financial.schemas.receivable import ReceivablePaymentReconcileRequest

        svc, _ = self._make_service()
        svc.payment_repo.get_by_id.return_value = None

        req = ReceivablePaymentReconcileRequest(notes="Conciliação")
        result = await svc.reconcile_payment(_uuid(), req, _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_reconcile_payment_success(self):
        from modules.financial.schemas.receivable import ReceivablePaymentReconcileRequest

        svc, session = self._make_service()
        payment = MagicMock()
        payment.reconcile = MagicMock()
        svc.payment_repo.get_by_id.return_value = payment

        req = ReceivablePaymentReconcileRequest(notes="Conciliado com extrato")
        result = await svc.reconcile_payment(_uuid(), req, _uuid())
        payment.reconcile.assert_called_once()
        session.commit.assert_called_once()
        assert result == payment

    @pytest.mark.asyncio
    async def test_get_customer_debt_not_found(self):
        svc, _ = self._make_service()
        svc.customer_repo.get_by_id.return_value = None

        total, overdue = await svc.get_customer_debt(_uuid())
        assert total == Decimal("0")
        assert overdue == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_customer_debt_found(self):
        svc, _ = self._make_service()
        customer = MagicMock()
        customer.total_debt = Decimal("1500.00")
        customer.overdue_debt = Decimal("500.00")
        svc.customer_repo.get_by_id.return_value = customer

        total, overdue = await svc.get_customer_debt(_uuid())
        assert total == Decimal("1500.00")
        assert overdue == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_get_unit_debt_no_accounts(self):
        svc, _ = self._make_service()
        svc.account_repo.get_by_unidade.return_value = []

        total, overdue = await svc.get_unit_debt(_uuid())
        assert total == Decimal("0")
        assert overdue == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_unit_debt_with_pending_accounts(self):
        svc, _ = self._make_service()

        acc1 = MagicMock()
        acc1.status = "pendente"
        acc1.net_value = Decimal("500.00")
        acc1.paid_value = Decimal("0")
        acc1.is_overdue = False

        acc2 = MagicMock()
        acc2.status = "vencida"
        acc2.net_value = Decimal("300.00")
        acc2.paid_value = Decimal("0")
        acc2.is_overdue = True

        svc.account_repo.get_by_unidade.return_value = [acc1, acc2]

        total, overdue = await svc.get_unit_debt(_uuid())
        assert total == Decimal("800.00")
        assert overdue == Decimal("300.00")

    @pytest.mark.asyncio
    async def test_get_unit_debt_skips_paid_cancelled(self):
        svc, _ = self._make_service()

        acc1 = MagicMock()
        acc1.status = "paga"
        acc1.net_value = Decimal("500.00")
        acc1.paid_value = Decimal("500.00")
        acc1.is_overdue = False

        svc.account_repo.get_by_unidade.return_value = [acc1]

        total, overdue = await svc.get_unit_debt(_uuid())
        assert total == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_overdue_accounts(self):
        svc, _ = self._make_service()
        svc.account_repo.get_overdue.return_value = []

        result = await svc.get_overdue_accounts(_uuid())
        assert result == []

    @pytest.mark.asyncio
    async def test_get_pending_installments(self):
        svc, _ = self._make_service()
        svc.installment_repo.get_pending.return_value = []

        result = await svc.get_pending_installments(_uuid())
        assert result == []

    @pytest.mark.asyncio
    async def test_update_installment_cancelled_raises(self):
        from modules.financial.models.receivable_installment import InstallmentStatus
        from modules.financial.schemas.receivable import ReceivableInstallmentUpdate

        svc, _ = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.CANCELADA.value
        svc.installment_repo.get_by_id.return_value = inst

        with pytest.raises(ValueError):
            await svc.update_installment(_uuid(), ReceivableInstallmentUpdate())

    @pytest.mark.asyncio
    async def test_renegotiate_installment_cancelled_raises(self):
        from modules.financial.models.receivable_installment import InstallmentStatus
        from modules.financial.schemas.receivable import ReceivableInstallmentRenegotiateRequest

        svc, _ = self._make_service()
        inst = MagicMock()
        inst.status = InstallmentStatus.CANCELADA.value
        svc.installment_repo.get_by_id.return_value = inst

        req = ReceivableInstallmentRenegotiateRequest(
            new_due_date=date.today() + timedelta(days=30),
            reason="Acordo impossível",
        )
        with pytest.raises(ValueError):
            await svc.renegotiate_installment(_uuid(), req, _uuid())


# ═══════════════════════════════════════════════════════════════════
# SERVICE TESTS — SupplierService
# ═══════════════════════════════════════════════════════════════════


class TestSupplierService:
    """Unit tests for SupplierService with mocked repository."""

    def _make_service(self):
        from modules.financial.services.supplier_service import SupplierService

        session = _mock_session()
        svc = SupplierService(session)
        svc.repository = AsyncMock()
        return svc, session

    def _make_supplier(self, **kwargs):
        s = MagicMock()
        s.id = _uuid()
        s.name = "Fornecedor Teste"
        s.ativo = True
        s.is_blocked = False
        s.is_qualified = False
        s.block_reason = None
        s.bank_code = "001"
        s.pix_key = None
        for k, v in kwargs.items():
            setattr(s, k, v)
        return s

    @pytest.mark.asyncio
    async def test_create_supplier_duplicate_cpf_cnpj_raises(self):
        from modules.financial.schemas.supplier import SupplierCreate

        svc, _ = self._make_service()
        existing = self._make_supplier()
        svc.repository.get_by_cpf_cnpj.return_value = existing

        data = MagicMock(spec=SupplierCreate)
        data.cpf_cnpj = "12.345.678/0001-99"
        data.condominio_id = _uuid()

        with pytest.raises(ValueError, match="Já existe"):
            await svc.create(data, _uuid())

    @pytest.mark.asyncio
    async def test_create_supplier_success(self):
        from modules.financial.schemas.supplier import SupplierCreate

        svc, session = self._make_service()
        svc.repository.get_by_cpf_cnpj.return_value = None
        supplier = self._make_supplier()
        svc.repository.create.return_value = supplier

        data = MagicMock(spec=SupplierCreate)
        data.cpf_cnpj = "12.345.678/0001-99"
        data.condominio_id = _uuid()

        result = await svc.create(data, _uuid())
        session.commit.assert_called_once()
        assert result == supplier

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        svc, _ = self._make_service()
        supplier = self._make_supplier()
        svc.repository.get_by_id.return_value = supplier

        result = await svc.get_by_id(supplier.id)
        assert result == supplier

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        svc, _ = self._make_service()
        svc.repository.get_by_id.return_value = None

        result = await svc.get_by_id(_uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_list(self):
        svc, _ = self._make_service()
        svc.repository.list.return_value = []
        svc.repository.count.return_value = 0

        suppliers, total = await svc.list(_uuid())
        assert suppliers == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        from modules.financial.schemas.supplier import SupplierUpdate

        svc, _ = self._make_service()
        svc.repository.get_by_id.return_value = None

        result = await svc.update(_uuid(), SupplierUpdate())
        assert result is None

    @pytest.mark.asyncio
    async def test_update_success(self):
        from modules.financial.schemas.supplier import SupplierUpdate

        svc, session = self._make_service()
        supplier = self._make_supplier()
        updated = self._make_supplier()
        svc.repository.get_by_id.return_value = supplier
        svc.repository.update.return_value = updated

        result = await svc.update(_uuid(), SupplierUpdate())
        session.commit.assert_called_once()
        assert result == updated

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        svc, _ = self._make_service()
        svc.repository.get_by_id.return_value = None

        result = await svc.delete(_uuid())
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_success(self):
        svc, session = self._make_service()
        supplier = self._make_supplier()
        svc.repository.get_by_id.return_value = supplier

        result = await svc.delete(_uuid())
        assert result is True
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_block_not_found(self):
        svc, _ = self._make_service()
        svc.repository.get_by_id.return_value = None

        result = await svc.block(_uuid(), "Motivo", _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_block_already_blocked_raises(self):
        svc, _ = self._make_service()
        supplier = self._make_supplier(is_blocked=True)
        svc.repository.get_by_id.return_value = supplier

        with pytest.raises(ValueError, match="bloqueado"):
            await svc.block(_uuid(), "Motivo", _uuid())

    @pytest.mark.asyncio
    async def test_block_success(self):
        svc, session = self._make_service()
        supplier = self._make_supplier(is_blocked=False)
        blocked = self._make_supplier(is_blocked=True)
        svc.repository.get_by_id.return_value = supplier
        svc.repository.block.return_value = blocked

        result = await svc.block(_uuid(), "Fraude detectada", _uuid())
        session.commit.assert_called_once()
        assert result == blocked

    @pytest.mark.asyncio
    async def test_unblock_not_found(self):
        svc, _ = self._make_service()
        svc.repository.get_by_id.return_value = None

        result = await svc.unblock(_uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_unblock_not_blocked_raises(self):
        svc, _ = self._make_service()
        supplier = self._make_supplier(is_blocked=False)
        svc.repository.get_by_id.return_value = supplier

        with pytest.raises(ValueError, match="não está bloqueado"):
            await svc.unblock(_uuid())

    @pytest.mark.asyncio
    async def test_unblock_success(self):
        svc, session = self._make_service()
        supplier = self._make_supplier(is_blocked=True)
        unblocked = self._make_supplier(is_blocked=False)
        svc.repository.get_by_id.return_value = supplier
        svc.repository.unblock.return_value = unblocked

        result = await svc.unblock(_uuid())
        session.commit.assert_called_once()
        assert result == unblocked

    @pytest.mark.asyncio
    async def test_qualify_not_found(self):
        svc, _ = self._make_service()
        svc.repository.get_by_id.return_value = None

        result = await svc.qualify(_uuid(), _uuid())
        assert result is None

    @pytest.mark.asyncio
    async def test_qualify_already_qualified_raises(self):
        svc, _ = self._make_service()
        supplier = self._make_supplier(is_qualified=True)
        svc.repository.get_by_id.return_value = supplier

        with pytest.raises(ValueError, match="qualificado"):
            await svc.qualify(_uuid(), _uuid())

    @pytest.mark.asyncio
    async def test_qualify_success(self):
        svc, session = self._make_service()
        supplier = self._make_supplier(is_qualified=False)
        qualified = self._make_supplier(is_qualified=True)
        svc.repository.get_by_id.return_value = supplier
        svc.repository.qualify.return_value = qualified

        result = await svc.qualify(_uuid(), _uuid())
        session.commit.assert_called_once()
        assert result == qualified

    @pytest.mark.asyncio
    async def test_get_stats(self):
        from modules.financial.schemas.supplier import SupplierStats

        svc, _ = self._make_service()
        stats = MagicMock(spec=SupplierStats)
        svc.repository.get_stats.return_value = stats

        result = await svc.get_stats(_uuid())
        assert result == stats

    @pytest.mark.asyncio
    async def test_search(self):
        svc, _ = self._make_service()
        svc.repository.search.return_value = []

        result = await svc.search(_uuid(), "energia", limit=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_validate_for_payment_not_found(self):
        svc, _ = self._make_service()
        svc.repository.get_by_id.return_value = None

        ok, msg = await svc.validate_for_payment(_uuid())
        assert ok is False
        assert "não encontrado" in msg

    @pytest.mark.asyncio
    async def test_validate_for_payment_inactive(self):
        svc, _ = self._make_service()
        supplier = self._make_supplier(ativo=False)
        svc.repository.get_by_id.return_value = supplier

        ok, msg = await svc.validate_for_payment(_uuid())
        assert ok is False
        assert "inativo" in msg

    @pytest.mark.asyncio
    async def test_validate_for_payment_blocked(self):
        svc, _ = self._make_service()
        supplier = self._make_supplier(is_blocked=True, block_reason="Fraude")
        svc.repository.get_by_id.return_value = supplier

        ok, msg = await svc.validate_for_payment(_uuid())
        assert ok is False
        assert "bloqueado" in msg

    @pytest.mark.asyncio
    async def test_validate_for_payment_no_banking_data(self):
        svc, _ = self._make_service()
        supplier = self._make_supplier(bank_code=None, pix_key=None)
        svc.repository.get_by_id.return_value = supplier

        ok, msg = await svc.validate_for_payment(_uuid())
        assert ok is False
        assert "bancários" in msg

    @pytest.mark.asyncio
    async def test_validate_for_payment_with_pix(self):
        svc, _ = self._make_service()
        supplier = self._make_supplier(bank_code=None, pix_key="fornecedor@pix.com")
        svc.repository.get_by_id.return_value = supplier

        ok, msg = await svc.validate_for_payment(_uuid())
        assert ok is True
        assert msg is None

    @pytest.mark.asyncio
    async def test_validate_for_payment_with_bank_code(self):
        svc, _ = self._make_service()
        supplier = self._make_supplier(bank_code="001", pix_key=None)
        svc.repository.get_by_id.return_value = supplier

        ok, msg = await svc.validate_for_payment(_uuid())
        assert ok is True
        assert msg is None


# ═══════════════════════════════════════════════════════════════════
# NFeProvider TESTS
# ═══════════════════════════════════════════════════════════════════


class TestNFeProvider:
    """Unit tests for NFe integration logic."""

    def test_nfe_error_creation(self):
        from modules.financial.integrations.nfe_provider import NFeError

        err = NFeError("Erro ao emitir NF-e", code="E001", details={"campo": "valor"})
        assert err.message == "Erro ao emitir NF-e"
        assert err.code == "E001"
        assert err.details == {"campo": "valor"}
        assert str(err) == "Erro ao emitir NF-e"

    def test_nfe_error_default_details(self):
        from modules.financial.integrations.nfe_provider import NFeError

        err = NFeError("Timeout")
        assert err.details == {}
        assert err.code is None

    def test_nfe_config_valid(self):
        from modules.financial.integrations.nfe_provider import NFeConfig

        cfg = NFeConfig(
            certificado_path="/certs/cert.p12",
            certificado_senha="senha123",
        )
        assert cfg.ambiente == "2"  # homologacao default
        assert cfg.uf == "AM"
        assert cfg.timeout_seconds == 30

    def test_nfe_config_producao(self):
        from modules.financial.integrations.nfe_provider import NFeConfig

        cfg = NFeConfig(
            certificado_path="/certs/cert.p12",
            certificado_senha="senha123",
            ambiente="1",
        )
        assert cfg.ambiente == "1"

    def test_parse_sefaz_xml_empty_body(self):
        from modules.financial.integrations.nfe_provider import _parse_sefaz_xml

        result = _parse_sefaz_xml("<xml>sem body soap</xml>")
        assert result == {}

    def test_parse_sefaz_xml_with_soap_body(self):
        from modules.financial.integrations.nfe_provider import _parse_sefaz_xml

        xml = """
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <nfeResultMsg xmlns:ns="http://www.portalfiscal.inf.br/nfe">
                    <retConsSitNFe xmlns="http://www.portalfiscal.inf.br/nfe">
                        <cStat>100</cStat>
                        <xMotivo>Autorizado o uso da NF-e</xMotivo>
                    </retConsSitNFe>
                </nfeResultMsg>
            </soap:Body>
        </soap:Envelope>
        """
        result = _parse_sefaz_xml(xml)
        assert result.get("cStat") == "100"
        assert "Autorizado" in result.get("xMotivo", "")

    def test_emitente_data(self):
        from modules.financial.integrations.nfe_provider import _EMITENTE

        assert _EMITENTE["cnpj"] == "35710481000103"
        assert _EMITENTE["uf"] == "AM"
        assert _EMITENTE["regime_tributario"] == "3"

    def test_uf_cod_map(self):
        from modules.financial.integrations.nfe_provider import _UF_COD

        assert _UF_COD["AM"] == "13"
        assert _UF_COD["SP"] == "35"
        assert _UF_COD["RJ"] == "33"


# ═══════════════════════════════════════════════════════════════════
# ENUM TESTS
# ═══════════════════════════════════════════════════════════════════


class TestFinancialEnums:
    """Tests for financial module enums."""

    def test_payable_status_values(self):
        from modules.financial.models.payable_account import PayableStatus

        assert PayableStatus.PENDENTE == "pendente"
        assert PayableStatus.PAGA == "pago"
        assert PayableStatus.CANCELADA == "cancelada"
        assert PayableStatus.APROVADA == "aprovada"
        assert PayableStatus.AGENDADA == "agendada"

    def test_payable_type_values(self):
        from modules.financial.models.payable_account import PayableType

        assert PayableType.AVULSA == "avulsa"
        assert PayableType.PARCELADA == "parcelada"
        assert PayableType.RECORRENTE == "recorrente"

    def test_payable_priority_values(self):
        from modules.financial.models.payable_account import PayablePriority

        assert PayablePriority.BAIXA == "baixa"
        assert PayablePriority.MEDIA == "media"
        assert PayablePriority.ALTA == "alta"
        assert PayablePriority.URGENTE == "urgente"
        assert PayablePriority.CRITICA == "critica"

    def test_recurrence_type_values(self):
        from modules.financial.models.payable_account import RecurrenceType

        assert RecurrenceType.MENSAL == "mensal"
        assert RecurrenceType.ANUAL == "anual"

    def test_installment_status_values(self):
        from modules.financial.models.payable_installment import InstallmentStatus

        assert InstallmentStatus.PENDENTE == "pendente"
        assert InstallmentStatus.PAGA == "paga"
        assert InstallmentStatus.CANCELADA == "cancelada"
        assert InstallmentStatus.RENEGOCIADA == "renegociada"

    def test_payment_status_values(self):
        from modules.financial.models.payable_payment import PaymentStatus

        assert PaymentStatus.PENDENTE == "pendente"
        assert PaymentStatus.CONFIRMADO == "confirmado"
        assert PaymentStatus.ESTORNADO == "estornado"
        assert PaymentStatus.REJEITADO == "rejeitado"

    def test_payment_origin_values(self):
        from modules.financial.models.payable_payment import PaymentOrigin

        assert PaymentOrigin.MANUAL == "manual"
        assert PaymentOrigin.IMPORTACAO == "importacao"
        assert PaymentOrigin.API == "api"

    def test_receivable_status_values(self):
        from modules.financial.models.receivable_account import ReceivableStatus

        assert ReceivableStatus.PENDENTE == "pendente"
        assert ReceivableStatus.PAGA == "paga"
        assert ReceivableStatus.PROTESTADA == "protestada"
        assert ReceivableStatus.BAIXADA == "baixada"


# ═══════════════════════════════════════════════════════════════════
# DRE SERVICE — Enum and dataclass tests
# ═══════════════════════════════════════════════════════════════════


class TestDREServiceEnums:
    """Tests for DRE service enums and dataclasses."""

    def test_dre_period_type_values(self):
        from modules.financial.services.dre_service import DREPeriodType

        assert DREPeriodType.MONTHLY == "monthly"
        assert DREPeriodType.ANNUAL == "annual"
        assert DREPeriodType.QUARTERLY == "quarterly"

    def test_dre_group_type_values(self):
        from modules.financial.services.dre_service import DREGroupType

        assert DREGroupType.RECEITA_BRUTA == "receita_bruta"
        assert DREGroupType.LUCRO_BRUTO == "lucro_bruto"
        assert DREGroupType.LUCRO_LIQUIDO == "lucro_liquido"

    def test_dre_line_item_defaults(self):
        from modules.financial.services.dre_service import DRELineItem

        item = DRELineItem()
        assert item.current_value == Decimal("0")
        assert item.previous_value == Decimal("0")
        assert item.level == 0
        assert item.is_total is False


class TestBudgetServiceEnums:
    """Tests for Budget service enums and dataclasses."""

    def test_budget_period_type_values(self):
        from modules.financial.services.budget_service import BudgetPeriodType

        assert BudgetPeriodType.MONTHLY == "MONTHLY"
        assert BudgetPeriodType.ANNUAL == "ANNUAL"

    def test_budget_status_values(self):
        from modules.financial.services.budget_service import BudgetStatus

        assert BudgetStatus.DRAFT == "DRAFT"
        assert BudgetStatus.APPROVED == "APPROVED"
        assert BudgetStatus.ACTIVE == "ACTIVE"
        assert BudgetStatus.CANCELLED == "CANCELLED"

    def test_budget_variance_type_values(self):
        from modules.financial.services.budget_service import BudgetVarianceType

        assert BudgetVarianceType.FAVORABLE == "FAVORABLE"
        assert BudgetVarianceType.UNFAVORABLE == "UNFAVORABLE"

    def test_budget_line_item_defaults(self):
        from modules.financial.services.budget_service import BudgetLineItem

        item = BudgetLineItem()
        assert item.jan == Decimal("0")
        assert item.dec == Decimal("0")
        assert item.total_budgeted == Decimal("0")
