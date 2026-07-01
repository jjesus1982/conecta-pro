"""Testes para models do módulo operacional.

Coverage: modules/operacional/models/
"""

from datetime import date, time, timedelta
from uuid import uuid4

from modules.operacional.models.allocation import Allocation, AllocationStatus
from modules.operacional.models.post import Post, PostStatus, PostType, ShiftType
from modules.operacional.models.shift import Shift, ShiftStatus


class TestPostModel:
    """Testes para model Post (Posto de trabalho)."""

    def test_post_creation(self):
        """Testa criação de instância Post com campos obrigatórios."""
        post_id = str(uuid4())
        client_id = str(uuid4())

        post = Post(
            id=post_id,
            code="POST-001",
            name="Posto Central",
            client_id=client_id,
            address="Rua Teste, 123",
            is_active=True,
        )

        assert post.id == post_id
        assert post.code == "POST-001"
        assert post.name == "Posto Central"
        assert post.client_id == client_id
        assert post.address == "Rua Teste, 123"
        assert post.is_active is True

    def test_post_default_values(self):
        """Testa que mapped_column defaults estão configurados corretamente.

        Nota: mapped_column(default=...) define INSERT defaults (aplicados pelo DB),
        não Python-side defaults. Verificamos as definições das colunas.
        """
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(Post)
        col_defaults = {}
        for col in mapper.columns:
            if col.default is not None:
                col_defaults[col.key] = col.default.arg

        assert col_defaults.get("is_active") is True
        assert col_defaults.get("post_type") == PostType.PORTEIRO.value
        assert col_defaults.get("status") == PostStatus.ACTIVE.value
        assert col_defaults.get("shift_type") == ShiftType.DIURNO.value
        assert col_defaults.get("required_headcount") == 1
        assert col_defaults.get("current_headcount") == 0
        assert col_defaults.get("break_duration_minutes") == 60
        assert col_defaults.get("requires_armed") is False
        assert col_defaults.get("requires_vehicle") is False

    def test_post_soft_delete(self):
        """Testa desativação de posto."""
        post = Post(
            id=str(uuid4()),
            code="POST-003",
            name="Posto Delete",
            is_active=True,
        )

        post.is_active = False
        post.status = PostStatus.INACTIVE.value

        assert post.is_active is False
        assert post.status == PostStatus.INACTIVE.value

    def test_post_enums(self):
        """Testa enums do Post."""
        assert PostType.PORTEIRO == "porteiro"
        assert PostType.PORTEIRO == "porteiro"
        assert PostType.SUPERVISOR == "supervisor"
        assert PostStatus.ACTIVE == "active"
        assert PostStatus.INACTIVE == "inactive"
        assert ShiftType.DIURNO == "diurno"
        assert ShiftType.NOTURNO == "noturno"
        assert ShiftType.ESCALA_12X36 == "12x36"

    def test_post_vacancy_count(self):
        """Testa cálculo de vagas disponíveis."""
        post = Post(
            code="POST-004",
            name="Posto Vagas",
            required_headcount=5,
            current_headcount=3,
        )

        assert post.vacancy_count == 2
        assert post.is_filled is False

    def test_post_filled(self):
        """Testa posto completamente preenchido."""
        post = Post(
            code="POST-005",
            name="Posto Cheio",
            required_headcount=2,
            current_headcount=2,
        )

        assert post.is_filled is True
        assert post.vacancy_count == 0

    def test_post_daily_hours(self):
        """Testa cálculo de horas diárias por tipo de turno."""
        post_diurno = Post(code="POST-D", name="Diurno", shift_type=ShiftType.DIURNO.value)
        post_admin = Post(code="POST-A", name="Admin", shift_type=ShiftType.ADMINISTRATIVO.value)
        post_integral = Post(code="POST-I", name="Integral", shift_type=ShiftType.INTEGRAL.value)

        assert post_diurno.daily_hours == 12.0
        assert post_admin.daily_hours == 8.0
        assert post_integral.daily_hours == 24.0

    def test_post_attributes(self):
        """Testa existência de atributos obrigatórios."""
        post = Post(code="POST-006", name="Teste")

        assert hasattr(post, "id")
        assert hasattr(post, "code")
        assert hasattr(post, "name")
        assert hasattr(post, "client_id")
        assert hasattr(post, "address")
        assert hasattr(post, "is_active")
        assert hasattr(post, "created_at")
        assert hasattr(post, "updated_at")
        assert hasattr(post, "post_type")
        assert hasattr(post, "status")
        assert hasattr(post, "shift_type")
        assert hasattr(post, "required_headcount")
        assert hasattr(post, "hourly_rate")

    def test_post_repr(self):
        """Testa representação string do Post."""
        post = Post(code="POST-007", name="Posto Repr")
        assert "POST-007" in repr(post)
        assert "Posto Repr" in repr(post)


