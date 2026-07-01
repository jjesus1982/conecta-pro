"""
Tests for modules/operacional — SERVICE LOGIC with mocks.

Covers:
  - PostRepository (CRUD, filters, stats, code generation, soft delete)
  - ScaleRepository (CRUD, approve, reject, publish, employee availability)
  - AllocationRepository (create, conflict detection, terminate, bulk ops)
  - ScaleGenerator (all scale types: 12x36, 6x1, 5x2, turno, generic, metrics)
  - TimeBankService (overtime calc, compensation value, expiration alerts,
                     validation, monthly summary, recommendations)
  - DiaristService (create, update, activate/deactivate, assignment,
                    schedule, payment, evaluation, batch schedule, payroll)
  - OccurrenceService (create, resolve, reopen, escalate, archive,
                       attachments, comments, dashboard stats, category config)
  - InspectionRoundService (create, start, pause, resume, complete, cancel,
                             checkpoints, dashboard stats)
  - GeolocationService (Haversine distance, validate_location,
                        is_point_in_polygon)
  - CheckInValidator (_validate_time, _validate_device, full validate_check_in)
  - PostCreate / PostBase Pydantic schema validators
  - DiaristSchemas basic validation
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_uuid() -> str:
    return str(uuid.uuid4())


def _mock_async_db():
    """Return an AsyncMock that acts as an AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


# ===========================================================================
# POST REPOSITORY
# ===========================================================================


class TestPostRepository:
    """Tests for PostRepository data-access logic."""

    @pytest.fixture
    def repo(self):
        from modules.operacional.repositories.post_repository import PostRepository

        db = _mock_async_db()
        return PostRepository(db), db

    # -----------------------------------------------------------------------
    # _generate_code
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_generate_code_first_post(self, repo):
        repository, db = repo
        scalar_result = MagicMock()
        scalar_result.scalar.return_value = 0
        db.execute.return_value = scalar_result

        code = await repository._generate_code()
        assert code == "POST-0001"

    @pytest.mark.asyncio
    async def test_generate_code_tenth_post(self, repo):
        repository, db = repo
        scalar_result = MagicMock()
        scalar_result.scalar.return_value = 9
        db.execute.return_value = scalar_result

        code = await repository._generate_code()
        assert code == "POST-0010"

    # -----------------------------------------------------------------------
    # create
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_post_calls_db_add_and_commit(self, repo):
        from modules.operacional.models.post import PostType, ShiftType
        from modules.operacional.schemas.post import PostCreate

        repository, db = repo

        # Stub _generate_code
        scalar_result = MagicMock()
        scalar_result.scalar.return_value = 0
        db.execute.return_value = scalar_result

        data = PostCreate(
            name="Portaria Norte",
            post_type=PostType.PORTEIRO,
            shift_type=ShiftType.DIURNO,
            required_headcount=2,
            hourly_rate=25.0,
            monthly_cost=5000.0,
        )

        post = await repository.create(data, created_by="user-1")

        db.add.assert_called_once()
        db.commit.assert_awaited()
        db.refresh.assert_awaited()
        assert post.name == "Portaria Norte"

    # -----------------------------------------------------------------------
    # get_by_id
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_by_id_returns_post(self, repo):
        from modules.operacional.models.post import Post

        repository, db = repo

        fake_post = MagicMock(spec=Post)
        fake_post.id = "abc"
        result = MagicMock()
        result.scalar_one_or_none.return_value = fake_post
        db.execute.return_value = result

        post = await repository.get_by_id("abc")
        assert post is fake_post

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_not_found(self, repo):
        repository, db = repo
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        post = await repository.get_by_id("nonexistent")
        assert post is None

    # -----------------------------------------------------------------------
    # get_by_code
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_by_code_returns_post(self, repo):
        from modules.operacional.models.post import Post

        repository, db = repo

        fake_post = MagicMock(spec=Post)
        fake_post.code = "POST-0001"
        result = MagicMock()
        result.scalar_one_or_none.return_value = fake_post
        db.execute.return_value = result

        post = await repository.get_by_code("POST-0001")
        assert post is fake_post

    # -----------------------------------------------------------------------
    # search_by_name
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_search_by_name_empty_string_returns_empty_list(self, repo):
        repository, db = repo
        result = await repository.search_by_name("  ")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_by_name_single_word_query(self, repo):
        repository, db = repo
        fake_posts = [MagicMock(), MagicMock()]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = fake_posts
        db.execute.return_value = result_mock

        posts = await repository.search_by_name("portaria", limit=5)
        assert len(posts) == 2

    @pytest.mark.asyncio
    async def test_search_by_name_short_word_skipped(self, repo):
        """Words shorter than 2 chars should be skipped in filter."""
        repository, db = repo
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute.return_value = result_mock

        # The single-char word 'a' should be skipped; query still runs
        posts = await repository.search_by_name("a", limit=5)
        assert posts == []

    # -----------------------------------------------------------------------
    # list
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_returns_tuple_of_posts_and_total(self, repo):
        repository, db = repo
        fake_posts = [MagicMock(), MagicMock(), MagicMock()]

        count_result = MagicMock()
        count_result.scalar.return_value = 3

        posts_result = MagicMock()
        posts_result.scalars.return_value.all.return_value = fake_posts

        db.execute.side_effect = [count_result, posts_result]

        posts, total = await repository.list(page=1, page_size=10)
        assert total == 3
        assert len(posts) == 3

    # -----------------------------------------------------------------------
    # update
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_returns_none_when_post_not_found(self, repo):
        from modules.operacional.schemas.post import PostUpdate

        repository, db = repo

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        updated = await repository.update("nonexistent", PostUpdate(name="X"))
        assert updated is None

    @pytest.mark.asyncio
    async def test_update_modifies_post_fields(self, repo):
        from modules.operacional.models.post import Post
        from modules.operacional.schemas.post import PostUpdate

        repository, db = repo

        fake_post = MagicMock(spec=Post)
        fake_post.id = "abc"
        fake_post.updated_at = datetime.utcnow()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_post
        db.execute.return_value = result_mock

        updated = await repository.update("abc", PostUpdate(name="Novo Nome"))
        assert updated is fake_post

    # -----------------------------------------------------------------------
    # delete (soft)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self, repo):
        repository, db = repo
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        deleted = await repository.delete("missing")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_soft_deletes_post(self, repo):
        from modules.operacional.models.post import Post, PostStatus

        repository, db = repo

        fake_post = MagicMock(spec=Post)
        fake_post.is_active = True
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_post
        db.execute.return_value = result_mock

        deleted = await repository.delete("abc")
        assert deleted is True
        assert fake_post.is_active is False

    # -----------------------------------------------------------------------
    # get_stats — empty and non-empty
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, repo):
        repository, db = repo
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute.return_value = result_mock

        stats = await repository.get_stats()
        assert stats.total == 0
        assert stats.filled == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_posts(self, repo):
        repository, db = repo

        fake_post = MagicMock()
        fake_post.status = "ATIVO"
        fake_post.post_type = "VIGILANTE"
        fake_post.shift_type = "DIURNO"
        fake_post.required_headcount = 2
        fake_post.monthly_cost = 5000.0
        fake_post.is_filled = True
        fake_post.vacancy_count = 0
        fake_post.current_headcount = 2

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [fake_post]
        db.execute.return_value = result_mock

        stats = await repository.get_stats()
        assert stats.total == 1
        assert stats.filled == 1
        assert stats.total_monthly_cost == 5000.0


# ===========================================================================
# SCALE REPOSITORY
# ===========================================================================


class TestScaleRepository:
    """Tests for ScaleRepository business logic."""

    @pytest.fixture
    def repo(self):
        from modules.operacional.repositories.scale_repository import ScaleRepository

        db = _mock_async_db()
        return ScaleRepository(db), db

    @pytest.mark.asyncio
    async def test_generate_code_format(self, repo):
        repository, _ = repo
        code = await repository._generate_code("post-abc123", month=3, year=2026)
        assert code.startswith("ESC-2026-03-")

    @pytest.mark.asyncio
    async def test_create_scale_commits(self, repo):
        from modules.operacional.models.scale import ScaleType
        from modules.operacional.schemas.scale import ScaleCreate

        repository, db = repo

        data = ScaleCreate(
            post_id="post-1",
            scale_type=ScaleType.SCALE_12X36,
            month=3,
            year=2026,
        )

        scale = await repository.create(data, created_by="user-1")
        db.add.assert_called_once()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, repo):
        from modules.operacional.models.scale import Scale

        repository, db = repo

        fake_scale = MagicMock(spec=Scale)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_scale
        db.execute.return_value = result_mock

        found = await repository.get_by_id("scale-id")
        assert found is fake_scale

    @pytest.mark.asyncio
    async def test_approve_requires_pending_approval_status(self, repo):
        from modules.operacional.models.scale import Scale, ScaleStatus

        repository, db = repo

        fake_scale = MagicMock(spec=Scale)
        # Status is DRAFT, not PENDING_APPROVAL
        fake_scale.status = ScaleStatus.DRAFT.value
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_scale
        db.execute.return_value = result_mock

        result = await repository.approve("scale-1", approved_by="mgr-1")
        assert result is None  # cannot approve when not pending

    @pytest.mark.asyncio
    async def test_approve_succeeds_when_pending(self, repo):
        from modules.operacional.models.scale import Scale, ScaleStatus

        repository, db = repo

        fake_scale = MagicMock(spec=Scale)
        fake_scale.status = ScaleStatus.PENDING_APPROVAL.value
        fake_scale.notes = None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_scale
        db.execute.return_value = result_mock

        result = await repository.approve("scale-1", approved_by="mgr-1", notes="OK")
        assert result is fake_scale
        assert fake_scale.status == ScaleStatus.APPROVED.value

    @pytest.mark.asyncio
    async def test_reject_scale_reverts_to_draft(self, repo):
        from modules.operacional.models.scale import Scale, ScaleStatus

        repository, db = repo

        fake_scale = MagicMock(spec=Scale)
        fake_scale.status = ScaleStatus.PENDING_APPROVAL.value
        fake_scale.notes = None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_scale
        db.execute.return_value = result_mock

        result = await repository.reject("scale-1", rejected_by="mgr-1", reason="Dados incorretos")
        assert result is fake_scale
        assert fake_scale.status == ScaleStatus.DRAFT.value

    @pytest.mark.asyncio
    async def test_reject_returns_none_when_not_pending(self, repo):
        from modules.operacional.models.scale import Scale, ScaleStatus

        repository, db = repo

        fake_scale = MagicMock(spec=Scale)
        fake_scale.status = ScaleStatus.APPROVED.value
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_scale
        db.execute.return_value = result_mock

        result = await repository.reject("scale-1", rejected_by="mgr-1", reason="...")
        assert result is None

    @pytest.mark.asyncio
    async def test_publish_requires_approved_status(self, repo):
        from modules.operacional.models.scale import Scale, ScaleStatus

        repository, db = repo

        fake_scale = MagicMock(spec=Scale)
        fake_scale.status = ScaleStatus.DRAFT.value
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_scale
        db.execute.return_value = result_mock

        result = await repository.publish("scale-1", published_by="mgr-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_publish_succeeds_when_approved(self, repo):
        from modules.operacional.models.scale import Scale, ScaleStatus

        repository, db = repo

        fake_scale = MagicMock(spec=Scale)
        fake_scale.status = ScaleStatus.APPROVED.value
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_scale
        db.execute.return_value = result_mock

        result = await repository.publish("scale-1", published_by="pub-1")
        assert result is fake_scale
        assert fake_scale.status == ScaleStatus.PUBLISHED.value

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_editable(self, repo):
        from modules.operacional.models.scale import Scale, ScaleStatus

        repository, db = repo

        fake_scale = MagicMock(spec=Scale)
        fake_scale.status = ScaleStatus.PUBLISHED.value
        fake_scale.can_edit = False
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_scale
        db.execute.return_value = result_mock

        deleted = await repository.delete("scale-1")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_check_employee_availability_no_conflicts(self, repo):
        repository, db = repo
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute.return_value = result_mock

        conflicts = await repository.check_employee_availability(
            employee_id="emp-1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_check_employee_availability_with_conflicts(self, repo):
        from modules.operacional.models.shift import Shift, ShiftStatus

        repository, db = repo

        fake_shift = MagicMock(spec=Shift)
        fake_shift.shift_date = date(2026, 3, 5)
        fake_shift.scale_id = "scale-xyz"
        fake_shift.id = "shift-abc"
        fake_shift.post_id = "post-1"
        fake_shift.status = ShiftStatus.SCHEDULED.value
        fake_shift.start_time = time(7, 0)
        fake_shift.end_time = time(19, 0)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [fake_shift]
        db.execute.return_value = result_mock

        conflicts = await repository.check_employee_availability(
            employee_id="emp-1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        assert len(conflicts) == 1
        assert conflicts[0]["shift_id"] == "shift-abc"


# ===========================================================================
# ALLOCATION REPOSITORY
# ===========================================================================


class TestAllocationRepository:
    """Tests for AllocationRepository conflict detection and lifecycle."""

    @pytest.fixture
    def repo(self):
        from modules.operacional.repositories.allocation_repository import AllocationRepository

        db = _mock_async_db()
        return AllocationRepository(db), db

    @pytest.mark.asyncio
    async def test_check_active_allocation_no_conflict(self, repo):
        repository, db = repo
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute.return_value = result_mock

        found = await repository.check_active_allocation(
            employee_id="emp-1",
            post_id="post-1",
            start_date=date(2026, 3, 1),
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_check_active_allocation_detects_open_ended_conflict(self, repo):
        from modules.operacional.models.allocation import Allocation

        repository, db = repo

        existing = MagicMock(spec=Allocation)
        existing.start_date = date(2026, 1, 1)
        existing.end_date = None  # indefinite

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [existing]
        db.execute.return_value = result_mock

        conflict = await repository.check_active_allocation(
            employee_id="emp-1",
            post_id="post-1",
            start_date=date(2026, 3, 1),  # after start of existing
        )
        assert conflict is existing

    @pytest.mark.asyncio
    async def test_check_active_allocation_detects_date_overlap(self, repo):
        from modules.operacional.models.allocation import Allocation

        repository, db = repo

        existing = MagicMock(spec=Allocation)
        existing.start_date = date(2026, 2, 1)
        existing.end_date = date(2026, 4, 30)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [existing]
        db.execute.return_value = result_mock

        conflict = await repository.check_active_allocation(
            employee_id="emp-1",
            post_id="post-1",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        assert conflict is existing

    @pytest.mark.asyncio
    async def test_create_raises_value_error_on_conflict(self, repo):
        from modules.operacional.models.allocation import Allocation
        from modules.operacional.schemas.allocation import AllocationCreate

        repository, db = repo

        existing = MagicMock(spec=Allocation)
        existing.id = "alloc-old"
        existing.start_date = date(2026, 1, 1)
        existing.end_date = None

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [existing]
        db.execute.return_value = result_mock

        data = AllocationCreate(
            post_id="post-1",
            employee_id="emp-1",
            start_date=date(2026, 3, 1),
        )

        with pytest.raises(ValueError, match="Funcionário já possui alocação ativa"):
            await repository.create(data, created_by="user-1")

    @pytest.mark.asyncio
    async def test_terminate_sets_terminated_status(self, repo):
        from modules.operacional.models.allocation import Allocation, AllocationStatus

        repository, db = repo

        fake_alloc = MagicMock(spec=Allocation)
        fake_alloc.id = "alloc-1"
        fake_alloc.post_id = "post-1"
        fake_alloc.notes = None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_alloc

        # _update_post_headcount also calls execute
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        db.execute.side_effect = [result_mock, count_result, MagicMock()]

        result = await repository.terminate(
            allocation_id="alloc-1",
            end_date=date(2026, 3, 31),
            reason="Fim de contrato",
        )
        assert result is fake_alloc
        assert fake_alloc.status == AllocationStatus.TERMINATED.value

    @pytest.mark.asyncio
    async def test_terminate_returns_none_when_not_found(self, repo):
        repository, db = repo
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        result = await repository.terminate(
            allocation_id="missing",
            end_date=date(2026, 3, 31),
            reason="test",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_bulk_delete_reports_success_and_errors(self, repo):
        from modules.operacional.models.allocation import Allocation

        repository, db = repo

        # First call finds an allocation (success), second returns None (error)
        found = MagicMock(spec=Allocation)
        found.id = "alloc-1"
        found.post_id = "post-1"
        result_found = MagicMock()
        result_found.scalar_one_or_none.return_value = found

        result_none = MagicMock()
        result_none.scalar_one_or_none.return_value = None

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        # Sequence: get_by_id(alloc-1) → found; _update_post_headcount query;
        #           extra commit; get_by_id(missing) → None
        db.execute.side_effect = [result_found, count_result, MagicMock(), result_none]

        result = await repository.bulk_delete(["alloc-1", "missing"])
        assert result["success_count"] == 1
        assert result["error_count"] == 1
        assert len(result["errors"]) == 1

    @pytest.mark.asyncio
    async def test_get_available_employees_filters_by_end_date(self, repo):
        from modules.operacional.models.allocation import Allocation, AllocationStatus

        repository, db = repo

        today = date.today()

        # One expired, one still active
        expired = MagicMock(spec=Allocation)
        expired.employee_id = "emp-expired"
        expired.start_date = today - timedelta(days=60)
        expired.end_date = today - timedelta(days=1)

        active = MagicMock(spec=Allocation)
        active.employee_id = "emp-active"
        active.start_date = today - timedelta(days=30)
        active.end_date = None

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [expired, active]
        db.execute.return_value = result_mock

        available = await repository.get_available_employees(shift_date=today)
        assert "emp-active" in available
        assert "emp-expired" not in available


# ===========================================================================
# SCALE GENERATOR
# ===========================================================================


class TestScaleGenerator:
    """Tests for the AI scale generation logic."""

    @pytest.fixture
    def generator(self):
        from modules.operacional.services.scale_generator import ScaleGenerator

        return ScaleGenerator()

    def test_generate_12x36_produces_shifts(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.SCALE_12X36,
            month=3,
            year=2026,
            employee_ids=["emp-1", "emp-2", "emp-3", "emp-4"],
        )
        # 31 days × 2 shifts (day + night) = 62
        assert len(shifts) == 62

    def test_generate_12x36_single_employee(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.SCALE_12X36,
            month=2,
            year=2026,
            employee_ids=["emp-1"],
        )
        # February 2026: 28 days × 2 = 56
        assert len(shifts) == 56

    def test_generate_6x1_produces_correct_count(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.SCALE_6X1,
            month=3,
            year=2026,
            employee_ids=["emp-1", "emp-2"],
        )
        # 31 days × 2 employees = 62
        assert len(shifts) == 62

    def test_generate_5x2_weekend_off(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.SCALE_5X2,
            month=3,
            year=2026,
            employee_ids=["emp-1"],
        )
        # 31 days × 1 employee = 31
        assert len(shifts) == 31
        # Weekend days should be marked as off
        weekend_shifts = [s for s in shifts if s.is_off_day]
        assert len(weekend_shifts) > 0

    def test_generate_administrativo_same_as_5x2(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.ADMINISTRATIVO,
            month=3,
            year=2026,
            employee_ids=["emp-1"],
        )
        assert len(shifts) == 31

    def test_generate_turno_revezamento(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.TURNO_REVEZAMENTO,
            month=3,
            year=2026,
            employee_ids=["emp-1", "emp-2", "emp-3"],
        )
        # 31 days × 3 employees = 93
        assert len(shifts) == 93

    def test_generate_generic_fallback(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.SCALE_5X1,
            month=3,
            year=2026,
            employee_ids=["emp-1", "emp-2"],
        )
        # 31 days × 2 employees = 62
        assert len(shifts) == 62

    def test_calculate_metrics_sums_correctly(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.SCALE_5X2,
            month=3,
            year=2026,
            employee_ids=["emp-1"],
        )
        metrics = generator.calculate_metrics(shifts)
        assert metrics["total_shifts"] == 31
        assert "work_shifts" in metrics
        assert "off_shifts" in metrics
        assert metrics["work_shifts"] + metrics["off_shifts"] == 31

    def test_optimize_scale_returns_same_length(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.SCALE_6X1,
            month=3,
            year=2026,
            employee_ids=["emp-1"],
        )
        optimized = generator.optimize_scale(shifts)
        assert len(optimized) == len(shifts)

    def test_create_6x1_pattern_distributes_off_days(self, generator):
        pattern = generator._create_6x1_pattern(
            employee_ids=["emp-1", "emp-2"],
            work_days=6,
            off_days=1,
            days_in_month=28,
        )
        assert "emp-1" in pattern
        assert "emp-2" in pattern
        # Off days for each employee should be different (distributed)
        assert pattern["emp-1"] != pattern["emp-2"]

    def test_generate_with_custom_config(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.SCALE_12X36,
            month=3,
            year=2026,
            employee_ids=["emp-1"],
            config={"work_hours": 10},
        )
        # Custom work_hours should propagate to shifts
        assert all(s.planned_hours == 10 for s in shifts if not s.is_off_day)

    def test_generate_marks_night_shifts_correctly(self, generator):
        from modules.operacional.models.scale import ScaleType

        shifts = generator.generate(
            scale_id="scale-1",
            post_id="post-1",
            scale_type=ScaleType.SCALE_12X36,
            month=3,
            year=2026,
            employee_ids=["emp-1", "emp-2"],
        )
        night_shifts = [s for s in shifts if s.is_night_shift]
        day_shifts = [s for s in shifts if not s.is_night_shift]
        assert len(night_shifts) > 0
        assert len(day_shifts) > 0


# ===========================================================================
# TIME BANK SERVICE
# ===========================================================================


class TestTimeBankService:
    """Tests for TimeBankService CLT business rules."""

    @pytest.fixture
    def service(self):
        from modules.operacional.services.time_bank_service import TimeBankService

        return TimeBankService()

    # -----------------------------------------------------------------------
    # calculate_overtime_hours
    # -----------------------------------------------------------------------

    def test_no_overtime_when_worked_equals_planned(self, service):
        result = service.calculate_overtime_hours(actual_hours=8.0, planned_hours=8.0)
        assert result["overtime_hours"] == 0.0
        assert result["normal_hours"] == 8.0
        assert result["negative_hours"] == 0.0

    def test_overtime_capped_at_2h_per_day(self, service):
        result = service.calculate_overtime_hours(actual_hours=11.0, planned_hours=8.0)
        assert result["overtime_hours"] == 2.0  # CLT cap

    def test_negative_hours_when_worked_less_than_planned(self, service):
        result = service.calculate_overtime_hours(actual_hours=6.0, planned_hours=8.0)
        assert result["negative_hours"] == 2.0
        assert result["overtime_hours"] == 0.0

    def test_break_minutes_deducted_from_worked_hours(self, service):
        # 9h actual - 1h break = 8h worked; no overtime
        result = service.calculate_overtime_hours(actual_hours=9.0, planned_hours=8.0, break_minutes=60)
        assert result["worked_hours"] == 8.0
        assert result["overtime_hours"] == 0.0

    def test_night_shift_sets_night_hours(self, service):
        result = service.calculate_overtime_hours(actual_hours=8.0, planned_hours=8.0, is_night_shift=True)
        assert result["night_hours"] == 8.0

    def test_no_night_hours_for_day_shift(self, service):
        result = service.calculate_overtime_hours(actual_hours=8.0, planned_hours=8.0, is_night_shift=False)
        assert result["night_hours"] == 0.0

    # -----------------------------------------------------------------------
    # calculate_compensation_value
    # -----------------------------------------------------------------------

    def test_base_value_calculation(self, service):
        result = service.calculate_compensation_value(hours=8.0, hourly_rate=20.0)
        assert result["base_value"] == 160.0
        assert result["total_value"] == 160.0

    def test_overtime_bonus_50_percent(self, service):
        result = service.calculate_compensation_value(hours=2.0, hourly_rate=20.0, is_overtime=True)
        assert result["overtime_bonus"] == 20.0  # 40 * 0.50

    def test_night_bonus_20_percent(self, service):
        result = service.calculate_compensation_value(hours=8.0, hourly_rate=10.0, is_night=True)
        assert result["night_bonus"] == 16.0  # 80 * 0.20

    def test_sunday_bonus_100_percent(self, service):
        result = service.calculate_compensation_value(hours=8.0, hourly_rate=10.0, is_sunday=True)
        assert result["sunday_bonus"] == 80.0  # 80 * 1.00

    def test_holiday_bonus_100_percent(self, service):
        result = service.calculate_compensation_value(hours=8.0, hourly_rate=10.0, is_holiday=True)
        assert result["holiday_bonus"] == 80.0

    def test_stacking_bonuses(self, service):
        result = service.calculate_compensation_value(
            hours=2.0,
            hourly_rate=20.0,
            is_overtime=True,
            is_night=True,
        )
        # base=40, night_bonus=8, overtime_bonus=20 → total=68
        assert result["total_value"] == 68.0

    # -----------------------------------------------------------------------
    # get_expiration_date
    # -----------------------------------------------------------------------

    def test_individual_agreement_expiration_180_days(self, service):
        ref = date(2026, 1, 1)
        exp = service.get_expiration_date(ref, has_collective_agreement=False)
        assert exp == ref + timedelta(days=180)

    def test_collective_agreement_expiration_365_days(self, service):
        ref = date(2026, 1, 1)
        exp = service.get_expiration_date(ref, has_collective_agreement=True)
        assert exp == ref + timedelta(days=365)

    # -----------------------------------------------------------------------
    # check_expiration_alerts
    # -----------------------------------------------------------------------

    def test_expired_entry_severity_critical(self, service):
        expired_date = (date.today() - timedelta(days=1)).isoformat()
        entries = [{"id": "e1", "employee_id": "emp-1", "hours": 5.0, "expiration_date": expired_date}]
        alerts = service.check_expiration_alerts(entries)
        assert len(alerts) == 1
        assert alerts[0]["status"] == "expired"
        assert alerts[0]["severity"] == "critical"

    def test_expiring_soon_high_severity_within_7_days(self, service):
        soon = (date.today() + timedelta(days=5)).isoformat()
        entries = [{"id": "e2", "employee_id": "emp-1", "hours": 3.0, "expiration_date": soon}]
        alerts = service.check_expiration_alerts(entries)
        assert len(alerts) == 1
        assert alerts[0]["status"] == "expiring_soon"
        assert alerts[0]["severity"] == "high"

    def test_expiring_soon_medium_severity_8_to_30_days(self, service):
        soon = (date.today() + timedelta(days=20)).isoformat()
        entries = [{"id": "e3", "employee_id": "emp-1", "hours": 3.0, "expiration_date": soon}]
        alerts = service.check_expiration_alerts(entries)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "medium"

    def test_no_alerts_for_far_expiration(self, service):
        far = (date.today() + timedelta(days=60)).isoformat()
        entries = [{"id": "e4", "employee_id": "emp-1", "hours": 10.0, "expiration_date": far}]
        alerts = service.check_expiration_alerts(entries)
        assert len(alerts) == 0

    def test_entry_without_expiration_date_ignored(self, service):
        entries = [{"id": "e5", "employee_id": "emp-1", "hours": 10.0}]
        alerts = service.check_expiration_alerts(entries)
        assert len(alerts) == 0

    # -----------------------------------------------------------------------
    # validate_compensation_request
    # -----------------------------------------------------------------------

    def test_valid_compensation_request(self, service):
        future = date.today() + timedelta(days=7)
        result = service.validate_compensation_request(
            employee_balance=16.0,
            requested_hours=8.0,
            compensation_date=future,
        )
        assert result["is_valid"] is True
        assert result["balance_after"] == 8.0

    def test_insufficient_balance_invalid(self, service):
        future = date.today() + timedelta(days=1)
        result = service.validate_compensation_request(
            employee_balance=4.0,
            requested_hours=8.0,
            compensation_date=future,
        )
        assert result["is_valid"] is False
        assert any("insuficiente" in e.lower() for e in result["errors"])

    def test_past_date_invalid(self, service):
        past = date.today() - timedelta(days=1)
        result = service.validate_compensation_request(
            employee_balance=16.0,
            requested_hours=4.0,
            compensation_date=past,
        )
        assert result["is_valid"] is False

    def test_weekend_compensation_produces_warning(self, service):
        # Find next Saturday
        today = date.today()
        days_ahead = (5 - today.weekday()) % 7 or 7
        saturday = today + timedelta(days=days_ahead)
        result = service.validate_compensation_request(
            employee_balance=16.0,
            requested_hours=8.0,
            compensation_date=saturday,
        )
        assert any("fim de semana" in w.lower() for w in result["warnings"])

    # -----------------------------------------------------------------------
    # calculate_monthly_summary
    # -----------------------------------------------------------------------

    def test_monthly_summary_sums_correctly(self, service):
        entries = [
            {"reference_date": "2026-03-05", "entry_type": "credit", "hours": 4.0},
            {"reference_date": "2026-03-10", "entry_type": "credit", "hours": 2.0},
            {"reference_date": "2026-03-15", "entry_type": "debit", "hours": 1.0},
            {"reference_date": "2026-02-20", "entry_type": "credit", "hours": 10.0},  # different month
        ]
        result = service.calculate_monthly_summary(entries, month=3, year=2026)
        assert result["total_credits"] == 6.0
        assert result["total_debits"] == 1.0
        assert result["net_balance"] == 5.0
        assert result["entries_count"] == 3

    def test_monthly_summary_empty_period(self, service):
        result = service.calculate_monthly_summary([], month=3, year=2026)
        assert result["entries_count"] == 0
        assert result["net_balance"] == 0.0

    # -----------------------------------------------------------------------
    # get_recommendations
    # -----------------------------------------------------------------------

    def test_recommendations_expiring_soon(self, service):
        recs = service.get_recommendations(employee_balance=5.0, expiring_soon=3.0, monthly_avg_overtime=5.0)
        assert any("expiram" in r.lower() for r in recs)

    def test_recommendations_high_balance(self, service):
        recs = service.get_recommendations(employee_balance=50.0, expiring_soon=0.0, monthly_avg_overtime=5.0)
        assert any("compensat" in r.lower() for r in recs)

    def test_recommendations_negative_balance(self, service):
        recs = service.get_recommendations(employee_balance=-15.0, expiring_soon=0.0, monthly_avg_overtime=5.0)
        assert any("negativo" in r.lower() for r in recs)

    def test_recommendations_high_overtime(self, service):
        recs = service.get_recommendations(employee_balance=5.0, expiring_soon=0.0, monthly_avg_overtime=35.0)
        assert any("contrata" in r.lower() for r in recs)

    def test_recommendations_normal_situation_no_recs(self, service):
        recs = service.get_recommendations(employee_balance=5.0, expiring_soon=0.0, monthly_avg_overtime=10.0)
        assert recs == []


# ===========================================================================
# DIARIST SERVICE
# ===========================================================================


class TestDiaristService:
    """Tests for DiaristService business logic."""

    @pytest.fixture
    def service_and_repo(self):
        from modules.operacional.diaristas.services.diarist_service import DiaristService

        db = AsyncMock()
        service = DiaristService(db)
        service.repository = AsyncMock()
        return service, service.repository

    @pytest.mark.asyncio
    async def test_create_diarist_duplicate_cpf_raises(self, service_and_repo):
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristCreate

        service, repo = service_and_repo

        repo.get_by_cpf.return_value = MagicMock()  # already exists

        data = DiaristCreate(
            nome="Maria",
            cpf="12345678901",
            valor_diaria=Decimal("150"),
        )
        with pytest.raises(ValueError, match="CPF"):
            await service.create_diarist(data)

    @pytest.mark.asyncio
    async def test_create_diarist_duplicate_email_raises(self, service_and_repo):
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristCreate

        service, repo = service_and_repo

        repo.get_by_cpf.return_value = None
        repo.get_by_email.return_value = MagicMock()  # email conflict

        data = DiaristCreate(
            nome="Maria",
            cpf="12345678901",
            email="maria@test.com",
            valor_diaria=Decimal("150"),
        )
        with pytest.raises(ValueError, match="Email"):
            await service.create_diarist(data)

    @pytest.mark.asyncio
    async def test_create_diarist_success(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import Diarist
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristCreate

        service, repo = service_and_repo

        repo.get_by_cpf.return_value = None
        repo.get_by_email.return_value = None
        fake_diarist = MagicMock(spec=Diarist)
        fake_diarist.id = uuid.uuid4()
        fake_diarist.nome = "Maria"
        repo.create.return_value = fake_diarist

        data = DiaristCreate(
            nome="Maria",
            cpf="12345678901",
            valor_diaria=Decimal("150"),
        )
        result = await service.create_diarist(data)
        assert result is fake_diarist
        repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_activate_diarist_sets_ativo(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import Diarist, DiaristStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=Diarist)
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake

        result = await service.activate_diarist(uuid.uuid4())
        assert result is fake
        assert fake.status == DiaristStatus.ATIVO
        assert fake.ativo is True

    @pytest.mark.asyncio
    async def test_activate_diarist_not_found_returns_none(self, service_and_repo):
        service, repo = service_and_repo
        repo.get_by_id.return_value = None

        result = await service.activate_diarist(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_deactivate_diarist(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import Diarist, DiaristStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=Diarist)
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake

        result = await service.deactivate_diarist(uuid.uuid4())
        assert result is fake
        assert fake.status == DiaristStatus.INATIVO
        assert fake.ativo is False

    @pytest.mark.asyncio
    async def test_create_assignment_diarist_not_found_raises(self, service_and_repo):
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristAssignmentCreate

        service, repo = service_and_repo

        repo.get_by_id.return_value = None

        data = MagicMock(spec=DiaristAssignmentCreate)
        data.diarist_id = uuid.uuid4()
        with pytest.raises(ValueError, match="Diarista não encontrada"):
            await service.create_assignment(data)

    @pytest.mark.asyncio
    async def test_create_assignment_inactive_diarist_raises(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import Diarist, DiaristStatus
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristAssignmentCreate

        service, repo = service_and_repo

        fake = MagicMock(spec=Diarist)
        fake.status = DiaristStatus.INATIVO
        repo.get_by_id.return_value = fake

        data = MagicMock(spec=DiaristAssignmentCreate)
        data.diarist_id = uuid.uuid4()
        with pytest.raises(ValueError, match="não está ativa"):
            await service.create_assignment(data)

    @pytest.mark.asyncio
    async def test_confirm_schedule_wrong_status_returns_none(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import DiaristSchedule, ScheduleStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=DiaristSchedule)
        fake.status = ScheduleStatus.CONFIRMADO  # already confirmed
        repo.get_schedule_by_id.return_value = fake

        result = await service.confirm_schedule(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_confirm_schedule_success(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import DiaristSchedule, ScheduleStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=DiaristSchedule)
        fake.status = ScheduleStatus.AGENDADO
        repo.get_schedule_by_id.return_value = fake
        repo.update_schedule.return_value = fake

        result = await service.confirm_schedule(uuid.uuid4())
        assert result is fake
        assert fake.status == ScheduleStatus.CONFIRMADO

    @pytest.mark.asyncio
    async def test_cancel_schedule_already_done_raises(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import DiaristSchedule, ScheduleStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=DiaristSchedule)
        fake.status = ScheduleStatus.CONCLUIDO
        repo.get_schedule_by_id.return_value = fake

        with pytest.raises(ValueError, match="não pode ser cancelado"):
            await service.cancel_schedule(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_schedule_success(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import DiaristSchedule, ScheduleStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=DiaristSchedule)
        fake.status = ScheduleStatus.AGENDADO
        fake.observacoes = None
        repo.get_schedule_by_id.return_value = fake
        repo.update_schedule.return_value = fake

        result = await service.cancel_schedule(uuid.uuid4(), motivo="Não precisa mais")
        assert result is fake
        assert fake.status == ScheduleStatus.CANCELADO

    @pytest.mark.asyncio
    async def test_create_payment_calculates_liquid(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import Diarist, DiaristPayment, PaymentMethod
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristPaymentCreate

        service, repo = service_and_repo

        fake_diarist = MagicMock(spec=Diarist)
        repo.get_by_id.return_value = fake_diarist

        fake_payment = MagicMock(spec=DiaristPayment)
        repo.create_payment.return_value = fake_payment

        data = DiaristPaymentCreate(
            diarist_id=uuid.uuid4(),
            data_referencia=date(2026, 3, 31),
            data_vencimento=date(2026, 4, 5),
            valor_bruto=Decimal("1000.00"),
            retencao_inss=Decimal("110.00"),
            forma_pagamento=PaymentMethod.PIX,
        )

        result = await service.create_payment(data)
        assert result is fake_payment
        repo.create_payment.assert_awaited_once()
        # The payment created should have valor_liquido = 1000 - 110 = 890
        created_payment = repo.create_payment.call_args[0][0]
        assert created_payment.valor_liquido == Decimal("890.00")

    @pytest.mark.asyncio
    async def test_create_evaluation_not_concluded_raises(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import DiaristSchedule, ScheduleStatus
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristEvaluationCreate

        service, repo = service_and_repo

        fake_schedule = MagicMock(spec=DiaristSchedule)
        fake_schedule.status = ScheduleStatus.AGENDADO
        repo.get_schedule_by_id.return_value = fake_schedule

        data = MagicMock(spec=DiaristEvaluationCreate)
        data.schedule_id = uuid.uuid4()
        with pytest.raises(ValueError, match="não foi concluído"):
            await service.create_evaluation(data)

    @pytest.mark.asyncio
    async def test_create_evaluation_already_evaluated_raises(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import DiaristSchedule, ScheduleStatus
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristEvaluationCreate

        service, repo = service_and_repo

        fake_schedule = MagicMock(spec=DiaristSchedule)
        fake_schedule.status = ScheduleStatus.CONCLUIDO
        fake_schedule.diarist_id = uuid.uuid4()
        repo.get_schedule_by_id.return_value = fake_schedule
        repo.get_evaluation_by_schedule.return_value = MagicMock()  # already has evaluation

        data = MagicMock(spec=DiaristEvaluationCreate)
        data.schedule_id = uuid.uuid4()
        with pytest.raises(ValueError, match="já foi avaliado"):
            await service.create_evaluation(data)

    @pytest.mark.asyncio
    async def test_generate_payment_from_schedules_no_schedules_returns_none(self, service_and_repo):
        service, repo = service_and_repo
        repo.list_schedules.return_value = []

        result = await service.generate_payment_from_schedules(
            diarist_id=uuid.uuid4(),
            data_inicio=date(2026, 3, 1),
            data_fim=date(2026, 3, 31),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_batch_schedules_skips_inactive_diarist(self, service_and_repo):
        from modules.operacional.diaristas.models.diarist import Diarist
        from modules.operacional.diaristas.schemas.diarist_schemas import BatchScheduleCreate

        service, repo = service_and_repo

        fake_diarist = MagicMock(spec=Diarist)
        fake_diarist.nome = "Inativa"
        fake_diarist.status = "INATIVO"
        repo.get_by_id.return_value = fake_diarist

        item = MagicMock()
        item.diarist_id = uuid.uuid4()
        item.horario_inicio = "08:00"
        item.horario_fim = "17:00"
        item.observacoes = None

        data = MagicMock(spec=BatchScheduleCreate)
        data.data = date.today()
        data.condominio_id = uuid.uuid4()
        data.items = [item]

        result = await service.create_batch_schedules(data)
        assert result["total_criados"] == 0
        assert result["total_erros"] == 1


# ===========================================================================
# OCCURRENCE SERVICE
# ===========================================================================


class TestOccurrenceService:
    """Tests for OccurrenceService workflow and validations."""

    @pytest.fixture
    def service_and_repo(self):
        from modules.operacional.occurrences.services.occurrence_service import OccurrenceService

        db = MagicMock()
        service = OccurrenceService(db)
        service.repository = MagicMock()
        return service, service.repository

    def test_get_by_id_raises_not_found(self, service_and_repo):
        from modules.operacional.occurrences.services.occurrence_service import OccurrenceNotFoundError

        service, repo = service_and_repo
        repo.get_by_id.return_value = None

        with pytest.raises(OccurrenceNotFoundError):
            service.get_by_id("missing-id")

    def test_get_by_id_returns_occurrence(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence

        service, repo = service_and_repo
        fake = MagicMock(spec=Occurrence)
        repo.get_by_id.return_value = fake

        result = service.get_by_id("occ-1")
        assert result is fake

    def test_start_analysis_wrong_status_raises(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence, OccurrenceStatus
        from modules.operacional.occurrences.services.occurrence_service import OccurrenceValidationError

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.status = OccurrenceStatus.RESOLVIDA.value
        repo.get_by_id.return_value = fake

        with pytest.raises(OccurrenceValidationError, match="status"):
            service.start_analysis("occ-1")

    def test_start_analysis_from_aberta(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence, OccurrenceStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.status = OccurrenceStatus.ABERTA.value
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake

        result = service.start_analysis("occ-1")
        fake.start_analysis.assert_called_once()
        assert result is fake

    def test_resolve_already_resolved_raises(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence, OccurrenceStatus
        from modules.operacional.occurrences.services.occurrence_service import OccurrenceValidationError

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.status = OccurrenceStatus.RESOLVIDA.value
        repo.get_by_id.return_value = fake

        resolve_req = MagicMock()
        with pytest.raises(OccurrenceValidationError, match="já esta resolvida"):
            service.resolve("occ-1", resolve_req)

    def test_resolve_archived_raises(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence, OccurrenceStatus
        from modules.operacional.occurrences.services.occurrence_service import OccurrenceValidationError

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.status = OccurrenceStatus.ARQUIVADA.value
        repo.get_by_id.return_value = fake

        resolve_req = MagicMock()
        with pytest.raises(OccurrenceValidationError, match="arquivada"):
            service.resolve("occ-1", resolve_req)

    def test_resolve_success(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence, OccurrenceStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.status = OccurrenceStatus.ABERTA.value
        fake.code = "OCC-001"
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake

        resolve_req = MagicMock()
        resolve_req.resolution_type = MagicMock()
        resolve_req.resolution_type.value = "RESOLVIDA"
        resolve_req.resolution = "Problema corrigido"
        resolve_req.resolved_by_id = uuid.uuid4()

        result = service.resolve("occ-1", resolve_req)
        fake.resolve.assert_called_once()
        assert result is fake

    def test_reopen_from_wrong_status_raises(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence, OccurrenceStatus
        from modules.operacional.occurrences.services.occurrence_service import OccurrenceValidationError

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.status = OccurrenceStatus.ABERTA.value
        repo.get_by_id.return_value = fake

        with pytest.raises(OccurrenceValidationError, match="nao pode ser reaberta"):
            service.reopen("occ-1")

    def test_reopen_from_resolvida(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence, OccurrenceStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.status = OccurrenceStatus.RESOLVIDA.value
        fake.sla_breached = True
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake

        result = service.reopen("occ-1")
        fake.reopen.assert_called_once()
        assert fake.sla_breached is False

    def test_escalate_closed_occurrence_raises(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence
        from modules.operacional.occurrences.services.occurrence_service import OccurrenceValidationError

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.is_open = False
        fake.status = "RESOLVIDA"
        repo.get_by_id.return_value = fake

        escalate_req = MagicMock()
        with pytest.raises(OccurrenceValidationError, match="nao pode ser escalada"):
            service.escalate("occ-1", escalate_req)

    def test_escalate_open_occurrence(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.is_open = True
        fake.code = "OCC-001"
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake

        escalate_req = MagicMock()
        escalate_req.escalated_to_id = uuid.uuid4()
        escalate_req.reason = "Urgente"

        with patch.object(service, "_notify_escalation"):
            result = service.escalate("occ-1", escalate_req)
        fake.escalate.assert_called_once()
        assert result is fake

    def test_archive_occurrence(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.code = "OCC-001"
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake

        result = service.archive("occ-1")
        fake.archive.assert_called_once()
        assert result is fake

    def test_add_attachment_requires_existing_occurrence(self, service_and_repo):
        from modules.operacional.occurrences.services.occurrence_service import OccurrenceNotFoundError

        service, repo = service_and_repo
        repo.get_by_id.return_value = None

        attachment_data = MagicMock()
        with pytest.raises(OccurrenceNotFoundError):
            service.add_attachment("missing", attachment_data)

    def test_get_dashboard_stats_builds_response(self, service_and_repo):
        from modules.operacional.occurrences.schemas import DashboardStats

        service, repo = service_and_repo

        repo.get_stats.return_value = {
            "total": 10,
            "abertas": 5,
            "em_analise": 2,
            "pendentes": 1,
            "resolvidas": 1,
            "arquivadas": 1,
            "criticas": 3,
            "sla_breached": 1,
            "by_category": {},
            "by_severity": {},
            "by_priority": {},
        }
        repo.list_sla_breaching.return_value = [MagicMock(), MagicMock()]

        stats = service.get_dashboard_stats(tenant_id="tenant-1")
        assert stats.total == 10
        assert stats.sla_at_risk == 2

    def test_create_category_config_duplicate_raises(self, service_and_repo):
        from modules.operacional.occurrences.services.occurrence_service import OccurrenceValidationError

        service, repo = service_and_repo

        repo.get_category_config.return_value = MagicMock()  # already exists

        data = MagicMock()
        data.tenant_id = uuid.uuid4()
        data.code = "CAT-001"
        with pytest.raises(OccurrenceValidationError, match="ja existe"):
            service.create_category_config(data)

    def test_delete_occurrence_calls_repository(self, service_and_repo):
        from modules.operacional.occurrences.models import Occurrence

        service, repo = service_and_repo

        fake = MagicMock(spec=Occurrence)
        fake.code = "OCC-001"
        repo.get_by_id.return_value = fake
        repo.delete.return_value = True

        result = service.delete("occ-1")
        assert result is True


# ===========================================================================
# INSPECTION ROUND SERVICE
# ===========================================================================


class TestInspectionRoundService:
    """Tests for InspectionRoundService workflow."""

    @pytest.fixture
    def service_and_repo(self):
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundService,
        )

        db = AsyncMock()
        service = InspectionRoundService(db)
        service.repository = AsyncMock()
        return service, service.repository

    @pytest.mark.asyncio
    async def test_get_by_id_raises_not_found(self, service_and_repo):
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundNotFoundError,
        )

        service, repo = service_and_repo
        repo.get_by_id.return_value = None

        with pytest.raises(InspectionRoundNotFoundError):
            await service.get_by_id("missing")

    @pytest.mark.asyncio
    async def test_start_round_from_agendada(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.AGENDADA.value
        fake.code = "RON-2026-001"
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake

        result = await service.start_round("round-1")
        fake.start.assert_called_once()
        assert result is fake

    @pytest.mark.asyncio
    async def test_start_round_invalid_status_raises(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundValidationError,
        )

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.CONCLUIDA.value
        repo.get_by_id.return_value = fake

        with pytest.raises(InspectionRoundValidationError, match="nao pode ser iniciada"):
            await service.start_round("round-1")

    @pytest.mark.asyncio
    async def test_pause_round_requires_em_andamento(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundValidationError,
        )

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.AGENDADA.value
        repo.get_by_id.return_value = fake

        with pytest.raises(InspectionRoundValidationError, match="nao esta em andamento"):
            await service.pause_round("round-1")

    @pytest.mark.asyncio
    async def test_pause_round_success(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.EM_ANDAMENTO.value
        fake.code = "RON-001"
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake

        result = await service.pause_round("round-1")
        fake.pause.assert_called_once()
        assert result is fake

    @pytest.mark.asyncio
    async def test_resume_round_requires_pausada(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundValidationError,
        )

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.AGENDADA.value
        repo.get_by_id.return_value = fake

        with pytest.raises(InspectionRoundValidationError, match="nao esta pausada"):
            await service.resume_round("round-1")

    @pytest.mark.asyncio
    async def test_complete_round_success(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.EM_ANDAMENTO.value
        fake.code = "RON-001"
        fake.total_occurrences = 0
        repo.get_by_id.return_value = fake
        repo.update.return_value = fake
        repo.get_checkpoints_by_round.return_value = [MagicMock(), MagicMock()]

        result = await service.complete_round("round-1")
        fake.complete.assert_called_once()
        assert fake.total_checkpoints == 2

    @pytest.mark.asyncio
    async def test_complete_round_requires_em_andamento(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundValidationError,
        )

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.PAUSADA.value
        repo.get_by_id.return_value = fake

        with pytest.raises(InspectionRoundValidationError, match="nao esta em andamento"):
            await service.complete_round("round-1")

    @pytest.mark.asyncio
    async def test_cancel_round_already_concluded_raises(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundValidationError,
        )

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.CONCLUIDA.value
        repo.get_by_id.return_value = fake

        with pytest.raises(InspectionRoundValidationError, match="ja concluida"):
            await service.cancel_round("round-1")

    @pytest.mark.asyncio
    async def test_create_checkpoint_requires_em_andamento(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundValidationError,
        )

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.AGENDADA.value
        repo.get_by_id.return_value = fake

        checkpoint_data = MagicMock()
        with pytest.raises(InspectionRoundValidationError, match="nao esta em andamento"):
            await service.create_checkpoint("round-1", checkpoint_data)

    @pytest.mark.asyncio
    async def test_delete_round_in_progress_raises(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundValidationError,
        )

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.EM_ANDAMENTO.value
        repo.get_by_id.return_value = fake

        with pytest.raises(InspectionRoundValidationError, match="em andamento"):
            await service.delete("round-1")

    @pytest.mark.asyncio
    async def test_get_dashboard_stats(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRoundStatus

        service, repo = service_and_repo

        repo.count_by_status.return_value = {
            InspectionRoundStatus.CONCLUIDA.value: 5,
            InspectionRoundStatus.AGENDADA.value: 3,
        }
        repo.get_rounds_in_progress.return_value = [MagicMock()]
        repo.get_rounds_scheduled_today.return_value = [MagicMock(), MagicMock()]

        stats = await service.get_dashboard_stats(tenant_id="tenant-1")
        assert stats.total_rounds == 8
        assert stats.rounds_completed == 5
        assert stats.rounds_today == 2

    @pytest.mark.asyncio
    async def test_update_not_editable_status_raises(self, service_and_repo):
        from modules.operacional.inspection_rounds.models import InspectionRound, InspectionRoundStatus
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            InspectionRoundValidationError,
        )

        service, repo = service_and_repo

        fake = MagicMock(spec=InspectionRound)
        fake.status = InspectionRoundStatus.CONCLUIDA.value
        repo.get_by_id.return_value = fake

        update_data = MagicMock()
        update_data.scheduled_date = None
        update_data.posts_to_visit = None
        update_data.observations = None
        update_data.summary = None

        with pytest.raises(InspectionRoundValidationError, match="nao pode ser editada"):
            await service.update("round-1", update_data)


# ===========================================================================
# GEOLOCATION SERVICE
# ===========================================================================


class TestGeolocationService:
    """Tests for GeolocationService Haversine calculations."""

    @pytest.fixture
    def geo_service(self):
        from modules.operacional.services.geolocation_service import GeolocationService

        return GeolocationService()

    def test_distance_same_point_is_zero(self, geo_service):
        from modules.operacional.services.geolocation_service import GeoPoint

        p = GeoPoint(-3.1190, -60.0217)
        distance = geo_service.calculate_distance(p, p)
        assert distance == 0.0

    def test_distance_between_two_points(self, geo_service):
        from modules.operacional.services.geolocation_service import GeoPoint

        # Known distance between Manaus airport and city center ≈ 14km
        airport = GeoPoint(-3.0386, -60.0499)
        center = GeoPoint(-3.1190, -60.0217)
        distance = geo_service.calculate_distance(airport, center)
        assert 8000 < distance < 20000  # somewhere in that range

    def test_validate_location_within_radius(self, geo_service):
        from modules.operacional.services.geolocation_service import GeoPoint

        post = GeoPoint(-3.1190, -60.0217)
        user = GeoPoint(-3.1191, -60.0218)  # very close
        result = geo_service.validate_location(user, post, allowed_radius_meters=100)
        assert result.is_valid is True
        assert result.within_radius is True

    def test_validate_location_outside_radius(self, geo_service):
        from modules.operacional.services.geolocation_service import GeoPoint

        post = GeoPoint(-3.1190, -60.0217)
        user = GeoPoint(-3.2000, -60.1000)  # far away
        result = geo_service.validate_location(user, post, allowed_radius_meters=100)
        assert result.is_valid is False
        assert result.within_radius is False

    def test_validate_location_poor_gps_accuracy(self, geo_service):
        from modules.operacional.services.geolocation_service import GeolocationService, GeoPoint

        service = GeolocationService(max_accuracy=50.0)
        post = GeoPoint(-3.1190, -60.0217)
        user = GeoPoint(-3.1191, -60.0218, accuracy=200.0)  # bad GPS
        result = service.validate_location(user, post, allowed_radius_meters=100)
        assert result.accuracy_acceptable is False
        assert result.is_valid is False

    def test_validate_location_no_accuracy_field_accepted(self, geo_service):
        from modules.operacional.services.geolocation_service import GeoPoint

        post = GeoPoint(-3.1190, -60.0217)
        user = GeoPoint(-3.1191, -60.0218, accuracy=None)
        result = geo_service.validate_location(user, post, allowed_radius_meters=100)
        assert result.accuracy_acceptable is True

    def test_get_address_from_coords(self, geo_service):
        from modules.operacional.services.geolocation_service import GeoPoint

        point = GeoPoint(-3.1190, -60.0217)
        address = geo_service.get_address_from_coords(point)
        assert "-3.1190" in address
        assert "-60.0217" in address

    def test_is_point_in_polygon_inside(self, geo_service):
        from modules.operacional.services.geolocation_service import GeoPoint

        # Simple square polygon
        polygon = [(-3.0, -60.1), (-3.0, -59.9), (-3.2, -59.9), (-3.2, -60.1)]
        point = GeoPoint(-3.1, -60.0)
        assert geo_service.is_point_in_polygon(point, polygon) is True

    def test_is_point_in_polygon_outside(self, geo_service):
        from modules.operacional.services.geolocation_service import GeoPoint

        polygon = [(-3.0, -60.1), (-3.0, -59.9), (-3.2, -59.9), (-3.2, -60.1)]
        point = GeoPoint(-4.0, -62.0)  # clearly outside
        assert geo_service.is_point_in_polygon(point, polygon) is False


# ===========================================================================
# CHECK-IN VALIDATOR
# ===========================================================================


class TestCheckInValidator:
    """Tests for CheckInValidator time/device validation logic."""

    @pytest.fixture
    def validator(self):
        from modules.operacional.services.biometric_service import BiometricService
        from modules.operacional.services.check_in_validator import CheckInValidator
        from modules.operacional.services.geolocation_service import GeolocationService

        geo = GeolocationService()
        bio = MagicMock(spec=BiometricService)
        return CheckInValidator(geo_service=geo, bio_service=bio)

    # -----------------------------------------------------------------------
    # _validate_time
    # -----------------------------------------------------------------------

    def test_validate_time_on_schedule_score_100(self, validator):
        result = validator._validate_time(
            check_time=time(7, 0),
            scheduled_time=time(7, 0),
            max_early=30,
            max_late=15,
        )
        assert result["score"] == 100.0
        assert result["is_late"] is False
        assert result["is_early"] is False

    def test_validate_time_early_within_limit_score_100(self, validator):
        result = validator._validate_time(
            check_time=time(6, 45),
            scheduled_time=time(7, 0),
            max_early=30,
            max_late=15,
        )
        assert result["is_early"] is True
        assert result["score"] == 100.0

    def test_validate_time_too_early_score_70(self, validator):
        result = validator._validate_time(
            check_time=time(6, 0),
            scheduled_time=time(7, 0),
            max_early=30,
            max_late=15,
        )
        assert result["is_early"] is True
        assert result["score"] == 70.0

    def test_validate_time_small_late_penalizes_score(self, validator):
        # 10 min late → score = 100 - (10 * 2) = 80
        result = validator._validate_time(
            check_time=time(7, 10),
            scheduled_time=time(7, 0),
            max_early=30,
            max_late=15,
        )
        assert result["score"] == 80.0
        assert result["is_late"] is False  # within max_late

    def test_validate_time_exceeds_max_late_score_zero(self, validator):
        result = validator._validate_time(
            check_time=time(7, 30),
            scheduled_time=time(7, 0),
            max_early=30,
            max_late=15,
        )
        assert result["is_late"] is True
        assert result["score"] == 0.0
        assert result["is_valid"] is False

    # -----------------------------------------------------------------------
    # _validate_device
    # -----------------------------------------------------------------------

    def test_validate_device_no_device_id_score_80(self, validator):
        result = validator._validate_device(
            device_id=None,
            known_device_id="known-123",
            allow_different=False,
        )
        assert result["score"] == 80.0

    def test_validate_device_same_device_score_100(self, validator):
        result = validator._validate_device(
            device_id="device-abc",
            known_device_id="device-abc",
            allow_different=False,
        )
        assert result["score"] == 100.0
        assert result["is_different"] is False

    def test_validate_device_different_not_allowed_score_50(self, validator):
        result = validator._validate_device(
            device_id="device-new",
            known_device_id="device-old",
            allow_different=False,
        )
        assert result["score"] == 50.0
        assert result["is_valid"] is False

    def test_validate_device_different_allowed_score_80(self, validator):
        result = validator._validate_device(
            device_id="device-new",
            known_device_id="device-old",
            allow_different=True,
        )
        assert result["score"] == 80.0
        assert result["is_different"] is True

    def test_validate_device_no_known_device_full_score(self, validator):
        # No known device → cannot detect difference
        result = validator._validate_device(
            device_id="device-abc",
            known_device_id=None,
            allow_different=False,
        )
        assert result["score"] == 100.0

    # -----------------------------------------------------------------------
    # validate_check_in (async integration)
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_validate_check_in_gps_required_but_missing(self, validator):
        from modules.operacional.services.check_in_validator import (
            CheckInData,
            ValidationConfig,
        )
        from modules.operacional.services.geolocation_service import GeoPoint

        config = ValidationConfig(
            require_geolocation=True,
            require_face_validation=False,
            require_photo=False,
        )
        data = CheckInData(
            employee_id=uuid.uuid4(),
            shift_id=uuid.uuid4(),
            post_id=uuid.uuid4(),
            latitude=None,
            longitude=None,
            timestamp=datetime.combine(date.today(), time(7, 0)),
        )

        result = await validator.validate_check_in(
            data=data,
            config=config,
            post_location=GeoPoint(-3.1190, -60.0217),
            scheduled_time=time(7, 0),
        )
        assert "GPS_NAO_DISPONIVEL" in result.anomalies
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_validate_check_in_outside_radius_anomaly(self, validator):
        from modules.operacional.services.check_in_validator import (
            CheckInData,
            ValidationConfig,
        )
        from modules.operacional.services.geolocation_service import GeoPoint

        config = ValidationConfig(
            require_geolocation=True,
            require_face_validation=False,
            require_photo=False,
            allowed_radius_meters=50.0,
        )
        data = CheckInData(
            employee_id=uuid.uuid4(),
            shift_id=uuid.uuid4(),
            post_id=uuid.uuid4(),
            latitude=-4.0,  # far from post
            longitude=-62.0,
            timestamp=datetime.combine(date.today(), time(7, 0)),
        )

        result = await validator.validate_check_in(
            data=data,
            config=config,
            post_location=GeoPoint(-3.1190, -60.0217),
            scheduled_time=time(7, 0),
        )
        assert "FORA_LOCAL" in result.anomalies
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_validate_check_in_late_anomaly(self, validator):
        from modules.operacional.services.check_in_validator import (
            CheckInData,
            ValidationConfig,
        )
        from modules.operacional.services.geolocation_service import GeoPoint

        config = ValidationConfig(
            require_geolocation=False,
            require_face_validation=False,
            require_photo=False,
            max_late_minutes=5,
        )
        # 30 minutes late
        data = CheckInData(
            employee_id=uuid.uuid4(),
            shift_id=uuid.uuid4(),
            post_id=uuid.uuid4(),
            timestamp=datetime.combine(date.today(), time(7, 30)),
        )

        result = await validator.validate_check_in(
            data=data,
            config=config,
            post_location=GeoPoint(-3.1190, -60.0217),
            scheduled_time=time(7, 0),
        )
        assert "ATRASO" in result.anomalies

    @pytest.mark.asyncio
    async def test_validate_check_in_overall_score_formula(self, validator):
        """Score = geo*0.30 + bio*0.35 + time*0.20 + device*0.15."""
        from modules.operacional.services.check_in_validator import (
            CheckInData,
            ValidationConfig,
        )
        from modules.operacional.services.geolocation_service import GeoPoint

        # No geo required, no bio, on time → geo=100, bio=100, time=100, device=100
        config = ValidationConfig(
            require_geolocation=False,
            require_face_validation=False,
            require_photo=False,
        )
        data = CheckInData(
            employee_id=uuid.uuid4(),
            shift_id=uuid.uuid4(),
            post_id=uuid.uuid4(),
            device_id=None,
            timestamp=datetime.combine(date.today(), time(7, 0)),
        )

        result = await validator.validate_check_in(
            data=data,
            config=config,
            post_location=GeoPoint(-3.1190, -60.0217),
            scheduled_time=time(7, 0),
        )
        assert result.overall_score == 95.0  # no device_id → device=80


# ===========================================================================
# PYDANTIC SCHEMA VALIDATORS
# ===========================================================================


class TestPostSchemaValidators:
    """Test Pydantic validation rules on PostCreate/PostBase."""

    def test_name_too_short_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):  # ValidationError
            PostCreate(name="X")  # min_length=2 but single char

    def test_state_is_uppercased(self):
        from modules.operacional.schemas.post import PostCreate

        post = PostCreate(name="Teste", state="sp")
        assert post.state == "SP"

    def test_invalid_zip_code_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):
            PostCreate(name="Teste", zip_code="123")  # only 3 digits

    def test_valid_zip_code(self):
        from modules.operacional.schemas.post import PostCreate

        post = PostCreate(name="Teste", zip_code="01310-100")
        assert post.zip_code == "01310-100"

    def test_negative_hourly_rate_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):
            PostCreate(name="Teste", hourly_rate=-1.0)

    def test_hourly_rate_over_1000_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):
            PostCreate(name="Teste", hourly_rate=1500.0)

    def test_monthly_cost_over_100k_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):
            PostCreate(name="Teste", monthly_cost=200000.0)

    def test_required_headcount_zero_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):
            PostCreate(name="Teste", required_headcount=0)

    def test_required_headcount_over_50_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):
            PostCreate(name="Teste", required_headcount=51)

    def test_latitude_out_of_range_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):
            PostCreate(name="Teste", latitude=100.0)  # > 90

    def test_longitude_out_of_range_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):
            PostCreate(name="Teste", longitude=-200.0)  # < -180

    def test_valid_post_create(self):
        from modules.operacional.models.post import PostType, ShiftType
        from modules.operacional.schemas.post import PostCreate

        post = PostCreate(
            name="Portaria Principal",
            post_type=PostType.PORTEIRO,
            shift_type=ShiftType.DIURNO,
            required_headcount=2,
            hourly_rate=25.50,
            monthly_cost=8000.0,
            state="am",
        )
        assert post.state == "AM"
        assert post.required_headcount == 2

    def test_night_shift_bonus_over_100_raises(self):
        from modules.operacional.schemas.post import PostCreate

        with pytest.raises(Exception):
            PostCreate(name="Teste", night_shift_bonus_percent=150.0)


class TestDiaristSchemaValidators:
    """Test Pydantic schemas for diaristas."""

    def test_nome_too_short_raises(self):
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristCreate

        with pytest.raises(Exception):
            DiaristCreate(nome="A", cpf="12345678901", valor_diaria=Decimal("100"))

    def test_cpf_too_short_raises(self):
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristCreate

        with pytest.raises(Exception):
            DiaristCreate(nome="Maria Silva", cpf="123", valor_diaria=Decimal("100"))

    def test_valid_diarist_create(self):
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristCreate

        data = DiaristCreate(
            nome="Maria Silva Santos",
            cpf="12345678901",
            valor_diaria=Decimal("150.00"),
        )
        assert data.nome == "Maria Silva Santos"
        assert data.valor_diaria == Decimal("150.00")

    def test_negative_valor_diaria_raises(self):
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristCreate

        with pytest.raises(Exception):
            DiaristCreate(
                nome="Maria Silva",
                cpf="12345678901",
                valor_diaria=Decimal("-50"),
            )

    def test_negative_experiencia_raises(self):
        from modules.operacional.diaristas.schemas.diarist_schemas import DiaristCreate

        with pytest.raises(Exception):
            DiaristCreate(
                nome="Maria Silva",
                cpf="12345678901",
                valor_diaria=Decimal("100"),
                experiencia_anos=-1,
            )