class TestShiftModel:
    """Testes para model Shift (Turno)."""

    def _make_shift(self, **kwargs):
        """Helper para criar shift com campos obrigatórios."""
        defaults = {
            "id": str(uuid4()),
            "scale_id": str(uuid4()),
            "post_id": str(uuid4()),
            "shift_date": date.today(),
            "planned_start_time": time(8, 0),
            "planned_end_time": time(16, 0),
        }
        defaults.update(kwargs)
        return Shift(**defaults)

    def test_shift_creation(self):
        """Testa criação de turno."""
        shift = self._make_shift(
            planned_start_time=time(22, 0),
            planned_end_time=time(6, 0),
            is_night_shift=True,
        )

        assert shift.planned_start_time == time(22, 0)
        assert shift.planned_end_time == time(6, 0)
        assert shift.is_night_shift is True

    def test_shift_default_values(self):
        """Testa que mapped_column defaults do Shift estão configurados."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(Shift)
        col_defaults = {}
        for col in mapper.columns:
            if col.default is not None:
                col_defaults[col.key] = col.default.arg

        assert col_defaults.get("status") == ShiftStatus.SCHEDULED.value
        assert col_defaults.get("is_active") is True
        assert col_defaults.get("is_holiday") is False
        assert col_defaults.get("is_night_shift") is False
        assert col_defaults.get("is_overtime") is False
        assert col_defaults.get("planned_hours") == 0.0
        assert col_defaults.get("actual_hours") == 0.0
        assert col_defaults.get("overtime_hours") == 0.0

    def test_shift_enums(self):
        """Testa enums do Shift."""
        assert ShiftStatus.SCHEDULED == "scheduled"
        assert ShiftStatus.COMPLETED == "completed"
        assert ShiftStatus.MISSED == "missed"
        assert ShiftStatus.SUBSTITUTED == "substituted"

    def test_shift_is_filled(self):
        """Testa verificação de turno com funcionário."""
        shift_empty = self._make_shift(employee_id=None)
        shift_filled = self._make_shift(employee_id=str(uuid4()))

        assert shift_empty.is_filled is False
        assert shift_filled.is_filled is True

    def test_shift_was_worked(self):
        """Testa verificação de turno trabalhado."""
        shift = self._make_shift(status=ShiftStatus.COMPLETED.value)
        assert shift.was_worked is True

        shift2 = self._make_shift(status=ShiftStatus.MISSED.value)
        assert shift2.was_worked is False

    def test_shift_calculate_overtime(self):
        """Testa cálculo de horas extras."""
        shift = self._make_shift(actual_hours=10.0, planned_hours=8.0)
        assert shift.calculate_overtime(regular_hours=8.0) == 2.0

        shift_normal = self._make_shift(actual_hours=7.0, planned_hours=8.0)
        assert shift_normal.calculate_overtime(regular_hours=8.0) == 0.0

    def test_shift_future_and_today(self):
        """Testa propriedades is_future e is_today."""
        shift_today = self._make_shift(shift_date=date.today())
        assert shift_today.is_today is True
        assert shift_today.is_future is False

        future_date = date.today() + timedelta(days=5)
        shift_future = self._make_shift(shift_date=future_date)
        assert shift_future.is_future is True
        assert shift_future.is_today is False

    def test_shift_attributes(self):
        """Testa existência de atributos."""
        shift = self._make_shift()

        assert hasattr(shift, "id")
        assert hasattr(shift, "scale_id")
        assert hasattr(shift, "employee_id")
        assert hasattr(shift, "post_id")
        assert hasattr(shift, "shift_date")
        assert hasattr(shift, "planned_start_time")
        assert hasattr(shift, "planned_end_time")
        assert hasattr(shift, "status")
        assert hasattr(shift, "is_active")
        assert hasattr(shift, "base_pay")
        assert hasattr(shift, "total_pay")


class TestAllocationModel:
    """Testes para model Allocation (Alocação)."""

    def _make_allocation(self, **kwargs):
        """Helper para criar allocation com campos obrigatórios."""
        defaults = {
            "id": str(uuid4()),
            "employee_id": str(uuid4()),
            "post_id": str(uuid4()),
            "start_date": date.today(),
        }
        defaults.update(kwargs)
        return Allocation(**defaults)

    def test_allocation_creation(self):
        """Testa alocação de funcionário em posto."""
        emp_id = str(uuid4())
        post_id = str(uuid4())

        allocation = self._make_allocation(
            employee_id=emp_id,
            post_id=post_id,
            start_date=date.today(),
        )

        assert allocation.employee_id == emp_id
        assert allocation.post_id == post_id
        assert allocation.start_date == date.today()

    def test_allocation_default_values(self):
        """Testa que mapped_column defaults da Allocation estão configurados."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(Allocation)
        col_defaults = {}
        for col in mapper.columns:
            if col.default is not None:
                col_defaults[col.key] = col.default.arg

        assert col_defaults.get("status") == AllocationStatus.ACTIVE.value
        assert col_defaults.get("is_active") is True
        assert col_defaults.get("is_primary") is True
        assert col_defaults.get("is_temporary") is False
        assert col_defaults.get("hourly_rate") == 0.0
        assert col_defaults.get("monthly_salary") == 0.0

    def test_allocation_with_end_date(self):
        """Testa alocação com data de término."""
        allocation = self._make_allocation(
            start_date=date.today() - timedelta(days=30),
            end_date=date.today(),
            status=AllocationStatus.TERMINATED.value,
            is_active=False,
        )

        assert allocation.end_date == date.today()
        assert allocation.is_active is False
        assert allocation.status == AllocationStatus.TERMINATED.value

    def test_allocation_enums(self):
        """Testa enums da Allocation."""
        assert AllocationStatus.ACTIVE == "active"
        assert AllocationStatus.INACTIVE == "inactive"
        assert AllocationStatus.PENDING == "pending"
        assert AllocationStatus.SUSPENDED == "suspended"
        assert AllocationStatus.TERMINATED == "terminated"

    def test_allocation_is_current(self):
        """Testa verificação de alocação corrente."""
        active = self._make_allocation(
            start_date=date.today() - timedelta(days=10),
            status=AllocationStatus.ACTIVE.value,
        )
        assert active.is_current is True

        terminated = self._make_allocation(
            start_date=date.today() - timedelta(days=10),
            status=AllocationStatus.TERMINATED.value,
        )
        assert terminated.is_current is False

    def test_allocation_days_allocated(self):
        """Testa cálculo de dias alocados."""
        start = date.today() - timedelta(days=30)
        allocation = self._make_allocation(
            start_date=start,
            end_date=date.today(),
        )
        assert allocation.days_allocated == 30

    def test_allocation_total_monthly_cost(self):
        """Testa cálculo de custo mensal total."""
        allocation = self._make_allocation(
            monthly_salary=3500.0,
            additional_benefits=800.0,
        )
        assert allocation.total_monthly_cost == 4300.0

    def test_allocation_attributes(self):
        """Testa existência de atributos."""
        allocation = self._make_allocation()

        assert hasattr(allocation, "id")
        assert hasattr(allocation, "employee_id")
        assert hasattr(allocation, "post_id")
        assert hasattr(allocation, "start_date")
        assert hasattr(allocation, "end_date")
        assert hasattr(allocation, "is_active")
        assert hasattr(allocation, "status")
        assert hasattr(allocation, "is_primary")
        assert hasattr(allocation, "monthly_salary")
        assert hasattr(allocation, "role")


class TestOperacionalIntegration:
    """Testes de integração entre models operacionais."""

    def test_post_shift_allocation_relationship(self):
        """Testa relacionamento entre Post, Shift e Allocation via IDs."""
        post_id = str(uuid4())

        post = Post(
            id=post_id,
            code="POST-INT-001",
            name="Posto Central",
            is_active=True,
        )

        shift = Shift(
            id=str(uuid4()),
            scale_id=str(uuid4()),
            post_id=post.id,
            shift_date=date.today(),
            planned_start_time=time(22, 0),
            planned_end_time=time(6, 0),
            is_night_shift=True,
        )

        allocation = Allocation(
            id=str(uuid4()),
            employee_id=str(uuid4()),
            post_id=post.id,
            start_date=date.today(),
        )

        assert shift.post_id == post.id
        assert allocation.post_id == post.id
